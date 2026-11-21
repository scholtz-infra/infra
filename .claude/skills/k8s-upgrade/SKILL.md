---
name: k8s-upgrade
description: Upgrade Kubernetes (kubeadm, kubelet, control plane) to a newer patch or minor version with a rolling upgrade.
---

# Upgrade Kubernetes

1. Target version: `curl -fsSL https://dl.k8s.io/release/stable.txt` for the newest release.
   Only one minor version per upgrade (1.37 -> 1.38, not 1.39). Read the changelog's
   "Urgent Upgrade Notes" for a minor upgrade and check that the pinned Cilium and Longhorn
   versions support the target; upgrade those first if needed (`platform-app`).
2. Health check must be green (`cluster-health`).
3. PR: change `kubernetes_version` in `inventory/production/group_vars/all.yml`.
4. After merge run `k8s-upgrade` (`run-workflow`). Control-plane nodes are upgraded first, one at
   a time (`kubeadm upgrade apply` on the first, `kubeadm upgrade node` on the others), each node
   is drained while its kubelet is upgraded. On a single-node cluster there is no drain and the
   API is briefly unavailable. Nodes already on the target version are skipped, so a failed run
   can simply be repeated after the fix.
5. Health check: every node reports the new kubelet version and is Ready.
