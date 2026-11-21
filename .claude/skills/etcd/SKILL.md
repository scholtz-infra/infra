---
name: etcd
description: Manage the etcd cluster that kubeadm runs on the control-plane nodes - check member health, database size and alarms, defragment, take or verify snapshots, clear a NOSPACE alarm, replace a failed member, restore from a snapshot.
---

# etcd

etcd runs as a static pod on every control-plane node (stacked etcd). `roles/etcd` installs on
each of them:

- `/usr/local/sbin/etcdctl` - etcdctl of the local etcd container with the right certificates
  (file paths are paths inside the container; `/var/lib/etcd` is shared with the host);
- `/usr/local/sbin/etcd-snapshot` and `etcd-snapshot.timer` - a snapshot plus a copy of
  `/etc/kubernetes/pki` every 6 hours into `/var/backups/etcd`, newest 14 kept.

The snapshots are **local only**. They do not survive the loss of the server; off-server backup
is still an open roadmap item. Say so whenever backups are discussed.

## Status (read-only)

Run the health check (`cluster-health` skill). Per control-plane node it reports members,
leader, database size, alarms and the age of the newest snapshot, and raises a problem when:
a member is unhealthy, there is no leader, the member count is even, an alarm is raised, the
database is over 70% of the 2 GiB quota, or the newest snapshot is older than 24 hours.

## Routine maintenance

Run the `maintenance` playbook (`run-workflow` skill; it also runs on the 1st of every month).
Per control-plane node, one at a time: verify all members are healthy, take a snapshot,
defragment when more than 25% of the database file is free space, wait until all members are
healthy again. Compaction needs no action, the API server compacts every 5 minutes.

## Incidents

These need commands on a server as root. Follow AGENTS.md rule 2 and 6: explain the plan, get
the owner's go-ahead, and prefer giving the owner the commands. Take a snapshot first whenever
etcd still answers (`etcd-snapshot`).

**NOSPACE alarm** (API becomes read-only: "etcdserver: mvcc: database space exceeded"):

```bash
etcdctl endpoint status --cluster -w table
etcdctl defrag --command-timeout=300s      # on every control-plane node, one after another
etcdctl alarm disarm
etcdctl alarm list                         # must be empty
```

Then find out what filled it (usually events or a controller writing in a loop) before closing.

**One member failed, quorum intact** (3 nodes, 1 lost): the cluster keeps working. If the
server comes back unchanged, do nothing. If it was reinstalled or replaced:

```bash
etcdctl member list -w table               # on a healthy node, note the ID of the dead member
etcdctl member remove <id>
kubectl delete node <name>
```

then run `site`: it joins the server again as a new control-plane member (`add-node` skill).
Never remove a member while another one is unhealthy.

**Quorum lost or data corrupted** (restore): destructive, owner decision. Outline for the
kubeadm layout, do it on one control-plane node and rejoin the others afterwards:

```bash
mkdir /root/manifests-off && mv /etc/kubernetes/manifests/*.yaml /root/manifests-off/   # stops the control plane
mv /var/lib/etcd /var/lib/etcd.broken
# etcdutl is in the etcd image; run it with the image version from /root/manifests-off/etcd.yaml
ctr -n k8s.io run --rm --mount type=bind,src=/var,dst=/var,options=rbind:rw <etcd-image> restore \
  etcdutl snapshot restore /var/backups/etcd/etcd-<stamp>.db --data-dir /var/lib/etcd \
  --name <node> --initial-cluster <node>=https://<node-ip>:2380 --initial-advertise-peer-urls https://<node-ip>:2380
mv /root/manifests-off/*.yaml /etc/kubernetes/manifests/
```

Other control-plane nodes: `kubeadm reset`, then `site` joins them fresh. Everything created
after the snapshot is gone from the API; running containers are reconciled to the restored state.
Verify the exact flags against the etcd documentation for the running version before use.

**Single-node cluster**: there is no quorum to lose and no member to fail over to. A broken etcd
means restore from the local snapshot; a lost server means rebuilding the cluster.
