# Kubernetes Benchmark-Job Runner
This tool runs a Kubernetes `Job` on our remote cluster via `ssh`, streams its logs locally, and optionally writes `stdout/stderr`
to files for collecting benchmarking measurements gathered.

---
### Features
- SSH connection to a remote jump host (denbi)
- Upload and apply k8s Job YAMLs
- Stream pod logs in real time
- Write stdout/stderr to files or local stdout/stderr (console)
- Wait for Job completion with timeout
- Automatic cleanup of Jobs and temporary files
---
### Prerequisites
- SSH access to the jump host
- `kubectl` installed and configured on the jump host (follow the instructions on notion)
- Access to the target Kubernetes cluster
- Job writes measurements to `stdout` / `stderr`
---
### Quick Start

##### 1. Prepare the Kubernetes Job
Ensure your Job emits output to stdout/stderr.
```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: runner-test-job
spec:
  template:
    spec:
      restartPolicy: Never
      containers:
        - name: example
          image: golang:latest
          command: ["sh", "-c", "echo id,value && echo 1,hello"]
```
> [!WARNING]   
> The job **must write measurements to `stdout` and logs to `stderr`**.
> Otherwise, results cannot be streamed or captured. The format is not important.

##### 2. Create a Runner-Config (please replace the values)
```yaml
ssh:
  user: "user" 
  host: "denbi-jumphost.org"
  keyPath: "~/.ssh/id_rsa"

job:
  name: "runner-test-job"
  namespace: "default"  # namespace must exist

paths:
  localConfig: "./job.yaml"
  remoteConfig: "/tmp/job.yaml"
  localOutput: "stdout"
  localLogs: "stderr"

timeout: "5m"
```

##### 3. Run
Working-Directory should be `runner/`:
```shell
go run cmd/main.go -c runner-config.yaml
```
---
### Notes, Future Improvements
- `~` is expanded only for the SSH key path
- Job name must match `metadata.name` field in the k8s-job-config
- Cleanup errors are logged but do not fail the run (Must do it yourself!!)
- Add automatic namespace creation!
- Support split logs for multi-container set-ups
- Trigger Cleanup if timeout expires
