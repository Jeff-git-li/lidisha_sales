# Database and Data Dictionary

## 1. General Rule

The current SQLite schema and actual query results are the primary source of truth.

This document records known contracts but must be updated when the schema changes.

## 2. Core Dimension Tables

### `dim_product`

Purpose:

- normalized product master
- product attributes used by analysis and filters

Known fields include concepts such as:

- `product_code`
- `product_name`
- year
- season
- wave
- level-1 category
- level-2 category
- standard retail price

Important rule:

Product Detail queries must not assume every raw fact query exposes product dimension columns.

### `dim_store`

Purpose:

- normalized store master
- store, region, and channel attributes

Known concepts include:

- `store_code`
- `store_name`
- channel
- region
- assigned warehouse

Important operational finding:

For most active stores, the assigned warehouse code matches the store code. This mapping supports terminal inventory logic.

### `dim_channel`

Purpose:

- normalized channel dimension

### `dim_calendar`

Purpose:

- normalized calendar/date dimension

## 3. Core Fact Tables

### `fact_retail_sales`

Purpose:

- normalized retail sales fact table

Known operational fields include concepts such as:

- sale date
- product code
- store code
- color
- size
- document number
- document type
- quantity
- standard amount
- actual amount
- source file
- source row hash
- import run metadata

Important contracts:

- Daily imports reuse the existing sales importer.
- Row conflict handling uses the existing `source_row_hash` strategy.
- Same-path corrected file replacement must be transaction-safe.
- Sales totals must not double after repeat import.

### Inventory fact table

The exact current table name must be confirmed from source code and schema before changes.

Purpose:

- inventory snapshot rows by product, warehouse, color, and size

Known source fields include:

- product code
- warehouse code
- color name
- size name
- quantity

Important contracts:

- terminal and all inventory bases use the existing inventory definition
- Data Center must not create a competing terminal-inventory formula

## 4. Operational Tables

### `daily_sales_import_registry`

Purpose:

- durable file-level registry for daily sales imports

Known columns:

- `file_hash`
- `source_file`
- `file_name`
- `file_size`
- `file_mtime`
- `imported_at`
- `status`
- `rows_read`
- `rows_imported`
- `rows_replaced`
- `duplicate_rows`
- `rows_rejected`
- `rejection_reasons`
- `sales_date_min`
- `sales_date_max`
- `error_message`

Important contracts:

- file hash is SHA-256
- byte-identical renamed files are skipped
- failed files may be retried after their contents change

### `import_log`

Purpose:

- run-level import logging

Known concepts include:

- import type
- source file
- start/finish times
- rows read
- duplicate rows
- unknown product/store information
- elapsed time
- status
- message

Data Center should avoid showing duplicate history rows when `import_log` and `daily_sales_import_registry` describe the same operation.

## 5. Snapshot Data

Snapshot table names and metadata must be confirmed from current source code before modification.

Data Center may display:

- latest snapshot build time
- snapshot row count
- date coverage
- whether the snapshot is behind latest sales

Opening Data Center must never rebuild a snapshot.

## 6. Known Baseline Values

These values are historical validation references only, not permanent constants:

- A restored sales baseline previously showed latest sales date `2026-07-06`.
- A restored sales baseline previously showed `447,829` rows in `fact_retail_sales`.
- Inventory validation previously observed 588,644 source rows and 9,765 unique products.

Always query the real database before reporting current values.

## 7. Schema Change Policy

Before adding or changing a table:

1. Prove the existing schema cannot support the requirement.
2. Prefer `CREATE TABLE IF NOT EXISTS` for additive operational metadata.
3. Do not rebuild existing fact tables casually.
4. Validate against the real database.
5. Record the migration or initialization behavior.
6. Confirm no production data is lost.
