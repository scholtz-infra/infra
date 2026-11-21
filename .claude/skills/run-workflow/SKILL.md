---
name: run-workflow
description: Dispatch a GitHub Actions workflow of this infra repo (site, platform, os-patch, k8s-upgrade, health check), supervise it to the end and report the result. Use whenever something has to be executed on the servers.
---

# Run and supervise a workflow

Servers are only changed through the `Run playbook` workflow (`.github/workflows/ansible.yml`).
It runs from `main`, so the change must be merged first.

1. Preconditions: `gh auth status` works; the relevant PR is merged; no other run is in progress
   (`gh run list --workflow ansible.yml --limit 5`). For disruptive playbooks (`os-patch`,
   `k8s-upgrade`) the last `Health check` must be green, unless this run is the fix.
2. Dispatch:
   ```bash
   gh workflow run ansible.yml -f playbook=<site|platform|os-patch|k8s-upgrade> [-f limit=<hosts>] [-f check=true]
   gh workflow run health.yml          # read-only, no approval
   ```
3. Find the run: `gh run list --workflow ansible.yml --limit 1 --json databaseId,status,url`.
   Give the owner the URL and say that it is **waiting for their approval** (`production`
   environment). Never approve it yourself.
4. Supervise: `gh run watch <id> --exit-status` (run it in the background for long playbooks).
5. On failure: `gh run view <id> --log-failed`; the full log is the `ansible-log` artifact
   (`gh run download <id> -n ansible-log`). Find the first failed task, explain the cause, and fix
   it with a PR. Playbooks are idempotent, re-running after a fix is safe.
6. After a successful change run `health.yml` and read its summary
   (`gh run view <id> --log` or the run page) to confirm the cluster is healthy.
7. Report: what ran, run URL, changed/failed counts from the play recap, health result, and
   anything left to do.
