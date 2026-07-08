package ashrclone

import (
	"errors"
	"testing"
)

func TestPostgresRepositorySatisfiesBackend(t *testing.T) {
	var _ ControlPlaneBackend = (*PostgresRepository)(nil)
}

func TestPostgresRepositoryCloseWithoutDB(t *testing.T) {
	repository := NewPostgresRepository(nil)
	if err := repository.Close(); err != nil {
		t.Fatalf("close nil db: %v", err)
	}
}

func TestPostgresRepositoryOperationsAreExplicitlyUnimplemented(t *testing.T) {
	repository := NewPostgresRepository(nil)
	_, err := repository.BootstrapProject("Tenant", "Project", Dataset{Name: "Dataset"}, "tenant", "project")
	if !errors.Is(err, ErrPostgresRepositoryNotImplemented) {
		t.Fatalf("expected not implemented error, got %v", err)
	}
}

func TestOpenPostgresRepositoryRequiresDSN(t *testing.T) {
	_, err := OpenPostgresRepository("  ")
	if err == nil {
		t.Fatal("expected DSN validation error")
	}
}
