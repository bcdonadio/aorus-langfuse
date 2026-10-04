# Dependency provenance

Deployment pins are in `images.lock.json` and each root-level Quadlet. Image
pulls use SHA-256 content addresses; Podman verifies manifests and layer content.
The current pins were resolved on 2026-10-03 from official release metadata
and registry manifests. The Collector pin selects the published amd64 image;
the release has no unsuffixed multi-architecture manifest in either registry.

| Component | Release | Primary source |
| --- | --- | --- |
| Langfuse web/worker | 4.50.0 | https://github.com/langfuse/langfuse/releases/tag/v4.50.0 |
| PostgreSQL | 18.6 | https://www.postgresql.org/versions.json |
| ClickHouse | 26.9.9.28 | https://github.com/ClickHouse/ClickHouse/releases/tag/v26.9.9.28-stable |
| Redis | 8.10.2 | https://github.com/redis/redis/releases/tag/8.10.2 |
| Collector Contrib | 0.162.0 | https://github.com/open-telemetry/opentelemetry-collector-releases/releases/tag/v0.162.0 |
| Loki | 3.7.8 | https://github.com/grafana/loki/releases/tag/v3.7.8 |
| Prometheus | 3.15.0 | https://github.com/prometheus/prometheus/releases/tag/v3.15.0 |
| Grafana | 13.2.3 | https://github.com/grafana/grafana/releases/tag/v13.2.3 |
| MinIO | Chainguard immutable build | https://images.chainguard.dev/directory/image/minio/overview |

The exact Chainguard MinIO digest in the lock file was executed with `--version`
in a network-disabled bounded container. It reports
`RELEASE.2026-09-22T19-25-18Z`, commit
`df34868a88cc8c396807e04a7e220810b321bdaa`, Go `1.27.1`. This is runtime evidence
of the embedded version, not an inference from the image date.

The user approved an explicit container-image exception to mandatory Socket
package scoring after Socket's OCI lookup returned an unsupported/server-error
response. No successful image vulnerability scan is claimed. A digest verifies
content identity, not absence of vulnerabilities. No scanner was downloaded or
installed solely to produce an unsupported claim.

## Codex transcript plugin

- npm: `@langfuse/codex-observability-plugin@0.4.0`
- Source tag: `v0.4.0`
- Source commit: `f4be3a47ac2c9c43721223a8f2e5d13f12e676c7`
- SHA-512: `sha512-f8klk8hDWQqSg+Vt3bCHunmhlK1+jU1itGiH2ewPIIjw+wUUfGquslSa8SRvxQ/Q2f5TiERdYScCTRgzHlnB/w==`
- Published npm provenance: https://registry.npmjs.org/-/npm/v1/attestations/@langfuse%2fcodex-observability-plugin@0.4.0
- Source: https://github.com/langfuse/codex-observability-plugin/tree/v0.4.0

Socket's exact-package deep score returned overall 74, maintenance 93, supply
chain 81, and vulnerability 100. The only alert was `unpopularPackage`
(middle severity, quality); no vulnerability alerts were reported. Its dependency
count was zero because
the published artifact bundles runtime dependencies; that is not evidence that
the embedded SDK has no dependencies. The installer verifies the tarball's
SHA-512, restricts extraction to the four expected regular files, and does not
run npm lifecycle scripts. The bundle reads local Codex transcripts and sends
captured records to the explicitly configured local Langfuse destination.

Host-provided Podman, systemd, Python, Git, and Node are reused. No CI actions or
floating downloaded tools are introduced.
