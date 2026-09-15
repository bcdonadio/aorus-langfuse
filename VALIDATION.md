# Deployment validation

Validated on Aorus on 2026-09-14/15 using the immutable images in
`images.lock.json`. This document records observed behavior, not a guarantee
against queue exhaustion or arbitrary oversized payloads.

- All ten containers started under user systemd.
- Every payload and supervisor was checked beneath `langfuse.slice`.
- Kernel limits: CPU `600000 100000`, memory.high `12884901888`, memory.max
  `17179869184`, memory.swap.max `2147483648`, pids.max `4096`, CPU/IO weights 25.
- Published endpoints bind to `127.0.0.1` only: 3000, 3001, 4318, 9000.
- Runtime image digests match the committed lock and Quadlets.
- Writable application mounts remain under `/mnt/aorus/langfuse`.
- Langfuse reports version 4.36.0; Grafana reports 13.2.1.
- S3 bootstrap created the required bucket and rerunning it confirmed existence.
- Collector, Loki, and Prometheus native configuration validators passed.
- Quadlet generation, generated systemd unit verification, Python compilation,
  dashboard JSON parsing, Git whitespace checks, and credential absence checks
  passed.
- A 27,042-byte synthetic log survived without truncation. Two delta metric
  points (2 and 3) produced a cumulative value of 5. Native OTLP spans reached
  Langfuse's v4 observations API.
- Controlled outage marker `aorus-recovery-490aae461f6c5632` was queued while Loki
  was stopped, survived a Collector restart, and appeared after Loki recovered.
- The filesystem gauge producer reports actual XFS free/used capacity using
  `statvfs`; it does not need to inspect database contents.

## Final target restart

A full `systemctl --user restart langfuse.target` completed successfully.
The final telemetry marker was `telemetry-verify-9e9e566e359bf2a98c9015da`:
27,042-byte log exact, delta sum 5, trace
`fed4c77397914126b13dd64caa36eb59` found through v2 observations, and filesystem
metrics present. The disk timer is active and its service completed successfully.
Loki's first readiness probe deliberately waits 15 seconds; the stack verifier
allows a bounded readiness period after restart.

## Real Codex capture

See `codex-verification.md` for the complete live two-turn evidence. Both fresh
Codex processes exited successfully, and the full 25,000-character tool payload
was present in the recorded transcript, Langfuse observations, and native Loki
logs. Raw prompts and Codex metrics were also verified.

The active desktop/app-server was deliberately not restarted. New CLI processes
were proven to load the configuration; an already-running process may require a
normal restart to adopt it. No test Codex process is left running.

## Corrections discovered by live validation

- ClickHouse's background pool cannot be reduced below its mutation thresholds.
  The deployment uses 16 background workers and a bounded 512-thread global pool;
  the first 128-thread pool stalled real query work despite `/ping` succeeding.
- Langfuse's health probes use container service addresses. Listening on a
  container interface made loopback probes fail even when the host-published UI
  worked.
- Langfuse v4 `events_only` ingestion is queried through observations rather than
  the legacy trace API, which intentionally returns 404 for these projects.
- The Collector hostmetrics filesystem scraper did not discover the bind-mounted
  directory on this host. The bounded systemd gauge producer replaces it.
- Persistent Collector queues now retry indefinitely within their bounded
  capacity, rather than discarding batches after a ten-minute outage.
