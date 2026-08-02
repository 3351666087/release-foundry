package releasefoundry

import (
	"context"
	"fmt"
	"strings"
	"time"
)

const defaultWorkerDaemonLeaseSeconds = 300

type WorkerJobRepository interface {
	LeaseWorkerJob(tenantID, projectID, leaseOwnerID string, options LeaseWorkerJobOptions) (Envelope[WorkerLeaseResult], error)
	HeartbeatWorkerJob(tenantID, projectID, jobID, leaseOwnerID string, leaseSeconds int) (Envelope[WorkerJob], error)
	CompleteWorkerJob(tenantID, projectID, jobID, leaseOwnerID string, result JSONMap, options CompleteWorkerJobOptions) (Envelope[WorkerJob], error)
	FailWorkerJob(tenantID, projectID, jobID, leaseOwnerID string, failure JSONMap, options FailWorkerJobOptions) (Envelope[WorkerJob], error)
}

type WorkerJobHandler interface {
	HandleWorkerJob(context.Context, WorkerJob) (JSONMap, error)
}

type WorkerJobHandlerFunc func(context.Context, WorkerJob) (JSONMap, error)

func (fn WorkerJobHandlerFunc) HandleWorkerJob(ctx context.Context, job WorkerJob) (JSONMap, error) {
	return fn(ctx, job)
}

type WorkerDaemon struct {
	Repository WorkerJobRepository
	Handler    WorkerJobHandler
	Options    WorkerDaemonOptions
}

type WorkerDaemonOptions struct {
	TenantID          string
	ProjectID         string
	LeaseOwnerID      string
	JobType           string
	LeaseSeconds      int
	MaxJobs           int
	MaxIdleLeases     int
	HeartbeatInterval time.Duration
	RetryAfterSeconds *int
	APIKeyID          string
	RequestID         string
}

type WorkerDaemonRunSummary struct {
	SchemaVersion string      `json:"schema_version"`
	TenantID      string      `json:"tenant_id"`
	ProjectID     string      `json:"project_id"`
	LeaseOwnerID  string      `json:"lease_owner_id"`
	JobType       string      `json:"job_type,omitempty"`
	Leased        int         `json:"leased"`
	Completed     int         `json:"completed"`
	Failed        int         `json:"failed"`
	Retrying      int         `json:"retrying"`
	DeadLettered  int         `json:"dead_lettered"`
	IdleLeases    int         `json:"idle_leases"`
	LeaseSeconds  int         `json:"lease_seconds"`
	MaxJobs       int         `json:"max_jobs"`
	Heartbeat     bool        `json:"heartbeat_enabled"`
	Heartbeats    int         `json:"heartbeats"`
	HeartbeatErrs int         `json:"heartbeat_errors"`
	Jobs          []WorkerJob `json:"jobs"`
	StartedAt     time.Time   `json:"started_at"`
	FinishedAt    time.Time   `json:"finished_at"`
}

type workerDaemonHeartbeatSummary struct {
	count  int
	errors int
}

func (daemon WorkerDaemon) Run(ctx context.Context) (summary WorkerDaemonRunSummary, err error) {
	options := normalizeWorkerDaemonOptions(daemon.Options)
	summary = WorkerDaemonRunSummary{SchemaVersion: ControlPlaneSchemaVersion, TenantID: options.TenantID, ProjectID: options.ProjectID, LeaseOwnerID: options.LeaseOwnerID, JobType: options.JobType, Jobs: []WorkerJob{}, LeaseSeconds: options.LeaseSeconds, MaxJobs: options.MaxJobs, Heartbeat: options.HeartbeatInterval > 0, StartedAt: time.Now().UTC()}
	defer func() { summary.FinishedAt = time.Now().UTC() }()

	if daemon.Repository == nil {
		return summary, fmt.Errorf("worker daemon repository is required")
	}
	if daemon.Handler == nil {
		return summary, fmt.Errorf("worker daemon handler is required")
	}
	if strings.TrimSpace(options.TenantID) == "" {
		return summary, fmt.Errorf("tenant_id is required")
	}
	if strings.TrimSpace(options.ProjectID) == "" {
		return summary, fmt.Errorf("project_id is required")
	}
	if strings.TrimSpace(options.LeaseOwnerID) == "" {
		return summary, fmt.Errorf("lease_owner_id is required")
	}

	for summary.Leased < options.MaxJobs && summary.IdleLeases < options.MaxIdleLeases {
		if err := ctx.Err(); err != nil {
			return summary, err
		}
		lease, err := daemon.Repository.LeaseWorkerJob(options.TenantID, options.ProjectID, options.LeaseOwnerID, LeaseWorkerJobOptions{LeaseSeconds: options.LeaseSeconds, JobType: options.JobType, APIKeyID: options.APIKeyID, RequestID: options.RequestID})
		if err != nil {
			return summary, err
		}
		if !lease.Result.Leased || lease.Result.Job == nil {
			summary.IdleLeases++
			continue
		}

		leasedJob := *lease.Result.Job
		summary.Leased++
		finished, heartbeatSummary, err := daemon.handleLeasedJob(ctx, leasedJob, options)
		if err != nil {
			return summary, err
		}
		summary.Heartbeats += heartbeatSummary.count
		summary.HeartbeatErrs += heartbeatSummary.errors
		if finished.Status == WorkerJobStatusCompleted {
			summary.Completed++
		} else if finished.Status == WorkerJobStatusRetrying {
			summary.Failed++
			summary.Retrying++
		} else if finished.Status == WorkerJobStatusDeadLettered {
			summary.Failed++
			summary.DeadLettered++
		}
		summary.Jobs = append(summary.Jobs, finished)
	}
	return summary, nil
}

func (daemon WorkerDaemon) RunOnce(ctx context.Context) (WorkerDaemonRunSummary, error) {
	copy := daemon
	copy.Options.MaxJobs = 1
	if copy.Options.MaxIdleLeases == 0 {
		copy.Options.MaxIdleLeases = 1
	}
	return copy.Run(ctx)
}

func (daemon WorkerDaemon) handleLeasedJob(ctx context.Context, job WorkerJob, options WorkerDaemonOptions) (WorkerJob, workerDaemonHeartbeatSummary, error) {
	var stopHeartbeat chan struct{}
	var heartbeatDone chan workerDaemonHeartbeatSummary
	if options.HeartbeatInterval > 0 {
		stopHeartbeat = make(chan struct{})
		heartbeatDone = make(chan workerDaemonHeartbeatSummary, 1)
		go daemon.heartbeatUntilStopped(options, job.JobID, stopHeartbeat, heartbeatDone)
	}

	result, handlerErr := daemon.Handler.HandleWorkerJob(ctx, job)
	heartbeatSummary := workerDaemonHeartbeatSummary{}
	if stopHeartbeat != nil {
		close(stopHeartbeat)
		heartbeatSummary = <-heartbeatDone
	}
	if ctxErr := ctx.Err(); ctxErr != nil {
		return job, heartbeatSummary, ctxErr
	}
	if handlerErr != nil {
		failure := publicWorkerDaemonFailure(handlerErr)
		failed, err := daemon.Repository.FailWorkerJob(options.TenantID, options.ProjectID, job.JobID, options.LeaseOwnerID, failure, FailWorkerJobOptions{RetryAfterSeconds: options.RetryAfterSeconds, APIKeyID: options.APIKeyID, RequestID: options.RequestID})
		if err != nil {
			return job, heartbeatSummary, err
		}
		return failed.Result, heartbeatSummary, nil
	}
	completed, err := daemon.Repository.CompleteWorkerJob(options.TenantID, options.ProjectID, job.JobID, options.LeaseOwnerID, defaultJSONMap(result), CompleteWorkerJobOptions{APIKeyID: options.APIKeyID, RequestID: options.RequestID})
	if err != nil {
		return job, heartbeatSummary, err
	}
	return completed.Result, heartbeatSummary, nil
}

func (daemon WorkerDaemon) heartbeatUntilStopped(options WorkerDaemonOptions, jobID string, stop <-chan struct{}, done chan<- workerDaemonHeartbeatSummary) {
	summary := workerDaemonHeartbeatSummary{}
	defer func() { done <- summary }()
	ticker := time.NewTicker(options.HeartbeatInterval)
	defer ticker.Stop()
	for {
		select {
		case <-stop:
			return
		case <-ticker.C:
			if _, err := daemon.Repository.HeartbeatWorkerJob(options.TenantID, options.ProjectID, jobID, options.LeaseOwnerID, options.LeaseSeconds); err != nil {
				summary.errors++
			} else {
				summary.count++
			}
		}
	}
}

func normalizeWorkerDaemonOptions(options WorkerDaemonOptions) WorkerDaemonOptions {
	if options.LeaseSeconds <= 0 {
		options.LeaseSeconds = defaultWorkerDaemonLeaseSeconds
	}
	if options.MaxJobs <= 0 {
		options.MaxJobs = 1
	}
	if options.MaxIdleLeases <= 0 {
		options.MaxIdleLeases = 1
	}
	return options
}

func publicWorkerDaemonFailure(err error) JSONMap {
	message := strings.TrimSpace(err.Error())
	if message == "" {
		message = "worker job failed"
	}
	failure := JSONMap{"type": "worker_handler_error", "message": message}
	redacted, ok := RedactSensitive(failure).(map[string]any)
	if !ok {
		return failure
	}
	return JSONMap(redacted)
}
