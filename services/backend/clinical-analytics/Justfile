#!/usr/bin/env just --justfile

# just test_influx NAMESPACE=test
test_influx NAMESPACE=test:
    minikube start --memory=7000 --cpus=4
    kubectl create namespace {{NAMESPACE}}
    kubectl apply -f ./k8s/influxdb/influx-deployment.yml -n {{NAMESPACE}}
    echo "Sleeping for 5 sek..."
    sleep 5
    kubectl port-forward svc/influx-service -n {{NAMESPACE}} 8086:8086
