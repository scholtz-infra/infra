---
name: add-node
description: Add a Hetzner dedicated server to the Kubernetes cluster (scale up), as worker or as control-plane node, including growing from one server to a highly available three-node control plane.
---

# Add a server to the cluster

Needed from the owner: confirmation that the new server was prepared according to
`docs/server-setup.md` (Ubuntu LTS, RAID 1, user `infra`, SSH port set, login tested) and that
its lines, starting with the new inventory name, were added to the `NODE_IPS` and
`SSH_KNOWN_HOSTS` secrets in both environments. Agree on the inventory name first. Do not ask
for the address: it must not appear in the repository, a PR or an issue.

1. Decide the role:
   - `control_plane` must stay at 1, 3 or 5 hosts. Going HA means adding **two** servers to
     `control_plane` in the same PR (1 -> 3). Never leave it at 2.
   - Everything else goes to `workers`.
2. PR: add the host(s) to `inventory/production/hosts.yml`
   (`nodeN: {}`, no address). The inventory name becomes hostname and node name; never
   rename or reorder existing hosts.
3. After merge run `site` without a limit (`run-workflow`). It updates the firewall and the API
   load balancer on all existing nodes first, then joins the new nodes (control planes one by one)
   and re-applies the platform (Cilium operator and Longhorn replica counts follow the node count).
4. Run the health check: all nodes Ready, same kubelet version.
5. When the cluster reaches 3 nodes, tell the owner that existing Longhorn volumes still have
   one replica: raise their replica count in the Longhorn UI or per volume, new volumes get 3.
6. Remind the owner to add the new server as IP target of the Hetzner load balancer
   (`docs/setup.md` step 5). No DNS change is needed: all names point at the load balancer.

Removing a node is destructive and not automated yet: ask the owner, then drain, `kubectl delete
node`, and for control planes remove the etcd member first.
