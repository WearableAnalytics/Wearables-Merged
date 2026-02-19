kubectl create secret generic grafana-auth-secrets -n monitoring --from-file=GRAFANA_JWT_PRIVATE_KEY=secrets/grafana-jwt-private.pem --dry-run=client -o yaml | kubectl apply -f -

helm upgrade --install grafana-auth gitops/apps/monitoring/grafana-proxy -n monitoring -f gitops/apps/monitoring/grafana-proxy/values.yaml