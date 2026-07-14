package ashrclone

import (
	"bytes"
	"context"
	"errors"
	"testing"

	"github.com/DATA-DOG/go-sqlmock"
	"github.com/lib/pq"
)

func TestNewPostgresIdentityCredentialLinkCoordinatorRequiresSharedDatabase(t *testing.T) {
	t.Parallel()

	if _, err := NewPostgresIdentityCredentialLinkCoordinator(nil, nil); err == nil {
		t.Fatal("expected nil dependencies to fail closed")
	}

	db, _, err := sqlmock.New()
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()
	otherDB, _, err := sqlmock.New()
	if err != nil {
		t.Fatal(err)
	}
	defer otherDB.Close()

	keys, err := newIdentityLifecycleKeyring("v1", bytes.Repeat([]byte{0x6a}, 32), nil)
	if err != nil {
		t.Fatal(err)
	}
	store := &ProductionIdentityStore{db: db, lifecycleKeys: keys}
	receipts := &postgresIdentityLifecycleReceiptStore{db: db, keys: keys}

	coordinator, err := NewPostgresIdentityCredentialLinkCoordinator(store, receipts)
	if err != nil {
		t.Fatalf("shared database was rejected: %v", err)
	}
	if coordinator.store != store || coordinator.receipts != receipts {
		t.Fatal("coordinator did not preserve the shared transaction dependencies")
	}

	mismatched := &postgresIdentityLifecycleReceiptStore{db: otherDB, keys: keys}
	if _, err := NewPostgresIdentityCredentialLinkCoordinator(store, mismatched); err == nil {
		t.Fatal("expected mismatched database handles to fail closed")
	}
	if _, err := NewPostgresIdentityCredentialLinkCoordinator(
		store, newMemoryIdentityLifecycleReceiptStore(),
	); err == nil {
		t.Fatal("expected non-PostgreSQL receipt store to fail closed")
	}
}

func TestMapPostgresIdentityCredentialLinkErrorIsPublicSafe(t *testing.T) {
	t.Parallel()

	tests := []struct {
		name string
		err  error
		code string
	}{
		{
			name: "unique conflict",
			err:  &pq.Error{Code: "23505", Message: "duplicate key exposes identity_credentials_subject_unique"},
			code: "identity_credential_link_conflict",
		},
		{
			name: "authorization",
			err:  &pq.Error{Code: "42501", Message: "identity_credential_link_step_up_unavailable"},
			code: "identity_credential_link_rejected",
		},
		{
			name: "invalid state",
			err:  &pq.Error{Code: "22023", Message: "identity_credential_link_invalid"},
			code: "identity_credential_link_rejected",
		},
		{
			name: "serialization exhausted",
			err:  &pq.Error{Code: "40001", Message: "relation identity_lifecycle_receipts"},
			code: "identity_credential_link_unavailable",
		},
		{
			name: "unknown infrastructure",
			err:  errors.New("password authentication failed for internal role"),
			code: "identity_credential_link_unavailable",
		},
	}
	for _, test := range tests {
		test := test
		t.Run(test.name, func(t *testing.T) {
			t.Parallel()
			mapped := mapPostgresIdentityCredentialLinkError(test.err)
			var domain IdentityDomainError
			if !errors.As(mapped, &domain) || domain.Code != test.code {
				t.Fatalf("mapped error=%#v want domain code %q", mapped, test.code)
			}
			if errors.Is(mapped, test.err) {
				t.Fatalf("public error retained private database error: %v", mapped)
			}
			for _, private := range []string{
				"identity_credentials_subject_unique",
				"identity_credential_link_step_up_unavailable",
				"identity_credential_link_invalid",
				"identity_lifecycle_receipts",
				"internal role",
			} {
				if bytes.Contains([]byte(mapped.Error()), []byte(private)) {
					t.Fatalf("public error leaked %q: %v", private, mapped)
				}
			}
		})
	}

	domain := identityCredentialLinkError("existing_safe_code", "existing safe message")
	if mapped := mapPostgresIdentityCredentialLinkError(domain); mapped != domain {
		t.Fatalf("domain error changed: %#v", mapped)
	}
	if mapped := mapPostgresIdentityCredentialLinkError(context.Canceled); !errors.Is(mapped, context.Canceled) {
		t.Fatalf("context cancellation changed: %v", mapped)
	}
	if mapped := mapPostgresIdentityCredentialLinkError(ErrIdentityProofScopeMismatch); !errors.Is(mapped, ErrIdentityProofScopeMismatch) {
		t.Fatalf("proof scope mismatch changed: %v", mapped)
	}
}
