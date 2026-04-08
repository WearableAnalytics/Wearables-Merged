# SeaweedFS deployment 
We use Umbrella Chart pattern to deploy SeaweedFS with the official Helm chart as dependency.

We use the official helm chart from here:
https://github.com/seaweedfs/seaweedfs/tree/master/k8s/charts/seaweedfs

THIS COMMANDS ASSUME YOU ARE IN THE ROOT OF THIS FOLDER (gitops/apps/ml-pipeline/seaweedfs)
Otherwise adjust the paths accordingly.

## 1. Build Dependencies
First, download the upstream SeaweedFS chart into your charts folder (you only do this once or when updating versions).

```bash
    helm dependency build .
```

You should see something like this: "Successfully got an update from the "https://seaweedfs.github.io/seaweedfs/helm" chart repository" and new folder `charts/` created with the seaweedfs chart inside (`.tgz` file).

## 2. Deploy 
We set the password secrets values via --set, the ids are hardcoded in the values.yaml file for simplicity.

```bash
    helm upgrade --install seaweedfs . \
    --namespace seaweedfs \
    --create-namespace \
```

If you want to first run dry run you can append the ` --dry-run --debug `

Next upgrades / revisions can be done with simple `helm upgrade --install seaweedfs . -n seaweedfs`

If you want to destroy the deployment later you can use:

```bash
   helm uninstall seaweedfs -n seaweedfs
```

## 4. See all pvcs - one should be claimed by seaweedfs

It should be called `data-seaweedfs-volume-0`
```bash
	kubectl get pv
```

## 5. Debugging

#### If some issues persist you can check the following:

```bash
    kubectl describe pod seaweedfs-volume-0 -n seaweedfs
    kubectl logs seaweedfs-volume-0 -n seaweedfs
```


#### Check secrets with

```bash
	kubectl get secrets --namespace seaweedfs
```


Should display something like

NAME                              TYPE                 DATA   AGE
seaweedfs-s3-secret               Opaque               5      5m21s
seaweedfs-secret                  Opaque               4      5m21s
secret-seaweedfs-db               Opaque               2      5m21s
sh.helm.release.v1.seaweedfs.v1   helm.sh/release.v1   1      5m21s

#### Delete pvc if not binded to appropriate volume in OpenStack
```bash
    kubectl patch pv pvc-72ed65e7-58e1-47a0-aa30-32455261b6cc -p '{"metadata":{"finalizers":null}}'
    kubectl delete pvc data-seaweedfs-volume-0 -n seaweedfs --force --grace-period=0
    # kubectl delete pv  pvc-72ed65e7-58e1-47a0-aa30-32455261b6cc --force --grace-period=0
```

#### Run temporary curl pod

```bash
    kubectl run -it --rm --image=curlimages/curl sw-test -n seaweedfs -- sh
```

From inside the pod you can test the seaweedfs filer service

```bash
    # Write
    curl -X PUT http://seaweedfs-filer:8888/test.txt -d "Success\n"

    # Read
    curl http://seaweedfs-filer:8888/test.txt
```

Then enter the filer shell to see the volumes

```bash
    kubectl exec -it seaweedfs-master-0 -n seaweedfs -- weed shell
```

see the volume list
```
    volume.list
```
check the disk space
```
    fs.du
```

# Might do later
- [x] Clean the repo
- [x] Better readme
- [x] Use secrets correctly
- [ ] Use encryption (UPDATE 02.2026: we do not need it right now)
- [ ] Schedule workers (UPDATE 02.2026: we do not need them right now)
- [ ] Add admin panel (UPDATE 02.2026: the upstream chart does not support it, failed after many attempts)
