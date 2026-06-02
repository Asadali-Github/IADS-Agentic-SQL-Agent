# Seed data

Demo data loaded by `scripts/seed_database.py` after `db/ddl/01_create_tables.sql` has run.

## Layout

Drop CSV files here, one per table:

```
db/seed/
├── customers.csv
├── orders.csv
└── ...
```

## Rules

- Filename matches the target table name exactly.
- First row is the header; column names match the DDL exactly.
- Files >1 MB go to OCI Object Storage; this directory is for small demo data only.
- If a CSV needs cleaning before loading, write a preprocessor in `scripts/preprocess_raw_data.py` and put the *raw* file in `data/raw/`.

## Loading

```bash
make seed-db
```

Idempotent: re-running truncates the tables before re-inserting.
