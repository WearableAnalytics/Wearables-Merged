#!/usr/bin/env just --justfile

start NAMESPACE:
    minikube start --memory=7000 --cpus=4
    kubectl create namespace {{NAMESPACE}}

# just test_influx NAMESPACE=test
influx NAMESPACE:
    kubectl apply -f ./k8s/influxdb/influx.yml -n {{NAMESPACE}}

kafka NAMESPACE:
    kubectl apply -f 'https://strimzi.io/install/latest?namespace={{NAMESPACE}}'
    kubectl apply -f ./k8s/kafka/kafka.yml -n {{NAMESPACE}}
