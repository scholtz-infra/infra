---
name: replace-disk
description: Handle a failing or failed disk on a Hetzner dedicated server reported by the health check (SMART failure, reallocated sectors, NVMe media errors, degraded mdadm RAID) through to the rebuilt RAID.
---

# Replace a failed disk

Disk replacement needs the owner (Hetzner Robot support request, a few minutes of downtime for
non hot-swap servers) and root commands on the server. This is the one runbook where commands are
run by hand on the server: give the owner the exact commands, or run them only with their
explicit go-ahead. Wiping the wrong disk destroys the server.

1. Identify the disk from the `health` artifact (`node-<host>.json`): device, **serial number**,
   which RAID arrays it belongs to, and whether the other disk is healthy. If both disks show
   problems, stop and discuss moving workloads off the server first.
2. If the cluster has more than one node: drain the server
   (`kubectl drain <node> --ignore-daemonsets --delete-emptydir-data`). Longhorn volumes with
   replicas elsewhere stay available; `local-path` volumes on this server are offline meanwhile.
3. Mark the disk failed and remove it from every array (example for `nvme1n1`):
   ```bash
   cat /proc/mdstat
   mdadm /dev/md0 --fail /dev/nvme1n1p1 --remove /dev/nvme1n1p1   # repeat per array/partition
   ```
4. Owner: Robot > server > Support > "Disk failure". Give the **serial number** of the failed
   disk and of the healthy one, attach the `smartctl -a` output, choose the replacement time.
5. After the replacement, copy the partition table from the healthy disk to the new one and
   re-add the partitions (example: healthy `nvme0n1`, new `nvme1n1`; double-check with
   `lsblk -o NAME,SERIAL,SIZE` first):
   ```bash
   sgdisk --backup=/root/pt.bak /dev/nvme0n1
   sgdisk --load-backup=/root/pt.bak /dev/nvme1n1
   sgdisk -G /dev/nvme1n1
   mdadm /dev/md0 --add /dev/nvme1n1p1                               # repeat per array
   grub-install /dev/nvme1n1                                         # BIOS boot; see Hetzner docs for UEFI
   ```
6. Watch the rebuild (`cat /proc/mdstat`); the health check shows the recovery percentage and
   stays red until every array is `[UU]`.
7. Uncordon the node, run the health check, close the `health-alert` issue with a summary.

Reference: Hetzner docs "Exchange of hard disks in a software RAID".
