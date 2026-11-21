# First-time setup

Steps only the owner can do. Everything else is done through pull requests and workflows.

## 1. Repository settings

1. Consider making the repository **private**: the inventory contains the server IP addresses.
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
environments, then delete the local file. Keep `infra-deploy.pub` for the server installation.

Choose the SSH port for all servers, a number between 20000 and 60999 that is not 53831, 53443 or
53080, and add it as secret `SSH_PORT` to **both** environments. It is not stored in the
repository. Servers are installed with the default port 22; the first `site` run moves sshd to
this port and closes 22. Afterwards you connect with `ssh -p <port> root@<server-ip>`.

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

1. Order the dedicated server in Hetzner Robot.
2. Install the newest Ubuntu LTS with `installimage` from the rescue system: software RAID 1 over
   both disks, no swap needed, hostname anything (Ansible sets it). Add your own public key and
   `infra-deploy.pub` to root's `authorized_keys`.
3. Collect the host key and store the output as secret `SSH_KNOWN_HOSTS` in **both** environments
   (one line per server, append when servers are added). The line starts with the inventory name
   of the server instead of its address, so it stays valid when the SSH port changes:

   ```bash
   ssh-keyscan -t ed25519 <server-ip> | sed 's/^[^ ]*/node1/'
   ```

## 5. Load balancer

In the Hetzner Cloud console, on the load balancer 167.235.110.199 (it must be in the same
account as the dedicated servers, and in an `eu-central` location):

- **Targets**: add each cluster server as *IP* target (its public IPv4). Add new servers here
  when the cluster grows.
- **Service**: protocol **TCP**, listen port **443**, destination port **53443**,
  **Proxy protocol: on**. No service on port 80.
- **Health check**: TCP on port 53443.

The servers accept the ingress port only from the load balancer's IPv4 address. If the health
check stays red although the cluster is up, tell the agent: that address assumption has to be
checked first.

## 6. Inventory

Open a pull request that replaces the placeholder address in
`inventory/production/hosts.yml` with the server IP (or tell the agent the IP). Optionally set
`kube_api_external_fqdn` in `inventory/production/group_vars/all.yml` to a DNS name pointing at
the server; it must be set **before** the cluster is created to be included in the API certificate.

## 7. Create the cluster

After the pull request is merged: *Actions > Run playbook > Run workflow > site*, then approve the
run. Or ask the agent to do it; it will dispatch the run, wait for your approval and supervise.

Then run *Health check* once to confirm disks, RAID and cluster are reported healthy.

## For the agent to supervise runs

The agent needs the GitHub CLI authenticated on the machine it runs on: install `gh` and run
`gh auth login` (scopes `repo` and `workflow`).
