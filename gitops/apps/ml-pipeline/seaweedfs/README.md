# SeaweedFS deployment via official Helm chart
We use the official helm chart from here:
https://github.com/seaweedfs/seaweedfs/tree/master/k8s/charts/seaweedfs

## 1. Add the official helm chart to helm repo
```bash
	helm repo add seaweedfs https://seaweedfs.github.io/seaweedfs/helm
	helm repo update
	helm repo list
```
## 2. Create the kubectl namespace and secrets

Create namespace
```bash
	kubectl create namespace seaweedfs
```
Create secrets
```bash
	kubectl create secret generic seaweedfs-secret \
  --from-literal=admin_access_key_id=admin \
  --from-literal=admin_secret_access_key=admin123 \
  --from-literal=read_access_key_id=readonly \
  --from-literal=read_secret_access_key=readonly123 \
  -n seaweedfs
```

Check with

```bash
	kubectl get secrets --namespace seaweedfs
```

Should display something like

NAME               TYPE     DATA   AGE
seaweedfs-secret   Opaque   4      11s

## 3. Claim the appropriate Persistent Volume in OpenStack
Find the real ID of openstack volume from output 

https://denbi-cloud.bihealth.org/dashboard/project/volumes/9f343329-2b97-453a-964c-bb641cb3b70a/

NAME pvc-d53d6734-90b2-4ba0-9b37-a0b19e0e93c5
ID 9f343329-2b97-453a-964c-bb641cb3b70a
Description Created by OpenStack Cinder CSI driver
Project ID c0c03998d10140a98cb2597f4d6511ae

```bash
    kubectl apply -f templates/bind-openstack-volume.yaml
```

Claim the openstack volume with appropriate name for helm chart

```bash
    kubectl apply -f templates/adopt-volume.yaml
```


## 4. Install the helm chart from the root of this folder
You need to have values.yaml file in here

If you want to first run dry run you can append the ` --dry-run --debug `

```bash
helm upgrade --install seaweedfs seaweedfs/seaweedfs \
  -n seaweedfs \
  -f values.yaml \
  --version 3.59
```

## 5. See all pvcs - one should be claimed by seaweedfs

It should be called `data-seaweedfs-volume-0`
```bash
	kubectl get pv
```

## 6. Debugging

#### If some issues persist you can check the following:

```bash
    kubectl describe pod seaweedfs-volume-0 -n seaweedfs
    kubectl logs seaweedfs-volume-0 -n seaweedfs
```

#### Delete pvc if not binded to appropriate volume in OpenStack

```bash
    kubectl delete pvc data-seaweedfs-volume-0 -n seaweedfs --force --grace-period=0
```

#### Run temporary curl pod

```bash
    kubectl run -it --rm --image=curlimages/curl sw-test -n seaweedfs -- sh
```

From inside the pod you can test the seaweedfs filer service

```bash
    # Write
    curl -X PUT http://seaweedfs-filer:8888/test.txt -d "Success"

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
 - [ ] Clean the repo
 - [ ] better readme
 - [ ] Add admin panel
 - [ ] Use secrets corrently
 - [ ] Use encryption
 - [ ] Schedule workers