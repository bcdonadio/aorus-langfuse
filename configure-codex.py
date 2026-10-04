#!/usr/bin/env python3
"""Install and configure pinned Langfuse observability for Codex."""

from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
from datetime import datetime, timezone
from urllib.request import Request, urlopen


PACKAGE = "@langfuse/codex-observability-plugin"
VERSION = "0.4.0"
TARBALL_URL = (
    "https://registry.npmjs.org/@langfuse/codex-observability-plugin/-/"
    "codex-observability-plugin-0.4.0.tgz"
)
INTEGRITY = "sha512-f8klk8hDWQqSg+Vt3bCHunmhlK1+jU1itGiH2ewPIIjw+wUUfGquslSa8SRvxQ/Q2f5TiERdYScCTRgzHlnB/w=="
SOURCE_TAG = "v0.4.0"
SOURCE_COMMIT = "f4be3a47ac2c9c43721223a8f2e5d13f12e676c7"
MARKETPLACE = "langfuse-local"
PLUGIN_NAME = "tracing"
BEGIN = "# BEGIN managed Langfuse Codex observability"
END = "# END managed Langfuse Codex observability"
MAX_PLUGIN_CHARS = 9_007_199_254_740_991
MAX_NATIVE_TOOL_BYTES = 9_223_372_036_854_775_807


def atomic_write(path: Path, data: bytes, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.close(fd)
        except OSError:
            pass
        Path(temporary).unlink(missing_ok=True)
        raise


def download_verified() -> bytes:
    request = Request(TARBALL_URL, headers={"User-Agent": "configure-codex-langfuse/1"})
    with urlopen(request, timeout=60) as response:
        payload = response.read()
    digest = "sha512-" + base64.b64encode(hashlib.sha512(payload).digest()).decode("ascii")
    if digest != INTEGRITY:
        raise RuntimeError("pinned npm tarball integrity verification failed")
    return payload


def validate_archive(archive: tarfile.TarFile) -> list[tarfile.TarInfo]:
    allowed = {
        "package/package.json",
        "package/.codex-plugin/plugin.json",
        "package/hooks/hooks.json",
        "package/dist/index.mjs",
    }
    members = archive.getmembers()
    names = {member.name.rstrip("/") for member in members if member.isfile()}
    if names != allowed:
        raise RuntimeError(f"unexpected npm package contents: {sorted(names ^ allowed)}")
    for member in members:
        parts = Path(member.name).parts
        if member.issym() or member.islnk() or member.isdev() or member.name.startswith("/") or ".." in parts:
            raise RuntimeError(f"unsafe npm archive member: {member.name}")
    return members


def install_marketplace(codex_home: Path, payload: bytes) -> Path:
    root = codex_home / "plugins" / MARKETPLACE
    root.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".langfuse-marketplace.", dir=root.parent))
    try:
        plugin_root = staging / "plugins" / PLUGIN_NAME
        plugin_root.mkdir(parents=True)
        with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as archive:
            members = validate_archive(archive)
            for member in members:
                if not member.isfile():
                    continue
                source = archive.extractfile(member)
                if source is None:
                    raise RuntimeError(f"could not read archive member: {member.name}")
                relative = Path(*Path(member.name).parts[1:])
                destination = plugin_root / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(source.read())
                destination.chmod(0o755 if relative == Path("dist/index.mjs") else 0o644)

        package = json.loads((plugin_root / "package.json").read_text())
        if package.get("name") != PACKAGE or package.get("version") != VERSION:
            raise RuntimeError("verified archive package identity does not match pin")
        manifest = {
            "name": MARKETPLACE,
            "plugins": [{
                "name": PLUGIN_NAME,
                "source": {"source": "local", "path": f"./plugins/{PLUGIN_NAME}"},
            }],
        }
        manifest_path = staging / ".agents" / "plugins" / "marketplace.json"
        manifest_path.parent.mkdir(parents=True)
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
        provenance = {
            "package": PACKAGE,
            "version": VERSION,
            "npm_integrity": INTEGRITY,
            "source_tag": SOURCE_TAG,
            "source_commit": SOURCE_COMMIT,
        }
        (staging / "PROVENANCE.json").write_text(json.dumps(provenance, indent=2) + "\n")
        backup = root.with_name(root.name + ".previous")
        if backup.exists():
            shutil.rmtree(backup)
        if root.exists():
            os.replace(root, backup)
        os.replace(staging, root)
        if backup.exists():
            shutil.rmtree(backup)
        return root
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def managed_config(marketplace_root: Path) -> str:
    quoted_root = json.dumps(str(marketplace_root))
    return f'''{BEGIN}
[otel]
log_user_prompt = true
environment = "local"

[otel.tool_result]
max_bytes = {MAX_NATIVE_TOOL_BYTES}

[otel.exporter.otlp-http]
endpoint = "http://127.0.0.1:4318/v1/logs"
protocol = "binary"

[otel.metrics_exporter.otlp-http]
endpoint = "http://127.0.0.1:4318/v1/metrics"
protocol = "binary"

[otel.trace_exporter.otlp-http]
endpoint = "http://127.0.0.1:4318/v1/traces"
protocol = "binary"

[marketplaces.{MARKETPLACE}]
source_type = "local"
source = {quoted_root}

[plugins."{PLUGIN_NAME}@{MARKETPLACE}"]
enabled = true
{END}
'''


def update_config(path: Path, block: str) -> bool:
    original = path.read_text() if path.exists() else ""
    if (BEGIN in original) != (END in original):
        raise RuntimeError(f"incomplete managed block in {path}")
    if BEGIN in original:
        before, remainder = original.split(BEGIN, 1)
        _, after = remainder.split(END, 1)
        updated = before.rstrip() + "\n\n" + block.rstrip() + after
    else:
        updated = original.rstrip() + ("\n\n" if original.strip() else "") + block
    if updated == original:
        return False
    if path.exists():
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup = path.with_name(f"{path.name}.before-langfuse.{stamp}")
        shutil.copy2(path, backup)
        backup.chmod(stat.S_IMODE(path.stat().st_mode))
    atomic_write(path, updated.encode(), 0o600)
    return True


def write_langfuse_config(path: Path, credentials_path: Path) -> None:
    credentials = json.loads(credentials_path.read_text())
    public_key = credentials.get("langfuse_public_key")
    secret_key = credentials.get("langfuse_secret_key")
    if not isinstance(public_key, str) or not public_key or not isinstance(secret_key, str) or not secret_key:
        raise RuntimeError("credentials file lacks non-empty langfuse_public_key/langfuse_secret_key")
    config = {
        "enabled": True,
        "public_key": public_key,
        "secret_key": secret_key,
        "base_url": "http://127.0.0.1:3000",
        "max_chars": MAX_PLUGIN_CHARS,
        "debug": False,
        "fail_on_error": False,
    }
    atomic_write(path, (json.dumps(config, indent=2) + "\n").encode(), 0o600)


def register_plugin(codex_home: Path, codex_bin: Path) -> None:
    if not codex_bin.is_file() or not os.access(codex_bin, os.X_OK):
        raise RuntimeError(f"Codex executable is unavailable: {codex_bin}")
    environment = os.environ.copy()
    environment["CODEX_HOME"] = str(codex_home)
    result = subprocess.run(
        [str(codex_bin), "plugin", "add", f"{PLUGIN_NAME}@{MARKETPLACE}", "--json"],
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=60,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or "unknown error"
        raise RuntimeError(f"Codex plugin registration failed: {detail}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--credentials", type=Path, default=Path.home() / ".config/aorus-langfuse/credentials.json")
    parser.add_argument("--codex-home", type=Path, default=Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")))
    parser.add_argument("--codex-bin", type=Path, default=Path("/opt/codex-desktop/resources/codex"))
    args = parser.parse_args()
    credentials = args.credentials.expanduser().resolve()
    if not credentials.is_file():
        parser.error(f"credentials file not found: {credentials}")
    codex_home = args.codex_home.expanduser().resolve()
    codex_home.mkdir(parents=True, exist_ok=True)
    marketplace_root = install_marketplace(codex_home, download_verified())
    write_langfuse_config(codex_home / "langfuse.json", credentials)
    changed = update_config(codex_home / "config.toml", managed_config(marketplace_root))
    register_plugin(codex_home, args.codex_bin.expanduser().resolve())
    print(json.dumps({
        "configured": True,
        "config_changed": changed,
        "plugin": f"{PLUGIN_NAME}@{MARKETPLACE}",
        "version": VERSION,
        "integrity_verified": True,
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
