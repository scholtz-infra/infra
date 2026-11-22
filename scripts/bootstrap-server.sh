#!/usr/bin/env bash
# Prepares a freshly installed Ubuntu server so that the infrastructure workflows can reach it.
# Run once, as root, on the new server (see docs/server-setup.md):
#
#   bash bootstrap-server.sh <ssh-port> <public-key-file>...
#
# What it does:
#   - creates the user "infra" without a password (key login only)
#   - installs the given public keys as the only way to log in as "infra"
#   - lets "infra" use sudo without a password
#   - moves sshd to <ssh-port> and switches password logins off
#
# It can be run again, for example to add a key. Root login is not touched: root's own
# authorized_keys keeps working, as the owner's last resort.
set -euo pipefail

user=infra

die() {
  echo "error: $*" >&2
  exit 1
}

[ "$(id -u)" -eq 0 ] || die "run this script as root"
[ "$#" -ge 2 ] || die "usage: bash bootstrap-server.sh <ssh-port> <public-key-file>..."

port=$1
shift
[[ "$port" =~ ^[0-9]+$ ]] || die "the SSH port must be a number"
{ [ "$port" -ge 20000 ] && [ "$port" -le 60999 ]; } || die "the SSH port must be between 20000 and 60999"
case "$port" in
  53831 | 53443 | 53080 | 7443) die "port $port is used by the cluster" ;;
esac
for key in "$@"; do
  ssh-keygen -l -f "$key" > /dev/null || die "$key is not a public key file"
done

# User: no password, so the only way in is a key.
if ! id "$user" > /dev/null 2>&1; then
  useradd --create-home --shell /bin/bash "$user"
fi
passwd --lock "$user" > /dev/null

home=$(getent passwd "$user" | cut -d: -f6)
install -d -m 700 -o "$user" -g "$user" "$home/.ssh"
cat "$@" | grep -v '^[[:space:]]*$' | sort -u > "$home/.ssh/authorized_keys"
chown "$user:$user" "$home/.ssh/authorized_keys"
chmod 600 "$home/.ssh/authorized_keys"

# sudo without a password: the workflows run unattended.
sudoers=$(mktemp)
echo "$user ALL=(ALL) NOPASSWD:ALL" > "$sudoers"
visudo -cf "$sudoers" > /dev/null
install -m 440 -o root -g root "$sudoers" "/etc/sudoers.d/90-$user"
rm -f "$sudoers"

# sshd: same file that Ansible manages afterwards (roles/ssh).
config=/etc/ssh/sshd_config.d/10-infra-hardening.conf
grep -Eq '^\s*Include\s+/etc/ssh/sshd_config\.d/' /etc/ssh/sshd_config \
  || die "/etc/ssh/sshd_config does not include sshd_config.d: not a standard Ubuntu installation"
if grep -Eq '^\s*Port\s' /etc/ssh/sshd_config; then
  die "/etc/ssh/sshd_config sets a Port itself: remove that line and run again"
fi
umask 077
cat > "$config" << EOF
Port $port
PasswordAuthentication no
KbdInteractiveAuthentication no
EOF
mkdir -p /run/sshd
sshd -t || { rm -f "$config"; die "sshd rejected the configuration, nothing was changed"; }

# Ubuntu starts sshd through ssh.socket, whose port is generated from the sshd configuration.
# systemd refuses to start a socket while its service runs, so the service is stopped first;
# the next connection starts it again. Sessions that are already open survive this.
systemctl daemon-reload
if systemctl is-enabled --quiet ssh.socket 2> /dev/null; then
  systemctl stop ssh.service
  systemctl restart ssh.socket
else
  systemctl restart ssh.service
fi

sleep 1
ss -Hltn "sport = :$port" | grep -q . || die "nothing listens on port $port: do NOT close this session, check 'systemctl status ssh.socket ssh.service'"

cat << EOF

Done. sshd now listens on port $port.

Keep this session open and test from your machine in a second terminal:

  ssh -p $port $user@<server-ip> sudo -n true && echo OK

Host key line for the SSH_KNOWN_HOSTS secret (replace NAME with the inventory name, e.g. node1):

  NAME $(cut -d' ' -f1,2 /etc/ssh/ssh_host_ed25519_key.pub)
EOF
