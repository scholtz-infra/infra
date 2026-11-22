# First-time setup

Steps only the owner can do. Everything else is done through pull requests and workflows.

The complete list of secrets with example values is in [secrets.md](secrets.md).

## 1. Repository settings

1. The repository can stay public: server addresses and the SSH port are only in secrets. The
   load balancer address, the API name and the API port are in the repository.
2. *Settings > Branches*: protect `main` (require a pull request, require the `lint` check).
3. *Settings > Environments*: create two environments, both restricted to the `main` branch
   (*Deployment branches and tags > Selected branches > main*):
   - `production` - add yourself as **required reviewer**. Used by everything that changes servers.
   - `monitoring` - no reviewer. Used by the read-only daily health check.
4. Optional: install the [Renovate app](https://github.com/apps/renovate) on the repository to get
   version update pull requests.

## 2. Deploy key

Create a key pair that GitHub Actions uses to reach the servers. Run this on your machine:

```bash
ssh-keygen -t ed25519 -N "" -C infra-deploy -f ./infra-deploy
```

Add the content of `infra-deploy` (private key) as secret `SSH_PRIVATE_KEY` to **both**
environments, then delete the local file. Keep `infra-deploy.pub` for the server preparation.

Choose the SSH port for all servers, a number between 20000 and 60999 that is not 53831, 53443 or
53080, and add it as secret `SSH_PORT` to **both** environments. It is not stored in the
repository. You set this port on every new server yourself (step 4); afterwards you connect with
`ssh -p <port> infra@<server-ip>`.

## 3. Cloudflare API token (certificates)

In Cloudflare: *My Profile > API Tokens > Create Token*, template **Edit zone DNS**, limited to
the zones (domains) your applications use. Permissions needed: `Zone / DNS / Edit` and
`Zone / Zone / Read`. Add it as secret `CLOUDFLARE_API_TOKEN` to the `production` environment.
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
- **Service "web"**: protocol **TCP**, listen port **443**, destination port **53443**,
  **Proxy protocol: on**, health check TCP on port 53443. No service on port 80.
- **Service "kubernetes api"**: protocol **TCP**, listen port **53831**, destination port
  **53831**, **Proxy protocol: off**, health check TCP on port 53831. When the cluster has
  workers that are not control-plane nodes, their target shows unhealthy for this service; that
  is expected.

`k8s.biatec.io` must be a DNS-only record in Cloudflare (grey cloud): the Cloudflare proxy does
not forward port 53831.

The servers accept these two ports only from the load balancer's IPv4 address. If the health
check stays red although the cluster is up, tell the agent: that address assumption has to be
checked first.

## 6. Inventory

Nothing to do for the first server: `node1` is already in `inventory/production/hosts.yml`, and
its address comes from the `NODE_IPS` secret. The API name `k8s.biatec.io` is already configured.

## 7. Create the cluster

After pull request #1 is merged: *Actions > Run playbook > Run workflow > site*, then approve the
run. Or ask the agent to do it; it will dispatch the run, wait for your approval and supervise.

Then run *Health check* once to confirm disks, RAID and cluster are reported healthy.

## For the agent to supervise runs

The agent needs the GitHub CLI authenticated on the machine it runs on: install `gh` and run
`gh auth login` (scopes `repo` and `workflow`).
