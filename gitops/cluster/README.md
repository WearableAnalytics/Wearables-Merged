# Cluster node pools

Kubermatic `MachineDeployment`s for the de.NBI cluster: one file per node pool. See
[docs/storage-concept.md](../../docs/storage-concept.md) for flavors, disks and quota.

```bash
cp cluster.env.example cluster.env   # fill in the IDs (git-ignored)
./apply-machinedeployments.sh         # diff against the cluster
./apply-machinedeployments.sh --apply # apply
```

Any change under `spec.template` (flavor, disk, image, SSH keys, labels) makes Kubermatic replace
every node of that pool, one at a time. Run the diff first, and only apply during a maintenance window.
