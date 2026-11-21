---
name: cluster-health
description: Check the state of the servers and the Kubernetes cluster (SMART, RAID, disk space, pending Ubuntu updates, reboot required, certificates, nodes, pods). Use for status questions, before disruptive work, and when a health-alert issue is open.
---

# Cluster health

1. Latest result: `gh run list --workflow health.yml --limit 3` and open issues:
   `gh issue list --label health-alert`.
2. Fresh data: `gh workflow run health.yml`, then `gh run watch <id>`. The Markdown report is in
   the run summary; raw data is the `health` artifact (`gh run download <id> -n health`), one
   `node-<host>.json` per server plus `cluster-nodes.json` and `cluster-pods.txt`.
3. Interpret and act:
   - SMART failure, reallocated/pending sectors, NVMe media errors, degraded RAID: `replace-disk`.
   - Pending updates or reboot required: run `os-patch` (`run-workflow`).
   - Certificate under 30 days: a Kubernetes upgrade renews them; otherwise propose a
     `kubeadm certs renew all` playbook.
   - Node not Ready / unhealthy pods: download the artifact, identify the node or workload, then
     decide whether it is infrastructure (fix here) or an application (tell the owner).
   - Server unreachable: check the Hetzner status page and ask the owner to look at Robot.
4. Close the `health-alert` issue only after a green run, with a comment saying what fixed it.

The checks live in `scripts/node_health.py` (thresholds at the top) and
`scripts/health_report.py`; tests in `tests/`.
