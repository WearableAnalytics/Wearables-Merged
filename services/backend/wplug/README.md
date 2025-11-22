# wplug

This load-generator tries to optimize for usability. It tries to resolve message types at runtime using `JSON-Schema` and `yaml`-Configs.
**Therefore, the message-creation will introduce a bottleneck at some point!**
The primary use case, are smoke/soak and average-load test. If one would like to use it as breakpoint/stress-test/spike-test please rewrite:
`supplier.go` by introducing struct to json mappings.