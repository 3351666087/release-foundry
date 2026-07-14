package ashrclone

import (
	"bytes"
	"testing"

	"github.com/DATA-DOG/go-sqlmock"
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
