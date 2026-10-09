# Storage concept

How the platform stores data on the de.NBI cluster, and how to rebuild it from scratch.

## Rule

**Data that must survive goes on Cinder volumes. Node disks only hold things that can be re-created.**

Kubermatic replaces worker nodes whenever their spec changes (flavor, image, OS profile), and
every replacement wipes the node disk. A volume (`StorageClass cinder-csi`) is detached from the
old node and attached to the new one.

| Where | What belongs there | Examples |
|---|---|---|
| Cinder volume (PVC, `cinder-csi`) | Databases, queues, time series, uploaded files, anything we can't regenerate | prod-postgres, InfluxDB, Kafka logs, Prometheus TSDB, Grafana DB, SeaweedFS volumes and master, Infisical, BayesPlatform DB/Redis/documents, Ollama models |
| Node disk (40 GB, `de.NBI k8c` local disk) | Container images, `emptyDir` scratch space, container logs | Image layers, Spark scratch, pod logs |
| Nowhere (prod-postgres instead) | SeaweedFS filer metadata | Stored in the `seaweedfs` database |

What follows from the rule:

- No `hostPath` and no `local-path` storage for anything stateful. The charts default to
  `cinder-csi`. `local-path` stays available only for local minikube/k3s tests
  (`STORAGE_CLASS=local-path ./setup-script.sh`).
- Data volumes are set to `Retain` (`gitops/setup/retain-data-volumes.sh`). `cinder-csi` uses
  `reclaimPolicy: Delete`, so without this a `helm uninstall` or a namespace delete would destroy
  the volume with its data.
- Big images (Spark notebook, ML images) need the 40 GB k8c disks. Keep at least 10 GB free
  per node, because the kubelet evicts pods below about 15% free.

## Node pools

The node pools are Kubermatic `MachineDeployment`s, kept in `gitops/cluster/machinedeployments/`:

| Pool | Flavor | Root disk | Purpose |
|---|---|---|---|
| wearables-node ×3 | de.NBI k8c (16 vCPU, 32 GB, 40 GB local) | local, no volume quota | Platform workloads |
| bayes-node | de.NBI small | 100 GB volume | BayesPlatform (label `workload=bayes`) |
| llm-node | de.NBI large | 50 GB volume | Ollama (taint `dedicated=llm`) |
| benchmark | de.NBI small | 20 GB volume | Benchmark runner |

`gitops/cluster/apply-machinedeployments.sh` diffs them against the cluster, and with `--apply`
applies them. Cluster IDs and SSH public keys are not in the repo; they come from a `cluster.env`
(see `cluster.env.example`).

## Quota (OpenStack project "Wearables", 2026-10-09)

- Compute: 112/112 cores, 224/224 GB RAM, 6/8 instances. A rolling node replacement (maxSurge 1)
  only works because Kubermatic deletes an old VM before creating the next one; with no headroom
  the next new VM waits for the quota (`InsufficientResources` on the Machine) until then.
- Volumes: 667 of 800 GB. That is about 330 GB of PVCs, 170 GB of root volumes (bayes, llm,
  benchmark), and 170 GB of unattached volumes (`extended-storage-1/2/3`, 50 GB each, and an
  unnamed 20 GB volume) that nothing in the cluster uses.

## Migrations from the old layout

1. **Retain on data volumes.** Run `gitops/setup/retain-data-volumes.sh` (use `--dry-run` first).
   This only changes the reclaim policy, so pods aren't touched.
2. **SeaweedFS master and filer off the node disk.** The master kept its Raft state in
   `hostPath /ssd/seaweed-master`, and filer and logs used `hostPath /storage/...`. The new values
   put the master on a 1 GiB volume and drop the rest (filer metadata is in Postgres). A
   StatefulSet's volumeClaimTemplates can't be changed in place, so:
   ```bash
   kubectl -n ml-pipeline-seaweedfs delete statefulset seaweedfs-master --cascade=orphan
   helm upgrade seaweedfs gitops/apps/ml-pipeline/seaweedfs -n ml-pipeline-seaweedfs
   kubectl -n ml-pipeline-seaweedfs delete pod seaweedfs-master-0
   ```
   The master rebuilds its topology from the volume servers' heartbeats. Volume data is on its own
   PVCs and is not touched.
3. **Unattached volumes.** Decide what to do with `extended-storage-1/2/3` and the unnamed 20 GB
   volume: delete them, or attach and copy what's needed. Deleting them frees 170 GB of quota.
4. **Kafka, prod-postgres, InfluxDB.** These already run on `cinder-csi`. Only the chart defaults
   changed, so a `helm upgrade` changes nothing for them.

## Status of the migrations (2026-10-09)

None of the migrations above have been run on the live cluster yet. They are on the project to-do
list. Until then the live cluster differs from this repo in two ways: the data volumes still use
`Delete`, and the SeaweedFS master still keeps its state in `hostPath`.

## Secrets and personal data

- No secrets in the repo. Passwords, keys and tokens come from environment variables or `.env`
  files outside git (`gitops/setup/.env.example` and `.../infisical/bootstrap/secrets.env.example`
  only hold `CHANGE_ME` placeholders). Chart values for credentials stay empty and are set by
  `setup-script.sh` with `--set-string`.
- No personal data either. SSH public keys, admin e-mail addresses and cluster IDs live next to
  the other secrets (`cluster.env`, `users.yml`, `.env`), never in tracked files.
- Until 2026-10-09 the repo contained the live prod-postgres, LakeFS and SeaweedFS credentials,
  and git history still has them. Treat any credential from before that date as leaked and rotate it.

## Building from scratch

1. Create the cluster in Kubermatic (OpenStack, de.NBI Berlin, Kubernetes 1.31, Cilium).
2. Node pools: `CLUSTER_ENV=... gitops/cluster/apply-machinedeployments.sh --apply`, then wait for
   all nodes to be `Ready`.
3. Platform: `gitops/setup/setup-script.sh` (see `gitops/setup/README.md` for the variables and
   secrets). It checks that the storage class exists and sets the data volumes to `Retain` at the end.
4. ML pipeline: `gitops/apps/ml-pipeline/deploy.sh`.
5. Restore data from backups into the fresh volumes (prod-postgres dump, InfluxDB backup).

Not covered yet: the BayesPlatform/LLM deployment lives on the `integration` branch, and some
releases were patched live (`kubectl patch`), which the charts have to catch up with.
