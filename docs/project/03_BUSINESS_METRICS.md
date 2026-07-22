# Business Metrics

## 1. Principle

Business metrics are contracts.

UI work, route work, Data Center work, and importer observability work must not redefine them.

When a metric already exists, reuse its query and semantic definition.

## 2. Inventory Basis

### Terminal Inventory

Terminal inventory represents inventory assigned to terminal/store warehouses according to the established warehouse-to-store mapping.

Rules:

- Reuse the current Inventory page definition.
- Do not create a separate Data Center definition.
- Do not infer terminal inventory from warehouse names alone.

### All Inventory

All inventory includes every supported inventory base, including non-terminal warehouse inventory where applicable.

## 3. Sales Metrics

Known sales measures include:

- sales quantity
- sales amount
- standard amount
- discount rate
- recent 30-day sales
- quarter sales
- cumulative sales

Definitions must come from current query code.

## 4. Inventory Measures

Known measures include:

- inventory quantity
- inventory amount
- terminal inventory quantity
- all inventory quantity
- warehouse count
- product count

## 5. Sell-Through Metrics

### Quarter Sell-Through

Use the established Inventory semantic/query definition.

Do not recreate the formula independently in Data Center, routes, or templates.

### Cumulative Sell-Through

Use the established Inventory semantic/query definition.

### Movement Rate

Use the current implementation and effective sales-date logic.

### Inventory Days

Use the current implementation.

Do not change denominator behavior, zero-handling, or date windows without explicit business approval.

## 6. Effective Sales Date

Reports that depend on recent sales must use the platform’s existing effective latest-sales-date logic rather than assuming the computer date is the latest available business date.

## 7. Inventory Health

Inventory health labels and thresholds must be reused from the existing Inventory feature where applicable.

Data Center may report freshness and operational health, but should not create a second inventory-health business model.

## 8. Freshness Status

Freshness is an operational status, not a sales metric.

Any freshness thresholds should be centralized and documented.

Suggested initial operational thresholds:

### Sales

- Healthy: within 2 calendar days
- Warning: 3–5 days behind
- Critical: more than 5 days behind

### Inventory

- Healthy: within 7 days
- Warning: 8–14 days behind
- Critical: more than 14 days behind

These thresholds must be checked against actual business cadence before being treated as permanent policy.

## 9. No Formula Duplication

Never place formulas in:

- templates
- navigation code
- Data Center route
- refresh route

Preferred ownership:

```text
queries/       → raw aggregates
semantic/      → interpretation and display status
routes/        → orchestration only
```
