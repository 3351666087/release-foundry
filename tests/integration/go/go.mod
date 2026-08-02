module github.com/3351666087/release-foundry/tests/integration/go

go 1.22

require github.com/3351666087/release-foundry/packages/go/releasefoundry v0.0.0

require (
	github.com/lib/pq v1.12.3
	golang.org/x/crypto v0.23.0 // indirect
	golang.org/x/sys v0.20.0 // indirect
)

replace github.com/3351666087/release-foundry/packages/go/releasefoundry => ../../../packages/go/releasefoundry
