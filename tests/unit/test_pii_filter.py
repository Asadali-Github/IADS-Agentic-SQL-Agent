"""Tests for src/sql_agent/safety/pii_filter.py."""

from __future__ import annotations

from sql_agent.core.models import AnswerSummary
from sql_agent.safety.pii_filter import PIIFilter, found, scrub, scrub_obj, scrub_rows, scrub_summary


def test_redacts_email():
    assert scrub("write to bob.smith@acme.co.uk now") == "write to [EMAIL] now"


def test_redacts_phone_with_separators_or_plus():
    assert scrub("call +44 7700 900123") == "call [PHONE]"
    assert scrub("call 415-555-0100") == "call [PHONE]"


def test_does_not_redact_plain_integers():
    # Revenue / counts must survive untouched - the key false-positive guard.
    assert scrub("Total revenue was 4200000 in 2026") == "Total revenue was 4200000 in 2026"
    assert scrub("We sold 4,200,000 units") == "We sold 4,200,000 units"


def test_redacts_card_ssn_ip():
    out = scrub("card 4111 1111 1111 1111 ssn 123-45-6789 ip 10.0.0.1")
    assert "[CARD]" in out and "[SSN]" in out and "[IP]" in out


def test_found_reports_labels():
    labels = found("email a@b.com phone +1 415 555 0100")
    assert "EMAIL" in labels and "PHONE" in labels


def test_scrub_obj_keeps_numbers_and_structure():
    out = scrub_obj({"user": "a@b.com", "count": 5, "rows": [["x@y.com", 3]]})
    assert out["user"] == "[EMAIL]"
    assert out["count"] == 5
    assert out["rows"] == [["[EMAIL]", 3]]


def test_scrub_summary_redacts_answer_and_bullets():
    s = AnswerSummary(answer="Email jane@x.com leads", explanation=["filtered on jane@x.com"],
                      tables_used=["orders"])
    out = scrub_summary(s)
    assert "[EMAIL]" in out.answer
    assert all("jane@x.com" not in b for b in out.explanation)
    assert out.tables_used == ["orders"]  # untouched


def test_empty_string_is_safe():
    assert scrub("") == ""


def test_custom_filter_template():
    f = PIIFilter(template="<redacted:{label}>")
    assert "<redacted:EMAIL>" in f.scrub("hi a@b.com")


# --- NER hook + dual-gate row scrubbing -------------------------------------
def test_scrub_rows_dual_gate_keeps_numbers():
    rows = [["Ada", "ada@x.com", 4200000], ["Bo", "bo@y.com", 5]]
    out = scrub_rows(["name", "email", "spend"], rows)
    assert out[0][1] == "[EMAIL]" and out[0][2] == 4200000
    assert out[1][1] == "[EMAIL]"


def test_extra_detectors_augment_regex():
    def ner(text):  # a fake NER that redacts a known name regex would miss
        return text.replace("Ada Lovelace", "[PERSON]")
    f = PIIFilter(extra_detectors=[ner])
    out = f.scrub("Ada Lovelace at ada@x.com")
    assert "[PERSON]" in out and "[EMAIL]" in out


def test_failing_detector_does_not_break_pipeline():
    def boom(text):
        raise RuntimeError("ner offline")
    f = PIIFilter(extra_detectors=[boom])
    assert f.scrub("email a@b.com") == "email [EMAIL]"


# --- strict floor + detector timeout guard ----------------------------------
def test_strict_mode_redacts_ids_and_postcodes_not_numbers():
    f = PIIFilter(strict=True)
    out = f.scrub("order ORD12345AB to SW1A 1AA total 4200000")
    assert "[ID]" in out and "[POSTCODE]" in out
    assert "4200000" in out  # plain revenue number survives


def test_detector_timeout_falls_back_to_regex_floor():
    import time
    def slow(text):
        time.sleep(2.0)
        return text
    f = PIIFilter(extra_detectors=[slow], detector_timeout_s=0.2)
    t0 = time.time()
    out = f.scrub("email a@b.com")
    assert time.time() - t0 < 1.5      # didn't wait for the slow detector
    assert out == "email [EMAIL]"      # regex floor still applied
