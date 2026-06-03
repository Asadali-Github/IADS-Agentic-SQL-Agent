"""Optional Microsoft Presidio NER detector for the PII filter.

Owner: Asad.

Regex catches structured PII (emails, phones, cards). It cannot catch
context-dependent PII - personal names, postal addresses, an account id hiding
in a free-text comment. Presidio (NER + recognisers) does. This module is the
adapter: it produces a `Detector` callable compatible with
`PIIFilter(extra_detectors=[...])`.

Presidio is an OPTIONAL, heavy dependency, so it is imported lazily and the
module degrades gracefully when it is absent:

    from sql_agent.safety.pii_filter import PIIFilter
    from sql_agent.safety.ner_presidio import try_build_presidio_detector

    det = try_build_presidio_detector()          # None if presidio not installed
    pii = PIIFilter(extra_detectors=[det] if det else [])

To enable it:  pip install presidio-analyzer presidio-anonymizer
               python -m spacy download en_core_web_lg
"""

from __future__ import annotations

import logging
from typing import Callable, Optional

logger = logging.getLogger(__name__)

Detector = Callable[[str], str]

_INSTALL_HINT = (
    "Presidio is not installed. Run:\n"
    "    pip install presidio-analyzer presidio-anonymizer\n"
    "    python -m spacy download en_core_web_lg"
)

# Default entity types worth redacting in our domain.
DEFAULT_ENTITIES = [
    "PERSON", "LOCATION", "EMAIL_ADDRESS", "PHONE_NUMBER",
    "CREDIT_CARD", "IBAN_CODE", "IP_ADDRESS", "US_SSN", "UK_NHS",
]


def is_available() -> bool:
    """True if the Presidio packages can be imported."""
    try:
        import presidio_analyzer  # noqa: F401
        import presidio_anonymizer  # noqa: F401
        return True
    except Exception:  # noqa: BLE001
        return False


def build_presidio_detector(
    language: str = "en",
    entities: Optional[list[str]] = None,
    threshold: float = 0.5,
) -> Detector:
    """Build a Presidio-backed detector. Raises ImportError if Presidio is absent.

    The returned callable maps text -> text with detected entities replaced by
    typed placeholders like <PERSON>, <LOCATION>.
    """
    try:
        from presidio_analyzer import AnalyzerEngine
        from presidio_anonymizer import AnonymizerEngine
        from presidio_anonymizer.entities import OperatorConfig
    except Exception as exc:  # noqa: BLE001
        raise ImportError(_INSTALL_HINT) from exc

    analyzer = AnalyzerEngine()
    anonymizer = AnonymizerEngine()
    ents = entities or DEFAULT_ENTITIES

    def detect(text: str) -> str:
        if not text:
            return text
        results = [r for r in analyzer.analyze(text=text, language=language, entities=ents)
                   if r.score >= threshold]
        if not results:
            return text
        operators = {e: OperatorConfig("replace", {"new_value": f"<{e}>"}) for e in ents}
        return anonymizer.anonymize(text=text, analyzer_results=results, operators=operators).text

    return detect


def try_build_presidio_detector(**kwargs) -> Optional[Detector]:
    """Return a Presidio detector, or None (with a log line) if unavailable.

    Safe to call unconditionally at wiring time - never raises.
    """
    if not is_available():
        logger.info("Presidio NER detector unavailable; using regex baseline only. %s",
                    _INSTALL_HINT)
        return None
    try:
        return build_presidio_detector(**kwargs)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to build Presidio detector: %s", exc)
        return None
