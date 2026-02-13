Benchmarking: Wearables-Analytical-Platform
---

#### Folder-Structure:

```shell
benchmarks/
|- runner/                  # Contains the Execution-Framework for the Benchmarks
|- benchmarks/              # Concrete implementations (Load-Generators)
    |- test/
    |- ingestion-service/
    |- mapper/
    |- end-to-end/          # ingestion-service -> influxdb
    |- ml-pipeline/         # @Lukasz should specify benchmarks for this service
    |- db-lord/             # @Oskar should specify benchmarks
    |- extraction-service/  # @Daniil should specify benchmarks
    |- registration-sevice/ # not clear if needed?
    |- frontend/            # qualitative evaluation?
```
Steps already taken and implemented
- [x] Runner
- [x] Test-Benchmark (Test-Runner)
- [x] Ingestion-Service-Latency (maybe Throughput) 
- [x] Mapper-Throughput (=> Approach Works)
- [ ] End-to-end-Throughput (=> Currently working on it)

---

Make sure that the Job is able to runnable!
```shell
docker buildx build \
  --platform linux/amd64 \
  -t <username>/<image-name>:latest \
  --push .
```

