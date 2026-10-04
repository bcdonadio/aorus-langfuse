# Deployment validation

The September 14/15 and September 19 results below used the original immutable
image set (Langfuse 4.36.0), before the October 3 update to `images.lock.json`. This document records observed behavior, not a guarantee
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

## 2026-09-19 boot recovery

The September 17 boot attempted preparation before the XFS automount was
activated. `findmnt` saw the autofs placeholder and rejected it; dependent
start jobs were not retried when preparation later succeeded. The mount check
now enters the directory with `os.scandir` before checking the exact XFS
source, without creating any data first. The existing service timeout bounds
a stalled mount. Ordering and wrong-filesystem rejection were tested with
mocks, and the live mount check passed. A cold reboot was not performed.

Starting `langfuse.target` recovered all ten containers. Both verification
scripts passed, including intact 27,042-byte logs, cumulative metric value 5,
filesystem metrics, and trace `33e86ceb6a756c3554e1f7421ed6e22d`.

## 2026-10-03 upgrade and cleanup

- Updated to the releases recorded in `DEPENDENCIES.md`; all ten running image
  digests match the new lock file and Quadlets.
- Before cleanup or upgrades, stopped all ten containers and backed up the data,
  owner-only configuration, repository, Codex configuration, and plugin to
  `/mnt/bcdtank/enc/infra/donadio/.langfuse-backups/2026-10-03-pre-upgrade`.
  Numeric ownership, ACLs, and extended attributes were preserved. SELinux labels
  are retained separately in `selinux-xattrs.txt` because the ZFS destination root
  cannot adopt the source label; `restore-notes.txt` records restoration steps.
  The final metadata/size/time comparison found no differences.
- Explicitly enabled the worker's v4 cleanup gate after all prerequisite backfills
  finished. `20260701_v4_step_5_drop_pid_tid_sorting_tables` completed at
  `2026-10-03T20:38:42.924Z`; `observations_pid_tid_sorting` is absent.
- After the upgrade, no PostgreSQL schema migration or background migration is
  incomplete or failed. ClickHouse's latest migration is version 50, clean.
- Langfuse health reports 4.50.0; Grafana reports 13.2.3; ClickHouse reports
  26.9.9.28. Collector, Loki, and Prometheus configuration validators passed
  against the new immutable images in bounded, network-disabled containers.
- Python compilation, JSON parsing, lock/Quadlet consistency, eleven generated
  systemd unit checks, and Git whitespace validation passed.
- `verify-stack.py` passed: all ten services, payload/supervisor containment,
  aggregate limits, loopback bindings, backend readiness, and S3 persistence.
- `verify-telemetry.py` passed with marker
  `telemetry-verify-22b8ad500b76c3827fb3ac48`: exact 27,042-byte log,
  cumulative delta value 5, filesystem gauges, and trace
  `0e2a374494146f35c9d35c8a74d489d8`.
- Plugin 0.4.0 passed the fresh-process capture check recorded in
  `codex-verification.md`. The running desktop/app-server was not restarted.

The controlled backend-outage test and cold reboot were not repeated for this
upgrade. Their earlier evidence remains historical.
