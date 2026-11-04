# Inventory recovery fixture

This second trusted adapter has a different schema and behavior from the document fixture:

- Six products with nested `specs/` attachments, two warehouses and twelve stock relationships.
- Authenticated `/inventory?q=SKU`, `/download/ID` and `/export` CSV aggregation.
- SQL assertions check product/warehouse cardinality, twelve relationships and total quantity 315.
- Every specification is checked against its stored SHA-256, API downloads inspect all six, and Chromium verifies search, one specification download and the full CSV export.

Authentication and the small bounded HTTP handler are shared with the document fixture. The adapter owns its schema, seeding, queries, export behavior, UI, smoke test and probe. Both use the same core bundle, restore, generic checker, SQLite, cleanup and report implementation.

Build both images with `python3 scripts/prepare-images.py` from the repository root. See [operations](../../docs/OPERATIONS.zh-TW.md) for backup and configured run commands. Serving never reseeds or repairs missing files. This is synthetic test software, not a production inventory or authentication service.
