# SQL Explanation prompt

Status: scaffold — content to be added during the hackathon.

## Purpose

Given the user's question, the schema we used, and the generated SQL, produce
a short natural-language explanation a non-technical user can follow.

## Output shape

- One sentence on **what** the query does (in plain English).
- 2–4 bullet points on **why**: which tables were used and why, which filters
  were applied, which aggregation was chosen.
- No SQL jargon. No mention of JOIN keyword. Speak in business terms.

## Template

(TODO during hackathon.)

```
You are explaining a database query to a business manager who does not write SQL...

Question: {question}
Schema we used: {schema_summary}
SQL we generated: {sql}

Explain:
- What the query is asking for, in one sentence.
- Why we chose these tables and columns.
- Any filters or aggregations and what they mean in business terms.
```
