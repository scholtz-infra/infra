---
name: deploy-app
description: Add, change or move an application that is deployed from the private config repository (manifests in ~/config, applied by the apps playbook), including its secrets in Vault. Use for "deploy this app", "copy this namespace from another cluster", "change this setting or secret of an app", "why does the secret not arrive".
---

# Applications from the config repository

Read `docs/apps.md` and `docs/vault.md` first. The step-by-step guide with the real names lives in
the private repository: `~/config/README.md` and `~/config/docs/`. Keep application details
(names of the owner's services, hostnames, settings) out of this public repository, out of its
pull requests and issues.

## Add or change an application

1. In `~/config`: add the namespace to `namespaces.yml` (`web: true` only if it serves a
   website), put the manifests in `apps/<namespace>/`.
2. Secrets: no value in any manifest, ConfigMap or commit. For each secret add a
   `VaultStaticSecret` (example in `docs/vault.md`) and reference the Kubernetes Secret it
   creates from the workload. Whole configuration files that contain a secret go into Vault as
   one key per file.
3. Write the values into Vault: the owner in the web UI, or you with `vault-import`
   (`docs/vault.md`, "Writing secrets from a workflow"). Never echo a value, never put one in a
   command line; pipe files into `gh secret set VAULT_IMPORT` and delete the file and the
   repository secret afterwards.
4. Ingress: `ingressClassName: cilium`, annotation `cert-manager.io/cluster-issuer: letsencrypt`,
   only HTTPS. The hostname must point at the load balancer (the owner does that in Cloudflare)
   and its zone must be covered by the Cloudflare token.
5. Commit and push `~/config` (it has no pull-request rule and no workflows), run `apps`
   (`run-workflow`), then verify.

## Verify (read-only, `ssh <control-plane node>`)

```bash
sudo kubectl --kubeconfig /etc/kubernetes/admin.conf -n <namespace> get vaultstaticsecret,secret,pods,ingress,certificate
sudo kubectl --kubeconfig /etc/kubernetes/admin.conf -n <namespace> describe vaultstaticsecret <name>
```

Never print a Secret's data.

| Symptom | Cause |
|---|---|
| VaultStaticSecret event "permission denied" | `path` does not start with the namespace name, or Vault is not configured (`platform`) |
| Event "secret not found" / no Kubernetes Secret | value not written to Vault yet, or wrong path |
| Event mentions "sealed" or connection refused | Vault is sealed: run `maintenance` |
| Pod stuck in ContainerCreating, "secret not found" | the VaultStaticSecret above has not synced |
| Website answers 403 | namespace lacks `web: true` |
| Certificate not Ready | DNS zone not covered by the Cloudflare token (`kubectl describe challenge`) |

## Moving a workload from another cluster

Copy it stopped first when running it twice is harmful (anything that signs, pays, sends, or
writes to a shared system): `suspend: true` for CronJobs, `replicas: 0` for Deployments. Tell
the owner what is stopped; switching over (start here, stop there, DNS) is the owner's decision.
Secrets found in ConfigMaps of the old cluster move to Vault, not to a ConfigMap.
