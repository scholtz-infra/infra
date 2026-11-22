# Preparing a new server

What the owner does by hand on every new Hetzner dedicated server before the agent and the
workflows can reach it. It takes about 15 minutes per server. Everything after that (hostname,
firewall, packages, Kubernetes) is done by the `site` playbook.

The workflows log in as the user **`infra`** with an SSH key and become root with `sudo`. There is
no password involved: `infra` has none, so it can only log in with a key, and sudo does not ask
for one.

Root login stays possible for **you**, as a last resort, with the key in
`/root/.ssh/authorized_keys` or with the root password. Put only your own key there, never the
deploy key: the workflows and the agent do not log in as root.

Because password logins are allowed, the root password is reachable from the internet on the SSH
port. Set a long random one (`passwd` as root, 20 characters or more from a password manager),
and do not give a password to any other account.

You need:

- the deploy key pair and the SSH port from [setup.md](setup.md) step 2 (`infra-deploy.pub` and
  the number you stored in the `SSH_PORT` secret),
- your own public SSH key, so that you can log in yourself,
- the inventory name of the server (`node1`, `node2`, ...).

## 1. Install Ubuntu

1. Order the server in Hetzner Robot and boot it into the **rescue system**.
2. Run `installimage` and choose the newest Ubuntu LTS. In the configuration file:
   - software RAID 1 over both disks (`SWRAID 1`, `SWRAIDLEVEL 1`),
   - no swap partition,
   - hostname: anything, Ansible sets it to the inventory name.
3. Reboot into the installed system. It accepts root logins on port 22 with the key you selected
   in Robot (or the rescue password). Select your own key: it remains root's key afterwards.

Leave the Hetzner Robot firewall for this server switched off, or allow at least the SSH port
from your address and from GitHub Actions, plus all traffic from the load balancer and the other
cluster servers. The servers bring their own firewall.

## 2. Create the user and set the SSH port

Copy the script and the public keys to the server and run the script as root. Replace
`<ssh-port>` with the number from the `SSH_PORT` secret:

```bash
scp scripts/bootstrap-server.sh infra-deploy.pub ~/.ssh/id_ed25519.pub root@<server-ip>:
ssh root@<server-ip> bash bootstrap-server.sh <ssh-port> infra-deploy.pub id_ed25519.pub
```

The script ([scripts/bootstrap-server.sh](../scripts/bootstrap-server.sh)):

| Does | Detail |
|---|---|
| Creates the user `infra` | Password locked, login only with a key |
| Installs the public keys | `/home/infra/.ssh/authorized_keys` contains exactly the key files you passed |
| Allows sudo without a password | `/etc/sudoers.d/90-infra`: `infra ALL=(ALL) NOPASSWD:ALL` |
| Moves sshd to the SSH port | `/etc/ssh/sshd_config.d/10-infra-hardening.conf`, port 22 is closed |
| Leaves root and password logins allowed | `PermitRootLogin yes`, `PasswordAuthentication yes`: your last resort |

It can be run again later, for example to replace a key: pass all keys that should remain.

## 3. Test the login

The script prints this command at the end. Run it from your machine **before** closing the root
session:

```bash
ssh -p <ssh-port> infra@<server-ip> sudo -n true && echo OK
```

`OK` means the workflows will be able to log in and become root. If it fails, fix it in the root
session that is still open. If you are locked out completely, boot the rescue system from Robot.

## 4. Update the secrets

Both secrets exist in the `production` and the `monitoring` environment and hold one line per
server. GitHub cannot show a stored secret, so keep the complete text in your password manager
and set the whole value again when a server is added. Formats and examples are in
[secrets.md](secrets.md).

| Secret | Line to add | Where it comes from |
|---|---|---|
| `NODE_IPS` | `node1 <server-ip>` | Public IPv4 of the server, from Robot |
| `SSH_KNOWN_HOSTS` | `node1 ssh-ed25519 AAAA...` | Printed by the script at the end; replace `NAME` with the inventory name |

## 5. Add the server to the load balancer

In the Hetzner Cloud console add the public IPv4 of the server as **IP target** of the load
balancer ([setup.md](setup.md) step 5).

## 6. Tell the agent

Say which inventory name the server has and whether it is a control-plane node or a worker. The
agent does not need the address. For the first server (`node1`) the inventory entry already
exists; for later servers the agent opens a pull request that adds the name. Then the agent
starts the `site` playbook and you approve the run.

## What happens to the server afterwards

The first `site` run changes these things, so you do not have to:

- hostname and `/etc/hosts` are set from the inventory name,
- root login is left as it is: `ssh -p <ssh-port> root@<server-ip>` keeps working with your key or the root password,
- the host firewall is installed: from the internet only the SSH port answers,
- swap is disabled, unattended security updates and SMART monitoring are set up,
- containerd, HAProxy and Kubernetes are installed and the server joins the cluster.

## Reinstalling a server

A reinstall creates a new host key: repeat steps 1 to 4 and replace the server's line in
`SSH_KNOWN_HOSTS`. If the server was part of the cluster, tell the agent first; removing a node
is not automated.
