# First-time setup

Steps only the owner can do. Everything else is done through pull requests and workflows.

The complete list of secrets with example values is in [secrets.md](secrets.md).

## 1. Repository settings

1. The repository can stay public: server addresses and the SSH port are only in secrets. The
   load balancer address and the API name are in the repository.
2. *Settings > Branches*: protect `main` (require a pull request, require the `lint` check).
3. Optional, *Settings > Environments > production*: add yourself as **required reviewer** if
   every run that changes servers should wait for your click. Without a reviewer the agent
   starts runs itself, based on what you agreed in the conversation, and the scheduled patching
   and maintenance start on their own.
4. Optional: install the [Renovate app](https://github.com/apps/renovate) on the repository to get
   version update pull requests.

## 2. Deploy key

Create a key pair that GitHub Actions uses to reach the servers. Run this on your machine:

```bash
ssh-keygen -t ed25519 -N "" -C infra-deploy -f ./infra-deploy
```

Add the content of `infra-deploy` (private key) as repository secret `SSH_PRIVATE_KEY`, then delete the local file. Keep `infra-deploy.pub` for the server preparation.

Choose the SSH port for all servers, a number between 20000 and 60999 that is not 53443, 53080
or the API port, and add it as repository secret `SSH_PORT`. It is not stored in the
repository. You set this port on every new server yourself (step 4); afterwards you connect with
`ssh -p <port> infra@<server-ip>`.

## 3. Cloudflare API token (certificates)

In Cloudflare: *My Profile > API Tokens > Create Token*, template **Edit zone DNS**, limited to
the zones (domains) your applications use. Permissions needed: `Zone / DNS / Edit` and
`Zone / Zone / Read`. Add it as repository secret `CLOUDFLARE_API_TOKEN`.
cert-manager uses it only to create the temporary `_acme-challenge` TXT records that prove
domain ownership to Let's Encrypt.

DNS records for your applications stay under your control: point each hostname (or one wildcard
record such as `*.example.com`) at the load balancer, `A 167.235.110.199` and
`AAAA 2a01:4f8:1c1f:690b::1`, with the Cloudflare proxy either off (DNS only) or on with SSL mode
"Full (strict)".

## 4. Server

Install the server, create the `infra` user, set the SSH port and store the server's address and
host key in the secrets `NODE_IPS` and `SSH_KNOWN_HOSTS`: follow
[server-setup.md](server-setup.md). The same steps apply to every server added later.

## 5. Load balancer

In the Hetzner Cloud console, on the load balancer 167.235.110.199 (it must be in the same
account as the dedicated servers, and in an `eu-central` location):

- **Targets**: add each cluster server as *IP* target (its public IPv4). Add new servers here
  when the cluster grows.
- **Service "web"**: protocol **TCP**, listen port **443**, destination port **53443** (443
  also works: the servers redirect it to 53443 for connections from the load balancer),
  **Proxy protocol: off**, health check TCP on the destination port. No service on port 80.
  Proxy protocol can be switched on to give applications the real client address, but only
  together with `ingress_proxy_protocol` in the inventory: tell the agent first.
- **Service "kubernetes api"**: protocol **TCP**, listen port and destination port both the
  number in the `K8S_API_PORT` secret, **Proxy protocol: off**, health check TCP on the same
  port. When the cluster has
  workers that are not control-plane nodes, their target shows unhealthy for this service; that
  is expected.

`k8s.biatec.io` must be a DNS-only record in Cloudflare (grey cloud): the Cloudflare proxy does
not forward the API port.

The servers accept these two ports only from the load balancer's IPv4 address. If the health
check stays red although the cluster is up, tell the agent: that address assumption has to be
checked first.

## 6. Inventory

Nothing to do for the first server: `s-01-de` is already in `inventory/production/hosts.yml`, and
its address comes from the `NODE_IPS` secret. The API name `k8s.biatec.io` is already configured.

## 7. Create the cluster

Ask the agent to create the cluster: it dispatches the `site` run and supervises it. Or start it
yourself: *Actions > Run playbook > Run workflow > site*.

Then run *Health check* once to confirm disks, RAID and cluster are reported healthy.

## For the agent to debug a server

Optional. To let the agent look at a server directly (read-only, see AGENTS.md rule 2), add an
entry per server to `~/.ssh/config` on the machine the agent runs on. Address and port stay on
your machine:

```text
Host s-01-de
  HostName <server-ip>
  Port <ssh-port>
  User infra
  IdentityFile ~/.ssh/infra
```

The private key file must be readable by you only: `chmod 600 ~/.ssh/infra`.

## For the agent to supervise runs

The agent needs the GitHub CLI authenticated on the machine it runs on: install `gh` and run
`gh auth login` (scopes `repo` and `workflow`).
