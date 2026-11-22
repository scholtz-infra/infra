---
name: maintenance
description: Perform or review the scheduled maintenance of the infrastructure - etcd defragmentation and snapshots, Kubernetes certificate renewal, OS patching, version updates of Kubernetes and platform charts, disk and RAID checks, storage and housekeeping. Use for the monthly maintenance run, for "is anything due?" questions, and after a maintenance or os-patch run was approved.
---

# Scheduled maintenance

## What runs by itself

| What | Where | When |
|---|---|---|
| Security updates (Ubuntu) | unattended-upgrades on each server | daily |
| etcd snapshot + PKI copy (local) | `etcd-snapshot.timer` on control-plane nodes | every 6 h |
| SMART self-tests | smartd | short weekly, long monthly |
| RAID consistency check, SSD trim | Ubuntu timers (`mdcheck`, `fstrim`) | monthly / weekly |
| Certificate renewal for applications | cert-manager | 30 days before expiry |
| Health check, raises `health-alert` issue | `Health check` workflow | daily |
| Version update pull requests | Renovate | continuously |

## What runs on a schedule and changes servers

| Run | Schedule | Does |
|---|---|---|
| `os-patch` | Sunday 03:00 UTC | all package updates, node by node, reboot if required |
| `maintenance` | 1st of the month 04:00 UTC | etcd snapshot + defragmentation when worthwhile, kubeadm certificate renewal within 60 days of expiry, package cache and journal cleanup |

Both appear as a `Run playbook` run and start by themselves. Check their result afterwards
(`gh run list --workflow ansible.yml --limit 5`) and report failures. If the owner has added a
required reviewer to the `production` environment they wait there: remind the owner, never
approve it yourself.

## Monthly routine for the agent

1. `cluster-health`: start from a green health check; resolve or explain every open
   `health-alert` first.
2. Scheduled runs: `gh run list --workflow ansible.yml --limit 10`. Read the result of every
   run since the last routine, fix failures, and run the health check again.
   On a single-node cluster say beforehand that a reboot or a certificate renewal makes the API
   and the applications unavailable for a few minutes.
3. Versions: list open Renovate PRs (`gh pr list --author app/renovate`). Per PR read the
   release notes, then merge and roll out in this order, one at a time with a health check in
   between: Cilium, cert-manager, Longhorn (`platform`), then Kubernetes (`k8s-upgrade` skill).
   Compare `kubernetes_version` with `https://dl.k8s.io/release/stable.txt`; a minor release is
   supported for about a year, do not fall more than one minor behind.
4. Capacity, from the health artifact: filesystems over 70%, etcd database growth month over
   month, NVMe wear, disk temperatures. Raise trends before they become alerts.
5. Things with no automation yet, check by hand and report:
   - Ubuntu release: a new LTS point release (`.1`) is the signal to plan the release upgrade.
   - Longhorn: volumes degraded or with fewer replicas than nodes allow (Longhorn UI or
     `kubectl -n longhorn-system get volumes.longhorn.io`).
   - Hetzner load balancer: every server is a healthy target for both services.
   - Off-server backups: still missing (roadmap item 1); repeat it in the report until done.
6. Report to the owner: what ran, what changed, what is pending their approval, what is due
   next month.

## On demand

`gh workflow run ansible.yml -f playbook=maintenance` runs the same maintenance immediately;
every step checks first whether it is needed, so running it twice is harmless.
Thresholds are variables at the top of `playbooks/maintenance.yml`.
