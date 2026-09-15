#!/usr/bin/python3
"""Pull verified immutable images sequentially; never execute a floating tag."""
import json, pathlib, subprocess
root = pathlib.Path(__file__).resolve().parent
for name, image in json.loads((root / 'images.lock.json').read_text()).items():
    print(f'Pulling {name}', flush=True)
    subprocess.run(['podman', '--cgroup-manager=systemd', 'pull', '--authfile', str(root / 'registry-anonymous.json'), image], check=True)
