# Wearables Benchmark Suite

A unified, reproducible benchmarking framework for the **Wearables Analytical Platform** — covering ingestion performance, mapping throughput, end-to-end pipeline behavior, and ML pipeline evaluation. All benchmarks run as Kubernetes Jobs and are orchestrated via a remote SSH-based runner.

---

## Table of Contents

- [Repository Structure](#repository-structure)
- [Benchmark Status](#benchmark-status)
- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
- [Building Benchmark Images](#building-benchmark-images)
- [Runner Configuration](#runner-configuration)
- [Benchmark Jobs](#benchmark-jobs)
  - [End-to-End Load Generator](#end-to-end-load-generator)
  - [Ingestion Service Load Generator](#ingestion-service-load-generator)
  - [Kafka Test Producer](#kafka-test-producer)
- [Node Exclusivity](#node-exclusivity)
- [Evaluation & Baselines](#evaluation--baselines)
- [Roadmap](#roadmap)
- [Notes](#notes)

---

## Repository Structure
```
benchmarks/
├── runner/                  # SSH-based Kubernetes Job execution framework
└── evaluation/              # Jupyter Notebook to evaluate measurements
    ├── measurements/
    └── plots/
└── benchmarks/              # Concrete benchmark implementations (load generators)
    ├── test/                # Runner smoke test
    ├── ingestion-service/   # Ingestion service latency & throughput
    ├── mapper/              # Mapper throughput
    ├── end-to-end/          # ingestion-service → InfluxDB pipeline
    └── ml-pipeline/         # 'wearables-lp' → InfluxDB (through the ML Pipeline)
```

---

## Benchmark Status

| Benchmark                   | Implementation-Status | Notes                         | Execution-Status | Relevance                                  |
|-----------------------------|-----------------------|-------------------------------|------------------|--------------------------------------------|
| Runner                      | ✅ Complete            | Kubernetes Job Runner via SSH | ✅ Tested         |                                            |
| Test Benchmark              | ✅ Complete            | Runner smoke test             | ✅ Complete       |                                            |
| Ingestion Service Latency   | ✅ Complete            | Partial throughput included   | ⏳ Pending        | 📝 Final Report                            |
| Mapper Throughput           | ✅ Complete            |                               | ⏳ Pending        | 📝 Final Report                            |
| End-to-End Throughput       | ✅ Complete            |                               | ⏳ Pending        | 👩‍🏫 Final Presentation / 📝 Final Report |
| End-to-End Processing-Time  | ✅ Complete            |                               | ⏳ Pending        | 👩‍🏫 Final Presentation / 📝 Final Report |
| ML Pipeline Throughput      | ✅ Complete            |                               | ⏳ Pending        | 👩‍🏫 Final Presentation / 📝 Final Report |
| ML Pipeline Processing-Time | ✅ Complete            |                               | ⏳ Pending        | 👩‍🏫 Final Presentation / 📝 Final Report |

---

## Prerequisites

- Docker with `buildx` support (for building multi-arch images)
- SSH access to the Kubernetes jump host
- `kubectl` installed and configured on the jump host
- Access to a running Kubernetes cluster with latest `kubeconfig`
- InfluxDB instance with a valid org, bucket, and token
- Valid JWT token for API authentication

---

## Quick Start

### 1. Build and push a benchmark image
```shell
docker buildx build \
  --platform linux/amd64 \
  -t <username>/<image-name>:latest \
  --push .
```

### 2. Create a runner config
```yaml
# runner-config.yaml
ssh:
  user: "username"
  host: "your-jumphost.example.org"
  keyPath: "~/.ssh/id_rsa"

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

### 3. Run the benchmark

From the `runner/` directory:
```shell
go run cmd/main.go -c runner-config.yaml
```

The runner uploads the Job YAML via SSH, applies it to the cluster, streams logs in real time, waits for completion, and writes outputs locally.

> **Important:** Benchmark Jobs **must** write measurement data to `stdout` and diagnostic logs to `stderr`. The runner captures each stream independently.

---

## Building Benchmark Images

All benchmark clients are packaged as container images and run as Kubernetes Jobs.
```shell
docker buildx build \
  --platform linux/amd64 \
  -t <username>/<image-name>:latest \
  --push .
```

---

## Runner Configuration

| Field                | Description                                         |
|----------------------|-----------------------------------------------------|
| `ssh.user`           | SSH username for the jump host                      |
| `ssh.host`           | Hostname or IP of the jump host                     |
| `ssh.keyPath`        | Path to the SSH private key (`~` is expanded)       |
| `job.name`           | Must match `metadata.name` in the Job YAML          |
| `job.namespace`      | Kubernetes namespace to deploy the Job into         |
| `paths.localConfig`  | Local path to the Job YAML                          |
| `paths.remoteConfig` | Remote path where the YAML will be uploaded         |
| `paths.localOutput`  | Local file for `stdout` output (or `"stdout"`)      |
| `paths.localLogs`    | Local file for `stderr` logs (or `"stderr"`)        |
| `timeout`            | Maximum wait time for Job completion (e.g., `"5m"`) |

---

## Benchmark Jobs

### End-to-End Load Generator

Sends requests to the ingestion service and validates data arrives in InfluxDB.
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
            - name: SERVICE_URL
              value: ""
            - name: INFLUX_URL
              value: ""
            - name: INFLUX_TOKEN
              value: "<YOUR_INFLUXDB_TOKEN>"
            - name: INFLUX_ORG
              value: "wearables-project"
            - name: INFLUX_BUCKET
              value: "measurements"
            - name: JWT_TOKEN
              value: "<YOUR_JWT_TOKEN>"
            - name: MESSAGE_SIZE
              value: "1024"          # bytes — 1 KB
            - name: RPS
              value: "100"
            - name: RAMP_UP_DURATION
              value: "0"
            - name: DURATION
              value: "60"
            - name: RAMP_DOWN_DURATION
              value: "0"
```

> **Networking:** Benchmarks use Kubernetes internal DNS (e.g. `*.svc.cluster.local`). Any URL reachable from within the cluster is valid — ClusterIP, internal load balancer, or routable endpoints.

---

### Ingestion Service Load Generator

Targets the ingestion service directly with configurable payload sizes and RPS profiles.
```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: ingestion-service-lg
spec:
  template:
    spec:
      restartPolicy: Never
      containers:
        - name: ingestion-service-job
          image: stahlco/ingestion-service-lg:latest
          env:
            - name: SERVICE_URL
              value: ""
            - name: MESSAGE_SIZE
              value: "102400"        # bytes — 100 KB
            - name: RPS
              value: "10"
            - name: RAMP_UP_DURATION
              value: "10"
            - name: DURATION
              value: "45"
            - name: RAMP_DOWN_DURATION
              value: "5"
```

---

### Kafka Test Producer

Publishes messages directly to a Kafka topic for pipeline stress testing.
```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: kafka-test
spec:
  template:
    spec:
      restartPolicy: Never
      containers:
        - name: kafka-test
          image: stahlco/kafka-test:latest
          env:
            - name: KAFKA_URL
              value: "kafka-dual-role-0.kafka-kafka-brokers.kafka.svc.cluster.local:9092"
            - name: TOPIC
              value: "wearables-raw"
            - name: MESSAGE_SIZE
              value: "102400"        # bytes — 100 KB
            - name: RPS
              value: "1"
            - name: RAMP_UP_DURATION
              value: "10"
            - name: DURATION
              value: "30"
            - name: RAMP_DOWN_DURATION
              value: "5"
```

---

## Node Exclusivity

To ensure benchmark accuracy, run load generators on a dedicated node with no competing workloads.

**Taint the node:**
```shell
kubectl taint node <node-name> key1=value1:NoSchedule
```

**Add a toleration to the Job:**
```yaml
spec:
  template:
    spec:
      tolerations:
        - key: "key1"
          operator: "Equal"
          value: "value1"
          effect: "NoSchedule"
```

---
## Benchmark Setup
This section describes the hardware and system configuration used for all benchmark experiments.

#### System Under Test (SUT)
The System Under Tests runs on a Kubernetes-Cluster running on 3 OpenStack Worker Nodes.
All Nodes are provisioned as **[deNBI-medium](https://cloud.denbi.de/wiki/Concept/flavors/)** instances with identical hardware specification.

Common specifications:
- RAM: 32GB per node
- Architecture: x86_64
- CPU Model: AMD EPYC Rome
- vCPUs: 16
- Threads per core: 1

Results of `lscpu` on each Node:
###### Node 1
```
Architecture:             x86_64
  CPU op-mode(s):         32-bit, 64-bit
  Address sizes:          48 bits physical, 48 bits virtual
  Byte Order:             Little Endian
CPU(s):                   16
  On-line CPU(s) list:    0-15
Vendor ID:                AuthenticAMD
  Model name:             AMD EPYC-Rome Processor
    CPU family:           23
    Model:                49
    Thread(s) per core:   1
    Core(s) per socket:   1
    Socket(s):            16
    Stepping:             0
    BogoMIPS:             3992.49
```

###### Node 2
```
Architecture:             x86_64
  CPU op-mode(s):         32-bit, 64-bit
  Address sizes:          48 bits physical, 48 bits virtual
  Byte Order:             Little Endian
CPU(s):                   16
  On-line CPU(s) list:    0-15
Vendor ID:                AuthenticAMD
  Model name:             AMD EPYC-Rome Processor
    CPU family:           23
    Model:                49
    Thread(s) per core:   1
    Core(s) per socket:   1
    Socket(s):            16
    Stepping:             0
    BogoMIPS:             3992.49
```
###### Node 3
```
Architecture:             x86_64
  CPU op-mode(s):         32-bit, 64-bit
  Address sizes:          48 bits physical, 48 bits virtual
  Byte Order:             Little Endian
CPU(s):                   16
  On-line CPU(s) list:    0-15
Vendor ID:                AuthenticAMD
  Model name:             AMD EPYC-Rome Processor
    CPU family:           23
    Model:                49
    Thread(s) per core:   1
    Core(s) per socket:   1
    Socket(s):            16
    Stepping:             0
    BogoMIPS:             3992.50
```

All 3 Nodes are homogeneous to ensure consistent performance measurements and to eliminate hardware-related variance.

#### Load Generator
The benchmark load is generated from a dedicated **[deNBI-small](https://cloud.denbi.de/wiki/Concept/flavors/)** instance.
This node is **locked** to prevent Kubernetes from scheduling pods on it unless explicitly configured in the job specifications.

**Specification**:
```
Architecture:                x86_64
  CPU op-mode(s):            32-bit, 64-bit
  Address sizes:             46 bits physical, 57 bits virtual
  Byte Order:                Little Endian
CPU(s):                      8
  On-line CPU(s) list:       0-7
Vendor ID:                   GenuineIntel
  Model name:                Intel Xeon Processor (Icelake)
    CPU family:              6
    Model:                   134
    Thread(s) per core:      1
    Core(s) per socket:      1
    Socket(s):               8
    Stepping:                0
    BogoMIPS:                4589.14
```
This separation ensures that benchmark traffic generation does not interfere with the system under test.

#### Time Synchronization (NTP)
All nodes and the benchmark client are synchronized using NTP to guarantee accurate latency and throughput measurements.

Results chronyc:
###### Node 1:
```
Reference ID    : 10.57.196.5
Stratum         : 4
System time     : 0.000130769 seconds slow of NTP time
RMS offset      : 0.000139269 seconds
Leap status     : Normal
```

###### Node 2
```
Reference ID    : 10.57.196.5
Stratum         : 4
System time     : 0.000026985 seconds slow of NTP time
RMS offset      : 0.000057518 seconds
Leap status     : Normal
```

###### Node 3
```
Reference ID    : 10.57.196.5
Stratum         : 4
System time     : 0.000000015 seconds fast of NTP time
RMS offset      : 0.000078484 seconds
Leap status     : Normal
```

###### Benchmark Client
```
Reference ID    : 10.57.196.5
Stratum         : 4
System time     : 0.000017690 seconds fast of NTP time
RMS offset      : 0.000309231 seconds
Leap status     : Normal
```

The observed offsets are within sub-millisecond range, ensuring reliable timestamp-based measurements.


## Evaluation & Baselines

All benchmark results are stored locally after each run for offline analysis.

**Execution standards (required):**
- Each benchmark must be run **10 times** for statistical validity
- All message size variants must be tested: **10 KB / 100 KB / 1 MB**
- RPS profiles must be explicitly defined before each run
- All plots must share a consistent visual baseline (font size, style, color palette)

---

## Roadmap

- [x] Define plotting baseline (framework, font size, layout)
- [x] Define minimum execution standard for all benchmarks
- [ ] Mapper: processing time across sampling configs — `0.1% / 1% / 10% / 100%`
- [ ] End-to-End: throughput test — `10k msg/sec` with `100 KB` payloads
- [x] ML Pipeline: define scope and key metrics
- [ ] Add automatic namespace creation in runner
- [x] Trigger cleanup automatically on timeout expiration

---

## Notes

- `~` is expanded **only** for the SSH key path in the runner config.
- `job.name` in the runner config must exactly match `metadata.name` in the Job YAML.
- Cleanup errors are logged but do not fail the run — manual cleanup may be required in failure scenarios.
- Sensitive values (`INFLUX_TOKEN`, `JWT_TOKEN`) should be managed via **Kubernetes Secrets** in production rather than plain environment variables.