# AGENTS.md

Instructions for AI agents (and humans) operating this repository. This repo is the single source
of truth for a Kubernetes cluster on Hetzner dedicated servers. The agent manages the
infrastructure; the owner oversees it through pull requests, workflow approvals and run history.

## What is managed here

| Layer | How | Where |
|---|---|---|
| Servers (Ubuntu, Hetzner dedicated) | Ansible roles | `roles/base`, `roles/firewall`, `roles/diskhealth` |
| Data volumes on the servers (`/mnt/...`) | Ansible | `roles/storage`, `inventory/production/host_vars/`, `playbooks/storage.yml`, `docs/storage.md` |
| Kubernetes (vanilla, kubeadm, stacked etcd) | Ansible | `roles/containerd`, `roles/apilb`, `roles/kubernetes`, `playbooks/site.yml` |
| In-cluster platform (Cilium incl. ingress, cert-manager, Longhorn, local-path, Headlamp dashboard, monitoring with Prometheus, Alertmanager and Grafana, Vault, later Redis etc.) | Helm, driven by Ansible | `platform/releases.yml`, `platform/values/`, `playbooks/platform.yml` |
| Application secrets (HashiCorp Vault, synced into Kubernetes Secrets) | Helm; initialised, unsealed and configured by Ansible | `playbooks/tasks/vault-*.yml`, `playbooks/vault-import.yml`, `docs/vault.md` |
| Access for application repositories | GitHub OIDC + RBAC | `platform/tenants.yml`, `docs/app-deploy.md` |
| Network access between namespaces | Cilium / Kubernetes network policies, deny-first | `platform/network.yml` |
| OS patching, Kubernetes upgrades | Ansible, rolling, one node at a time | `playbooks/os-patch.yml`, `playbooks/k8s-upgrade.yml` |
| etcd snapshots and defragmentation, certificate renewal, housekeeping | systemd timer on the nodes, monthly playbook | `roles/etcd`, `playbooks/maintenance.yml` |
| Health (SMART, RAID, updates, certificates, etcd, nodes, pods, Vault seal state) | Daily workflow, opens an issue | `playbooks/health.yml`, `scripts/` |

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
  allows everything between cluster nodes; from the internet only the SSH port; the API and
  ingress ports only from the load balancer.
- **Non-standard ports, kept secret**: API servers listen on `kube_api_port` (not 6443), which
  exists only in the `K8S_API_PORT` secret; the public API address is
  `https://k8s.biatec.io:<K8S_API_PORT>` through the load balancer. sshd listens on a high port
  that exists only in the `SSH_PORT` secret (the owner sets it when preparing a server). Never
  write either number into the repository, a PR, an issue or a log.
  Cilium is the CNI, replaces kube-proxy, and encrypts pod traffic between nodes with WireGuard.
- **Deny-first networking**: every pod only accepts traffic from its own namespace and from the
  nodes; DNS is open. Traffic between namespaces, and from the internet, exists only if it is
  listed in `platform/network.yml`. Never widen the baseline policies in
  `playbooks/templates/network-policies.yaml.j2` without asking the owner. Outgoing traffic is
  not restricted. Tenant namespaces enforce the `baseline` pod security standard.
- **Web traffic**: a Hetzner Cloud Load Balancer (167.235.110.199 / 2a01:4f8:1c1f:690b::1,
  configured by the owner in the Hetzner console) forwards TCP 443 (PROXY protocol on or off, matching `ingress_proxy_protocol`) to
  `ingress_https_port` on every node, or to 443, which the host firewall redirects there for
  the load balancer only (and the API port without PROXY protocol to the API servers), where Cilium's built-in ingress controller (IngressClass `cilium`, classic Ingress
  API) terminates TLS. Port 80 is not served anywhere. DNS records
  point at the load balancer and are managed by the owner in Cloudflare. cert-manager issues Let's Encrypt
  certificates with the Cloudflare DNS-01 challenge (ClusterIssuers `letsencrypt` and
  `letsencrypt-staging`). A namespace only receives web traffic if it is in `network_web`.
- **Storage**: `longhorn` (default StorageClass, replicated across nodes once there are several)
  and `local-path` (node-local disk, fastest, pod is pinned to its node).
- **Server access**: Ansible logs in as the unprivileged user `infra` (key only, no password)
  and becomes root with passwordless sudo. Root login over SSH, with a key or with the
  root password, stays possible as the owner's last resort (`PermitRootLogin yes`,
  `PasswordAuthentication yes`): never switch it off, never use it. The owner
  prepares every new server by hand with `scripts/bootstrap-server.sh` (`docs/server-setup.md`).
- **Server addresses** exist only in the `NODE_IPS` secret (`<inventory name> <IPv4>` per line);
  the inventory holds names and groups only. Like the SSH port, never write a server address
  into the repository, a PR, an issue or a log. Files that leave the runner (log artifact,
  health report) pass through `scripts/redact.py`.
- **Infrastructure secrets** are GitHub repository secrets of this repo, by the owner's choice not split per
  environment (`SSH_PRIVATE_KEY`, `SSH_KNOWN_HOSTS`, `SSH_PORT`, `NODE_IPS`,
  `K8S_API_PORT`, `CLOUDFLARE_API_TOKEN`, `VAULT_UNSEAL_KEY`, `VAULT_ROOT_TOKEN`,
  `VAULT_ADMIN_PASSWORD`; list and formats in `docs/secrets.md`). Never commit a secret, never print one in a workflow log (`no_log: true`
  in Ansible).
- **Application secrets** live in HashiCorp Vault (`docs/vault.md`), in `kv/<namespace>/<name>`,
  and nowhere else: not in a repository (this one is public), not in a ConfigMap, not in a
  workflow log. The Vault Secrets Operator copies them into Kubernetes Secrets and keeps them
  current; a namespace can only read its own path. Vault is unsealed by the playbooks with the
  `VAULT_UNSEAL_KEY` repository secret; the key is not stored in the cluster. The Vault login
  page is public at `vault_fqdn`.
- **Versions are pinned** in `inventory/production/group_vars/all.yml` and
  `platform/releases.yml`, and move forward only by pull request (Renovate opens them).

## Rules for the agent

1. **Every change is a pull request.** Never push to `main`. One topic per PR, and the PR
   description says what will change on the servers and which workflow has to run after merge.
   The agent merges its own pull request when `Lint` is green and the change follows what was
   agreed with the owner in the conversation (rule 4).
2. **Servers are changed only by GitHub Actions** (`Run playbook` workflow). Reading state is
   done with the `Health check` workflow first. When that is not enough, the agent may log in
   directly from the owner's machine **for debugging only**: `ssh <inventory name>` (the owner
   keeps address, port, user `infra` and key in `~/.ssh/config`). On that connection only look:
   read files, logs and command output (`lsblk`, `df`, `journalctl`, `systemctl status`,
   `kubectl get`/`describe`, ...). Never change anything through it: no edits, installs,
   restarts, `kubectl apply`/`delete`. A fix found this way goes through a pull request and a
   workflow like any other change. Say in the conversation when the connection was used and
   for what. Never copy the address or the port from that configuration anywhere.
3. **Supervise what you start.** After dispatching a workflow, watch it to the end, read the log
   on failure, and report the outcome truthfully, including partial failures. Use the
   `run-workflow` skill.
4. **The owner approves in the conversation, not per run.** The owner does not want to review
   every pull request or run: what was agreed in the conversation may be merged and executed
   by the agent without asking again. Anything not discussed, anything that changes an
   architecture decision above, and everything in rule 6 still needs the owner's answer first.
   If the owner later adds a required reviewer to the `production` environment, runs wait
   there: never try to bypass or self-approve that.
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
| `Run playbook` (`ansible.yml`) | manual; weekly schedule runs `os-patch`, monthly `maintenance` | `production` | `site`, `platform`, `os-patch`, `k8s-upgrade`, `maintenance`, `storage`, `vault-import` |
| `Health check` (`health.yml`) | daily 05:17 UTC, manual | none (no approval) | read-only report; opens/updates the `health-alert` issue |

Playbooks:

- `site` - converge all servers: OS baseline, firewall, sshd port, SMART monitoring, containerd, HAProxy,
  kubeadm; creates the cluster on first run, joins servers added to the inventory, then runs
  `platform`. Idempotent. Must not be limited away from control-plane nodes.
- `platform` - Helm releases, local-path-provisioner, tenant namespaces and RBAC, network policies.
- `os-patch` - `apt dist-upgrade` node by node; drain, reboot if required, uncordon.
- `k8s-upgrade` - rolling kubeadm upgrade to `kubernetes_version`.
- `storage` - creates and mounts the data volumes listed per server in `host_vars`
  (`docs/storage.md`); never touches a volume that already exists.
- `maintenance` - etcd snapshot and defragmentation, kubeadm certificate renewal, Vault unseal,
  housekeeping; every step only acts when needed.
- `vault-import` - writes the content of the temporary `VAULT_IMPORT` repository secret into
  Vault (`docs/vault.md`); delete that secret after the run.

## How oversight works

- **What changed and why**: merged pull requests.
- **What ran on the servers**: Actions history of `Run playbook`. Each run shows who started it,
  the commit, the play recap in the run summary, and keeps the full log as an artifact for 90 days.
- **Approval**: given by the owner in the conversation with the agent (rule 4). The
  `production` environment has no required reviewer, so runs, including the scheduled ones,
  start without waiting. The owner can add themselves as reviewer there at any time to get a
  click-to-approve step back.
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
| etcd: status, defragmentation, snapshots, member replacement, restore | `etcd` |
| Monthly maintenance routine, "is anything due?" | `maintenance` |

## Known gaps / roadmap

Not built yet, in rough priority order. Tell the owner when one of them becomes relevant.

1. **etcd, Vault and volume backups off the server** (Hetzner Storage Box or S3). etcd snapshots exist
   only on the control-plane nodes themselves (`/var/backups/etcd`); losing the only server
   loses the cluster state and every secret stored in Vault.
2. Alert delivery: Prometheus, Alertmanager and Grafana run (`docs/monitoring.md`), but
   Alertmanager sends notifications nowhere until the owner names a destination. etcd,
   scheduler and controller manager are not scraped.
3. Redis and other infrastructure applications, on request.
4. Node removal playbook; Ubuntu release upgrades (e.g. 24.04 to 26.04) are manual so far.
5. Vault with three replicas once the cluster has three servers (`docs/vault.md`).
