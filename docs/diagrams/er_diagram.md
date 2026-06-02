# Entity-Relationship diagram

Status: scaffold — fill in during the hackathon once the DDL is written.
Owner: Abdul Qayyum + Asad.

Mermaid renders natively in GitHub. Keep this file in sync with
`db/ddl/01_create_tables.sql` and `db/schema_descriptions.yaml`.

```mermaid
erDiagram
    %% TODO: replace with the real demo schema.
    %% Example below — uncomment, adapt.

    %% CUSTOMERS ||--o{ ORDERS : "places"
    %% CUSTOMERS {
    %%   NUMBER       customer_id PK
    %%   VARCHAR2     full_name
    %%   CHAR2        country_code
    %%   TIMESTAMP    created_at
    %% }
    %% ORDERS {
    %%   NUMBER       order_id PK
    %%   NUMBER       customer_id FK
    %%   DATE         order_date
    %%   NUMBER       total_gbp
    %% }

    PLACEHOLDER ||--|| TODO : "fill-in-during-hackathon"
```

## Conventions

- `||--o{` — one-to-many
- `||--||` — one-to-one
- `}o--o{` — many-to-many
- PK / FK annotations on the column line
