package ashrclone

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
	now           func() time.Time
}

type OAuthRevocationBatchResult struct {
	Claimed      int
	Delivered    int
	Retried      int
	DeadLettered int
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
	if options.LeaseDuration < 5*time.Second || options.LeaseDuration > time.Hour {
		return nil, fmt.Errorf("OAuth revocation worker lease duration is invalid")
	}
	if options.BaseBackoff < time.Second || options.MaxBackoff < options.BaseBackoff || options.MaxBackoff > 24*time.Hour {
		return nil, fmt.Errorf("OAuth revocation worker backoff is invalid")
	}
	if options.Now == nil {
		options.Now = time.Now
	}
	return &OAuthRevocationWorker{
		store: options.Store, vault: options.Vault, providers: options.Providers,
		credentials: options.Credentials, leaseOwner: options.LeaseOwner,
		leaseDuration: options.LeaseDuration, baseBackoff: options.BaseBackoff,
		maxBackoff: options.MaxBackoff, now: options.Now,
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
		if err := worker.processTask(ctx, task); err != nil {
			deadLettered, _, retryErr := worker.store.RetryOAuthRevocation(
				ctx,
				task,
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
			} else {
				result.Retried++
			}
			continue
		}
		result.Delivered++
	}
	return result, errors.Join(batchErrors...)
}

func (worker *OAuthRevocationWorker) processTask(ctx context.Context, task OAuthRevocationTask) error {
	provider, err := worker.providers.OAuthRevocationProvider(ctx, task.Provider)
	if err != nil {
		return fmt.Errorf("provider_unavailable: %w", err)
	}
	if provider == nil || provider.Name() != task.Provider {
		return fmt.Errorf("provider_mismatch")
	}
	if task.ProviderRevokedAt == nil {
		tokenPayload, err := worker.vault.Get(ctx, task.OpaqueRef)
		if err != nil {
			return fmt.Errorf("vault_read_failed: %w", err)
		}
		token := string(tokenPayload)
		if strings.TrimSpace(token) == "" {
			return fmt.Errorf("vault_token_empty")
		}
		credentials, err := worker.credentials.OAuthCredentials(ctx, task.Provider)
		if err != nil {
			return fmt.Errorf("credentials_unavailable: %w", err)
		}
		if err := provider.RevokeToken(ctx, credentials, token); err != nil {
			return fmt.Errorf("provider_revoke_failed: %w", err)
		}
		if err := worker.store.MarkOAuthProviderRevoked(ctx, task, worker.now().UTC()); err != nil {
			return fmt.Errorf("provider_checkpoint_failed: %w", err)
		}
	}
	if task.VaultDeletedAt == nil {
		// OAuthOpaqueVault.Delete implementations used by the worker must be
		// idempotent so a crash between deletion and this checkpoint is safe.
		if err := worker.vault.Delete(ctx, task.OpaqueRef); err != nil {
			return fmt.Errorf("vault_delete_failed: %w", err)
		}
		if err := worker.store.MarkOAuthVaultDeleted(ctx, task, worker.now().UTC()); err != nil {
			return fmt.Errorf("vault_checkpoint_failed: %w", err)
		}
	}
	if err := worker.store.CompleteOAuthRevocation(ctx, task, worker.now().UTC()); err != nil {
		return fmt.Errorf("completion_failed: %w", err)
	}
	return nil
}

func oauthRevocationFailureCode(err error) string {
	message := strings.ToLower(err.Error())
	for _, code := range []string{
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
