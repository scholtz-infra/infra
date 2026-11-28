# Applications from the configuration repository

Applications that have no deployment pipeline of their own are described in a second, **private**
repository (`config`, same GitHub owner as this one) and deployed by the `apps` playbook of this
repository.

| | This repository (`infra`) | `config` repository |
|---|---|---|
| Visibility | public | private |
| Holds | how the cluster is built and operated; all workflows | which applications run: namespaces, manifests, hostnames, settings; the knowledge base for adding one |
| Workflows | all of them | none, on purpose |
| Secrets | infrastructure secrets, as repository secrets | none. Manifests name a Vault path, the value is in Vault ([vault.md](vault.md)) |

Anything that describes the owner's applications belongs in `config`, not here. A secret belongs
in neither.

## Layout of the configuration repository

```text
namespaces.yml            the namespaces, and who may reach them
apps/<namespace>/*.yaml   Kubernetes manifests of that namespace
docs/                     how to add an application, how its secrets are handled
```

`namespaces.yml`:

```yaml
namespaces:
  - name: my-app
    web: true                 # pods may receive traffic from the internet through the ingress
    allow_from:               # other namespaces that may connect (optional)
      - namespace: monitoring
        ports: [9090]
  - name: my-jobs             # no web traffic, reachable from nowhere else
```

## What the `apps` playbook does

For every namespace in `namespaces.yml`:

1. creates the namespace with the `baseline` pod security standard;
2. creates the service account `vault-secrets` and the `VaultAuth` object `vault`, which let the
   Vault Secrets Operator read `kv/<namespace>/` for this namespace and nothing else;
3. applies the network policies: traffic inside the namespace is allowed, from the ingress only
   with `web: true`, from another namespace only when listed in `allow_from`. Policies that are
   no longer listed are removed;
4. runs `kubectl apply -n <namespace>` on everything in `apps/<namespace>/`. A manifest that
   names a different namespace is refused.

Namespaces that belong to the platform or to a tenant repository (`platform/tenants.yml`) are
rejected.

To let an application reach a platform service (for example a shared Redis), add the pair to
`network_allow` in `platform/network.yml` of this repository, as for any other namespace.

## Deploying a change

1. Commit and push the change to `main` of the `config` repository.
2. Run `Run playbook` with `apps` (skill `run-workflow`). The run log lists the objects that
   were created or changed, by name. Manifest contents are never printed: the log is public.

`apps` is safe to repeat and only touches the namespaces listed in `namespaces.yml`.

## What it does not do

- **It never deletes.** Removing a manifest or a namespace from the repository leaves the object
  in the cluster. Deleting is a decision for the owner (rule 6 in `AGENTS.md`).
- **It does not write secrets.** Values go into Vault through the web UI or the `vault-import`
  playbook ([vault.md](vault.md)).
- **It does not build images.** Manifests name an image tag; a new version is deployed by
  changing the tag in `config` and running `apps`.

## How the workflow reaches the private repository

The repository secret `CONFIG_REPO_DEPLOY_KEY` is the private half of a read-only deploy key of
the `config` repository ([secrets.md](secrets.md)). The workflow checks the repository out into
`./config` only for the `apps` playbook. A different repository name can be set with the
repository variable `CONFIG_REPOSITORY` (`owner/name`).

The `config` repository is trusted like this one: its manifests are applied with full cluster
rights. Only give write access to people (and agents) you trust with the cluster.
