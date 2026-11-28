# GitHub secrets

Every secret this repository uses to run the infrastructure. Secrets of *applications* are not
kept here: they live in Vault ([vault.md](vault.md)). They are **repository secrets**
(*Settings > Secrets and variables > Actions > Repository secrets*): one copy, used by all
workflows.

| Secret | Used by | Used for |
|---|---|---|
| `SSH_PRIVATE_KEY` | Run playbook, Health check | Ansible logs in to the servers as user `infra` with this key |
| `SSH_KNOWN_HOSTS` | Run playbook, Health check | Verifies that Ansible talks to the real servers |
| `NODE_IPS` | Run playbook, Health check | The public address of every server; kept out of the repository |
| `SSH_PORT` | Run playbook, Health check | The port sshd listens on; kept out of the repository |
| `K8S_API_PORT` | Run playbook, Health check | The port the Kubernetes API listens on; kept out of the repository |
| `CLOUDFLARE_API_TOKEN` | Run playbook | cert-manager proves domain ownership to Let's Encrypt (DNS-01) |
| `VAULT_UNSEAL_KEY` | Run playbook | Unseals Vault after a restart |
| `VAULT_ROOT_TOKEN` | Run playbook | Configures Vault and writes imported secrets |
| `VAULT_ADMIN_PASSWORD` | Run playbook | Password of the owner's Vault login `admin` |
| `VAULT_IMPORT` | Run playbook (`vault-import`) | Temporary: secrets to write into Vault; deleted after the run |

Repository secrets can be read by a workflow on any branch of this repository, so only give
write access to people (and agents) you trust with the servers. Pull requests from forks never
receive them. The `production` environment holds no secrets.

All example values below are made up.

## SSH_PRIVATE_KEY

The private half of the deploy key, the whole file including the first and last line. The
public half (`infra-deploy.pub`) is installed for the user `infra` on every server by
`scripts/bootstrap-server.sh` ([server-setup.md](server-setup.md)).

```text
-----BEGIN OPENSSH PRIVATE KEY-----
b3BlbnNzaC1rZXktdjEAAAAABG5vbmUAAAAEbm9uZQAAAAAAAAABAAAAMwAAAAtzc2gtZW
QyNTUxOQAAACBexampleexampleexampleexampleexampleexampleexampleAAAAJhexa
...
-----END OPENSSH PRIVATE KEY-----
```

Create it without a passphrase: `ssh-keygen -t ed25519 -N "" -C infra-deploy -f ./infra-deploy`

## SSH_KNOWN_HOSTS

One line per server: the **inventory name** of the server (as in
`inventory/production/hosts.yml`), then its ed25519 host key. Not the IP address and no port.

```text
s-01-de ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIExampleHostKeyOfNode1xxxxxxxxxxxxxxxxxxxxxxxx
s-02-de ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIExampleHostKeyOfNode2xxxxxxxxxxxxxxxxxxxxxxxx
```

`scripts/bootstrap-server.sh` prints the line for a new server. To get it again later:

```bash
ssh-keyscan -p <ssh-port> -t ed25519 <server-ip> | sed 's/^[^ ]*/s-01-de/'
```

Update this secret every time a server is added or reinstalled (a reinstall creates a new host
key).

## NODE_IPS

One line per server: the **inventory name** of the server, a space, its public IPv4 address.
Every host in `inventory/production/hosts.yml` needs a line.

```text
s-01-de 203.0.113.10
s-02-de 203.0.113.11
```

Update this secret every time a server is added or gets a new address. The workflows hide these
addresses in their logs, in the health report and in the log artifacts.

## SSH_PORT

Only the number. Between 20000 and 60999, and not 53443, 53080 or the API port (used by the
cluster).

```text
41922
```

## K8S_API_PORT

Only the number: the port the Kubernetes API servers listen on, and the port of the
"kubernetes api" service of the load balancer. Between 20000 and 60999, and not 53443, 53080 or
the SSH port.

```text
51234
```

To change it later: update this secret, change the load balancer service to the new port, then
run `site`. The API is unreachable for a short time while the API servers move, and application
repositories need the new port in their `K8S_SERVER` secret.

## CLOUDFLARE_API_TOKEN

A Cloudflare API **token** (not the Global API Key), created from the "Edit zone DNS" template
with `Zone / DNS / Edit` and `Zone / Zone / Read` on the zones your applications use. Only the
token string:

```text
u7Hk2ExampleExampleExampleExample9xQ_pL
```

## VAULT_UNSEAL_KEY and VAULT_ROOT_TOKEN

Created by Vault itself on the first install, not chosen by anyone. How they get from the server
into these secrets is described in [vault.md](vault.md), "First install". The unseal key is a
base64 string, the root token starts with `hvs.`:

```text
pZ0ExampleExampleExampleExampleExampleExampl=
hvs.ExampleExampleExampleExample
```

Keep a copy of the unseal key outside GitHub: without it the data in Vault cannot be read again.

## VAULT_ADMIN_PASSWORD

Chosen by the owner: the password of user `admin` at <https://vault.k8s.biatec.io>. That page is
reachable from the internet, so use a long random one. To change the password, change this secret
and run `platform`.

```text
correct-horse-Example-battery-staple-49
```

## VAULT_IMPORT

Exists only while secrets are being written into Vault from a workflow ([vault.md](vault.md),
"Writing secrets from a workflow"). A JSON object; delete the secret after the `vault-import`
run.

```json
{ "my-app/database": { "username": "app", "password": "example" } }
```

## Setting them from the command line

```bash
gh secret set SSH_PRIVATE_KEY < ./infra-deploy
gh secret set SSH_KNOWN_HOSTS < ./known_hosts
gh secret set NODE_IPS        < ./node_ips
gh secret set SSH_PORT        --body "41922"
gh secret set K8S_API_PORT    --body "51234"
gh secret set CLOUDFLARE_API_TOKEN   # paste the token when asked
gh secret set VAULT_ADMIN_PASSWORD   # paste the password when asked
```

## Not secrets

- Application repositories need no cluster credential: they log in with their GitHub OIDC token
  (`docs/app-deploy.md`). Their `K8S_SERVER` contains the API port, so it is a secret there;
  `K8S_CA` is a repository *variable*.
- The load balancer address and the API name are in the inventory.
- There is no sudo password: the user `infra` has no password and uses sudo without one.
