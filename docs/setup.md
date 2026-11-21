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
environments, then delete the local file. Keep `infra-deploy.pub` for the next step.

## 3. Server

1. Order the dedicated server in Hetzner Robot.
2. Install the newest Ubuntu LTS with `installimage` from the rescue system: software RAID 1 over
   both disks, no swap needed, hostname anything (Ansible sets it). Add your own public key and
   `infra-deploy.pub` to root's `authorized_keys`.
3. Collect the host keys and store the output as secret `SSH_KNOWN_HOSTS` in **both** environments
   (one block per server, append when servers are added):

   ```bash
   ssh-keyscan -t ed25519 <server-ip>
   ```

## 4. Inventory

Open a pull request that replaces the placeholder address in
`inventory/production/hosts.yml` with the server IP (or tell the agent the IP). Optionally set
`kube_api_external_fqdn` in `inventory/production/group_vars/all.yml` to a DNS name pointing at
the server; it must be set **before** the cluster is created to be included in the API certificate.

## 5. Create the cluster

After the pull request is merged: *Actions > Run playbook > Run workflow > site*, then approve the
run. Or ask the agent to do it; it will dispatch the run, wait for your approval and supervise.

Then run *Health check* once to confirm disks, RAID and cluster are reported healthy.

## For the agent to supervise runs

The agent needs the GitHub CLI authenticated on the machine it runs on: install `gh` and run
`gh auth login` (scopes `repo` and `workflow`).
