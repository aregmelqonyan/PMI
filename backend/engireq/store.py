"""SQLite persistence. Original model output and every human change are kept, never overwritten."""
from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Optional

DATA_DIR = Path(os.environ.get("ENGIREQ_DATA_DIR", Path(__file__).resolve().parents[1] / "data"))
PDF_DIR = DATA_DIR / "pdfs"
DB_PATH = DATA_DIR / "engireq.sqlite3"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY, filename TEXT NOT NULL, sha256 TEXT NOT NULL UNIQUE, uploaded_at TEXT NOT NULL,
    method TEXT NOT NULL, partition TEXT NOT NULL DEFAULT 'unassigned', synthetic INTEGER NOT NULL DEFAULT 0,
    pages TEXT NOT NULL, warnings TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS blocks (
    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE, block_id TEXT NOT NULL, text TEXT NOT NULL,
    PRIMARY KEY (document_id, block_id)
);
CREATE TABLE IF NOT EXISTS passages (
    span_id TEXT PRIMARY KEY, document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE, ordinal INTEGER NOT NULL,
    data TEXT NOT NULL, gold_label TEXT, labeled_by TEXT, labeled_at TEXT
);
CREATE TABLE IF NOT EXISTS records (
    id TEXT PRIMARY KEY, document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE, ordinal INTEGER NOT NULL,
    data TEXT NOT NULL, original TEXT NOT NULL, validation TEXT NOT NULL, original_overall TEXT NOT NULL,
    review_status TEXT NOT NULL DEFAULT 'unreviewed', reviewer TEXT, elapsed_ms INTEGER NOT NULL DEFAULT 0, updated_at TEXT
);
CREATE TABLE IF NOT EXISTS audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT, record_id TEXT NOT NULL, document_id TEXT NOT NULL, at TEXT NOT NULL,
    actor TEXT NOT NULL, action TEXT NOT NULL, before TEXT, after TEXT, elapsed_ms INTEGER NOT NULL DEFAULT 0, note TEXT
);
CREATE INDEX IF NOT EXISTS idx_passages_doc ON passages(document_id, ordinal);
CREATE INDEX IF NOT EXISTS idx_records_doc ON records(document_id, ordinal);
CREATE INDEX IF NOT EXISTS idx_audit_record ON audit(record_id, id);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def init() -> None:
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    with connection() as db:
        db.executescript(_SCHEMA)


@contextmanager
def connection() -> Iterator[sqlite3.Connection]:
    db = sqlite3.connect(DB_PATH, timeout=30)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def pdf_path(document_id: str) -> Path:
    return PDF_DIR / f"{document_id}.pdf"


def _document_row(row: sqlite3.Row, db: sqlite3.Connection) -> dict[str, Any]:
    counts = db.execute(
        """SELECT COUNT(*) total,
                  COALESCE(SUM(review_status != 'unreviewed'), 0) reviewed,
                  COALESCE(SUM(review_status = 'accepted'), 0) accepted,
                  COALESCE(SUM(review_status = 'edited'), 0) edited,
                  COALESCE(SUM(review_status = 'rejected'), 0) rejected
           FROM records WHERE document_id = ?""",
        (row["id"],),
    ).fetchone()
    passages = db.execute(
        "SELECT COUNT(*) total, COALESCE(SUM(gold_label IS NOT NULL), 0) labeled FROM passages WHERE document_id = ?",
        (row["id"],),
    ).fetchone()
    return {
        "id": row["id"], "filename": row["filename"], "sha256": row["sha256"], "uploaded_at": row["uploaded_at"],
        "method": row["method"], "partition": row["partition"], "synthetic": bool(row["synthetic"]),
        "pages": json.loads(row["pages"]), "warnings": json.loads(row["warnings"]),
        "records": dict(counts), "passages": dict(passages),
    }


def find_by_hash(sha256: str) -> Optional[dict[str, Any]]:
    with connection() as db:
        row = db.execute("SELECT * FROM documents WHERE sha256 = ?", (sha256,)).fetchone()
        return _document_row(row, db) if row else None


def list_documents() -> list[dict[str, Any]]:
    with connection() as db:
        rows = db.execute("SELECT * FROM documents ORDER BY uploaded_at DESC, id").fetchall()
        return [_document_row(r, db) for r in rows]


def get_document(document_id: str) -> Optional[dict[str, Any]]:
    with connection() as db:
        row = db.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()
        return _document_row(row, db) if row else None


def insert_document(document: dict[str, Any], blocks: list[tuple[str, str]], passages: list[dict], records: list[dict]) -> None:
    with connection() as db:
        db.execute(
            "INSERT INTO documents (id, filename, sha256, uploaded_at, method, synthetic, pages, warnings) VALUES (?,?,?,?,?,?,?,?)",
            (document["id"], document["filename"], document["sha256"], now(), document["method"], int(document["synthetic"]),
             json.dumps(document["pages"]), json.dumps(document["warnings"])),
        )
        db.executemany("INSERT INTO blocks VALUES (?,?,?)", [(document["id"], b, t) for b, t in blocks])
        db.executemany(
            "INSERT INTO passages (span_id, document_id, ordinal, data) VALUES (?,?,?,?)",
            [(p["span_id"], document["id"], i, json.dumps(p, ensure_ascii=False)) for i, p in enumerate(passages)],
        )
        db.executemany(
            "INSERT INTO records (id, document_id, ordinal, data, original, validation, original_overall) VALUES (?,?,?,?,?,?,?)",
            [(r["record"]["requirement_id"], document["id"], i, json.dumps(r["record"], ensure_ascii=False),
              json.dumps(r["record"], ensure_ascii=False), json.dumps(r["validation"], ensure_ascii=False), r["validation"]["overall"])
             for i, r in enumerate(records)],
        )


def set_partition(document_id: str, partition: str) -> None:
    with connection() as db:
        db.execute("UPDATE documents SET partition = ? WHERE id = ?", (partition, document_id))


def delete_document(document_id: str) -> None:
    with connection() as db:
        db.execute("DELETE FROM audit WHERE document_id = ?", (document_id,))
        db.execute("DELETE FROM documents WHERE id = ?", (document_id,))
    pdf_path(document_id).unlink(missing_ok=True)


def _passage(row: sqlite3.Row) -> dict[str, Any]:
    return {**json.loads(row["data"]), "gold_label": row["gold_label"], "labeled_by": row["labeled_by"]}


def _record(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "record": json.loads(row["data"]), "validation": json.loads(row["validation"]), "review_status": row["review_status"],
        "reviewer": row["reviewer"], "elapsed_ms": row["elapsed_ms"], "updated_at": row["updated_at"],
        "original_overall": row["original_overall"], "document_id": row["document_id"], "id": row["id"],
    }


def list_passages(document_id: str) -> list[dict[str, Any]]:
    with connection() as db:
        rows = db.execute("SELECT * FROM passages WHERE document_id = ? ORDER BY ordinal", (document_id,)).fetchall()
        return [_passage(r) for r in rows]


def set_label(span_id: str, label: Optional[str], reviewer: str) -> Optional[dict[str, Any]]:
    with connection() as db:
        cursor = db.execute(
            "UPDATE passages SET gold_label = ?, labeled_by = ?, labeled_at = ? WHERE span_id = ?",
            (label, reviewer if label else None, now() if label else None, span_id),
        )
        if cursor.rowcount == 0:
            return None
        return _passage(db.execute("SELECT * FROM passages WHERE span_id = ?", (span_id,)).fetchone())


def list_records(document_id: str) -> list[dict[str, Any]]:
    with connection() as db:
        rows = db.execute("SELECT * FROM records WHERE document_id = ? ORDER BY ordinal", (document_id,)).fetchall()
        return [_record(r) for r in rows]


def get_record(record_id: str) -> Optional[dict[str, Any]]:
    with connection() as db:
        row = db.execute("SELECT * FROM records WHERE id = ?", (record_id,)).fetchone()
        return _record(row) if row else None


def get_original(record_id: str) -> Optional[dict[str, Any]]:
    with connection() as db:
        row = db.execute("SELECT original FROM records WHERE id = ?", (record_id,)).fetchone()
        return json.loads(row["original"]) if row else None


def block_text(document_id: str, block_id: str) -> Optional[str]:
    with connection() as db:
        row = db.execute("SELECT text FROM blocks WHERE document_id = ? AND block_id = ?", (document_id, block_id)).fetchone()
        return row["text"] if row else None


def update_record(record_id: str, data: dict, validation: dict, status: str, actor: str, action: str, elapsed_ms: int,
                  before: Any, after: Any, note: Optional[str] = None) -> dict[str, Any]:
    stamp = now()
    with connection() as db:
        db.execute(
            "UPDATE records SET data = ?, validation = ?, review_status = ?, reviewer = ?, elapsed_ms = elapsed_ms + ?, updated_at = ? WHERE id = ?",
            (json.dumps(data, ensure_ascii=False), json.dumps(validation, ensure_ascii=False), status, actor, elapsed_ms, stamp, record_id),
        )
        document_id = db.execute("SELECT document_id FROM records WHERE id = ?", (record_id,)).fetchone()["document_id"]
        db.execute(
            "INSERT INTO audit (record_id, document_id, at, actor, action, before, after, elapsed_ms, note) VALUES (?,?,?,?,?,?,?,?,?)",
            (record_id, document_id, stamp, actor, action, json.dumps(before, ensure_ascii=False),
             json.dumps(after, ensure_ascii=False), elapsed_ms, note),
        )
        return _record(db.execute("SELECT * FROM records WHERE id = ?", (record_id,)).fetchone())


def history(record_id: str) -> list[dict[str, Any]]:
    with connection() as db:
        rows = db.execute("SELECT * FROM audit WHERE record_id = ? ORDER BY id DESC", (record_id,)).fetchall()
    return [{"id": r["id"], "at": r["at"], "actor": r["actor"], "action": r["action"], "elapsed_ms": r["elapsed_ms"], "note": r["note"],
             "before": json.loads(r["before"]) if r["before"] else None, "after": json.loads(r["after"]) if r["after"] else None} for r in rows]


def all_for_evaluation(partition: Optional[str]) -> dict[str, list[dict[str, Any]]]:
    clause, args = ("", ())
    if partition and partition != "all":
        clause, args = (" WHERE d.partition = ?", (partition,))
    with connection() as db:
        documents = db.execute(f"SELECT d.id, d.filename, d.partition, d.synthetic FROM documents d{clause}", args).fetchall()
        passages = db.execute(f"SELECT p.* FROM passages p JOIN documents d ON d.id = p.document_id{clause}", args).fetchall()
        records = db.execute(f"SELECT r.* FROM records r JOIN documents d ON d.id = r.document_id{clause}", args).fetchall()
        audit = db.execute(f"SELECT a.* FROM audit a JOIN documents d ON d.id = a.document_id{clause}", args).fetchall()
    return {
        "documents": [dict(d) for d in documents],
        "passages": [{**_passage(p), "document_id": p["document_id"]} for p in passages],
        "records": [_record(r) for r in records],
        "audit": [dict(a) for a in audit],
    }
