-- Schema for the IADS SQL Agent demo dataset.
-- Owner: Abdul Qayyum + Asad
-- Status: DRAFT for the real product_sales dataset (data/raw/product_sales_dataset_final.csv,
--         cleaned to db/seed/product_sales.csv by scripts/preprocess_raw_data.py).
--         Abdul to confirm types / load mechanics against Oracle Autonomous DB.
--
-- Style guide:
--   * snake_case identifiers
--   * PRIMARY KEYs always declared
--   * Each column gets a COMMENT clause matching db/schema_descriptions.yaml
--   * Indexes on every column that appears in a likely WHERE clause
--
-- Update the ER diagram in docs/diagrams/er_diagram.md whenever this file changes.

-- ============================================================================
-- product_sales — one row per order line of a US retail sales dataset.
-- Denormalised (single fact table); 200,000 rows.
-- ============================================================================
CREATE TABLE product_sales (
    order_id        NUMBER          PRIMARY KEY,
    order_date      DATE            NOT NULL,
    customer_name   VARCHAR2(200)   NOT NULL,
    city            VARCHAR2(100)   NOT NULL,
    state           VARCHAR2(100)   NOT NULL,
    region          VARCHAR2(20)    NOT NULL,
    country         VARCHAR2(60)    NOT NULL,
    category        VARCHAR2(60)    NOT NULL,
    sub_category    VARCHAR2(60)    NOT NULL,
    product_name    VARCHAR2(120)   NOT NULL,
    quantity        NUMBER(6)       NOT NULL,
    unit_price      NUMBER(10, 2)   NOT NULL,
    revenue         NUMBER(12, 2)   NOT NULL,
    profit          NUMBER(12, 2)   NOT NULL
);

COMMENT ON TABLE  product_sales              IS 'One row per order line of a US retail sales dataset (denormalised fact table).';
COMMENT ON COLUMN product_sales.order_id     IS 'Unique identifier for an order line.';
COMMENT ON COLUMN product_sales.order_date   IS 'Calendar date the order was placed. Spans 2023-2024. Used for all date filtering.';
COMMENT ON COLUMN product_sales.customer_name IS 'Customer full name. Personal data - never surface in logs unredacted.';
COMMENT ON COLUMN product_sales.city         IS 'City of the customer / order.';
COMMENT ON COLUMN product_sales.state        IS 'US state (47 distinct), e.g. California, Texas.';
COMMENT ON COLUMN product_sales.region       IS 'US sales region: one of Centre, East, South, West.';
COMMENT ON COLUMN product_sales.country      IS 'Country of sale. Constant: United States.';
COMMENT ON COLUMN product_sales.category     IS 'Top-level product category: Accessories, Clothing & Apparel, Electronics, Home & Furniture.';
COMMENT ON COLUMN product_sales.sub_category IS 'Product sub-category (19 distinct), e.g. Laptops, Footwear.';
COMMENT ON COLUMN product_sales.product_name IS 'Product name (49 distinct), e.g. Phone Case, Nike Air Force 1.';
COMMENT ON COLUMN product_sales.quantity     IS 'Units sold on this order line (1-11).';
COMMENT ON COLUMN product_sales.unit_price   IS 'Price per unit in US dollars (USD).';
COMMENT ON COLUMN product_sales.revenue      IS 'Total line revenue in USD (= quantity * unit_price). The canonical sales/revenue measure.';
COMMENT ON COLUMN product_sales.profit       IS 'Total line profit in USD after costs. The canonical margin measure.';

CREATE INDEX idx_ps_order_date   ON product_sales(order_date);
CREATE INDEX idx_ps_region       ON product_sales(region);
CREATE INDEX idx_ps_category     ON product_sales(category);
CREATE INDEX idx_ps_sub_category ON product_sales(sub_category);
CREATE INDEX idx_ps_state        ON product_sales(state);
CREATE INDEX idx_ps_product_name ON product_sales(product_name);
