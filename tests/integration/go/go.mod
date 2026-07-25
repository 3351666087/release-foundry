module github.com/ashr-labs/ashr/tests/integration/go

go 1.22

require github.com/ashr-labs/ashr/packages/go/ashrclone v0.0.0

require (
	github.com/lib/pq v1.12.3
	golang.org/x/crypto v0.23.0 // indirect
	golang.org/x/sys v0.20.0 // indirect
)

replace github.com/ashr-labs/ashr/packages/go/ashrclone => ../../../packages/go/ashrclone
