# AGENTS.md

Instructions for AI agents (and humans) operating this repository. This repo is the single source
of truth for a Kubernetes cluster on Hetzner dedicated servers. The agent manages the
infrastructure; the owner oversees it through pull requests, workflow approvals and run history.

## What is managed here

| Layer | How | Where |
|---|---|---|
| Servers (Ubuntu, Hetzner dedicated) | Ansible roles | `roles/base`, `roles/firewall`, `roles/diskhealth` |
| Kubernetes (vanilla, kubeadm, stacked etcd) | Ansible | `roles/containerd`, `roles/apilb`, `roles/kubernetes`, `playbooks/site.yml` |
| In-cluster platform (Cilium, Longhorn, local-path, later Redis etc.) | Helm, driven by Ansible | `platform/releases.yml`, `platform/values/`, `playbooks/platform.yml` |
| Access for application repositories | GitHub OIDC + RBAC | `platform/tenants.yml`, `docs/app-deploy.md` |
| OS patching, Kubernetes upgrades | Ansible, rolling, one node at a time | `playbooks/os-patch.yml`, `playbooks/k8s-upgrade.yml` |
| Health (SMART, RAID, updates, certificates, nodes, pods) | Daily workflow, opens an issue | `playbooks/health.yml`, `scripts/` |

Applications themselves are **not** deployed from here. They are deployed by GitHub Actions in
their own repositories into the namespace granted in `platform/tenants.yml`.

## Architecture decisions (do not change without asking the owner)

- **Vanilla Kubernetes with kubeadm**, etcd stacked on the control-plane nodes (static pods).
- **Control-plane nodes also run workloads** (taint removed). `control_plane` must contain 1, 3 or
  5 hosts. The cluster starts with **one** server: it is *not* highly available until there are
  three control-plane nodes. Go from 1 straight to 3, never to 2 (etcd quorum).
- **API high availability without a floating IP**: every node runs HAProxy on
  `127.0.0.1:7443` balancing over all API servers. `controlPlaneEndpoint` is
  `api.k8s.internal:7443`, which resolves to 127.0.0.1 on every node.
- **Network**: servers only have public IPs. The host firewall (nftables table `inet hostfw`)
  allows everything between cluster nodes and only `firewall_public_tcp_ports` from the internet.
  Cilium is the CNI, replaces kube-proxy, and encrypts pod traffic between nodes with WireGuard.
- **Storage**: `longhorn` (default StorageClass, replicated across nodes once there are several)
  and `local-path` (node-local disk, fastest, pod is pinned to its node).
- **Secrets** live in GitHub Environment secrets of this repo. Never commit a secret, never print
  one in a workflow log (`no_log: true` in Ansible).
- **Versions are pinned** in `inventory/production/group_vars/all.yml` and
  `platform/releases.yml`, and move forward only by pull request (Renovate opens them).

## Rules for the agent

1. **Every change is a pull request.** Never push to `main`. One topic per PR, and the PR
   description says what will change on the servers and which workflow has to run after merge.
2. **Servers are changed only by GitHub Actions** (`Run playbook` workflow). Do not SSH into
   servers to change anything. Reading state for diagnosis is done with the `Health check`
   workflow; if that is not enough, ask the owner before any direct access.
3. **Supervise what you start.** After dispatching a workflow, watch it to the end, read the log
   on failure, and report the outcome truthfully, including partial failures. Use the
   `run-workflow` skill.
4. **The owner approves.** Runs of `Run playbook` wait for approval on the `production`
   environment. Never try to bypass or self-approve. Say what is waiting for approval and why.
5. **One node at a time.** Anything disruptive (reboot, upgrade, drain) is rolling with
   `serial: 1`. Never run a disruptive action while the health check reports a degraded cluster,
   unless that action is the fix.
6. **Ask before destructive or irreversible actions**: removing a node, `kubeadm reset`, deleting
   volumes or namespaces, anything touching etcd data, wiping a disk.
7. **Latest versions, deliberately.** Keep Ubuntu packages, Kubernetes and platform charts
   current, but Kubernetes moves one minor version at a time, and a version bump is only done
   when the health check is green.
8. Before pushing: `yamllint .`, `ansible-lint`, `ansible-playbook --syntax-check`, and
   `python3 -m unittest discover tests` must pass (the `Lint` workflow runs the same).

## Workflows

| Workflow | Trigger | Environment | Purpose |
|---|---|---|---|
| `Lint` (`lint.yml`) | PR, push to main | none | yamllint, ansible-lint, syntax check, unit tests |
| `Run playbook` (`ansible.yml`) | manual; weekly schedule runs `os-patch` | `production` (approval) | `site`, `platform`, `os-patch`, `k8s-upgrade` |
| `Health check` (`health.yml`) | daily 05:17 UTC, manual | `monitoring` (no approval) | read-only report; opens/updates the `health-alert` issue |

Playbooks:

- `site` - converge all servers: OS baseline, firewall, SMART monitoring, containerd, HAProxy,
  kubeadm; creates the cluster on first run, joins servers added to the inventory, then runs
  `platform`. Idempotent. Must not be limited away from control-plane nodes.
- `platform` - Helm releases, local-path-provisioner, tenant namespaces and RBAC.
- `os-patch` - `apt dist-upgrade` node by node; drain, reboot if required, uncordon.
- `k8s-upgrade` - rolling kubeadm upgrade to `kubernetes_version`.

## How oversight works

- **What changed and why**: merged pull requests.
- **What ran on the servers**: Actions history of `Run playbook`. Each run shows who started it,
  the commit, the play recap in the run summary, and keeps the full log as an artifact for 90 days.
- **Approval**: the `production` environment requires the owner as reviewer.
- **Problems**: the daily health check comments on the open `health-alert` issue.
- The agent reports in the conversation what it dispatched, the run URL and the result.

## Common tasks (skills in `.claude/skills/`)

| Task | Skill |
|---|---|
| Dispatch and supervise a workflow | `run-workflow` |
| Check the state of servers and cluster | `cluster-health` |
| Add a server / scale the cluster | `add-node` |
| Upgrade Kubernetes | `k8s-upgrade` |
| Add or update an infrastructure app (Redis, ...) | `platform-app` |
| Replace a failed disk | `replace-disk` |

## Known gaps / roadmap

Not built yet, in rough priority order. Tell the owner when one of them becomes relevant.

1. **etcd and volume backups off the server** (Hetzner Storage Box or S3). With one server there
   is currently no backup of cluster state.
2. Ingress (Gateway API) and cert-manager, so applications can receive HTTPS traffic.
3. Monitoring and alerting inside the cluster (Prometheus, alert delivery).
4. Redis and other infrastructure applications, on request.
5. Node removal playbook; Ubuntu release upgrades (e.g. 24.04 to 26.04) are manual so far.
6. Optional: move secrets to Azure Key Vault with External Secrets Operator.
