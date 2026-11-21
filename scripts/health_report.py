#!/usr/bin/env python3
"""Render the files collected by playbooks/health.yml as a Markdown report.

Usage: health_report.py <health-dir> <inventory.json from `ansible-inventory --list`>
Prints Markdown to stdout. Exit code 0 = healthy, 1 = at least one problem found.
"""
import json
import os
import sys


def load_json(path):
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return None


def cluster_problems(nodes, pods_text):
    problems = []
    for node in (nodes or {}).get("items", []):
        name = node["metadata"]["name"]
        ready = next((c["status"] for c in node["status"]["conditions"] if c["type"] == "Ready"), "Unknown")
        if ready != "True":
            problems.append(f"node {name} is not Ready")
        if node["spec"].get("unschedulable"):
            problems.append(f"node {name} is cordoned")
    for line in pods_text.splitlines():
        parts = line.split()
        if len(parts) < 3:
            continue
        namespace, name, phase = parts[:3]
        ready = parts[3] if len(parts) > 3 else ""
        if phase == "Succeeded":
            continue
        if phase != "Running" or "false" in ready:
            problems.append(f"pod {namespace}/{name} is unhealthy (phase {phase}, containers ready: {ready or 'n/a'})")
    return problems


def main():
    health_dir, inventory_path = sys.argv[1], sys.argv[2]
    inventory = load_json(inventory_path) or {}
    hosts = sorted(inventory.get("_meta", {}).get("hostvars", {}))
    problems = []
    rows = []

    for host in hosts:
        data = load_json(os.path.join(health_dir, f"node-{host}.json"))
        if data is None:
            problems.append(f"**{host}**: unreachable or the health probe failed")
            rows.append(f"| {host} | unreachable | | | | | | |")
            continue
        problems += [f"**{host}**: {problem}" for problem in data["problems"]]
        disks = ", ".join(
            f"{d.get('device')} {'ok' if not d['problems'] else 'FAIL'}"
            + (f" {d['temperature_c']}°C" if d.get("temperature_c") else "")
            + (f" wear {d['wear_percent']}%" if d.get("wear_percent") is not None else "")
            for d in data["disks"]
        )
        raid = ", ".join(f"{a['name']} [{a['state']}]" + (f" {a['resync']}" if a["resync"] else "") for a in data["mdraid"])
        etcd = data.get("etcd")
        etcd_text = "-"
        if etcd:
            local = max((m["db_size_mb"] for m in etcd["members"]), default=0)
            age = etcd["snapshot_age_hours"]
            etcd_text = f"{len(etcd['members'])} members, {local} MB, snapshot {'none' if age is None else f'{age:.0f}h ago'}"
        rows.append(
            f"| {host} | {data['os']} / {data['kernel']} | {data['uptime_days']}d "
            f"| {data['pending_updates']}{' (reboot required)' if data['reboot_required'] else ''} "
            f"| {disks or 'none found'} | {raid or 'none'} | {data['certificates_min_days_left'] or '-'} | {etcd_text} |"
        )

    nodes = load_json(os.path.join(health_dir, "cluster-nodes.json"))
    try:
        with open(os.path.join(health_dir, "cluster-pods.txt"), encoding="utf-8") as handle:
            pods_text = handle.read()
    except OSError:
        pods_text = ""
    problems += cluster_problems(nodes, pods_text)

    print("## Infrastructure health\n")
    print(f"**{'PROBLEMS FOUND' if problems else 'All healthy'}**\n")
    for problem in problems:
        print(f"- {problem}")
    print("\n| Server | OS / kernel | Uptime | Pending updates | Disks | RAID | Cert days left | etcd |")
    print("|---|---|---|---|---|---|---|---|")
    print("\n".join(rows))
    if nodes:
        print("\n| Kubernetes node | Version | Ready |")
        print("|---|---|---|")
        for node in nodes.get("items", []):
            ready = next((c["status"] for c in node["status"]["conditions"] if c["type"] == "Ready"), "Unknown")
            print(f"| {node['metadata']['name']} | {node['status']['nodeInfo']['kubeletVersion']} | {ready} |")
    else:
        print("\nNo Kubernetes cluster data (cluster not created yet, or the API is unreachable).")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
