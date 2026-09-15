# Dependency provenance

Deployment pins are in `images.lock.json` and each root-level Quadlet. Image
pulls use SHA-256 content addresses; Podman verifies manifests and layer content.
The pins were resolved on 2026-09-14/15 and pulled successfully on Aorus.

| Component | Release | Primary source |
| --- | --- | --- |
| Langfuse web/worker | 4.36.0 | https://github.com/langfuse/langfuse/releases/tag/v4.36.0 |
| PostgreSQL | 18.6 | https://www.postgresql.org/versions.json |
| ClickHouse | 26.8.4.11 | https://github.com/ClickHouse/ClickHouse/releases/tag/v26.8.4.11-lts |
| Redis | 8.10.1 | https://github.com/redis/redis/releases/tag/8.10.1 |
| Collector Contrib | 0.160.0 | https://github.com/open-telemetry/opentelemetry-collector-releases/releases/tag/v0.160.0 |
| Loki | 3.7.7 | https://github.com/grafana/loki/releases/tag/v3.7.7 |
| Prometheus | 3.14.0 | https://github.com/prometheus/prometheus/releases/tag/v3.14.0 |
| Grafana | 13.2.1 | https://github.com/grafana/grafana/releases/tag/v13.2.1 |
| MinIO | Chainguard immutable build | https://images.chainguard.dev/directory/image/minio/overview |

The exact Chainguard MinIO digest in the lock file was executed with `--version`
in a network-disabled bounded container. It reports
`RELEASE.2026-07-17T12-07-51Z`, commit
`3cd981e1616a18c5679805bf9a1454d794bbee4f`, Go `1.27.1`. This is runtime evidence
of the embedded version, not an inference from the image date.

The user approved an explicit container-image exception to mandatory Socket
package scoring after Socket's OCI lookup returned an unsupported/server-error
response. No successful image vulnerability scan is claimed. A digest verifies
content identity, not absence of vulnerabilities. No scanner was downloaded or
installed solely to produce an unsupported claim.

## Codex transcript plugin

- npm: `@langfuse/codex-observability-plugin@0.3.0`
- Source tag: `v0.3.0`
- Source commit: `e2406316578941a016b290e81121ac750eb47176`
- SHA-512: `sha512-/dKNvHXwRIBPbs7DckLDHY9rZL0O9B4gLGjws+5TglA3ZMTnDLsz/Bp5/XYy329sjKjgx2FI8UIIOJgG+fJ7zA==`
- Published npm provenance: https://registry.npmjs.org/-/npm/v1/attestations/@langfuse%2fcodex-observability-plugin@0.3.0
- Source: https://github.com/langfuse/codex-observability-plugin/tree/v0.3.0

Socket's exact-package deep score returned overall 75, maintenance 89, supply
chain 80, vulnerability 100, and no alerts. Its dependency count was zero because
the published artifact bundles runtime dependencies; that is not evidence that
the embedded SDK has no dependencies. The installer verifies the tarball's
SHA-512, restricts extraction to the four expected regular files, and does not
run npm lifecycle scripts. The bundle reads local Codex transcripts and sends
captured records to the explicitly configured local Langfuse destination.

Host-provided Podman, systemd, Python, Git, and Node are reused. No CI actions or
floating downloaded tools are introduced.
