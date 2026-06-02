# Raw Dataset

Place the product sales CSV here:

```text
data/raw/product_sales_dataset_final.csv
```

The current file can be profiled with:

```powershell
python -m app.data.csv_profiler data/raw/product_sales_dataset_final.csv
```

The profiler turns CSV headers, sample values, and inferred column types into
schema context that we can later convert into RAG documents.

Current known dataset shape:

```text
Rows: 200000
Columns: Order_ID, Order_Date, Customer_Name, City, State, Region, Country,
Category, Sub_Category, Product_Name, Quantity, Unit_Price, Revenue, Profit
```

Note: the raw CSV headers for `Unit_Price`, `Revenue`, and `Profit` include
extra spaces. The profiler strips those spaces for schema/RAG output.
