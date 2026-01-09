# LakeFS Helm Chart Deployment

This repository uses secret values from a separate file `my-secrets.yaml` which is gitignored for security reasons.

You need to create it yourself based on the `placeholder-secrets.yaml` file provided.

Then just deploy with:

helm upgrade --install my-lakefs . \
  --namespace lakefs \
  --create-namespace \
  -f values.yaml \
  -f my-secrets.yaml

## Accessing the LakeFS Web Interface
To access the web interface from your local machine, use double port forwarding pattern:

Run this on your local machine:
```bash
  ssh -L 8000:127.0.0.1:8000 yourusername@denbi-jumphost-01.bihealth.org    
```

Then on the jumphost, run:
```bash
  kubectl port-forward svc/my-lakefs 8000:80 -n lakefs
```

## First time setup

1. Credentials
After accessing the web interface for the first time, you will create acceess credentials.
They are automatically generate and stored in the database we use (here PostgreSQL). If we connect again, it will use the same credentials.

For example, you will see something like this:
      access_key_id: "AKIAIOSFOLEXAMPLE"
      secret_access_key: "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"

Save them somewhere safe, as you will need them to access lakeFS programmatically (and for Spark!!)

2. Create a repository

Login to UI, create a Repository (e.g., `test-lake-repo`) using the storage namespace `s3://lake-test` (this bucket must exist in SeaweedFS).

If you do not have the bucket create, you can create it for example with seaweedfs weed mount command (look into SeaweedFS README for more details).


## Further configurations

## The connection endpoint to SeaweedFS

The temporary URL to connect to SeaweedFS from lakeFS is:
http://<Service-Name>.<Namespace>.svc.cluster.local:<Port>

You need to replace `<Service-Name>`, `<Namespace>`, and `<Port>` with the actual values from your SeaweedFS deployment

To discover these values, you can use the following kubectl commands:

```bash
  kubectl get svc -n seaweedfs
```

and search for seaweedfs-s3 service

The final endpoint should look something like this:
http://seaweedfs-s3.seaweedfs.svc.cluster.local:8333

If you want further details on how to configure lakeFS use the official chart documentation:
https://github.com/treeverse/charts/blob/master/charts/lakefs/values.yaml

