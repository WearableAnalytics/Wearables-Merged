#!/usr/bin/env just --justfile

test_influx:
    minikube start --memory=7000 --cpus=4
    kubectl create namespace test_influx
    kubectl apply -f ./k8s/influx-deployment.yml -n kafka
    echo "Sleeping for 5 sek..."
    sleep 5
    kubectl port-foward svc/influx-service -n kafka 8086:8086
