#!/usr/bin/env python3
"""Node health probe. Runs on a server as root (via playbooks/health.yml), standard library only.

Prints one JSON document: disks (SMART), software RAID, filesystems, pending updates,
certificate expiry, and a flat list of "problems" that need a human or the agent to act.
"""
import glob
import json
import os
import re
import shutil
import subprocess
import time

DISK_USAGE_WARN_PERCENT = 85
CERT_WARN_DAYS = 30
ETCD_QUOTA_BYTES = 2 * 1024**3  # etcd default, kubeadm does not change it
ETCD_SIZE_WARN_PERCENT = 70
ETCD_SNAPSHOT_MAX_AGE_HOURS = 24
ETCDCTL = "/usr/local/sbin/etcdctl"
ETCD_SNAPSHOT_DIR = "/var/backups/etcd"
NVME_WEAR_WARN_PERCENT = 90
# ATA attributes where any non-zero raw value means the disk is on its way out.
ATA_FAILURE_ATTRIBUTES = {
    5: "reallocated sectors",
    187: "reported uncorrectable errors",
    197: "pending sectors",
    198: "offline uncorrectable sectors",
}


def run(cmd, timeout=60):
    """Return (returncode, stdout). Never raises."""
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
        return proc.returncode, proc.stdout
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 127, str(exc)


def evaluate_smart(data):
    """Turn one `smartctl -j -H -A -i` document into a summary with a list of problems."""
    problems = []
    passed = data.get("smart_status", {}).get("passed")
    if passed is False:
        problems.append("SMART overall health check FAILED")
    elif passed is None:
        problems.append("SMART status could not be read")

    nvme = data.get("nvme_smart_health_information_log")
    wear = None
    if nvme:
        wear = nvme.get("percentage_used")
        if nvme.get("critical_warning", 0):
            problems.append(f"NVMe critical warning flags: {nvme['critical_warning']}")
        if nvme.get("media_errors", 0):
            problems.append(f"NVMe media errors: {nvme['media_errors']}")
        if wear is not None and wear >= NVME_WEAR_WARN_PERCENT:
            problems.append(f"NVMe wear at {wear}% of rated life")
        spare, threshold = nvme.get("available_spare"), nvme.get("available_spare_threshold")
        if spare is not None and threshold is not None and spare <= threshold:
            problems.append(f"NVMe spare capacity {spare}% at or below threshold {threshold}%")

    for attr in data.get("ata_smart_attributes", {}).get("table", []):
        label = ATA_FAILURE_ATTRIBUTES.get(attr.get("id"))
        raw = attr.get("raw", {}).get("value", 0)
        if label and raw:
            problems.append(f"{raw} {label} (attribute {attr['id']})")

    return {
        "device": data.get("device", {}).get("name"),
        "model": data.get("model_name"),
        "serial": data.get("serial_number"),
        "passed": passed,
        "temperature_c": data.get("temperature", {}).get("current"),
        "power_on_hours": data.get("power_on_time", {}).get("hours"),
        "wear_percent": wear,
        "problems": problems,
    }


def collect_disks():
    if not shutil.which("smartctl"):
        return [], ["smartctl is not installed (run the site playbook)"]
    # --scan-open reports the real type: SATA disks show up as "sat" instead of "scsi", which
    # would hide their SMART status and attributes.
    code, out = run(["smartctl", "--scan-open", "-j"])
    try:
        devices = json.loads(out).get("devices", [])
    except ValueError:
        return [], [f"smartctl --scan failed (exit {code})"]
    if not devices:
        return [], ["smartctl found no disks"]
    disks = []
    for dev in devices:
        _, out = run(["smartctl", "-j", "-H", "-A", "-i", "-d", dev.get("type", "auto"), dev["name"]])
        try:
            disks.append(evaluate_smart(json.loads(out)))
        except ValueError:
            disks.append({"device": dev["name"], "problems": ["smartctl returned no data"]})
    return disks, []


def parse_mdstat(text):
    """Parse /proc/mdstat into [{name, level, members, state, degraded, resync}]."""
    arrays = []
    current = None
    for line in text.splitlines():
        match = re.match(r"^(md\S+) : (\S+)(?: \(\S+\))? (\S+) (.*)$", line)
        if match:
            current = {
                "name": match.group(1),
                "level": match.group(3),
                "members": match.group(4).split(),
                "state": None,
                "degraded": match.group(2) != "active",
                "resync": None,
            }
            arrays.append(current)
            continue
        if current is None:
            continue
        state = re.search(r"\[(\d+)/(\d+)\] \[([U_]+)\]", line)
        if state:
            current["state"] = state.group(3)
            if "_" in state.group(3) or state.group(1) != state.group(2):
                current["degraded"] = True
        progress = re.search(r"(recovery|resync|reshape|check)\s*=\s*([\d.]+%)", line)
        if progress:
            current["resync"] = f"{progress.group(1)} {progress.group(2)}"
        if not line.strip():
            current = None
    for array in arrays:
        if any("(F)" in member for member in array["members"]):
            array["degraded"] = True
    return arrays


def evaluate_etcd(status, health, alarms, snapshot_age_hours):
    """Summarise `etcdctl endpoint status/health --cluster -w json` and `alarm list` output."""
    problems = []
    members = []
    for entry in status or []:
        info = entry.get("Status", {})
        size = int(info.get("dbSize", 0))
        members.append({
            "endpoint": entry.get("Endpoint"),
            "version": info.get("version"),
            "db_size_mb": round(size / 1024**2),
            "db_in_use_mb": round(int(info.get("dbSizeInUse", 0)) / 1024**2),
            "leader": info.get("leader") == info.get("header", {}).get("member_id"),
        })
        if size * 100 >= ETCD_QUOTA_BYTES * ETCD_SIZE_WARN_PERCENT:
            problems.append(f"etcd database on {entry.get('Endpoint')} is {round(size / 1024**2)} MB, "
                            f"over {ETCD_SIZE_WARN_PERCENT}% of the quota: defragment (maintenance playbook)")
    if not members:
        problems.append("etcd status could not be read")
    elif not any(member["leader"] for member in members):
        problems.append("etcd has no leader")
    for entry in health or []:
        if not entry.get("health"):
            problems.append(f"etcd member {entry.get('endpoint')} is unhealthy")
    if health is not None and len(health) % 2 == 0:
        problems.append(f"etcd has {len(health)} members: an even number cannot lose a member safely")
    if alarms.strip():
        problems.append(f"etcd alarm raised: {' '.join(alarms.split())}")
    if snapshot_age_hours is None:
        problems.append("no local etcd snapshot found")
    elif snapshot_age_hours > ETCD_SNAPSHOT_MAX_AGE_HOURS:
        problems.append(f"newest local etcd snapshot is {int(snapshot_age_hours)} hours old")
    return {"members": members, "snapshot_age_hours": snapshot_age_hours, "problems": problems}


def collect_etcd():
    """Only on control-plane nodes of an existing cluster; None elsewhere."""
    if not (os.path.exists(ETCDCTL) and os.path.exists("/etc/kubernetes/manifests/etcd.yaml")):
        return None

    def etcd_json(*args):
        code, out = run([ETCDCTL, *args, "--write-out=json"])
        try:
            return json.loads(out) if code == 0 else None
        except ValueError:
            return None

    _, alarms = run([ETCDCTL, "alarm", "list"])
    snapshots = glob.glob(os.path.join(ETCD_SNAPSHOT_DIR, "etcd-*.db"))
    age = (time.time() - max(os.path.getmtime(s) for s in snapshots)) / 3600 if snapshots else None
    return evaluate_etcd(
        etcd_json("endpoint", "status", "--cluster"),
        etcd_json("endpoint", "health", "--cluster"),
        alarms,
        round(age, 1) if age is not None else None,
    )


def collect_filesystems():
    result = []
    seen = set()
    with open("/proc/mounts", encoding="utf-8") as mounts:
        for line in mounts:
            device, mountpoint, fstype = line.split()[:3]
            if fstype not in ("ext4", "xfs", "btrfs") or device in seen or "/kubelet/" in mountpoint:
                continue
            seen.add(device)
            usage = shutil.disk_usage(mountpoint)
            result.append({"mount": mountpoint, "used_percent": round(usage.used * 100 / usage.total)})
    return result


def collect_certificates():
    result = []
    for path in sorted(glob.glob("/etc/kubernetes/pki/*.crt") + glob.glob("/etc/kubernetes/pki/etcd/*.crt")):
        code, out = run(["openssl", "x509", "-noout", "-enddate", "-in", path])
        if code != 0 or "=" not in out:
            continue
        expires = time.mktime(time.strptime(out.strip().split("=", 1)[1], "%b %d %H:%M:%S %Y %Z"))
        result.append({"path": path, "days_left": int((expires - time.time()) // 86400)})
    return result


def main():
    disks, problems = collect_disks()
    for disk in disks:
        problems += [f"disk {disk['device']} ({disk.get('serial')}): {p}" for p in disk["problems"]]

    mdraid = []
    if os.path.exists("/proc/mdstat"):
        with open("/proc/mdstat", encoding="utf-8") as mdstat:
            mdraid = parse_mdstat(mdstat.read())
    for array in mdraid:
        if array["degraded"]:
            problems.append(f"RAID {array['name']} is DEGRADED [{array['state']}] members: {' '.join(array['members'])}")

    filesystems = collect_filesystems()
    for fs in filesystems:
        if fs["used_percent"] >= DISK_USAGE_WARN_PERCENT:
            problems.append(f"filesystem {fs['mount']} is {fs['used_percent']}% full")

    certificates = collect_certificates()
    for cert in certificates:
        if cert["days_left"] < CERT_WARN_DAYS:
            problems.append(f"certificate {cert['path']} expires in {cert['days_left']} days")

    etcd = collect_etcd()
    if etcd:
        problems += etcd["problems"]

    _, simulated = run(["apt-get", "-s", "-o", "Debug::NoLocking=true", "dist-upgrade"], timeout=120)
    with open("/proc/uptime", encoding="utf-8") as uptime:
        uptime_days = int(float(uptime.read().split()[0]) // 86400)
    os_release = {}
    with open("/etc/os-release", encoding="utf-8") as release:
        for line in release:
            key, _, value = line.strip().partition("=")
            os_release[key] = value.strip('"')

    print(json.dumps({
        "hostname": os.uname().nodename,
        "os": os_release.get("PRETTY_NAME"),
        "kernel": os.uname().release,
        "uptime_days": uptime_days,
        "pending_updates": sum(1 for line in simulated.splitlines() if line.startswith("Inst ")),
        "reboot_required": os.path.exists("/var/run/reboot-required"),
        "disks": disks,
        "mdraid": mdraid,
        "filesystems": filesystems,
        "etcd": etcd,
        "certificates_min_days_left": min((c["days_left"] for c in certificates), default=None),
        "problems": problems,
    }))


if __name__ == "__main__":
    main()
