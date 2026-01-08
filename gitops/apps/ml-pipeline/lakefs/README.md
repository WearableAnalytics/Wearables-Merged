# LakeFS Helm Chart Deployment

This repository uses secret values from a separate file `my-secrets.yaml` which is gitignored for security reasons.

You need to create it yourself based on the `placeholder-secrets.yaml` file provided.

Then just deploy with:

helm upgrade --install my-lakefs . \
  --namespace lakefs \
  --create-namespace \
  -f my-secrets.yaml

