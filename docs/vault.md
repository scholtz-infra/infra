# Vault (application secrets)

HashiCorp Vault holds every secret an application needs: passwords, API keys, mnemonics. The
secret is written once in Vault and arrives in the cluster as an ordinary Kubernetes Secret; a
later change in Vault reaches that Secret by itself.

Address: <https://vault.k8s.biatec.io> (web UI and API)

What goes where:

| Kind of secret | Where it lives |
|---|---|
| Secrets of applications | Vault, `kv/<namespace>/<secret name>` |
| Secrets that run the infrastructure itself (SSH key, Cloudflare token, the Vault unseal key, ...) | Repository secrets of this repo ([secrets.md](secrets.md)) |
| Anything in a Git repository, public or private | Never a secret. Manifests only name the Vault path |

## How secrets are organised

One secret engine, `kv` (key-value, version 2: every change is kept as a version and can be
rolled back). Below it, the first path element is always the Kubernetes namespace:

```text
kv/<namespace>/<secret name>      e.g.  kv/my-app/database
    key: value                           username: app
    key: value                           password: ...
```

One Vault secret becomes one Kubernetes Secret; its keys become the keys of that Secret. To give
an application a whole file (`config.json`), use the file name as the key and the file content as
the value.

A namespace can only read `kv/<its own name>/`. This is enforced by Vault, not by convention:
the operator logs in to Vault as the service account `vault-secrets` of the namespace that asks,
and the policy `namespace-read` only opens the path with that namespace's name.

## From Vault to a Kubernetes Secret

The Vault Secrets Operator watches `VaultStaticSecret` objects. Each one names a Vault path and
the Kubernetes Secret to keep equal to it:

```yaml
apiVersion: secrets.hashicorp.com/v1beta1
kind: VaultStaticSecret
metadata:
  name: database
  namespace: my-app
spec:
  vaultAuthRef: vault        # created in every application namespace by the `apps` playbook
  mount: kv
  type: kv-v2
  path: my-app/database      # kv/my-app/database
  refreshAfter: 60s          # how often Vault is asked for changes
  destination:
    name: database           # the Kubernetes Secret
    create: true
  rolloutRestartTargets:     # optional: restart these when the secret changes
    - kind: Deployment
      name: my-app
```

A change in Vault is in the Kubernetes Secret within `refreshAfter`. What happens then depends on
how the application uses the Secret:

- mounted as files: the files change within about a minute, without a restart (not with
  `subPath` mounts);
- environment variables, `subPath` mounts, or an application that reads its configuration only at
  start: list the workload under `rolloutRestartTargets`;
- CronJobs: the next run uses the new value.

The manifests live in the private `config` repository and are applied by the `apps` playbook
([apps.md](apps.md)).

## Changing a secret

- **Web UI**: log in at <https://vault.k8s.biatec.io> with method *Username*, user `admin` and the
  password stored as the `VAULT_ADMIN_PASSWORD` repository secret. Open `kv`, the namespace, the
  secret, *Create new version*.
- **From a workflow** (no typing into a browser, used by the agent): see below.

### Writing secrets from a workflow

1. Put the secrets into a file outside any repository, as JSON:

   ```json
   {
     "my-app/database": { "username": "app", "password": "..." },
     "my-app/config": { "config.json": "{ \"whole\": \"file\" }" }
   }
   ```

   Each entry replaces all keys of `kv/<namespace>/<secret name>` (as a new version).
2. `gh secret set VAULT_IMPORT < file`, then delete the file.
3. Run the `vault-import` playbook (`Run playbook` workflow).
4. `gh secret delete VAULT_IMPORT`.

The run log shows only how many secrets were written.

## Sealed and unsealed

Vault encrypts its data with a key it does not keep on disk. After every restart of its pod
(server reboot, Vault upgrade, node drain) it is **sealed**: it runs but can read nothing until
it is given the unseal key.

While Vault is sealed, applications keep running with the Kubernetes Secrets they already have.
Only changes made in Vault, and Secrets for new applications, wait.

The unseal key is the `VAULT_UNSEAL_KEY` repository secret and nothing else. Vault is unsealed
by the playbooks: `platform`, `site`, `os-patch` (after the reboot), `k8s-upgrade`, `maintenance`
and `vault-import`. The daily health check reports a sealed Vault; the fix is to run
`maintenance`.

## First install

Done once. `platform` initialises a new Vault and writes the unseal key and the root token to
`/root/vault-init.json` on the first control-plane server (readable by root only), because a
workflow cannot store repository secrets.

1. Run `platform`. Its last Vault task says that the init file is still on the server.
2. Copy both values into repository secrets, from a machine with `gh` and SSH access, without
   displaying them:

   ```bash
   ssh s-01-de sudo cat /root/vault-init.json | python3 -c \
     'import json,sys; print(json.load(sys.stdin)["unseal_keys_b64"][0], end="")' | gh secret set VAULT_UNSEAL_KEY
   ssh s-01-de sudo cat /root/vault-init.json | python3 -c \
     'import json,sys; print(json.load(sys.stdin)["root_token"], end="")' | gh secret set VAULT_ROOT_TOKEN
   ```

3. The owner chooses a password for the web UI: `gh secret set VAULT_ADMIN_PASSWORD`.
4. Run `platform` again. It compares the repository secrets with the file, deletes the file when
   they are equal, and creates the user `admin`.

**Keep a copy of the unseal key outside GitHub** (password manager). A repository secret cannot
be read back: if it is ever overwritten or the repository is lost, the data in Vault is gone for
good without that key.

## How it is set up

| Part | Where |
|---|---|
| Helm releases `vault` and `vault-secrets-operator` | `platform/releases.yml`, `platform/values/` |
| Initialise, unseal, configure | `playbooks/tasks/vault-configure.yml`, `playbooks/tasks/vault-unseal.yml` |
| Policy that ties a namespace to its path | `playbooks/templates/vault-policy-namespace.hcl.j2` |
| Import from a workflow | `playbooks/vault-import.yml` |
| Public name | `vault_fqdn` in `inventory/production/group_vars/all.yml` |
| Network | `platform/network.yml`: the operator may reach Vault on 8200; `vault` is in `network_web` |
| Storage | Raft, one replica, 10 GiB Longhorn volume `data-vault-0` |
| Audit log | Every request, with hashed values, in the log of pod `vault-0` |

What the configuration creates inside Vault: secret engine `kv`; login methods `kubernetes`
(role `namespace`: service account `vault-secrets` of any namespace, token audience `vault`,
policy `namespace-read`) and `userpass` (user `admin`, policy `admin`: everything).

## Limits and risks to know

- **A synced secret is a Kubernetes Secret.** It is stored in etcd on the control-plane servers
  and readable by anyone with access to that namespace or to the servers. Vault adds one place to
  manage secrets, history, an audit log and a clean Git repository; it does not hide a secret
  from the cluster that uses it.
- **The root token** stays in use by the playbooks (`VAULT_ROOT_TOKEN`). It can do everything in
  Vault, like the SSH key can on the servers.
- **The login page is on the internet.** The `admin` password must be long and random.
- **No backup off the server yet.** Vault's data is on the same server as everything else
  (roadmap in `AGENTS.md`).
- **Upgrades**: the chart does not restart Vault by itself (`OnDelete`). After a chart upgrade
  the pod keeps running the old version until it is restarted, which needs an unseal afterwards.
- **More replicas** (when the cluster has three servers) need `retry_join` in the Raft
  configuration and an unseal of each new pod; not prepared yet.

## If the unseal key or root token leaks

Tell the owner. Rotating means `vault operator rekey` (new unseal key) and generating a new root
token with the unseal key (`vault operator generate-root`), then updating both repository
secrets. Secrets stored in Vault that may have been read must be changed at their source.
