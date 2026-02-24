INFO: \
goos: darwin \
goarch: arm64 \
pkg: loadgen \
cpu: Apple M2 

##### Old Implementation

| Size  | Time  (ns) | Time(ms)    |
|-------|------------|-------------|
| 1KB   | 5488ns     | 0.005488ms  |
| 10KB  | 344720ns   | 0.34472ms   |
| 50KB  | 8187311ns  | 8.187311ms  |
| 100KB | 32679066ns | 32.679066ms |

##### New Implementation

| Size  | Time (ns)   | Time (ms)   |
|-------|-------------|-------------|
| 1KB   | 9942 ns     | 0.009942ms  |
| 10KB  | 872191 ns   | 0.872191ms  |
| 50KB  | 20083357 ns | 20.083357ms |
| 100KB | 78439696 ns | 78.439696ms |

=> But this will not be the bottleneck due to method GetData

goos: darwin \
goarch: arm64 \
pkg: loadgen \
cpu: Apple M2

| Benchmark                             | Iterations | ns/op | B/op | allocs/op |
|---------------------------------------|-----------:|------:|-----:|----------:|
| BenchmarkProvider_GetData/size_1024   | 19,910,251 | 53.20 |   16 |         2 |
| BenchmarkProvider_GetData/size_10240  | 23,735,037 | 52.15 |   16 |         2 |
| BenchmarkProvider_GetData/size_51200  | 23,769,848 | 53.73 |   16 |         2 |
| BenchmarkProvider_GetData/size_102400 | 20,620,195 | 53.98 |   16 |         2 |
