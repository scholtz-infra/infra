# GitHub secrets

Every secret this repository uses. They are **environment secrets**
(*Settings > Environments > production / monitoring > Environment secrets*), not repository
secrets, so that only workflows running from `main` can read them.

| Secret | `production` | `monitoring` | Used for |
|---|---|---|---|
| `SSH_PRIVATE_KEY` | yes | yes | Ansible logs in to the servers as user `infra` with this key |
| `SSH_KNOWN_HOSTS` | yes | yes | Verifies that Ansible talks to the real servers |
| `NODE_IPS` | yes | yes | The public address of every server; kept out of the repository |
| `SSH_PORT` | yes | yes | The port sshd listens on; kept out of the repository |
| `CLOUDFLARE_API_TOKEN` | yes | no | cert-manager proves domain ownership to Let's Encrypt (DNS-01) |

The values in `production` and `monitoring` must be identical. All example values below are
made up.

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
node1 ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIExampleHostKeyOfNode1xxxxxxxxxxxxxxxxxxxxxxxx
node2 ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIExampleHostKeyOfNode2xxxxxxxxxxxxxxxxxxxxxxxx
```

`scripts/bootstrap-server.sh` prints the line for a new server. To get it again later:

```bash
ssh-keyscan -p <ssh-port> -t ed25519 <server-ip> | sed 's/^[^ ]*/node1/'
```

Update this secret every time a server is added or reinstalled (a reinstall creates a new host
key).

## NODE_IPS

One line per server: the **inventory name** of the server, a space, its public IPv4 address.
Every host in `inventory/production/hosts.yml` needs a line.

```text
node1 203.0.113.10
node2 203.0.113.11
```

Update this secret every time a server is added or gets a new address. The workflows hide these
addresses in their logs, in the health report and in the log artifacts.

## SSH_PORT

Only the number. Between 20000 and 60999, and not 53831, 53443 or 53080 (used by the cluster).

```text
41922
```

## CLOUDFLARE_API_TOKEN

A Cloudflare API **token** (not the Global API Key), created from the "Edit zone DNS" template
with `Zone / DNS / Edit` and `Zone / Zone / Read` on the zones your applications use. Only the
token string:

```text
u7Hk2ExampleExampleExampleExample9xQ_pL
```

## Setting them from the command line

```bash
for env in production monitoring; do
  gh secret set SSH_PRIVATE_KEY --env "$env" < ./infra-deploy
  gh secret set SSH_KNOWN_HOSTS --env "$env" < ./known_hosts
  gh secret set NODE_IPS        --env "$env" < ./node_ips
  gh secret set SSH_PORT        --env "$env" --body "41922"
done
gh secret set CLOUDFLARE_API_TOKEN --env production   # paste the token when asked
```

## Not secrets

- Application repositories need no cluster credential: they log in with their GitHub OIDC token
  (`docs/app-deploy.md`). Their `K8S_SERVER` (`https://k8s.biatec.io:53831`) and `K8S_CA`
  values are repository *variables*.
- The load balancer address, the API name and the API port are in the inventory.
- There is no sudo password: the user `infra` has no password and uses sudo without one.
