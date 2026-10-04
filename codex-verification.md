# Codex observability verification

The Codex integration is pinned to `@langfuse/codex-observability-plugin@0.4.0`
from source tag `v0.4.0` at commit
`f4be3a47ac2c9c43721223a8f2e5d13f12e676c7`. Its npm tarball must verify as:

```text
sha512-f8klk8hDWQqSg+Vt3bCHunmhlK1+jU1itGiH2ewPIIjw+wUUfGquslSa8SRvxQ/Q2f5TiERdYScCTRgzHlnB/w==
```

Run the idempotent installer after the credential bootstrap has created the
credential file:

```bash
./configure-codex.py --credentials ~/.config/aorus-langfuse/credentials.json
```

The script never prints credentials. It installs a fixed local marketplace,
writes `~/.codex/langfuse.json` with mode `0600`, registers the plugin through
the local Codex executable, backs up a changed Codex
configuration, and adds a delimited managed block without changing existing
hooks or unrelated settings. It configures plugin transcript capture to the
JavaScript maximum safe integer (`9007199254740991`) and native Codex tool-result
capture to the maximum signed TOML integer (`9223372036854775807`). Native logs,
metrics, and traces use
binary OTLP/HTTP at `127.0.0.1:4318`.

## Static checks

```bash
python3 -m py_compile configure-codex.py
python3 -c 'import tomllib; tomllib.load(open("/home/bcdonadio/.codex/config.toml", "rb"))'
/opt/codex-desktop/resources/codex plugin marketplace list --json
/opt/codex-desktop/resources/codex plugin list --json
stat -c '%a %n' ~/.codex/langfuse.json
```

Expected results include marketplace `langfuse-local`, enabled plugin
`tracing@langfuse-local`, and mode `600` for the credential
derived configuration.

## Fresh-process integration check

Do not restart the active Codex GUI or its app server. After the Langfuse stack
is healthy, start a separate fresh Codex CLI process and submit a unique prompt
that invokes a tool returning a unique long sentinel. Let the turn stop so the
plugin's `Stop` hook uploads the completed rollout.

Verify in Langfuse that the resulting trace contains the exact, unredacted
prompt, the model generation, tool call arguments, and the complete tool result
including the sentinel's final bytes. Verify collector evidence for all three
native Codex signals: one request each to `/v1/logs`, `/v1/metrics`, and
`/v1/traces`. Record the trace ID, fresh Codex process ID, UTC timestamp, and
collector evidence below.

### Runtime evidence

The September 15 evidence below used plugin 0.3.0.

- Status: passed against Langfuse 4.36.0 in `events_only` mode
- Session: `01a0a2a9-bd7a-7a90-89bb-9c5f04b4a480`
- UTC timestamp: `2026-09-15T01:23:48Z` through `2026-09-15T01:24:41Z`
- Marker: `CODEX_LF_20260915T012347Z_4572`
- Plugin hook sidecar trace IDs: `01a0a2a9-be80-7fd1-8b98-45a4a0e412eb`,
  `01a0a2aa-751b-7ef0-87d1-15794f411ecd`
- Full-content sentinel: passed. ClickHouse `events_full` stored the `exec`
  event with output length `25319`; the begin marker was at position `58` and
  the end marker at position `25272`, after all 25,000 payload characters.
- Two-turn continuity: passed. Both turn prompts and both completion markers
  were stored with the same Codex session ID.
- Plugin observations: passed. Langfuse stored `AGENT`, `GENERATION`, and `TOOL`
  events with parent/child span relationships. Direct `/api/public/traces` is
  intentionally unavailable in Langfuse v4 `events_only` mode, so evidence was
  read from the canonical `events_full` store.
- Native logs: passed. Loki stored exact `codex.user_prompt` records for both
  turns and the `codex.tool_result` record with its complete output in labels.
- Native metrics: passed. Prometheus stored Codex series including
  `codex_process_start_total{job="codex_exec",originator="codex_exec"}=2` for
  the two fresh CLI processes, plus Codex startup and runtime series.
- Native traces: passed. Langfuse `events_full` contains the native and plugin
  trace/event records associated with the session.
- Process bound: each CLI invocation used a 180-second timeout; both exited 0.
- Multi-agent: disabled for both invocations; no subagents were created.
- Repository writes by test agent: none.

### 2026-10-03 plugin 0.4.0 upgrade

- SHA-512, exact four-file archive, package identity, and published source
  provenance checked before installation. Socket findings are in
  `DEPENDENCIES.md`.
- Fresh CLI session: `01a1037f-4daf-7731-9934-faaa6d720dc0`; marker:
  `CODEX_LF_UPGRADE_20261003_2042Z`.
- One CLI process, multi-agent disabled, 180-second timeout, exit 0; no repository
  edits. The marker is an identifier, not the process start timestamp.
- Trace: `c8382457596d4154ee7900a1f57a4fb1`. Langfuse `events_full` contained
  AGENT, GENERATION, and TOOL records with `service_name=codex`.
- The TOOL output has 25,453 characters, including exactly 25,000 consecutive
  `X` characters and the complete begin/end markers.
- Loki contains the fresh session's native `codex.user_prompt` and
  `codex.tool_result`, with the full sentinel in the output attribute. Native
  event bodies can be empty; query the event attributes rather than only lines.
- The existing local native tool-result limit, `9007199254740991`, was preserved
  after the installer regenerated its managed block. It exceeds the tested
  payload size. Unrelated hooks/settings and the active desktop were preserved.
