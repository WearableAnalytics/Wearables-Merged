# wplug

This load-generator tries to optimize for usability. It tries to resolve message types at runtime using `JSON-Schema` and `yaml`-Configs.
**Therefore, the message-creation will introduce a bottleneck at some point!**
The primary use case, are smoke/soak and average-load test. If one would like to use it as breakpoint/stress-test/spike-test please rewrite:
`supplier.go` by introducing struct to json mappings.

---

### Introduction: Load Testing

Load Testing is an important concept to find breakpoints, test functionality under load and test system behavior.
Such a test must not test whether the system breaks, because probably if executed on your local machine the load generator will be the bottleneck.
This Load Generator only provides functionality for local setups, but can be extended in the future to run in remote setups.

A typical sequence of steps performed in a Load-Test:
1. Traffic Ramp-up (warm-up)
2. Actual Test (do not change the req/s)
3. Traffic Ramp-down (gracefully reduce the req/s till = 0)


There are several different types of workloads/tests, here is a list of the most commonly used ones:

#### Smoke Tests
Smoke Tests validate that your script works and that the system performs adequately under minimal load.
You should run a smoke test whenever a test script is created or updated. Smoke testing should also be done whenever the relevant application code is updated.

**Good Practice**
Run a smoke test as a first step, with the following goal: 
- Script has no errors
- System doesn't throw any errors
- Gather baseline performance metrics under minimal load

Keep the throughput small and duration short:
- You don't need to gradually increase (ramp-up) the load
- 2 to 20 virtual users (=> 2-20req/s)
- 30 sec to 3 minutes
- Means that the system receives just a couple KB/s

#### Average-load Tests
Average-load Tests assess how your system performs under expected normal conditions. 
Average-Load testing helps understand whether a system meets performance goals on a typical day (commonplace load).
Typical day here means when an average number of users access the application at the same time, doing normal, average work.

**Good Practice**
- Know the number of users and the typical throughput per process in the system.
- Gradually increase load to the target average
- ~ 5 min Ramp-up, 30 min Test, 5 min Ramp-down

#### Soak Tests
Soak Tests assess the reliability and performance of your system over extended periods. The soak test differs from an average-load test in test duration. 
In a soak test, the peak load duration (usually an average amount) extends several hours and even days.

**Good Practice**
- Configure the duration to be considerable longer than any other test
- If possible, re-use the average-load test script
- Run Average-load Tests before
- Monitor the backend resources and code efficiency.
- ~ 5 min Ramp-up, 8h - 48h Test, 5 min Ramp-down

#### Stress Tests
Stress Tests assess how a system performs at its limits when load exceeds the expected average.
The load pattern of a stress test resembles that of an average-load test. 
The main difference is higher load. To account for higher load, the ramp-up period takes longer in proportion to the load increase.

**Good Practice**
- Load should be higher than what the system experiences on average
- **Only run stress tests after running average-load tests**
- Re-use the Average-test script
- Expect worse performance compared to average load
- ~ 10 min Ramp-up, 30 min Test, 5 min Ramp-down

**Following Tests might introduce a severe bottleneck on the load-generator, especially tested locally**

#### Spike Tests
Spike tests are useful when the system may experience events of sudden and massive traffic.

**Good Practice**
- Focus on key processes in this test type. Assess whether the spike in traffic triggers the same or different processes
- The test often won't finish. Errors are common under these scenarios (=> Test Error-rate)
- ~ 2 min Ramp-up (e.g. to 2.000/10.000 users), 1 min Ramp-down
- **Test, tune, repeat**
- **Monitor the system**

#### Breakpoint Tests
Breakpoint testing aims to find system limits. Reasons you might want to know the limits include.

**Good Practice**
- Avoid breakpoint tests in elastic cloud environments (FaaS)
- Increase the load gradually
- System failure could mean different things to different teams
- Slow Ramp-up to an extreme high number of users (4h to 100.000 Users)

---