kubectl get ns --no-headers -o custom-columns=":metadata.name" \
| grep -vE 'kube-system|kube-public|kube-node-lease|default' \
| xargs kubectl delete ns