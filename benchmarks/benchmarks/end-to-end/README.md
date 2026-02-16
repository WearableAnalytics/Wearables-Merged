End-to-End Load Generator
---

Kubernetes-Job-Configuration:
```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: end-to-end-lg
spec:
  template:
    spec:
      restartPolicy: Never
      containers:
        - name: end-to-end-job
          image: stahlco/end-to-end-lg:latest
          env:
            # Target service endpoint
            - name: SERVICE_URL
              value: ""

            # InfluxDB connection settings
            - name: INFLUX_URL
              value: ""
            - name: INFLUX_TOKEN
              value: "<YOUR_INFLUXDB_TOKEN>"
            - name: INFLUX_ORG
              value: "wearables-project"
            - name: INFLUX_BUCKET
              value: "measurements"

            # Authentication token for API access
            - name: JWT_TOKEN
              value: "<YOUR_JWT_TOKEN>"

            # Load generation settings
            - name: MESSAGE_SIZE
              value: "1024"      # Message size in bytes (e.g. 1024 = 1KB)
            - name: RPS
              value: "100"       # Requests per second
            - name: RAMP_UP_DURATION
              value: "0"         # Ramp-up time in seconds
            - name: DURATION
              value: "60"        # Test duration in seconds
            - name: RAMP_DOWN_DURATION
              value: "0"         # Ramp-down time in seconds
```

For the benchmarks, Kubernetes internal DNS names were used (for example, *.svc.cluster.local). However, any URL is valid as long as it is accessible from within the cluster(e.g. ClusterIP services, internal load balancers, or other routable endpoints), because only this is tested.

---

Runner Config:
```yaml
ssh:
  user: "username"
  host: ""
  keyPath: "~/.ssh/github"
job:
  name: "end-to-end-lg"
  namespace: "default"
paths:
  localConfig: "../benchmarks/end-to-end/job-config.yaml"
  remoteConfig: "/tmp/end-to-end.yaml"
  localOutput: "../evaluation/measurements/end-to-end/file.csv"
  localLogs: "stderr"
timeout: "2m"
```

---


