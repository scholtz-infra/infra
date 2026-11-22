#!/usr/bin/env python3
"""Removes server addresses and the SSH port from files before they leave the runner.

GitHub masks secrets in the live log only. Log artifacts, the health report and the alert issue
are written by us, so they are cleaned here. Reads the NODE_IPS and SSH_PORT environment
variables (same format as the secrets, see docs/secrets.md).

Usage: redact.py <file or directory>...
"""
import os
import re
import sys
from pathlib import Path


def parse_node_ips(text):
    """'node1 203.0.113.10\\nnode2 203.0.113.11' -> {'node1': '203.0.113.10', ...}"""
    tokens = text.split()
    return dict(zip(tokens[0::2], tokens[1::2]))


def redact(text, node_ips, ssh_port):
    # longest address first, so that 10.0.0.1 never eats the start of 10.0.0.11
    for name, address in sorted(node_ips.items(), key=lambda item: -len(item[1])):
        text = re.sub(rf"(?<![\d.]){re.escape(address)}(?![\d])", f"[{name}-address]", text)
    if ssh_port:
        text = re.sub(rf"(?<!\d){re.escape(ssh_port)}(?!\d)", "***", text)
    return text


def redact_file(path, node_ips, ssh_port):
    original = path.read_text(encoding="utf-8", errors="surrogateescape")
    cleaned = redact(original, node_ips, ssh_port)
    if cleaned != original:
        path.write_text(cleaned, encoding="utf-8", errors="surrogateescape")


def main():
    node_ips = parse_node_ips(os.environ.get("NODE_IPS", ""))
    ssh_port = os.environ.get("SSH_PORT", "").strip()
    for argument in sys.argv[1:]:
        root = Path(argument)
        files = [p for p in root.rglob("*") if p.is_file()] if root.is_dir() else [root]
        for path in files:
            redact_file(path, node_ips, ssh_port)


if __name__ == "__main__":
    main()
