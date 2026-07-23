# Sprint History

## Purpose

This file records completed decisions and verified outcomes, not detailed chat transcripts.

Update it after each accepted and pushed sprint.

---

## Sprint 6.1 — Normalized Dimensions

Status: Completed

Delivered:

- `dim_product`
- `dim_store`
- `dim_channel`
- `dim_calendar`

Key outcome:

The warehouse gained normalized dimensions for reuse across analysis modules.

---

## Sprint 6.2 — Inventory Dashboard

Status: Completed

Delivered:

- inventory KPIs
- warehouse ranking
- store ranking
- Top 20 inventory
- category summaries
- channel/store filtering

---

## Sprint 6.3 — Inventory Channel Filter

Status: Completed

Business reason:

Inventory data is unreliable for some distributors, so inventory analysis must support channel and store filtering.

---

## Sprint 6.4 — Inventory Health

Status: Completed

Delivered:

- recent 30-day sales
- sell-through-related health indicators
- inventory days
- inventory health cards
- localized labels

---

## Sprint 6.5 — Formal Sell-Through Analysis

Status: Completed

Known commit:

```text
55b24d5
```

Delivered:

- `inventory_basis`
- terminal inventory
- all inventory
- quarter sell-through
- cumulative sell-through
- product sell-through ranking

Regression fixed before acceptance:

Product Detail inherited a global women-category scope that injected `category_name` into raw `fact_retail_sales` queries.

Root fix:

Product Detail uses a detail-specific filter normalization that forces scope to `all` and retains exact product code.

Validated routes included:

- `/products/KU21T1013`
- `/inventory`
- `/inventory?inventory_basis=terminal`
- `/inventory?inventory_basis=all`
- `/quarter`
- `/`

---

## Sprint 7.1 — Automatic Daily Sales Ingestion

Status: Completed

Delivered:

- automatic scan of `exports/sales/daily/`
- SHA-256 file registry
- duplicate skip
- file-atomic import
- same-path corrected-file replacement
- invalid-row tracking
- `.xlsx` and `.xls` support
- `/api/reload` integration
- existing 07:10 scheduler integration
- cross-process import lock
- snapshot rebuild only when needed

Known operational baseline used during validation:

- latest sales date restored to `2026-07-06`
- `fact_retail_sales` restored to `447,829` rows

Known remaining edge:

A corrected file with both changed contents and changed path may be treated as a new source.

---

## Daily Folder Path Refactor

Status: Completed

Changed production path:

```text
exports/daily/
→ exports/sales/daily/
```

This was a path-only refactor.

---

## Sprint 8.1 — Data Center

Status: Completed

Delivered:

- Data Center
- Overall system health
- Sales freshness
- Inventory freshness
- Snapshot status
- Registry-aware daily queue
- Import lock state
- Import history
- Master data quality
- Operational alerts

Key implementation:

- Registry-aware pending queue
- Shared inventory quantity helper
- Read-only architecture
- Compatibility redirect from /imports

Validation:

- GET /data-center is read-only
- Queue semantics verified
- Existing routes verified
- Shared inventory contract reused
- No importer or snapshot side effects

Known remaining risk:

- Initial render performance (~2–3 s) can be optimized in a future sprint if necessary.

Commit:
Status: Completed

Delivered:

- Data Center
- Overall system health
- Sales freshness
- Inventory freshness
- Snapshot status
- Registry-aware daily queue
- Import lock state
- Import history
- Master data quality
- Operational alerts

Key implementation:

- Registry-aware pending queue
- Shared inventory quantity helper
- Read-only architecture
- Compatibility redirect from /imports

Validation:

- GET /data-center is read-only
- Queue semantics verified
- Existing routes verified
- Shared inventory contract reused
- No importer or snapshot side effects

Known remaining risk:

- Initial render performance (~2–3 s) can be optimized in a future sprint if necessary.

Commit:
ea76feb

---

## How to Update This File

For every accepted sprint, add:

- sprint name
- status
- commit hash
- exact files changed
- business outcome
- real validation results
- known remaining risks
