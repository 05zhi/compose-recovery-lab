# ADR 0004: Durable attempts, bounded checks and trusted adapters

Status: accepted, 2026-11-04.

SQLite WAL with FULL synchronization stores runs, attempts, phases, resource intents, observed IDs, check results and redacted events. The Linux account lock serializes execution. Each retry gets fresh Docker resources and an attempt ID under the same logical run; no partially restored database is resumed. Intent is written before Docker, and label discovery closes the external-create/database-update gap.

JSON journals remain a recovery compatibility path; SQLite owns historical reports, including HTML regeneration. Cleanup and verification outcomes remain independent. Known assertions fail the run, incomplete required evidence cannot pass, and cleanup failures keep a nonzero CLI exit.

Two adapters share PostgreSQL restore, upload extraction, generated Compose isolation, lifecycle tracking, generic checkers and reporting. The document and inventory adapters own their schemas, synthetic data, HTTP semantics and fixed browser workflows. Templates are compiled allowlist entries, not executable plugins. Sources must identify a matching template and immutable image lock.

Custom checks run inside the isolated application container. SQL has a separate SELECT role, read-only transactions, statement timeout and bounded result count/size. HTTP stays on application loopback and does not follow redirects. Attachment paths stay below uploads. These controls constrain trusted-operator configurations; containers and PostgreSQL are not a hostile-code execution sandbox.

Playwright/Chromium is installed before drills, uses bounded tmpfs, and records synthetic UI actions. Video is streamed out before cleanup because Docker archive copy does not reliably expose tmpfs contents. A missing video is reported explicitly, separate from assertion results.

Notifications are opt-in delivery of minimal terminal failure summaries, never raw reports or credentials. Scheduled scripts run configurations sequentially. No scheduler is installed and no external destination is contacted by default.

Tradeoffs: CGO SQLite requires a Linux C toolchain at build time; binary portability is limited by glibc. The local account and Docker operator are trusted. Local history retention and webhook delivery retries are explicit operator tasks. Full VM power-loss/filesystem corruption testing and independent user trials remain separate acceptance activities. Local benchmark campaigns distinguish warmed input files from input-only cache eviction, while both keep images cached.


Browser capacity was raised to 768 MiB / 256 PIDs with an init process after an observed opaque application/browser failure during the first benchmark. This does not establish a unique root cause; later acceptance and repeated benchmark runs validate the revised configuration. The DB remains 512 MiB / 128 PIDs. Unlike the host IPC option discussed in the [official Playwright Docker guide](https://playwright.dev/python/docs/docker), these templates keep namespaces private and use bounded tmpfs with Chromium's disable-dev-shm-usage flag.

A 1 GiB restore reached the original 90-second command ceiling. Bulk pg_dump/pg_restore operations now have a 10-minute ceiling, always constrained by the caller's total deadline. Other Docker operations remain bounded at 90 seconds and cleanup has its independent 60-second budget.
