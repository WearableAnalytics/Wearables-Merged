#!/usr/bin/env just --justfile

# just test_influx NAMESPACE=test
test_influx NAMESPACE:
    minikube start --memory=7000 --cpus=4
    kubectl create namespace {{NAMESPACE}}
    kubectl apply -f ./k8s/influxdb/influx-pvc.yml -n {{NAMESPACE}}
    kubectl apply -f ./k8s/influxdb/influx-deployment.yml -n {{NAMESPACE}}
