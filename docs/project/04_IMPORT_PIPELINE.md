# Import Pipeline

## 1. Export Folder Contract

```text
exports/
├── master/
├── inventory/
└── sales/
    ├── history/
    └── daily/
```

Daily sales production path:

```text
exports/sales/daily/
```

## 2. Daily Sales Workflow

```text
BSERP daily sales export
→ place file in exports/sales/daily/
→ scan supported Excel files
→ calculate SHA-256
→ consult daily_sales_import_registry
→ validate workbook structure
→ import through existing sales importer
→ commit file atomically
→ record result
→ rebuild dependent snapshot when needed
→ clear relevant caches
```

## 3. Supported Files

Supported:

- `.xlsx`
- `.xls`

Ignored:

- files beginning with `~$`
- hidden files
- non-Excel files
- directories
- lock files

Files are processed deterministically by:

1. oldest modification time
2. filename

## 4. Idempotency

Primary file identity:

- SHA-256 file hash

Expected behavior:

- same bytes, same name → skip
- same bytes, renamed → skip
- changed contents, same path → replace using established source-file strategy
- failed file with changed contents → eligible for retry

Known edge case:

A corrected file whose contents and filename/path both change may be treated as a new source because the existing row hash includes source-file identity.

Operational rule until improved:

> For corrected daily exports, overwrite the original file at the same path instead of renaming it.

## 5. File Atomicity

A daily sales file must be atomic.

Required behavior:

```text
BEGIN
→ remove prior rows for same source path when replacement is required
→ insert/update all valid rows
→ update registry/log
COMMIT
```

On failure:

```text
ROLLBACK
```

Do not commit deletion separately before replacement rows are safely imported.

## 6. Validation

Minimum row/file validation includes:

- required columns exist
- sales date is parseable
- product code exists in the row
- store code exists where required
- quantity is numeric
- monetary fields are numeric when populated

Rejected rows must be counted and explained.

Do not silently discard invalid rows.

## 7. Registry

Table:

```text
daily_sales_import_registry
```

Tracks:

- file identity
- source filename/path
- status
- row counts
- replacement count
- duplicate count
- rejection count/reasons
- sales date range
- error message

## 8. Manual Execution

CLI:

```powershell
python import_daily_sales.py
```

Structured mode:

```powershell
python import_daily_sales.py --json
```

The JSON flag should ideally produce machine-parseable JSON only. If human-readable text is also emitted, treat that as a future cleanup item.

## 9. Application Refresh

The existing refresh endpoint is reused.

Expected workflow:

```text
/api/reload
→ scan exports/sales/daily/
→ import new files
→ rebuild dependent snapshots only when needed
→ return structured result
```

Do not create a second refresh endpoint without a proven requirement.

## 10. Scheduler

The existing daily scheduler is reused.

Known target time:

```text
07:10
```

Requirements:

- prevent duplicate execution from Werkzeug parent/child processes
- prevent overlapping imports
- use the existing cross-process lock

Lock path:

```text
exports/sales/daily/.daily_import.lock
```

## 11. File Lifecycle

Production source files must not be deleted unexpectedly.

The current safe approach is to leave imported files in place and rely on the registry.

Failed files remain available for inspection.

## 12. Validation Contract

Every importer change should validate:

- empty folder
- one valid file
- second-run duplicate skip
- renamed identical file
- mixed valid and invalid files
- corrected same-path file
- latest sales date movement
- no doubled totals
- route health
- sell-through refresh
- lock contention
- no unexpected source-file deletion
