"""HTTP API. Bound to localhost by the launch scripts, because documents may be restricted (proposal 3.3)."""
from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Any, Literal, Optional

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles

from . import BASELINE_VERSION, evaluate, store
from .parse import render_page_png
from .pipeline import analyze_text, ingest_pdf
from .sample import build_sample_pdf
from .schema import DecisionBody, DocumentPatch, LabelBody, PlaygroundBody, RecordPatch
from .units import known_canonical_units
from .validate import FLAG_TEXT, validate_record

MAX_UPLOAD_BYTES = 60 * 1024 * 1024
SAMPLE_NAME = "synthetic-battery-subsystem-spec.pdf"

app = FastAPI(title="EngiReq-AI pilot", version="0.1.0")
store.init()


def _document_or_404(document_id: str) -> dict[str, Any]:
    document = store.get_document(document_id)
    if document is None:
        raise HTTPException(404, "Document not found.")
    return document


def _record_or_404(record_id: str) -> dict[str, Any]:
    record = store.get_record(record_id)
    if record is None:
        raise HTTPException(404, "Record not found.")
    return record


@app.get("/api/meta")
def meta() -> dict[str, Any]:
    return {"method": BASELINE_VERSION, "units": known_canonical_units(), "flags": FLAG_TEXT}


@app.get("/api/documents")
def documents() -> list[dict[str, Any]]:
    return store.list_documents()


@app.post("/api/documents", status_code=201)
async def upload(file: UploadFile = File(...)) -> dict[str, Any]:
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "The file is larger than the 60 MB limit.")
    if not content.startswith(b"%PDF-"):
        raise HTTPException(415, "Only PDF files are supported in this pilot.")
    try:
        document, duplicate = ingest_pdf(content, file.filename or "document.pdf")
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    except RuntimeError as error:
        raise HTTPException(422, "This PDF could not be read.") from error
    return {"document": document, "duplicate": duplicate}


@app.post("/api/documents/sample", status_code=201)
def sample() -> dict[str, Any]:
    document, duplicate = ingest_pdf(build_sample_pdf(), SAMPLE_NAME, synthetic=True)
    return {"document": document, "duplicate": duplicate}


@app.get("/api/documents/{document_id}")
def document_detail(document_id: str) -> dict[str, Any]:
    return _document_or_404(document_id)


@app.patch("/api/documents/{document_id}")
def patch_document(document_id: str, body: DocumentPatch) -> dict[str, Any]:
    _document_or_404(document_id)
    store.set_partition(document_id, body.partition)
    return _document_or_404(document_id)


@app.delete("/api/documents/{document_id}", status_code=204)
def delete_document(document_id: str) -> Response:
    _document_or_404(document_id)
    store.delete_document(document_id)
    return Response(status_code=204)


@app.get("/api/documents/{document_id}/pages/{page}.png")
def page_image(document_id: str, page: int) -> Response:
    _document_or_404(document_id)
    try:
        image = render_page_png(str(store.pdf_path(document_id)), page)
    except IndexError as error:
        raise HTTPException(404, "Page not found.") from error
    return Response(image, media_type="image/png", headers={"Cache-Control": "private, max-age=86400"})


@app.get("/api/documents/{document_id}/passages")
def passages(document_id: str) -> list[dict[str, Any]]:
    _document_or_404(document_id)
    return store.list_passages(document_id)


@app.put("/api/passages/{span_id}/label")
def label(span_id: str, body: LabelBody) -> dict[str, Any]:
    updated = store.set_label(span_id, body.label, body.reviewer)
    if updated is None:
        raise HTTPException(404, "Passage not found.")
    return updated


@app.get("/api/documents/{document_id}/records")
def records(document_id: str) -> list[dict[str, Any]]:
    _document_or_404(document_id)
    return store.list_records(document_id)


@app.patch("/api/records/{record_id}")
def edit_record(record_id: str, body: RecordPatch) -> dict[str, Any]:
    current = _record_or_404(record_id)
    data = json.loads(json.dumps(current["record"]))
    before = json.loads(json.dumps(data))
    changes = body.model_dump(exclude_unset=True, exclude={"reviewer", "elapsed_ms"})
    block = store.block_text(current["document_id"], data["evidence"]["block_id"])

    for name, value in changes.items():
        if isinstance(value, str):
            value = value.strip() or None
        data[name] = value

    if "constraints" in changes:
        start, end = data["evidence"]["start_char"], data["evidence"]["end_char"]
        for constraint in data["constraints"]:
            # A constraint added by a reviewer is anchored by finding its quoted words in the evidence.
            if constraint.get("start_char") is None and block is not None:
                position = block.find(constraint["surface_text"], start, end)
                if position != -1:
                    constraint["start_char"] = position
                    constraint["end_char"] = position + len(constraint["surface_text"])

    if data == before:
        return current
    validation = validate_record(data, block)
    # A correction that contradicts the source stays open, so it can never reach an approved export by accident.
    status = "unreviewed" if validation["overall"] == "abstain" else "edited"
    return store.update_record(record_id, data, validation, status, body.reviewer, "edit", body.elapsed_ms, before, data)


@app.post("/api/records/{record_id}/decision")
def decide(record_id: str, body: DecisionBody) -> dict[str, Any]:
    current = _record_or_404(record_id)
    status: str = body.decision
    action: str = body.decision
    if body.decision == "accepted" and current["record"] != store.get_original(record_id):
        status = "edited"  # accepting a corrected record keeps the fact that it was corrected
    if body.decision == "accepted" and current["validation"]["overall"] == "abstain":
        action = "accepted_with_override"
    return store.update_record(record_id, current["record"], current["validation"], status, body.reviewer, action, body.elapsed_ms,
                               {"review_status": current["review_status"]}, {"review_status": status}, body.note)


@app.post("/api/records/{record_id}/restore")
def restore(record_id: str, reviewer: str = Query("reviewer", max_length=80)) -> dict[str, Any]:
    current = _record_or_404(record_id)
    original = store.get_original(record_id)
    block = store.block_text(current["document_id"], original["evidence"]["block_id"])
    return store.update_record(record_id, original, validate_record(original, block), "unreviewed", reviewer, "restore_original", 0,
                               current["record"], original)


@app.get("/api/records/{record_id}/history")
def record_history(record_id: str) -> list[dict[str, Any]]:
    _record_or_404(record_id)
    return store.history(record_id)


_CSV_COLUMNS = ["requirement_id", "document_id", "page", "section", "source_label", "requirement_type", "component", "action_or_state", "negated",
                "parameter", "operator", "value", "tolerance", "unit", "condition", "exception", "quoted_text", "start_char", "end_char", "block_id",
                "validation", "review_status", "reviewer", "quality_flags", "method", "source_sha256"]


def _csv_text(value: Any) -> Any:
    """Source text can start with a formula character, so neutralize it for spreadsheet software."""
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value


@app.get("/api/documents/{document_id}/export")
def export(document_id: str, format: Literal["jsonl", "csv"] = "jsonl", scope: Literal["approved", "all"] = "approved") -> PlainTextResponse:
    document = _document_or_404(document_id)
    rows = store.list_records(document_id)
    if scope == "approved":
        rows = [r for r in rows if r["review_status"] in ("accepted", "edited")]
    stem = Path(document["filename"]).stem.replace('"', "")
    headers = {"Content-Disposition": f'attachment; filename="{stem}-{scope}.{format}"'.encode("ascii", "ignore").decode()}

    if format == "jsonl":
        lines = [json.dumps({**r["record"], "validation": r["validation"]["overall"], "checks": r["validation"]["checks"],
                             "review_status": r["review_status"], "reviewer": r["reviewer"], "updated_at": r["updated_at"]}, ensure_ascii=False) for r in rows]
        return PlainTextResponse("\n".join(lines) + ("\n" if lines else ""), media_type="application/x-ndjson", headers=headers)

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=_CSV_COLUMNS)
    writer.writeheader()
    for row in rows:
        record = row["record"]
        evidence = record["evidence"]
        base = {"requirement_id": record["requirement_id"], "document_id": record["document_id"], "page": evidence["page"], "section": _csv_text(evidence["section"]),
                "source_label": _csv_text(record["source_label"]), "requirement_type": record["requirement_type"], "component": _csv_text(record["component"]),
                "action_or_state": _csv_text(record["action_or_state"]), "negated": record["negated"], "exception": _csv_text(record["exception"]),
                "condition": _csv_text(record["condition"]), "quoted_text": _csv_text(evidence["quoted_text"]), "start_char": evidence["start_char"], "end_char": evidence["end_char"],
                "block_id": evidence["block_id"], "validation": row["validation"]["overall"], "review_status": row["review_status"], "reviewer": _csv_text(row["reviewer"]),
                "quality_flags": ";".join(record["quality_flags"]), "method": record["method"], "source_sha256": record["source_sha256"]}
        constraints = record["constraints"] or [{}]
        for constraint in constraints:
            writer.writerow({**base, "parameter": constraint.get("parameter"), "operator": _csv_text(constraint.get("operator")), "value": constraint.get("value"),
                             "tolerance": constraint.get("tolerance"), "unit": _csv_text(constraint.get("unit")),
                             "condition": _csv_text(constraint.get("condition") or record["condition"])})
    return PlainTextResponse(output.getvalue(), media_type="text/csv", headers=headers)


@app.get("/api/evaluation")
def get_evaluation(partition: Optional[Literal["all", "dev", "test", "unassigned"]] = "all") -> dict[str, Any]:
    return evaluate.evaluation(partition)


@app.post("/api/evaluation/regression")
def regression() -> dict[str, Any]:
    return evaluate.run_regression()


@app.post("/api/playground")
def playground(body: PlaygroundBody) -> dict[str, Any]:
    return analyze_text(body.text)


# In production mode the built frontend is served from here, so only one port is needed.
_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if _DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        if path.startswith("api/"):
            raise HTTPException(404, "Not found.")
        return FileResponse(_DIST / "index.html")
