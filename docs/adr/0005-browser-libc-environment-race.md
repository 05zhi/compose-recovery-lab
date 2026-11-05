# ADR 0005: Require repaired libc environment-array lifetime for browser probes

Status: accepted, 2026-11-05. Supersedes the Python base-image choice in ADR 0001; the PostgreSQL image is unchanged.

## Evidence and decision

The reproducible application-check failure occurs during Chromium launch, before a page or recording exists. Kernel tracing identified a user-mode general-protection fault in `ThreadPoolForeg`. A subsequent register capture and disassembly of the exact image resolved the instruction to glibc 2.36 `getenv+0x9d`, dereferencing an invalid environment-entry pointer while looking up the static `LANGUAGE` key.

Chromium 145.0.7632.6 contains a late `FC_FONTATIONS` environment mutation during font initialization. Current upstream Chromium explicitly documents the getenv/setenv race and moves that mutation before thread creation. This is a matching source-level path, not a captured stack of the concurrent writer. The local libc concurrency reproducer independently crashes on the old image and passes on glibc 2.41. [Exact browser source](https://chromium.googlesource.com/chromium/src/+/refs/tags/145.0.7632.6/ui/gfx/linux/fontconfig_util.cc), [upstream explanation](https://chromium.googlesource.com/chromium/src/+/main/ui/gfx/linux/fontconfig_util.cc).

Use the digest-pinned Python 3.12.12 slim-trixie base with glibc 2.41, which retains environment arrays across concurrent readers and writers. Build-time checking rejects libc older than 2.41. Both adapters inherit the same base. [glibc bug 15607 and fixing commit](https://sourceware.org/pipermail/glibc-bugs/2025-July/059702.html).

Python 3.12.12, Playwright 1.58.0, Chromium 145.0.7632.6, and Python dependency versions remain unchanged. The Chromium executable SHA-256 is identical before and after. OS libraries change with the Debian base, so both adapters require full restore and negative acceptance, not just a browser launch test.

## Alternatives and consequences

Switching headless-shell to full Chromium still crashed and was rejected. Disabling glibc rseq still crashed; the captured kernel path is a general-protection fault. Increasing memory/PID limits has no supporting evidence: earlier failures had no OOM or limit hits. Retries would mask a failed attempt and are not added.

Pre-populating one environment key would depend on a particular browser initialization path; the upstream libc repair covers the underlying environment-array lifetime problem. Upgrading the browser is a separate change with a larger UI behavior surface. No runtime preload, custom libc patch, host kernel setting, or compiler in the application image is required.

New fixtures must be made with the new trusted image locks. Existing bundles retain their original image identity and are not silently retargeted. The precise exceptions of the two older historical incidents were discarded, so they cannot retrospectively be proved identical to this reproduced fault.

Validation and repeat counts are recorded in [the incident report](../BROWSER_INCIDENT.zh-TW.md). This decision does not promise arbitrary browser versions or platforms are free of unrelated crashes.
