# Data volumes on the servers

Disk space outside the system disk, prepared by the `storage` playbook from the list in
`inventory/production/host_vars/<server>.yml`.

## s-01-de

| Mount point | Device | Size | Redundancy | Meant for |
|---|---|---|---|---|
| `/` and `/boot` | `md1`, `md0`: mirror over both NVMe drives | 1 TB | survives one NVMe drive | system, Kubernetes, Longhorn volumes |
| `/mnt/nvme1` | rest of the first NVMe drive (`nvme0n1`) | 2.5 TiB | **none** | fast data that can be lost or is replicated by the application |
| `/mnt/nvme2` | rest of the second NVMe drive (`nvme1n1`) | 2.5 TiB | **none** | same |
| `/mnt/14TB` | `md3`: mirror over both hard disks | 14.6 TB | survives one hard disk | bulk data, backups |

All three are ext4, found by filesystem label (`nvme1`, `nvme2`, `hdd14tb`) and mounted with
`nofail`: a broken data disk does not keep the server from booting.

Kubernetes does not use these mount points yet: there is no StorageClass on them. Ask the agent
when workloads should get volumes there.

## How the playbook works

`Run playbook > storage`. For every volume in the list:

- If a filesystem with the volume's label exists, nothing is created; the playbook only makes
  sure it is in `/etc/fstab` and mounted. Running it again is harmless.
- A RAID volume is created only on disks that are empty or that hold nothing but the old arrays
  listed under `wipe_array_uuids`. Anything else on the disks, a mounted partition or a running
  array stops the run before anything is written.
- A partition volume takes the largest unpartitioned block of its disk. Existing partitions are
  not moved or resized.

A new mirror synchronises in the background after creation (about a day for the hard disks); it
can be used meanwhile. Progress: `cat /proc/mdstat`.

## Adding a volume on another server

Add `storage_arrays` / `storage_partitions` to that server's file in `host_vars` (format in
`roles/storage/defaults/main.yml`), always naming disks by `/dev/disk/by-id/...`, and run
`storage`. Creating a volume on disks that hold old data needs the owner's go first
(AGENTS.md rule 6).
