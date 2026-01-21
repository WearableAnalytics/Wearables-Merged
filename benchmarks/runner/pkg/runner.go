package pkg

import (
	"fmt"
	"io"
	"log"
	"os"
	"strings"

	"github.com/melbahja/goph"
)

type Runner struct {
	config       *Config
	client       *goph.Client
	outputWriter io.WriteCloser
	logsWriter   io.WriteCloser
}

func NewRunner(cfg *Config) (*Runner, error) {
	auth, err := goph.Key(cfg.SSH.KeyPath, "")
	if err != nil {
		return nil, fmt.Errorf("failed to load SSH key: %v", err)
	}

	client, err := goph.New(cfg.SSH.User, cfg.SSH.Host, auth)
	if err != nil {
		return nil, fmt.Errorf("failed to create ssh client: %v", err)
	}

	r := &Runner{
		config: cfg,
		client: client,
	}

	if err := r.setupOutputWriter(); err != nil {
		client.Close()
		return nil, err
	}

	if err := r.setupLogsWriter(); err != nil {
		r.outputWriter.Close()
		client.Close()
		return nil, err
	}

	return r, nil
}

func (r *Runner) Run() error {
	if err := r.applyJob(); err != nil {
		return fmt.Errorf("error applying job: %v", err)
	}

	done := make(chan error, 1)
	go func() {
		done <- r.streamLogs()
	}()

	if err := r.waitForCompletion(); err != nil {
		return fmt.Errorf("error waiting for completion: %v", err)
	}

	if err := <-done; err != nil {
		log.Printf("log streaming ended with error: %v", err)
	}

	return r.cleanup()
}

func (r *Runner) Close() error {
	var errs []error

	if r.client != nil {
		if err := r.client.Close(); err != nil {
			errs = append(errs, err)
		}
	}

	if r.outputWriter != nil && r.outputWriter != os.Stdout {
		if err := r.outputWriter.Close(); err != nil {
			errs = append(errs, err)
		}
	}

	if r.logsWriter != nil && r.logsWriter != os.Stderr {
		if err := r.logsWriter.Close(); err != nil {
			errs = append(errs, err)
		}
	}

	if len(errs) > 0 {
		return fmt.Errorf("errors during cleanup: %v", errs)
	}

	return nil
}

func (r *Runner) applyJob() error {
	if err := r.uploadJobYAML(); err != nil {
		return fmt.Errorf("error uploading job-yaml: %v", err)
	}

	cmd := fmt.Sprintf(
		"kubectl apply -n %s -f %s",
		r.config.Job.Namespace,
		r.config.Paths.RemoteConfig,
	)

	resp, err := r.client.Run(cmd)
	if err != nil {
		return fmt.Errorf("running command failed with err: %v: %s", err, resp)
	}

	log.Printf("job applied: %s", string(resp))
	return nil
}

func (r *Runner) waitForCompletion() error {
	timeout := r.config.Timeout
	if timeout == "" {
		timeout = "5m"
	}

	cmd := fmt.Sprintf(
		"kubectl wait -n %s --for=condition=complete job/%s --timeout=%s",
		r.config.Job.Namespace,
		r.config.Job.Name,
		timeout,
	)

	if _, err := r.client.Run(cmd); err != nil {
		return fmt.Errorf("job did not complete: %w", err)
	}

	log.Printf("job completed successfully")
	return nil
}

func (r *Runner) streamLogs() error {
	if err := r.waitForPodRunning("2m"); err != nil {
		return fmt.Errorf("pod did not become ready: %v", err)
	}

	pod, err := r.getPodName()
	if err != nil {
		return err
	}

	cmd := fmt.Sprintf(
		"kubectl logs -n %s -f %s --all-containers=true",
		r.config.Job.Namespace,
		pod,
	)

	session, err := r.client.Client.NewSession()
	if err != nil {
		return err
	}
	defer session.Close()

	session.Stdout = r.outputWriter
	session.Stderr = r.logsWriter

	return session.Run(cmd)
}

func (r *Runner) cleanup() error {
	cmds := []string{
		fmt.Sprintf("kubectl delete job -n %s %s --ignore-not-found",
			r.config.Job.Namespace, r.config.Job.Name),
		fmt.Sprintf("rm -rf %s", r.config.Paths.RemoteConfig),
	}

	for _, cmd := range cmds {
		if _, err := r.client.Run(cmd); err != nil {
			log.Printf("cleanup error on command: %s : %v", cmd, err)
		}
	}

	return nil
}

func (r *Runner) uploadJobYAML() error {
	return r.client.Upload(r.config.Paths.LocalConfig, r.config.Paths.RemoteConfig)
}

func (r *Runner) setupOutputWriter() error {
	path := r.config.Paths.LocalOutput

	if path == "stdout" || path == "" {
		r.outputWriter = os.Stdout
		return nil
	}

	file, err := os.Create(path)
	if err != nil {
		return fmt.Errorf("failed to create output file: %v", err)
	}

	r.outputWriter = file
	return nil
}

func (r *Runner) setupLogsWriter() error {
	path := r.config.Paths.LocalLogs

	if path == "stderr" || path == "" {
		r.logsWriter = os.Stderr
		return nil
	}

	file, err := os.Create(path)
	if err != nil {
		return fmt.Errorf("failec to create logs file: %v", err)
	}

	r.logsWriter = file
	return nil
}

func (r *Runner) waitForPodRunning(timeout string) error {
	cmd := fmt.Sprintf(
		"kubectl wait -n %s --for=condition=Ready pod -l job-name=%s --timeout=%s",
		r.config.Job.Namespace,
		r.config.Job.Name,
		timeout,
	)

	resp, err := r.client.Run(cmd)
	if err != nil {
		return err
	}

	log.Printf("pod ready: %s", string(resp))
	return nil
}

func (r *Runner) getPodName() (string, error) {
	cmd := fmt.Sprintf(
		"kubectl get pod -n %s -l job-name=%s -o jsonpath='{.items[0].metadata.name}'",
		r.config.Job.Namespace,
		r.config.Job.Name,
	)

	out, err := r.client.Run(cmd)
	if err != nil {
		return "", err
	}

	return strings.Trim(string(out), "'\n"), nil
}
