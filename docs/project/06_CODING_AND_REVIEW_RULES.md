# Coding and Review Rules

## 1. Reviewer Role

Act as a senior architect and code reviewer.

Do not trust Copilot or Codex progress summaries without evidence.

Require:

- exact files changed
- relevant diffs
- real database results
- real Flask route checks
- cleanup of temporary artifacts

## 2. Change Scope

Prefer minimal root-cause fixes.

Avoid:

- broad rewrites
- unrelated refactors
- new parallel importers
- duplicated formulas
- speculative schema changes

## 3. Layering Rules

### Query Layer

- SQL belongs in `queries/`.
- Use grouped aggregates.
- Avoid N+1 queries.

### Semantic Layer

- display formatting
- statuses
- alerts
- typed models

### Routes

- request handling
- orchestration
- rendering

Routes must not contain raw SQL or metric formulas.

### Templates

Templates must not contain:

- SQL
- business formulas
- data mutations

## 4. Business Contract Preservation

Do not change without explicit approval:

- terminal inventory definition
- all inventory definition
- sell-through formulas
- movement-rate formula
- inventory-days logic
- importer uniqueness strategy
- Product Detail filter scope behavior

## 5. Importer Rules

- reuse the existing sales importer
- preserve hash idempotency
- preserve file atomicity
- never silently drop invalid rows
- never delete source Excel files unexpectedly
- never commit deletion before replacement import is safe

## 6. Data Center Rules

Data Center is read-only.

Opening it must not:

- import data
- rebuild snapshots
- clear caches
- remove lock files
- move source files
- modify database rows

## 7. Validation Rules

Validate against:

- the real SQLite database
- the real Flask app/test client
- real routes
- real filesystem queue state

Do not use fake stubs when runtime validation is available.

Core route regression checks commonly include:

```text
/
/quarter
/inventory
/products/KU21T1013
/api/dashboard
/api/reload
/data-center
```

Use only routes relevant to the current change.

## 8. Git Rules

Before commit:

```powershell
git status
git diff --stat
git diff -- <explicit files>
```

Stage explicit files:

```powershell
git add path/to/file1 path/to/file2
```

Never use:

```powershell
git add .
```

Do not recommend pushing until:

- scope is confirmed
- runtime behavior is verified
- temporary files are removed
- database state is known

## 9. Non-Production Artifacts

Do not commit:

- validation scripts
- temporary workbooks
- SQLite backups
- lock files
- logs
- generated output files
- test-only exports
- local environment files

## 10. Communication Rules

- Respond to the project owner in Chinese.
- Write implementation prompts for Copilot/Codex in English.
- Clearly separate verified facts from assumptions.
- State remaining risks explicitly.
