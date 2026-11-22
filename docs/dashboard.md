# Dashboard (Headlamp)

A web view of the cluster: workloads, pods and their logs, storage, nodes, events.

Address: <https://dashboard.k8s.biatec.io>

## Logging in

Headlamp has no users or passwords of its own. It asks for a Kubernetes token and then shows and
allows exactly what that token may do. The login page is reachable from the internet; without a
valid token it gives access to nothing.

Create a token on a control-plane server, as root:

```bash
kubectl --kubeconfig /etc/kubernetes/admin.conf -n headlamp create token headlamp-admin --duration=8h
```

Paste the output into the login page. The token stops working after the given duration; create
a new one when you need the dashboard again.

Tokens of `headlamp-admin` have **full access to the cluster** (`cluster-admin`). Treat one like
a root password: do not store it, do not send it to anyone, and keep the duration short.

## Read-only or limited access for someone else

Ask the agent to add a service account bound to the `view` role (whole cluster or a single
namespace). A token for it is created the same way, with that account's name.

## How it is set up

| Part | Where |
|---|---|
| Helm release `headlamp`, namespace `headlamp` | `platform/releases.yml`, `platform/values/headlamp.yaml` |
| Public name | `dashboard_fqdn` in `inventory/production/group_vars/all.yml` |
| Web access from the internet | `headlamp` in `network_web`, `platform/network.yml` |
| Certificate | Let's Encrypt through cert-manager, secret `headlamp-tls` |

The DNS record for the dashboard name must point at the load balancer, like every other
hostname served by the cluster.
