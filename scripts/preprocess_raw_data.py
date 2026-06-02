"""Preprocess raw demo data into seed CSVs.

Owner: Asad
Status: scaffold — implement during the hackathon if raw data needs cleaning.

Use case:
  We pull a demo dataset (e.g. from Kaggle, OCI sample data, or a public
  source). Before loading into the Autonomous DB, the data needs:
    - column renaming to match db/ddl naming conventions
    - type coercion
    - null handling
    - de-duplication
    - light feature derivation (e.g. extract year from order_date)

Pipeline:
  data/raw/<source>.csv
      → preprocess_raw_data.py
      → db/seed/<table>.csv
      → scripts/seed_database.py (loads into the DB)

TODO:
- Read raw CSV(s) from data/raw/
- Apply cleaning rules (document each rule in a comment)
- Write cleaned CSVs to db/seed/
- Emit a summary report: rows in / rows out / rows dropped + reasons
- Idempotent: safe to re-run

Make target:
  make preprocess   (TODO: add to Makefile)
"""
