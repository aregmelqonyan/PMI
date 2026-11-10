import os
import sys
import tempfile
from pathlib import Path

os.environ["ENGIREQ_DATA_DIR"] = tempfile.mkdtemp(prefix="engireq-test-")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from engireq.api import app  # noqa: E402
from engireq.evaluate import prf, run_regression  # noqa: E402
from engireq.pipeline import analyze_text  # noqa: E402
from engireq.validate import validate_record  # noqa: E402

client = TestClient(app)


def one(text):
    result = analyze_text(text)
    assert len(result["records"]) == 1, result
    return result["records"][0]


def test_regression_fixture_has_no_failures():
    result = run_regression()
    assert result["failures"] == []


@pytest.mark.parametrize("text", ["During continuous discharge, the battery-case temperature shall not exceed 60 degrees Celsius.",
                                  "The relay shall open within 50 ms, and the indicator shall illuminate within 2 s."])
def test_offsets_are_exact(text):
    result = analyze_text(text)
    for item in result["records"]:
        evidence = item["record"]["evidence"]
        assert result["source"][evidence["start_char"]:evidence["end_char"]] == evidence["quoted_text"]
        for constraint in item["record"]["constraints"]:
            assert result["source"][constraint["start_char"]:constraint["end_char"]] == constraint["surface_text"]
        assert item["validation"]["source_alignment_status"] == "verified"


def test_negation_and_condition_fields():
    item = one("During continuous discharge, the battery-case temperature shall not exceed 60 degrees Celsius.")
    record = item["record"]
    assert record["negated"] is True
    assert record["condition"] == "During continuous discharge"
    assert record["action_or_state"] == "battery-case temperature"
    assert record["constraints"][0]["condition"] == "During continuous discharge"
    assert item["validation"]["overall"] == "pass"


def test_condition_after_requirement_id():
    record = one("[V2 9021] During critical operations, the program shall limit current to at most 2 mA.")["record"]
    assert record["source_label"] == "V2 9021"
    assert record["condition"] == "During critical operations"
    assert record["component"] == "program"


def test_second_clause_inherits_subject():
    records = analyze_text("The hatch shall open manually and shall lock automatically.")["records"]
    assert records[1]["record"]["component"] == "hatch"
    assert "inherited_subject" in records[1]["record"]["quality_flags"]


def test_validator_catches_reversed_operator():
    text = "The case temperature shall not exceed 60 degrees Celsius."
    record = one(text)["record"]
    record["constraints"][0]["operator"] = ">"
    outcome = validate_record(record, text)
    assert outcome["overall"] == "abstain"
    assert any(c["id"] == "constraints" and c["status"] == "fail" for c in outcome["checks"])


def test_validator_catches_changed_value_unit_and_shifted_offsets():
    text = "The case temperature shall not exceed 60 degrees Celsius."
    base = one(text)["record"]
    changed_value = {**base, "constraints": [{**base["constraints"][0], "value": 65}]}
    assert validate_record(changed_value, text)["overall"] == "abstain"
    changed_unit = {**base, "constraints": [{**base["constraints"][0], "unit": "degF"}]}
    assert validate_record(changed_unit, text)["overall"] == "abstain"
    assert validate_record(base, "X" + text)["source_alignment_status"] == "failed"


def test_absolute_zero_and_tbd_route_to_expert():
    assert one("The heater power shall be TBD W during lunar night.")["validation"]["overall"] == "abstain"
    assert one("The coolant temperature shall be at least -300 °C.")["validation"]["overall"] == "abstain"


def test_vague_wording_warns():
    item = one("The enclosure shall provide adequate protection against leakage.")
    assert "vague_term" in item["record"]["quality_flags"]
    assert item["validation"]["overall"] == "warn"


def test_f1_zero_denominator():
    assert prf(0, 0, 0) == {"precision": None, "recall": None, "f1": None}
    assert prf(0, 2, 2)["f1"] == 0.0


def test_full_api_flow_with_sample_pdf():
    uploaded = client.post("/api/documents/sample")
    assert uploaded.status_code == 201
    document = uploaded.json()["document"]
    assert client.post("/api/documents/sample").json()["duplicate"] is True

    doc_id = document["id"]
    records = client.get(f"/api/documents/{doc_id}/records").json()
    assert len(records) >= 12
    for item in records:
        assert item["validation"]["source_alignment_status"] == "verified", item
        assert item["record"]["evidence"]["rects"], item

    assert client.get(f"/api/documents/{doc_id}/pages/1.png").headers["content-type"] == "image/png"
    assert client.get(f"/api/documents/{doc_id}/pages/99.png").status_code == 404

    target = next(r for r in records if "shall not exceed 60" in r["record"]["evidence"]["quoted_text"])
    constraint = target["record"]["constraints"][0]
    bad = client.patch(f"/api/records/{target['id']}", json={"reviewer": "t", "elapsed_ms": 1500, "constraints": [{**constraint, "operator": ">="}]}).json()
    assert bad["review_status"] == "unreviewed" and bad["validation"]["overall"] == "abstain"
    assert client.get(f"/api/documents/{doc_id}/export?format=jsonl&scope=approved").text == ""
    restored = client.post(f"/api/records/{target['id']}/restore").json()
    assert restored["review_status"] == "unreviewed" and restored["validation"]["overall"] == "pass"
    assert len(client.get(f"/api/records/{target['id']}/history").json()) == 2

    assert client.post(f"/api/records/{target['id']}/decision", json={"decision": "accepted", "reviewer": "t", "elapsed_ms": 900}).json()["review_status"] == "accepted"
    exported = client.get(f"/api/documents/{doc_id}/export?format=jsonl&scope=approved").text.strip().splitlines()
    assert len(exported) == 1
    assert "requirement_id" in client.get(f"/api/documents/{doc_id}/export?format=csv&scope=all").text

    passages = client.get(f"/api/documents/{doc_id}/passages").json()
    positive = next(p for p in passages if p["detected"])
    negative = next(p for p in passages if not p["detected"])
    client.put(f"/api/passages/{positive['span_id']}/label", json={"label": "requirement"})
    client.put(f"/api/passages/{negative['span_id']}/label", json={"label": "requirement"})
    metrics = client.get("/api/evaluation").json()["detection"]
    assert metrics["confusion"] == {"tp": 1, "fp": 0, "fn": 1, "tn": 0}
    assert metrics["recall"] == 0.5

    assert client.post("/api/documents", files={"file": ("x.pdf", b"not a pdf")}).status_code == 415
    assert client.delete(f"/api/documents/{doc_id}").status_code == 204
    assert client.get(f"/api/documents/{doc_id}").status_code == 404
