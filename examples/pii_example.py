#!/usr/bin/env python3
"""PII filter: scrub free text, result rows, and application logs.

    python examples/pii_example.py
"""
import _path  # noqa: F401

import io
import logging

from sql_agent.safety.pii_filter import PIIFilter, scrub, scrub_rows, install_log_redaction

# 1. Free-text scrubbing (numbers like revenue survive).
print("text:", scrub("email ada@maths.org, phone +44 7700 900123, revenue 4200000"))

# 2. Dual-gate: scrub result rows at the DB boundary (numbers untouched).
rows = [["Ada Lovelace", "ada@maths.org", 18420.0]]
print("rows:", scrub_rows(["name", "email", "spend"], rows))

# 3. Strict mode adds postcodes + mixed-case ids when NER is unavailable.
print("strict:", PIIFilter(strict=True).scrub("order ORD12345AB to SW1A 1AA"))

# 4. Inbound log gate: PII never reaches the log sink.
buf = io.StringIO()
logging.getLogger().addHandler(logging.StreamHandler(buf))
logging.getLogger().setLevel(logging.INFO)
install_log_redaction()
logging.getLogger("demo").info("signup: %s", "jane@x.com")
print("log line:", buf.getvalue().strip())
