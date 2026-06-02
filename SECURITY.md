# Security

> Status: scaffold — content to be added during the hackathon.

## Threat model

This system accepts untrusted natural-language input and produces SQL that runs against a database. Concrete threats:

1. **SQL injection via NL** — the LLM is coaxed into emitting destructive SQL.
2. **Prompt injection** — user input overrides system prompt (e.g. "ignore previous instructions and...").
3. **Data exfiltration** — generated SQL pulls sensitive columns the user shouldn't see.
4. **Resource exhaustion** — generated SQL runs an unbounded join or full scan.
5. **PII leakage in summaries** — the summariser repeats raw PII back to the user.

## Mitigations (current)

(TODO: map each threat to a mitigation in `src/sql_agent/safety/` and the DB-level controls.)

## Out of scope

- Authentication (no auth in the hackathon scaffold).
- Per-user rate limiting.

## Reporting

(TODO: contact + responsible disclosure window.)
