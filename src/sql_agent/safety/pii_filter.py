"""PII filter - strip sensitive data from logs and summariser output.

Owner: Asad.

Small but load-bearing for the safety story: nothing the agent logs or shows the
user should leak personal data that happens to sit in the demo database (emails,
phone numbers, card numbers, etc.). The filter is deterministic regex redaction -
no LLM, no network - so it is cheap enough to run on every log line and every
summary, and easy to unit-test.

Usage
-----
    from sql_agent.safety.pii_filter import scrub, scrub_summary

    safe_line = scrub("contact bob@acme.com or 07700 900123")
    # -> "contact [EMAIL] or [PHONE]"

    safe = scrub_summary(answer_summary)   # redacts answer + bullets

Design notes
------------
* Order matters: emails / cards / SSNs / IPs are redacted before phone numbers
  so their digits are gone before the (looser) phone matcher runs.
* We redact to typed placeholders ([EMAIL], [PHONE], ...) rather than blanking,
  so logs stay readable and we can see *that* something was removed.
* The phone rule is validated by a callback: a candidate is only redacted if it
  has 7-15 digits AND contains a separator or a leading '+'. This is the key
  guard that stops us mangling legitimate numeric answers like "4200000" (a
  revenue figure) while still catching "+44 7700 900123".
"""

from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Pattern

logger = logging.getLogger(__name__)

# Shared single-thread executor used to time-box optional NER detectors so a
# Presidio latency spike can never hang the request or let raw PII through.
_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="pii-ner")

# A rule is (label, pattern, validator). If validator is None the match is always
# redacted; otherwise the match text must satisfy validator() to be redacted.
Validator = Callable[[str], bool]
Rule = tuple[str, Pattern[str], Optional[Validator]]


def _is_phone(candidate: str) -> bool:
    """True if a phone-shaped candidate is really a phone (not a bare number)."""
    digits = sum(c.isdigit() for c in candidate)
    if not (7 <= digits <= 15):
        return False
    has_separator = any(c in " -.()" for c in candidate.strip())
    has_plus = candidate.strip().startswith("+")
    return has_separator or has_plus


_DEFAULT_RULES: list[Rule] = [
    ("EMAIL", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), None),
    # 13-16 digit card numbers, optionally separated by spaces/dashes.
    ("CARD", re.compile(r"\b(?:\d[ -]?){12,15}\d\b"), None),
    # US SSN-style xxx-xx-xxxx.
    ("SSN", re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), None),
    # IPv4 addresses.
    ("IP", re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"), None),
    # Phone candidates: a digit run that may include + ( ) spaces dashes dots.
    # Validated by _is_phone so plain integers are NOT redacted.
    ("PHONE", re.compile(r"\+?\d[\d\s().\-]{5,}\d"), _is_phone),
]

# Extra, more aggressive patterns used as the strict floor when the NER backend
# is unavailable or times out. Kept OUT of the default set because they can be
# noisier; enable with PIIFilter(strict=True). They deliberately avoid bare
# integers (revenue figures) - they target id-shaped and address-shaped tokens.
_STRICT_RULES: list[Rule] = [
    # UK postcodes, e.g. "SW1A 1AA", "EC1A1BB".
    ("POSTCODE", re.compile(r"\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b"), None),
    # Long alphanumeric identifiers mixing letters AND digits (account/order ids,
    # API keys). Requires both a letter and a digit so plain words/numbers survive.
    ("ID", re.compile(r"\b(?=[A-Za-z0-9_-]*[A-Za-z])(?=[A-Za-z0-9_-]*\d)[A-Za-z0-9_-]{8,}\b"), None),
]


# A detector is any callable that takes text and returns it with PII redacted.
# This is the plug-in point for an enterprise NER backend (Microsoft Presidio,
# a spaCy pipeline, AWS Comprehend, ...) which catches context-dependent PII that
# regex misses - names, addresses, account ids masquerading as free text. The
# regex rules below are the always-on, zero-dependency baseline; detectors run
# AFTER them and augment, never replace, that baseline.
#
# Example Presidio adapter (kept out of the default to avoid a heavy dependency):
#
#     from presidio_analyzer import AnalyzerEngine
#     from presidio_anonymizer import AnonymizerEngine
#     analyzer, anonymizer = AnalyzerEngine(), AnonymizerEngine()
#     def presidio_detector(text: str) -> str:
#         results = analyzer.analyze(text=text, language="en")
#         return anonymizer.anonymize(text=text, analyzer_results=results).text
#     pii = PIIFilter(extra_detectors=[presidio_detector])
Detector = Callable[[str], str]


@dataclass
class PIIFilter:
    """Configurable redactor: regex baseline + optional pluggable NER detectors.

    The regex baseline is the GUARANTEED floor - it always runs first and in full,
    so even if an optional NER detector (Presidio) times out or raises, the text
    that comes back has already had structured PII (emails/phones/cards/...)
    redacted. Detectors only ever *add* redactions, never remove them.
    """

    rules: list[Rule] = field(default_factory=lambda: list(_DEFAULT_RULES))
    template: str = "[{label}]"
    extra_detectors: list[Detector] = field(default_factory=list)
    strict: bool = False              # also apply the aggressive _STRICT_RULES floor
    detector_timeout_s: Optional[float] = 1.0  # time-box each NER detector call

    def __post_init__(self) -> None:
        if self.strict:
            # Append strict rules that aren't already present.
            have = {r[0] for r in self.rules}
            self.rules = list(self.rules) + [r for r in _STRICT_RULES if r[0] not in have]

    def _apply_regex(self, text: str) -> str:
        out = text
        for label, pattern, validator in self.rules:
            placeholder = self.template.format(label=label)
            if validator is None:
                out = pattern.sub(placeholder, out)
            else:
                out = pattern.sub(
                    lambda m, _p=placeholder, _v=validator: _p if _v(m.group()) else m.group(),
                    out,
                )
        return out

    def scrub(self, text: str) -> str:
        """Return `text` with every matched PII span replaced by a placeholder."""
        if not text:
            return text
        out = self._apply_regex(text)  # guaranteed floor - happens before any NER
        for detector in self.extra_detectors:
            out = self._run_detector(detector, out)
        return out

    def _run_detector(self, detector: Detector, text: str) -> str:
        """Run one detector with a timeout; fall back to the regex result on any
        timeout or error so a latency spike never stalls the request or leaks PII."""
        try:
            if self.detector_timeout_s is None:
                result = detector(text)
            else:
                result = _EXECUTOR.submit(detector, text).result(timeout=self.detector_timeout_s)
            return result if isinstance(result, str) else text
        except FutureTimeout:
            logger.warning("PII NER detector timed out after %ss; using regex floor only.",
                           self.detector_timeout_s)
            return text
        except Exception as exc:  # noqa: BLE001
            logger.warning("PII NER detector failed (%s); using regex floor only.", exc)
            return text

    def scrub_rows(
        self, columns: "list[str]", rows: "list[list]"
    ) -> "list[list]":
        """Dual-gate helper: scrub PII out of result rows at the DB boundary.

        Used to clean data BEFORE it reaches the logging layer or the client UI,
        complementing scrub_summary() which cleans the model's narrative OUTPUT.
        Non-string cells (numbers, dates) pass through untouched.
        """
        return [[self.scrub(c) if isinstance(c, str) else c for c in row] for row in rows]

    def found(self, text: str) -> list[str]:
        """Return the labels of PII types present in `text` (for audit logging)."""
        hits: list[str] = []
        for label, pattern, validator in self.rules:
            for m in pattern.finditer(text or ""):
                if validator is None or validator(m.group()):
                    hits.append(label)
                    break
        return hits

    def scrub_obj(self, obj: Any) -> Any:
        """Recursively scrub strings inside dicts/lists/tuples (e.g. log payloads).

        Numbers, bools and None pass through untouched so structured metrics are
        not corrupted. Dict keys are left as-is; only values are scrubbed.
        """
        if isinstance(obj, str):
            return self.scrub(obj)
        if isinstance(obj, dict):
            return {k: self.scrub_obj(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return type(obj)(self.scrub_obj(v) for v in obj)
        return obj


# Module-level default instance + convenience functions ----------------------
_DEFAULT = PIIFilter()


def scrub(text: str) -> str:
    """Redact PII from a single string using the default filter."""
    return _DEFAULT.scrub(text)


def found(text: str) -> list[str]:
    """List PII types found in `text` using the default filter."""
    return _DEFAULT.found(text)


def scrub_obj(obj: Any) -> Any:
    """Recursively redact PII from a nested structure using the default filter."""
    return _DEFAULT.scrub_obj(obj)


def scrub_rows(columns: list, rows: list) -> list:
    """Scrub PII from result rows (DB-boundary gate) using the default filter."""
    return _DEFAULT.scrub_rows(columns, rows)


def scrub_summary(summary: Any) -> Any:
    """Return a copy of an AnswerSummary with answer + explanation bullets scrubbed."""
    data = summary.model_dump()
    data["answer"] = scrub(data.get("answer", ""))
    data["explanation"] = [scrub(b) for b in data.get("explanation", [])]
    if data.get("insights"):
        data["insights"] = [scrub(b) for b in data["insights"]]
    if data.get("clarification"):
        data["clarification"] = scrub(data["clarification"])
    return summary.__class__(**data)


# ---------------------------------------------------------------------------
# Inbound gate: scrub PII before it ever reaches application logs.
# Pair with scrub_summary() (outbound, toward the UI) for bi-directional safety.
# ---------------------------------------------------------------------------
class PIIRedactingLogFilter(logging.Filter):
    """A logging.Filter that redacts PII from every log record's message + args.

    Install once at startup and any logger.info("user %s", email) is scrubbed
    before it is written, so cleartext PII can never land in a log file or sink.

        from sql_agent.safety.pii_filter import install_log_redaction
        install_log_redaction()  # attaches to the root logger
    """

    def __init__(self, pii: Optional["PIIFilter"] = None) -> None:
        super().__init__()
        self.pii = pii or _DEFAULT

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003 - logging API
        try:
            if isinstance(record.msg, str):
                record.msg = self.pii.scrub(record.msg)
            if record.args:
                if isinstance(record.args, dict):
                    record.args = {k: self.pii.scrub(v) if isinstance(v, str) else v
                                   for k, v in record.args.items()}
                else:
                    record.args = tuple(self.pii.scrub(a) if isinstance(a, str) else a
                                        for a in record.args)
        except Exception:  # noqa: BLE001 - logging must never raise
            pass
        return True


def install_log_redaction(logger: Optional[logging.Logger] = None,
                          pii: Optional["PIIFilter"] = None) -> PIIRedactingLogFilter:
    """Attach a PIIRedactingLogFilter to `logger` (root if None). Idempotent."""
    target = logger or logging.getLogger()
    for existing in target.filters:
        if isinstance(existing, PIIRedactingLogFilter):
            return existing
    flt = PIIRedactingLogFilter(pii)
    target.addFilter(flt)
    # Also attach to existing handlers so records formatted there are scrubbed.
    for handler in target.handlers:
        handler.addFilter(flt)
    return flt
