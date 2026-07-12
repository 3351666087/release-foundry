# A1 Kubernetes Deployment Contract

This Terraform module validates operator inputs for the reviewed Helm chart in `infra/kubernetes/ashr-runtime`. It deliberately creates only a `terraform_data` contract record.

It does not:

- authenticate to a Kubernetes cluster;
- install a Helm release;
- create Postgres, Redis/Valkey, object-storage, identity-relay, payment, or cloud vendor accounts;
- read or store secret values.

It does validate:

- immutable `repository@sha256:digest` image references for all five images;
- multi-instance API, queue-worker, and identity-delivery replica counts;
- Kubernetes namespace, release, and Secret name/key references;
- credential-free Postgres, queue, object-storage, and identity endpoint metadata;
- restrictive, non-world-open NetworkPolicy CIDRs;
- Git commit/tree and deterministic SBOM/provenance bindings;
- production TLS, replica, and placeholder-rejection gates.

Run static validation:

```sh
terraform -chdir=infra/terraform/kubernetes-runtime fmt -check
terraform -chdir=infra/terraform/kubernetes-runtime init -backend=false
terraform -chdir=infra/terraform/kubernetes-runtime validate
terraform -chdir=infra/terraform/kubernetes-runtime test
```

Production adapters should consume `deployment_contract`, translate it into reviewed Helm values, and perform apply in a separately authorized delivery pipeline.
