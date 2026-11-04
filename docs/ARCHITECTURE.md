# Execution and recovery architecture

```mermaid
flowchart LR
    Config[Versioned config] --> Plan[Offline plan + source validation]
    Bundle[Manifest + dump + uploads] --> Plan
    Plan --> Doctor[Read-only environment doctor]
    Doctor --> Runner[Account-locked executor]
    Runner <--> State[(SQLite attempts + intents + evidence)]
    Runner --> Network[Fresh internal Docker network]
    Network --> DB[PostgreSQL 17]
    Network --> App[Trusted document or inventory adapter]
    App --> Checks[SQL / files / relations / HTTP / Chromium]
    Checks --> Report[JSON + HTML + browser recording]
    Report --> Notify[Opt-in redacted failure event]
    Runner --> Cleanup[ID + ownership reconciliation]
    Cleanup --> State
    State --> Retry[New attempt after cleanup]
    Retry --> Runner
```

Backups never mount production paths into containers. The source bundle is copied into private staging and revalidated before restore. The database checker uses a separate read-only role. All application and browser operations use the internal network; image preparation happens earlier.

On an uncatchable crash, the next invocation reads pending attempts, discovers owned Docker IDs by label, verifies ownership and removes only those resources. Historical evidence remains inconclusive or failed; a retry cannot overwrite it with a later success.
