
## Installation

```
    kubectl apply -k argo/
```

## Access UI

```
    kubectl port-forward deployment/argo-server 2746:2746 -n argo
````