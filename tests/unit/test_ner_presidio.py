"""Tests for the optional Presidio NER adapter (graceful-degradation path)."""

from __future__ import annotations

import pytest

from sql_agent.safety import ner_presidio


def test_is_available_returns_bool():
    assert isinstance(ner_presidio.is_available(), bool)


def test_try_build_is_safe_when_unavailable(monkeypatch):
    monkeypatch.setattr(ner_presidio, "is_available", lambda: False)
    assert ner_presidio.try_build_presidio_detector() is None


def test_build_raises_helpful_importerror_when_absent():
    if ner_presidio.is_available():
        pytest.skip("Presidio is installed in this environment")
    with pytest.raises(ImportError) as exc:
        ner_presidio.build_presidio_detector()
    assert "pip install presidio" in str(exc.value)


def test_detector_composes_with_pii_filter():
    # Simulate a built NER detector and confirm it layers on the regex baseline.
    from sql_agent.safety.pii_filter import PIIFilter

    def fake_detector(text: str) -> str:
        return text.replace("Ada Lovelace", "<PERSON>")

    pii = PIIFilter(extra_detectors=[fake_detector])
    out = pii.scrub("Ada Lovelace emailed ada@x.com")
    assert "<PERSON>" in out and "[EMAIL]" in out
