package releasefoundry

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"time"
)

type OAuthRevocationProviderResolver interface {
	OAuthRevocationProvider(context.Context, string) (OAuthProviderAdapter, error)
}

type OAuthRevocationWorkerOptions struct {
	Store         OAuthRevocationOutboxStore
	Vault         OAuthOpaqueVault
	Providers     OAuthRevocationProviderResolver
	Credentials   OAuthCredentialsProvider
	LeaseOwner    string
	LeaseDuration time.Duration
	BaseBackoff   time.Duration
	MaxBackoff    time.Duration
	CallTimeout   time.Duration
	Now           func() time.Time
}

type OAuthRevocationWorker struct {
	store         OAuthRevocationOutboxStore
	vault         OAuthOpaqueVault
	providers     OAuthRevocationProviderResolver
	credentials   OAuthCredentialsProvider
	leaseOwner    string
	leaseDuration time.Duration
	baseBackoff   time.Duration
	maxBackoff    time.Duration
	callTimeout   time.Duration
	now           func() time.Time
}

type OAuthRevocationPublicEvent struct {
	Type     string  `json:"type"`
	Metadata JSONMap `json:"metadata"`
}

type OAuthRevocationBatchResult struct {
	Claimed      int
	Delivered    int
	Retried      int
	DeadLettered int
	Events       []OAuthRevocationPublicEvent
}

func NewOAuthRevocationWorker(options OAuthRevocationWorkerOptions) (*OAuthRevocationWorker, error) {
	if options.Store == nil || options.Vault == nil || options.Providers == nil || options.Credentials == nil {
		return nil, fmt.Errorf("OAuth revocation worker dependencies are required")
	}
	if strings.TrimSpace(options.LeaseOwner) == "" {
		return nil, fmt.Errorf("OAuth revocation worker lease owner is required")
	}
	if options.LeaseDuration == 0 {
		options.LeaseDuration = time.Minute
	}
	if options.BaseBackoff == 0 {
		options.BaseBackoff = 5 * time.Second
	}
	if options.MaxBackoff == 0 {
		options.MaxBackoff = time.Hour
	}
	if options.CallTimeout == 0 {
		options.CallTimeout = options.LeaseDuration / 2
		if options.CallTimeout > 30*time.Second {
			options.CallTimeout = 30 * time.Second
		}
	}
	if options.LeaseDuration < 5*time.Second || options.LeaseDuration > time.Hour {
		return nil, fmt.Errorf("OAuth revocation worker lease duration is invalid")
	}
	if options.BaseBackoff < time.Second || options.MaxBackoff < options.BaseBackoff || options.MaxBackoff > 24*time.Hour {
		return nil, fmt.Errorf("OAuth revocation worker backoff is invalid")
	}
	if options.CallTimeout < time.Second || options.CallTimeout >= options.LeaseDuration {
		return nil, fmt.Errorf("OAuth revocation worker call timeout must be positive and shorter than the lease")
	}
	if options.Now == nil {
		options.Now = time.Now
	}
	return &OAuthRevocationWorker{
		store: options.Store, vault: options.Vault, providers: options.Providers,
		credentials: options.Credentials, leaseOwner: options.LeaseOwner,
		leaseDuration: options.LeaseDuration, baseBackoff: options.BaseBackoff,
		maxBackoff: options.MaxBackoff, callTimeout: options.CallTimeout,
		now: options.Now,
	}, nil
}

func (worker *OAuthRevocationWorker) ProcessBatch(
	ctx context.Context,
	tenantID string,
	projectID string,
	limit int,
) (OAuthRevocationBatchResult, error) {
	tasks, err := worker.store.ClaimOAuthRevocations(
		ctx, tenantID, projectID, worker.leaseOwner, limit,
		worker.leaseDuration, worker.now().UTC(),
	)
	if err != nil {
		return OAuthRevocationBatchResult{}, err
	}
	result := OAuthRevocationBatchResult{Claimed: len(tasks)}
	var batchErrors []error
	for _, task := range tasks {
		now := worker.now().UTC()
		if err := validateOAuthRevocationTask(task, worker.leaseOwner, now); err != nil {
			if fenceErr := validateOAuthRevocationFence(task, now); fenceErr != nil {
				batchErrors = append(batchErrors, errors.Join(err, fenceErr))
				continue
			}
			if deadLetterErr := worker.store.DeadLetterOAuthRevocation(
				ctx, task, "malformed_task", now,
			); deadLetterErr != nil {
				batchErrors = append(batchErrors, errors.Join(err, deadLetterErr))
				continue
			}
			result.DeadLettered++
			result.Events = append(result.Events, OAuthRevocationPublicEvent{
				Type: "oauth.revocation.dead_lettered",
				Metadata: JSONMap{
					"failure_code": "malformed_task",
				},
			})
			continue
		}
		processedTask, err := worker.processTask(ctx, task)
		if err != nil {
			deadLettered, _, retryErr := worker.store.RetryOAuthRevocation(
				ctx,
				processedTask,
				oauthRevocationFailureCode(err),
				worker.baseBackoff,
				worker.maxBackoff,
				worker.now().UTC(),
			)
			if retryErr != nil {
				batchErrors = append(batchErrors, errors.Join(err, retryErr))
				continue
			}
			if deadLettered {
				result.DeadLettered++
				event, eventErr := oauthRevocationPublicEvent(
					"oauth.revocation.dead_lettered", processedTask,
					oauthRevocationFailureCode(err),
				)
				if eventErr != nil {
					batchErrors = append(batchErrors, eventErr)
				} else {
					result.Events = append(result.Events, event)
				}
			} else {
				result.Retried++
				event, eventErr := oauthRevocationPublicEvent(
					"oauth.revocation.retry_scheduled", processedTask,
					oauthRevocationFailureCode(err),
				)
				if eventErr != nil {
					batchErrors = append(batchErrors, eventErr)
				} else {
					result.Events = append(result.Events, event)
				}
			}
			continue
		}
		result.Delivered++
		event, eventErr := oauthRevocationPublicEvent(
			"oauth.revocation.delivered", processedTask, "",
		)
		if eventErr != nil {
			batchErrors = append(batchErrors, eventErr)
		} else {
			result.Events = append(result.Events, event)
		}
	}
	return result, errors.Join(batchErrors...)
}

func (worker *OAuthRevocationWorker) processTask(
	ctx context.Context,
	task OAuthRevocationTask,
) (OAuthRevocationTask, error) {
	var err error
	task, err = worker.renewLease(ctx, task)
	if err != nil {
		return task, fmt.Errorf("lease_renewal_failed: %w", err)
	}
	callCtx, cancel := context.WithTimeout(ctx, worker.callTimeout)
	provider, err := worker.providers.OAuthRevocationProvider(callCtx, task.Provider)
	cancel()
	if err != nil {
		return task, fmt.Errorf("provider_unavailable: %w", err)
	}
	if provider == nil || provider.Name() != task.Provider {
		return task, fmt.Errorf("provider_mismatch")
	}
	if task.ProviderRevokedAt == nil {
		task, err = worker.renewLease(ctx, task)
		if err != nil {
			return task, fmt.Errorf("lease_renewal_failed: %w", err)
		}
		callCtx, cancel = context.WithTimeout(ctx, worker.callTimeout)
		tokenPayload, err := worker.vault.Get(callCtx, task.OpaqueRef)
		cancel()
		if err != nil {
			return task, fmt.Errorf("vault_read_failed: %w", err)
		}
		token := string(tokenPayload)
		if strings.TrimSpace(token) == "" {
			return task, fmt.Errorf("vault_token_empty")
		}
		task, err = worker.renewLease(ctx, task)
		if err != nil {
			return task, fmt.Errorf("lease_renewal_failed: %w", err)
		}
		callCtx, cancel = context.WithTimeout(ctx, worker.callTimeout)
		credentials, err := worker.credentials.OAuthCredentials(callCtx, task.Provider)
		cancel()
		if err != nil {
			return task, fmt.Errorf("credentials_unavailable: %w", err)
		}
		task, err = worker.renewLease(ctx, task)
		if err != nil {
			return task, fmt.Errorf("lease_renewal_failed: %w", err)
		}
		callCtx, cancel = context.WithTimeout(ctx, worker.callTimeout)
		err = provider.RevokeToken(callCtx, credentials, token)
		cancel()
		if err != nil {
			return task, fmt.Errorf("provider_revoke_failed: %w", err)
		}
		if err := worker.store.MarkOAuthProviderRevoked(ctx, task, worker.now().UTC()); err != nil {
			return task, fmt.Errorf("provider_checkpoint_failed: %w", err)
		}
	}
	if task.VaultDeletedAt == nil {
		// OAuthOpaqueVault.Delete implementations used by the worker must be
		// idempotent so a crash between deletion and this checkpoint is safe.
		task, err = worker.renewLease(ctx, task)
		if err != nil {
			return task, fmt.Errorf("lease_renewal_failed: %w", err)
		}
		callCtx, cancel = context.WithTimeout(ctx, worker.callTimeout)
		err = worker.vault.Delete(callCtx, task.OpaqueRef)
		cancel()
		if err != nil {
			return task, fmt.Errorf("vault_delete_failed: %w", err)
		}
		if err := worker.store.MarkOAuthVaultDeleted(ctx, task, worker.now().UTC()); err != nil {
			return task, fmt.Errorf("vault_checkpoint_failed: %w", err)
		}
	}
	if err := worker.store.CompleteOAuthRevocation(ctx, task, worker.now().UTC()); err != nil {
		return task, fmt.Errorf("completion_failed: %w", err)
	}
	return task, nil
}

func (worker *OAuthRevocationWorker) renewLease(
	ctx context.Context,
	task OAuthRevocationTask,
) (OAuthRevocationTask, error) {
	return worker.store.RenewOAuthRevocationLease(
		ctx, task, worker.leaseDuration, worker.now().UTC(),
	)
}

func oauthRevocationFailureCode(err error) string {
	message := strings.ToLower(err.Error())
	for _, code := range []string{
		"lease_renewal_failed",
		"provider_unavailable", "provider_mismatch", "vault_read_failed",
		"vault_token_empty", "credentials_unavailable", "provider_revoke_failed",
		"provider_checkpoint_failed", "vault_delete_failed",
		"vault_checkpoint_failed", "completion_failed",
	} {
		if strings.Contains(message, code) {
			return code
		}
	}
	return "revocation_failed"
}

func oauthRevocationPublicEvent(
	eventType string,
	task OAuthRevocationTask,
	failureCode string,
) (OAuthRevocationPublicEvent, error) {
	metadata := JSONMap{}
	switch eventType {
	case "oauth.revocation.delivered":
		metadata = JSONMap{
			"provider": task.Provider, "operation_kind": task.OperationKind,
			"attempt": task.Attempt, "max_attempts": task.MaxAttempts,
		}
	case "oauth.revocation.retry_scheduled", "oauth.revocation.dead_lettered":
		if !oauthRevocationErrorCodePattern.MatchString(failureCode) {
			return OAuthRevocationPublicEvent{}, fmt.Errorf("OAuth revocation public failure code is invalid")
		}
		metadata = JSONMap{
			"provider": task.Provider, "operation_kind": task.OperationKind,
			"attempt": task.Attempt, "max_attempts": task.MaxAttempts,
			"failure_code": failureCode,
		}
	default:
		return OAuthRevocationPublicEvent{}, fmt.Errorf("OAuth revocation public event type is invalid")
	}
	for key, value := range metadata {
		if isPrivateIdentityMetadataKey(key) || oauthRevocationPublicValueLeaks(value) {
			return OAuthRevocationPublicEvent{}, fmt.Errorf(
				"OAuth revocation public metadata rejected for %s", eventType,
			)
		}
	}
	return OAuthRevocationPublicEvent{Type: eventType, Metadata: metadata}, nil
}

func oauthRevocationPublicValueLeaks(value any) bool {
	text, ok := value.(string)
	if !ok {
		return false
	}
	text = strings.TrimSpace(text)
	return isOAuthOpaqueReference(text) ||
		stringContainsSensitiveMaterial(text) ||
		strings.Contains(strings.ToLower(text), "client_secret") ||
		strings.Contains(strings.ToLower(text), "refresh_token") ||
		strings.Contains(strings.ToLower(text), "access_token")
}
