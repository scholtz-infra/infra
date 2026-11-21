---
name: platform-app
description: Add, configure or upgrade an infrastructure application that runs inside the cluster and is owned by this repo (Cilium, Longhorn, Redis, databases, ingress, cert-manager, monitoring), or grant an application repository access to a namespace.
---

# Platform applications

Platform apps are Helm releases listed in `platform/releases.yml`, installed in list order by
`playbooks/platform.yml` with `helm upgrade --install --wait`.

## Add an application (example: Redis)

1. Pick the official or most widely used maintained chart and look up its newest version
   (`helm search repo` or the chart's `index.yaml`). Do not guess versions.
2. Add an entry to `platform_releases` with a `# renovate:` comment above `version` like the
   existing entries.
3. Create `platform/values/<name>.yaml`. It is a Jinja template: inventory variables such as
   `groups['k8s_cluster'] | length` are available, so replica counts can follow the cluster size.
   Keep it minimal, comment every non-default choice.
4. Storage: `longhorn` for data that must survive a server loss, `local-path` when the
   application replicates itself and needs raw disk speed (pods are then pinned to their node).
5. Secrets (passwords): never in the values file. Add the secret to the `production`
   environment (the owner does this), pass it to the playbook as an environment variable in
   `.github/workflows/ansible.yml`, and create the Kubernetes Secret from Ansible with
   `no_log: true`; reference it from the chart via its `existingSecret` option.
6. Network: the new namespace is closed to all other namespaces. Add one `network_allow` entry
   to `platform/network.yml` per namespace that must reach it, limited to the service port. Only
   add what the owner asked for; if a chart's components span several namespaces, list each pair.
7. PR, merge, run `platform` (`run-workflow`), then the health check.
8. Document in the PR how applications reach the service (DNS name, port, secret name).

## Upgrade

Bump `version` (Renovate does this), read the chart's upgrade notes, merge, run `platform`.
Cilium and Longhorn: one minor version at a time.

## Allow traffic between namespaces

Add `{to, from, ports}` to `network_allow` in `platform/network.yml` and run `platform`. Removing
the entry and re-running removes the access. Symptom of a missing entry: connections time out
(packets are dropped, not rejected).

## Expose a namespace to the internet

Add the namespace to `network_web` in `platform/network.yml` and run `platform`. The application
then needs an Ingress with `ingressClassName: cilium` and the annotation
`cert-manager.io/cluster-issuer: letsencrypt` (example in `docs/app-deploy.md`). Symptoms:
HTTP 403 from the ingress = namespace not in `network_web`; certificate stays not Ready =
`kubectl describe challenge` in the app namespace, usually the Cloudflare token does not cover
the zone or `CLOUDFLARE_API_TOKEN` is missing.

## Grant an application repository access

Add `{namespace, repository}` to `platform/tenants.yml`, make sure the owner is in
`github_oidc_allowed_owners`, run `platform`. Details in `docs/app-deploy.md`.
