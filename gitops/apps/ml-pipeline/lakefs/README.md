# LakeFS Helm Chart Deployment

Secrets are managed by Infisical. The operator syncs the `lakefs-secrets` Kubernetes Secret
into the `ml-pipeline-lakefs` namespace automatically before this chart is deployed.

Deploy via the unified script:
```bash
./deploy.sh --start-from lakefs
```

Or manually:
```bash
cd lakefs && helm dependency build .
helm upgrade --install lakefs . \
  --namespace ml-pipeline-lakefs \
  -f values.yaml
```

## Accessing the LakeFS Web Interface

```bash
kubectl port-forward svc/lakefs 8000:80 -n ml-pipeline-lakefs
```

For remote access via a jumphost:
```bash
# On local machine:
ssh -L 8000:127.0.0.1:8000 yourusername@denbi-jumphost-01.bihealth.org

# On jumphost:
kubectl port-forward svc/lakefs 8000:80 -n ml-pipeline-lakefs
```

## First Time Setup

After accessing the web interface for the first time, create admin credentials. They are stored
in PostgreSQL and reused on subsequent logins.

Example credentials shown on first login:
```
access_key_id:     AKIAIOSFOLEXAMPLE
secret_access_key: wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
```

Save these — they are needed to access LakeFS programmatically (Spark, CLI, etc.).

Then create a repository (e.g. `test-lake-repo`) using storage namespace `s3://lake-test`
(the bucket must already exist in SeaweedFS).

## SeaweedFS Endpoint

```
http://seaweedfs-s3.ml-pipeline-seaweedfs.svc.cluster.local:8333
```

For full chart options: https://github.com/treeverse/charts/blob/master/charts/lakefs/values.yaml
