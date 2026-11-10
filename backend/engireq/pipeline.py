"""End-to-end flow: PDF → blocks → passages → records → validation → storage."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from . import BASELINE_VERSION, store
from .baseline import extract
from .parse import parse_pdf, text_block
from .validate import validate_record


def ingest_pdf(content: bytes, filename: str, synthetic: bool = False) -> tuple[dict[str, Any], bool]:
    """Process and store a PDF. Returns (document, already_existed). Copies are never counted twice."""
    sha256 = hashlib.sha256(content).hexdigest()
    existing = store.find_by_hash(sha256)
    if existing:
        return existing, True

    document_id = f"doc_{sha256[:10]}"
    path = store.pdf_path(document_id)
    path.write_bytes(content)
    try:
        parsed = parse_pdf(str(path))
        texts = {b.block_id: b.text for b in parsed.blocks}
        passages, records = extract(parsed.blocks, document_id, sha256)
        validated = []
        for record in records:
            data = record.model_dump()
            validated.append({"record": data, "validation": validate_record(data, texts[record.evidence.block_id])})
        store.insert_document(
            {"id": document_id, "filename": Path(filename).name[:200] or "document.pdf", "sha256": sha256, "method": BASELINE_VERSION,
             "synthetic": synthetic, "pages": parsed.pages, "warnings": parsed.warnings},
            list(texts.items()), [p.model_dump() for p in passages], validated,
        )
    except Exception:
        path.unlink(missing_ok=True)
        raise
    document = store.get_document(document_id)
    assert document is not None
    return document, False


def analyze_text(text: str) -> dict[str, Any]:
    """Run the same extractor and validator on typed text. Nothing is stored."""
    block = text_block(" ".join(text.split()))
    passages, records = extract([block], "playground", "0" * 64)
    return {
        "source": block.text,
        "passages": [p.model_dump() for p in passages],
        "records": [{"record": r.model_dump(), "validation": validate_record(r.model_dump(), block.text)} for r in records],
    }
