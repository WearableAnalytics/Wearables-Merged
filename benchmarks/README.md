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
```
Steps already taken and implemented
- [x] Runner
- [x] Test-Benchmark (Test-Runner)
- [x] Ingestion-Service-Latency (maybe Throughput) 
- [x] Mapper-Throughput
- [x] End-to-end-Throughput
- [ ] ML-Pipeline?? Clarify how
---
### Next Steps (so I don't forget)
- [ ] Mapper: Processing Time with different Sampling Configs (0,1%, 1%, 10%, 100%)
- [ ] End-to-End: Processing Time different Message-Sizes
- [ ] End-to-End: Throughput
  - [ ] Test 10k msg/sec á 100KB



Make sure that the Job is able to runnable!
```shell
docker buildx build \
  --platform linux/amd64 \
  -t <username>/<image-name>:latest \
  --push .
```

