"""Deterministic checks (proposal sections 3.4 and 8 in the pipeline table).

The validator deliberately shares only number and unit parsing with the extractor. Its polarity table is
separate, so a wrong operator from any source, a model or a reviewer edit, is caught against the quoted words.
Passing means the record is consistent with its source text. It does not mean the record is correct engineering.
"""
from __future__ import annotations

import re
from typing import Any

from pydantic import ValidationError

from .schema import Requirement
from .units import NUMBER_RE, UNIT_RE, canonical_unit, parse_number, to_absolute_c

_NEG = r"(?:not|never|no)\b(?:\s+[\w-]+){0,3}\s+"
_UPPER_EVIDENCE = re.compile(
    rf"{_NEG}(?:exceed\w*|more|greater|higher|larger|longer|above|over)\b|at\s+most|up\s+to|maximum|\bmax\b|within"
    r"|(?:less|lower|smaller)\s+than\s+or\s+equal|≤|<=",
    re.I,
)
_LOWER_EVIDENCE = re.compile(
    rf"{_NEG}(?:less|fewer|lower|smaller|shorter|below|under|beneath)\b|at\s+least|minimum|\bmin\b"
    r"|(?:greater|more|higher)\s+than\s+or\s+equal|≥|>=",
    re.I,
)
_PLAIN_UPPER = re.compile(r"\b(?:less|fewer|lower|smaller|shorter)\s+than\b|\bbelow\b|\bunder\b|\bbeneath\b|<", re.I)
_PLAIN_LOWER = re.compile(r"\bexceed\w*|\b(?:greater|more|higher|larger|longer)\s+than\b|\babove\b|\bover\b|>", re.I)
_RANGE = re.compile(r"\bbetween\b|\bfrom\b|\bto\b|–|—", re.I)

BLOCKING_FLAGS = {"tbd_value", "conflicting_threshold"}

FLAG_TEXT = {
    "vague_term": "Wording is vague",
    "undefined_unit": "Number has no recognized unit",
    "ambiguous_unit": "Unit is ambiguous (g can be grams or acceleration)",
    "unclear_reference": "Unclear reference",
    "mixed_obligation": "Several kinds of limit in one statement",
    "conflicting_threshold": "Lower bound is above upper bound",
    "operator_not_stated": "Quantity has no stated comparator",
    "implicit_requirement": "No modal verb, inferred from a limit pattern",
    "inherited_subject": "Subject inherited from an earlier clause",
    "inherited_list_stem": "Subject inherited from a list stem",
    "decimal_comma": "Decimal comma was interpreted as a decimal point",
    "missing_component": "No subject found",
    "tbd_value": "Source contains TBD, TBR or TBC",
}


def _check(checks: list[dict], check_id: str, label: str, status: str, detail: str) -> None:
    checks.append({"id": check_id, "label": label, "status": status, "detail": detail})


def _polarity_problem(surface: str, operator: str | None, range_bound: bool) -> str | None:
    if operator is None or range_bound:
        return None
    if _UPPER_EVIDENCE.search(surface):
        if operator not in ("<=", "<"):
            return f"Source wording sets an upper limit, but the operator is {operator}."
        return None
    if _LOWER_EVIDENCE.search(surface):
        if operator not in (">=", ">"):
            return f"Source wording sets a lower limit, but the operator is {operator}."
        return None
    if _PLAIN_UPPER.search(surface) and operator not in ("<", "<="):
        return f"Source wording says below, but the operator is {operator}."
    if _PLAIN_LOWER.search(surface) and operator not in (">", ">="):
        return f"Source wording says above, but the operator is {operator}."
    return None


def validate_record(record: dict[str, Any], block_text: str | None) -> dict[str, Any]:
    checks: list[dict] = []
    try:
        Requirement.model_validate(record)
        _check(checks, "schema", "Schema", "pass", "All fields have the expected types and allowed values.")
        schema_status = "valid"
    except ValidationError as error:
        first = error.errors()[0]
        _check(checks, "schema", "Schema", "fail", f"{'.'.join(map(str, first['loc']))}: {first['msg']}")
        return {"overall": "abstain", "schema_status": "invalid", "source_alignment_status": "not_checked", "checks": checks}

    evidence = record["evidence"]
    start, end = evidence["start_char"], evidence["end_char"]
    aligned = block_text is not None and 0 <= start < end <= len(block_text) and block_text[start:end] == evidence["quoted_text"]
    if aligned:
        _check(checks, "span", "Exact source span", "pass", f"The quote is identical to source characters {start}–{end}.")
    else:
        _check(checks, "span", "Exact source span", "fail", "The quoted text does not occur at the stated offsets.")

    constraint_failures: list[str] = []
    for index, constraint in enumerate(record.get("constraints", []), start=1):
        surface = constraint["surface_text"]
        c_start, c_end = constraint.get("start_char"), constraint.get("end_char")
        if not (block_text is not None and c_start is not None and c_end is not None and block_text[c_start:c_end] == surface
                and start <= c_start and c_end <= end):
            constraint_failures.append(f"Constraint {index}: “{surface}” is not inside the evidence span.")
            continue
        numbers = [parse_number(m.group(0))[0] for m in NUMBER_RE.finditer(surface)]
        value = constraint.get("value")
        if value is not None and not any(abs(n - value) < 1e-9 for n in numbers):
            constraint_failures.append(f"Constraint {index}: value {value:g} does not appear in “{surface}”.")
        tolerance = constraint.get("tolerance")
        if tolerance is not None and not any(abs(n - tolerance) < 1e-9 for n in numbers):
            constraint_failures.append(f"Constraint {index}: tolerance {tolerance:g} does not appear in “{surface}”.")
        units = {canonical_unit(m.group(0)) for m in UNIT_RE.finditer(surface)} - {None}
        unit = constraint.get("unit")
        if unit is not None and unit not in units:
            constraint_failures.append(f"Constraint {index}: unit {unit} does not appear in “{surface}”.")
        if unit is None and units:
            constraint_failures.append(f"Constraint {index}: “{surface}” states a unit but the record has none.")
        range_bound = bool(_RANGE.search(surface)) and len(numbers) >= 2
        problem = _polarity_problem(surface, constraint.get("operator"), range_bound)
        if problem:
            constraint_failures.append(f"Constraint {index}: {problem}")
        if value is not None and unit:
            celsius = to_absolute_c(value, unit)
            if celsius is not None and celsius < -273.15:
                constraint_failures.append(f"Constraint {index}: temperature is below absolute zero.")

    if record.get("constraints"):
        if constraint_failures:
            _check(checks, "constraints", "Value, unit and operator", "fail", " ".join(constraint_failures))
        else:
            _check(checks, "constraints", "Value, unit and operator", "pass",
                   "Each value, unit and operator agrees with its quoted words.")
    else:
        _check(checks, "constraints", "Value, unit and operator", "pass", "This record states no numeric limit.")

    flags = record.get("quality_flags", [])
    if flags:
        _check(checks, "quality", "Expert attention", "warn", "; ".join(FLAG_TEXT.get(f, f) for f in flags) + ".")
    else:
        _check(checks, "quality", "Expert attention", "pass", "No ambiguity patterns were found.")

    failed = any(c["status"] == "fail" for c in checks)
    blocked = any(f in BLOCKING_FLAGS for f in flags)
    if failed or blocked:
        overall = "abstain"
    elif any(c["status"] == "warn" for c in checks):
        overall = "warn"
    else:
        overall = "pass"
    return {"overall": overall, "schema_status": schema_status,
            "source_alignment_status": "verified" if aligned and not constraint_failures else "failed", "checks": checks}
