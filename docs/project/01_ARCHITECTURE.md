# Architecture

## 1. Architectural Flow

```text
RPA
→ BSERP Excel exports
→ Importers
→ SQLite warehouse
→ Query Layer
→ Semantic Layer
→ Flask Routes
→ Templates
→ Cloudflare Tunnel
```

Each layer has a distinct responsibility.

## 2. Layer Responsibilities

### 2.1 Export Layer

Expected production export locations:

```text
exports/
├── master/
├── inventory/
└── sales/
    ├── history/
    └── daily/
```

- `exports/master/`: product, store, warehouse, and other master data
- `exports/inventory/`: inventory snapshots
- `exports/sales/history/`: historical or bulk sales exports
- `exports/sales/daily/`: incremental daily sales exports

### 2.2 Importer Layer

Responsibilities:

- locate and parse source files
- validate required columns
- normalize values
- preserve existing importer contracts
- write facts and dimensions to SQLite
- record import results
- enforce idempotency and atomicity

Importers must not contain presentation logic.

### 2.3 SQLite Warehouse

SQLite is the operational source of truth for dashboard queries.

It contains:

- normalized dimensions
- sales facts
- inventory facts
- import registry/log data
- snapshot data or snapshot metadata where implemented

### 2.4 Query Layer

Location:

```text
queries/
```

Responsibilities:

- SQL only
- grouped aggregates
- joins
- filters
- efficient retrieval
- safe handling of empty data where expected

Rules:

- SQL must not leak into Flask routes.
- SQL must not appear in templates.
- Avoid N+1 query patterns.
- Reuse established business definitions.

### 2.5 Semantic Layer

Location:

```text
semantic/
```

Responsibilities:

- typed models or typed dictionaries
- display-ready labels
- date and quantity formatting
- status mapping
- alert severity
- business interpretation based on query results

Rules:

- no raw SQL
- no HTML generation
- no database mutation

### 2.6 Flask Route Layer

Location:

```text
routes/
```

Responsibilities:

- request parsing
- calling query and semantic layers
- rendering templates
- returning structured JSON for APIs

Rules:

- no SQL
- no duplicated business formulas
- no filesystem mutation on read-only pages

### 2.7 Template Layer

Location:

```text
templates/
```

Responsibilities:

- presentation
- layout
- user interaction

Rules:

- no raw SQL
- no business metric calculations
- no hidden data-import side effects

## 3. Main Architectural Contracts

### Product Detail

Product Detail is product-specific and must not inherit the global category scope filter.

The exact product code is already sufficient to define the detail context.

### Inventory

Inventory supports two bases:

- `terminal`
- `all`

Terminal inventory must reuse the established inventory definition and warehouse/store mapping.

### Daily Sales

Daily sales files belong in:

```text
exports/sales/daily/
```

Daily imports must remain:

- SHA-256 hash-idempotent
- file-atomic
- safe across duplicate filenames and byte-identical renames
- compatible with the existing warehouse importer

### Data Center

Data Center is read-only unless explicitly approved otherwise.

Opening Data Center must not:

- run imports
- rebuild snapshots
- clear caches
- modify database rows
- move or delete files

## 4. Change Strategy

Prefer:

- minimal root-cause fixes
- small scoped commits
- reuse of existing helpers
- real-database validation
- real-route validation

Avoid:

- broad rewrites
- parallel implementations
- speculative abstractions
- hidden schema changes
