package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"os"
	"strconv"
	"strings"
	"time"

	"github.com/3351666087/release-foundry/packages/go/releasefoundry"
)

const commandName = "releasefoundry-worker"

type workerCommandConfig struct {
	Options releasefoundry.WorkerDaemonOptions
}

func main() {
	log.SetOutput(os.Stderr)

	config, err := workerCommandConfigFromEnv(os.LookupEnv)
	if err != nil {
		log.Fatal(err)
	}

	selection, err := releasefoundry.NewBackendFromEnv()
	if err != nil {
		log.Fatal(err)
	}
	if selection.Migrate != nil {
		ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
		defer cancel()
		if err := selection.Migrate(ctx); err != nil {
			log.Fatalf("migrate backend %s: %v", selection.Name, err)
		}
		selection.Ready = true
	}
	if selection.Close != nil {
		defer func() {
			if err := selection.Close(); err != nil {
				log.Printf("close backend: %v", err)
			}
		}()
	}

	daemon := releasefoundry.WorkerDaemon{
		Repository: selection.Backend,
		Handler:    releasefoundry.WorkerJobHandlerFunc(handleWorkerJob),
		Options:    config.Options,
	}
	summary, err := daemon.Run(context.Background())
	if err != nil {
		log.Fatal(err)
	}

	encoder := json.NewEncoder(os.Stdout)
	encoder.SetIndent("", "  ")
	if err := encoder.Encode(summary); err != nil {
		log.Fatal(err)
	}
}

func handleWorkerJob(ctx context.Context, job releasefoundry.WorkerJob) (releasefoundry.JSONMap, error) {
	if err := ctx.Err(); err != nil {
		return nil, err
	}
	return releasefoundry.JSONMap{
		"handler":        commandName,
		"job_id":         job.JobID,
		"job_type":       job.JobType,
		"payload_sha256": job.PayloadSHA256,
		"public_safe":    true,
	}, nil
}

func workerCommandConfigFromEnv(lookup func(string) (string, bool)) (workerCommandConfig, error) {
	leaseSeconds, err := envInt(lookup, 0, "RELEASEFOUNDRY_WORKER_LEASE_SECONDS", "RELEASEFOUNDRY_LEASE_SECONDS")
	if err != nil {
		return workerCommandConfig{}, err
	}
	maxJobs, err := envInt(lookup, 0, "RELEASEFOUNDRY_WORKER_MAX_JOBS", "RELEASEFOUNDRY_MAX_JOBS")
	if err != nil {
		return workerCommandConfig{}, err
	}
	maxIdleLeases, err := envInt(lookup, 0, "RELEASEFOUNDRY_WORKER_MAX_IDLE_LEASES", "RELEASEFOUNDRY_MAX_IDLE_LEASES")
	if err != nil {
		return workerCommandConfig{}, err
	}
	heartbeatInterval, err := envDuration(lookup, 0, "RELEASEFOUNDRY_WORKER_HEARTBEAT_INTERVAL", "RELEASEFOUNDRY_HEARTBEAT_INTERVAL")
	if err != nil {
		return workerCommandConfig{}, err
	}

	options := releasefoundry.WorkerDaemonOptions{
		TenantID:          envString(lookup, "RELEASEFOUNDRY_WORKER_TENANT_ID", "RELEASEFOUNDRY_TENANT_ID"),
		ProjectID:         envString(lookup, "RELEASEFOUNDRY_WORKER_PROJECT_ID", "RELEASEFOUNDRY_PROJECT_ID"),
		LeaseOwnerID:      envString(lookup, "RELEASEFOUNDRY_WORKER_LEASE_OWNER_ID", "RELEASEFOUNDRY_LEASE_OWNER_ID"),
		JobType:           envString(lookup, "RELEASEFOUNDRY_WORKER_JOB_TYPE", "RELEASEFOUNDRY_JOB_TYPE"),
		LeaseSeconds:      leaseSeconds,
		MaxJobs:           maxJobs,
		MaxIdleLeases:     maxIdleLeases,
		HeartbeatInterval: heartbeatInterval,
		RequestID:         envString(lookup, "RELEASEFOUNDRY_WORKER_REQUEST_ID", "RELEASEFOUNDRY_REQUEST_ID"),
		APIKeyID:          envString(lookup, "RELEASEFOUNDRY_WORKER_API_KEY_ID", "RELEASEFOUNDRY_API_KEY_ID"),
	}
	return workerCommandConfig{Options: options}, nil
}

func envString(lookup func(string) (string, bool), keys ...string) string {
	for _, key := range keys {
		value, ok := lookup(key)
		if ok && strings.TrimSpace(value) != "" {
			return strings.TrimSpace(value)
		}
	}
	return ""
}

func envInt(lookup func(string) (string, bool), defaultValue int, keys ...string) (int, error) {
	value := envString(lookup, keys...)
	if value == "" {
		return defaultValue, nil
	}
	parsed, err := strconv.Atoi(value)
	if err != nil {
		return 0, fmt.Errorf("%s must be an integer: %w", keys[0], err)
	}
	return parsed, nil
}

func envDuration(lookup func(string) (string, bool), defaultValue time.Duration, keys ...string) (time.Duration, error) {
	value := envString(lookup, keys...)
	if value == "" {
		return defaultValue, nil
	}
	if seconds, err := strconv.Atoi(value); err == nil {
		return time.Duration(seconds) * time.Second, nil
	}
	parsed, err := time.ParseDuration(value)
	if err != nil {
		return 0, fmt.Errorf("%s must be a Go duration or integer seconds: %w", keys[0], err)
	}
	return parsed, nil
}
