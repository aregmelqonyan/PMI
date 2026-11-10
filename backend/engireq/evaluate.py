"""Metrics computed only from stored human labels and decisions (proposal section 4.8)."""
from __future__ import annotations

import json
import random
import statistics
from pathlib import Path
from typing import Any, Optional

from . import store
from .pipeline import analyze_text

REGRESSION_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "regression.json"
BOOTSTRAP_RESAMPLES = 2000
EDITABLE_FIELDS = ["requirement_type", "component", "action_or_state", "condition", "exception", "negated", "constraints"]


def _safe(numerator: float, denominator: float) -> Optional[float]:
    return numerator / denominator if denominator else None


def prf(tp: int, fp: int, fn: int) -> dict[str, Optional[float]]:
    precision, recall = _safe(tp, tp + fp), _safe(tp, tp + fn)
    if precision is None or recall is None or precision + recall == 0:
        f1 = 0.0 if (tp + fp + fn) and tp == 0 else None
    else:
        f1 = 2 * precision * recall / (precision + recall)
    return {"precision": precision, "recall": recall, "f1": f1}


def _bootstrap_f1(per_document: list[dict[str, int]]) -> Optional[list[float]]:
    """95% percentile interval, resampling whole documents so passages in one document stay together."""
    if len(per_document) < 2:
        return None
    generator = random.Random(20261215)
    samples = []
    for _ in range(BOOTSTRAP_RESAMPLES):
        tp = fp = fn = 0
        for _ in per_document:
            pick = generator.choice(per_document)
            tp, fp, fn = tp + pick["tp"], fp + pick["fp"], fn + pick["fn"]
        value = prf(tp, fp, fn)["f1"]
        if value is not None:
            samples.append(value)
    if not samples:
        return None
    samples.sort()
    return [samples[int(0.025 * (len(samples) - 1))], samples[int(0.975 * (len(samples) - 1))]]


def _detection(data: dict[str, list[dict]]) -> dict[str, Any]:
    names = {d["id"]: d["filename"] for d in data["documents"]}
    per: dict[str, dict[str, int]] = {}
    errors: list[dict] = []
    uncertain = 0
    for passage in data["passages"]:
        label = passage["gold_label"]
        if label is None:
            continue
        if label == "uncertain":
            uncertain += 1
            continue
        row = per.setdefault(passage["document_id"], {"tp": 0, "fp": 0, "fn": 0, "tn": 0})
        gold, predicted = label == "requirement", passage["detected"]
        key = "tp" if gold and predicted else "fn" if gold else "fp" if predicted else "tn"
        row[key] += 1
        if key in ("fp", "fn"):
            errors.append({"kind": key, "document_id": passage["document_id"], "filename": names.get(passage["document_id"]),
                           "span_id": passage["span_id"], "page": passage.get("page"), "text": passage["text"], "reason": passage["reason"]})

    total = {k: sum(row[k] for row in per.values()) for k in ("tp", "fp", "fn", "tn")}
    positive = prf(total["tp"], total["fp"], total["fn"])
    negative = prf(total["tn"], total["fn"], total["fp"])
    macro = None
    if positive["f1"] is not None and negative["f1"] is not None:
        macro = (positive["f1"] + negative["f1"]) / 2
    documents = [
        {"document_id": doc_id, "filename": names.get(doc_id), "labeled": sum(row.values()), **row, **prf(row["tp"], row["fp"], row["fn"])}
        for doc_id, row in per.items()
    ]
    documents.sort(key=lambda d: d["filename"] or "")
    return {"confusion": total, **positive, "macro_f1": macro, "f1_ci95": _bootstrap_f1(list(per.values())),
            "labeled": sum(total.values()), "uncertain_excluded": uncertain, "documents": documents, "errors": errors[:200]}


def _review(data: dict[str, list[dict]]) -> dict[str, Any]:
    records = data["records"]
    status_counts = {s: sum(r["review_status"] == s for r in records) for s in ("unreviewed", "accepted", "edited", "rejected")}
    reviewed = [r for r in records if r["review_status"] != "unreviewed"]
    timed = [r["elapsed_ms"] for r in reviewed if r["review_status"] != "rejected" and r["elapsed_ms"] > 0]

    outcomes = {o: {"total": 0, "accepted": 0, "edited": 0, "rejected": 0, "unreviewed": 0} for o in ("pass", "warn", "abstain")}
    for record in records:
        row = outcomes[record["original_overall"]]
        row["total"] += 1
        row[record["review_status"]] += 1

    field_edits = {f: 0 for f in EDITABLE_FIELDS}
    edited_records: set[str] = set()
    for event in data["audit"]:
        if event["action"] != "edit" or event["before"] is None or event["after"] is None:
            continue
        before, after = json.loads(event["before"]), json.loads(event["after"])
        for name in EDITABLE_FIELDS:
            if before.get(name) != after.get(name):
                field_edits[name] += 1
        edited_records.add(event["record_id"])

    kept = status_counts["accepted"] + status_counts["edited"]
    return {"total_records": len(records), "status": status_counts, "reviewed": len(reviewed),
            "accepted_unchanged_rate": _safe(status_counts["accepted"], len(reviewed)),
            "kept_rate": _safe(kept, len(reviewed)),
            "median_ms_per_kept_record": statistics.median(timed) if timed else None,
            "validator_outcomes": outcomes, "field_edits": field_edits}


def evaluation(partition: Optional[str]) -> dict[str, Any]:
    data = store.all_for_evaluation(partition)
    return {"partition": partition or "all", "documents": len(data["documents"]),
            "synthetic_documents": sum(bool(d["synthetic"]) for d in data["documents"]),
            "detection": _detection(data), "review": _review(data)}


def _tuple(constraint: dict) -> tuple:
    return (constraint.get("operator"), round(constraint["value"], 6) if constraint.get("value") is not None else None, constraint.get("unit"))


def run_regression() -> dict[str, Any]:
    cases = json.loads(REGRESSION_PATH.read_text(encoding="utf-8"))
    tp = fp = fn = tn = c_tp = c_fp = c_fn = records_right = 0
    failures: list[dict] = []
    for case in cases:
        result = analyze_text(case["text"])
        predicted = any(p["detected"] for p in result["passages"])
        gold = case["is_requirement"]
        tp, fp, fn, tn = tp + (gold and predicted), fp + (not gold and predicted), fn + (gold and not predicted), tn + (not gold and not predicted)

        got = [_tuple(c) for r in result["records"] for c in r["record"]["constraints"]]
        expected = [(c["operator"], c["value"], c["unit"]) for c in case.get("constraints", [])]
        remaining = list(got)
        matched = 0
        for item in expected:
            if item in remaining:
                remaining.remove(item)
                matched += 1
        c_tp, c_fn, c_fp = c_tp + matched, c_fn + len(expected) - matched, c_fp + len(remaining)
        count_ok = "records" not in case or case["records"] == len(result["records"])
        records_right += count_ok
        if gold != predicted or matched != len(expected) or remaining or not count_ok:
            failures.append({"text": case["text"], "expected_detected": gold, "detected": predicted,
                             "expected_constraints": expected, "extracted_constraints": got,
                             "expected_records": case.get("records"), "extracted_records": len(result["records"])})
    return {"cases": len(cases), "confusion": {"tp": tp, "fp": fp, "fn": fn, "tn": tn}, "detection": prf(tp, fp, fn),
            "constraints": prf(c_tp, c_fp, c_fn), "constraint_counts": {"tp": c_tp, "fp": c_fp, "fn": c_fn}, "failures": failures}
