# LiDiSha Retail Intelligence Platform

## 1. Purpose

The LiDiSha Retail Intelligence Platform is a local-first retail BI and operational intelligence system for a Chinese fashion business.

Its purpose is to turn BSERP exports into reliable, reusable business information for sales, inventory, product, store, quarter, and operational data-health analysis.

The platform is designed for repeated internal use rather than one-off reporting.

## 2. Repository

- GitHub: `Jeff-git-li/lidisha_sales`
- Primary branch: `main`
- Local application: Flask
- Database: SQLite
- External access: Cloudflare Tunnel

## 3. Technology Stack

- Python
- Flask
- SQLite
- BSERP Excel exports
- OpenPyXL / Pandas where required by import format
- HTML / CSS / JavaScript
- Cloudflare Tunnel

## 4. Core Architecture

```text
RPA
→ Excel exports
→ Importers
→ SQLite
→ Query Layer
→ Semantic Layer
→ Flask Routes
→ Templates
→ Cloudflare Tunnel
```

## 5. Current Product Modules

- Home
- Quarter
- Product Explorer
- Product Detail
- Inventory
- Daily Sales Import
- Data Center (Sprint 8.1)

## 6. Current Platform Stage

The project has moved beyond a simple dashboard and now includes:

- normalized dimensions
- operational fact tables
- inventory basis controls
- sell-through metrics
- automatic daily sales ingestion
- file hash idempotency
- file-atomic import behavior
- scheduled refresh
- dashboard snapshot rebuilds
- operational status visibility

The platform should now be treated as an internal retail intelligence product.

## 7. Current Priorities

1. Complete Data Center as a read-only operational status page.
2. Stabilize import and snapshot observability.
3. Improve performance without changing business metrics.
4. Add management-facing insight only after data reliability is established.

## 8. Non-Goals

Unless explicitly approved, do not:

- replace Flask with another framework
- replace SQLite without a proven need
- duplicate existing importers
- redesign all dashboards at once
- move SQL into routes or templates
- alter business metrics during UI work
- add write actions to Data Center

## 9. Source of Truth Priority

When information conflicts, prefer:

1. Current source code
2. Current SQLite schema and real query results
3. Project resource files
4. Sprint history
5. Earlier chat descriptions
