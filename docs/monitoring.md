# Monitoring (Prometheus, Alertmanager, Grafana)

| Part | What it does | Reachable |
|---|---|---|
| Prometheus | collects and stores the metrics, evaluates the alert rules | inside the cluster only |
| Alertmanager | groups alerts, silences them, sends notifications | inside the cluster only, used through Grafana |
| Grafana | dashboards and the view of alerts | <https://grafana.k8s.biatec.io> |
| node-exporter, kube-state-metrics | metrics of the servers and of the Kubernetes objects | inside the cluster only |

Metrics are kept for 15 days (at most 40 GB).

## Logging in to Grafana

User `admin`. The password was generated on the first installation and exists only in the
cluster. Read it on a control-plane server, as root:

```bash
kubectl --kubeconfig /etc/kubernetes/admin.conf -n monitoring get secret monitoring-grafana \
  -o jsonpath='{.data.admin-password}' | base64 -d; echo
```

The login page is reachable from the internet. Do not replace the password with a weak one; if
you change it in the web interface, the secret above no longer shows the valid password.

Further users are created in Grafana under *Administration > Users*.

## What is collected

- Servers: CPU, memory, disks, filesystems, network (node-exporter on every node).
- Kubernetes: API server, kubelet and containers (CPU, memory, restarts), state of deployments,
  pods, volumes, jobs (kube-state-metrics), cluster DNS.
- The monitoring stack itself.

Not collected: etcd, scheduler and controller manager. kubeadm exposes their metrics on
`127.0.0.1` of the control-plane nodes only. etcd health is covered by the daily health check.

Dashboards for all of the above come with the installation (*Dashboards* in Grafana, names
starting with "Kubernetes /" and "Node Exporter /").

## Alerts

The standard alert rules of the `kube-prometheus-stack` project are active (node down, disk
filling up, pod crash-looping, certificate expiring, volume full, ...). See them in Grafana
under *Alerting > Alert rules*; firing alerts and silences are under *Alerting > Alert groups*
(choose the Alertmanager named `Alertmanager`).

The alert `Watchdog` fires always, by design: it proves that the chain works.

**Notifications are not sent anywhere yet.** Tell the agent where alerts should go (e-mail,
Slack, Telegram, a webhook, ...). The credentials for that become a repository secret, like the
Cloudflare token.

Monitoring runs on the cluster it watches. When the only server is down, nothing can alert;
the daily `Health check` workflow, which runs on GitHub, is the outside view.

## Metrics of your own applications

Prometheus picks up `ServiceMonitor`, `PodMonitor` and `PrometheusRule` objects from every
namespace. Two things are needed per application namespace:

1. A `ServiceMonitor` (or `PodMonitor`) in the application's namespace pointing at its metrics
   port.
2. Network access for Prometheus, because namespaces are closed to each other: ask the agent to
   add an entry to `network_allow` in `platform/network.yml`:

   ```yaml
   - to: my-app
     from: monitoring
     ports: [9090]   # the metrics port
   ```

   Without it the target shows as down in Prometheus (the connection times out).

## How it is set up

| Part | Where |
|---|---|
| Helm release `monitoring` (chart `kube-prometheus-stack`), namespace `monitoring` | `platform/releases.yml`, `platform/values/monitoring.yaml` |
| Public name of Grafana | `grafana_fqdn` in `inventory/production/group_vars/all.yml` |
| Web access from the internet | `monitoring` in `network_web`, `platform/network.yml` |
| Prometheus may read the DNS metrics | `network_allow` in `platform/network.yml` |
| Certificate | Let's Encrypt through cert-manager, secret `grafana-tls` |
| Storage | Longhorn volumes: Prometheus 50 GiB, Grafana 5 GiB, Alertmanager 2 GiB |

The DNS record for the Grafana name must point at the load balancer, like every other hostname
served by the cluster.

To look at Prometheus or Alertmanager directly (debugging), forward a port from a machine with
cluster access, for example
`kubectl -n monitoring port-forward svc/monitoring-kube-prometheus-prometheus 9090`.
