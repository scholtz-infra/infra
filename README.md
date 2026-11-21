# AI assisted infrastructure

Kubernetes on Hetzner dedicated servers, managed by an AI agent and overseen by a human.

- Vanilla Kubernetes (kubeadm, stacked etcd) deployed with Ansible, control plane and workloads on
  the same servers, built to grow from one server to a highly available cluster.
- Cilium networking (WireGuard encrypted), Longhorn and local-path storage.
- Rolling Ubuntu patching and Kubernetes upgrades, daily SMART/RAID/cluster health check.
- Everything is changed by pull request and executed by GitHub Actions with an approval step.

| Read | For |
|---|---|
| [docs/setup.md](docs/setup.md) | First-time setup: what you have to do by hand |
| [docs/secrets.md](docs/secrets.md) | Which GitHub secrets exist and what they look like |
| [AGENTS.md](AGENTS.md) | How the repo works, rules for the agent, workflows, roadmap |
| [docs/app-deploy.md](docs/app-deploy.md) | Deploying an application from its own repository |

Where to look to follow what is happening: merged pull requests (what changed), the
[Actions](../../actions) tab (what ran on the servers, with logs), and issues labelled
`health-alert` (what is broken).
