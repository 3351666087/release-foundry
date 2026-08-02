variable "environment" {
  description = "Deployment environment used by the Helm release contract."
  type        = string
  default     = "development"

  validation {
    condition     = contains(["development", "staging", "production"], var.environment)
    error_message = "environment must be development, staging, or production."
  }
}

variable "release_name" {
  description = "Helm release name."
  type        = string
  default     = "releasefoundry"

  validation {
    condition     = can(regex("^[a-z0-9]([-a-z0-9]*[a-z0-9])?$", var.release_name)) && length(var.release_name) <= 40
    error_message = "release_name must be a lower-case DNS label no longer than 40 characters."
  }
}

variable "namespace" {
  description = "Existing or operator-created Kubernetes namespace."
  type        = string
  default     = "releasefoundry-system"

  validation {
    condition     = can(regex("^[a-z0-9]([-a-z0-9]*[a-z0-9])?$", var.namespace)) && length(var.namespace) <= 63
    error_message = "namespace must be a Kubernetes DNS label."
  }
}

variable "kubernetes_context_ref" {
  description = "Opaque reference to an operator-selected kubeconfig context; this module never reads credentials."
  type        = string
  default     = "context://operator-selected/releasefoundry-cluster"

  validation {
    condition     = can(regex("^context://[A-Za-z0-9._/-]{3,200}$", var.kubernetes_context_ref))
    error_message = "kubernetes_context_ref must be an opaque context:// reference."
  }
}

variable "chart_path" {
  description = "Repository-relative path to the reviewed ReleaseFoundry runtime Helm chart."
  type        = string
  default     = "infra/kubernetes/releasefoundry-runtime"

  validation {
    condition     = var.chart_path == "infra/kubernetes/releasefoundry-runtime"
    error_message = "chart_path must reference the reviewed A1 Helm chart."
  }
}

variable "allow_placeholder_digests" {
  description = "Development-only escape hatch for static chart validation. Must be false for a production release."
  type        = bool
  default     = true
}

variable "image_refs" {
  description = "Immutable OCI references for every A1 production workload."
  type = object({
    api               = string
    worker            = string
    identity_delivery = string
    migration         = string
    verifier          = string
  })
  default = {
    api               = "registry.invalid/releasefoundry/a1-go-runtime@sha256:d11aa1b5a977de20a601f45500420e543f3be22fbee21b4c19254165a45d77b9"
    worker            = "registry.invalid/releasefoundry/a1-go-runtime@sha256:75973ade13ec20d39b2d175be0b467351a7a5a93e5540580817318f89b38bdfb"
    identity_delivery = "registry.invalid/releasefoundry/a1-go-runtime@sha256:880482f0bcdcec25c5e7fada9aadf2d15824412f4553aceaa73f30885ccc5841"
    migration         = "registry.invalid/releasefoundry/a1-postgres-migrations@sha256:bc71da90a0577f2f441783c0292e871947f36df46df948c727c1019992632a17"
    verifier          = "registry.invalid/releasefoundry/a1-runtime-verifier@sha256:5b6c85334c7950eb5d9a1290246a06e6d5e590eece41253953df6d57b37d9919"
  }

  validation {
    condition = alltrue([
      for reference in values(var.image_refs) :
      can(regex("^[A-Za-z0-9][A-Za-z0-9._:/-]+@sha256:[0-9a-f]{64}$", reference))
    ])
    error_message = "Every image_refs value must be an immutable repository@sha256:digest reference."
  }
}

variable "replicas" {
  description = "Multi-instance replica contract for long-running workloads."
  type = object({
    api               = number
    worker            = number
    identity_delivery = number
  })
  default = {
    api               = 2
    worker            = 2
    identity_delivery = 2
  }

  validation {
    condition = alltrue([
      for count in values(var.replicas) : count >= 2 && count <= 100 && floor(count) == count
    ])
    error_message = "All long-running workloads require between 2 and 100 whole replicas."
  }
}

variable "postgres" {
  description = "Postgres network endpoint plus an existing Kubernetes Secret reference for the DSN and migration password."
  type = object({
    host                   = string
    port                   = number
    database               = string
    user                   = string
    secret_name            = string
    dsn_key                = string
    migration_password_key = string
  })
  default = {
    host                   = "postgres.database.svc.cluster.local"
    port                   = 5432
    database               = "releasefoundry"
    user                   = "releasefoundry_runtime"
    secret_name            = "releasefoundry-runtime-secrets"
    dsn_key                = "postgres-dsn"
    migration_password_key = "postgres-password"
  }

  validation {
    condition = (
      can(regex("^[A-Za-z0-9][A-Za-z0-9.-]{0,252}[A-Za-z0-9]$", var.postgres.host)) &&
      var.postgres.port >= 1 && var.postgres.port <= 65535 &&
      can(regex("^[A-Za-z_][A-Za-z0-9_]{0,62}$", var.postgres.database)) &&
      can(regex("^[A-Za-z_][A-Za-z0-9_]{0,62}$", var.postgres.user)) &&
      can(regex("^[a-z0-9]([-a-z0-9]*[a-z0-9])?$", var.postgres.secret_name)) &&
      can(regex("^[A-Za-z0-9._-]{1,253}$", var.postgres.dsn_key)) &&
      can(regex("^[A-Za-z0-9._-]{1,253}$", var.postgres.migration_password_key))
    )
    error_message = "postgres must use a valid endpoint, identifiers, and Kubernetes Secret name/key references."
  }
}

variable "queue" {
  description = "Queue endpoint without userinfo plus an existing Secret key that may hold an authenticated URL."
  type = object({
    endpoint    = string
    secret_name = string
    url_key     = string
  })
  default = {
    endpoint    = "redis://redis.queue.svc.cluster.local:6379/0"
    secret_name = "releasefoundry-runtime-secrets"
    url_key     = "queue-url"
  }

  validation {
    condition = (
      can(regex("^rediss?://[^@[:space:]]+$", var.queue.endpoint)) &&
      can(regex("^[a-z0-9]([-a-z0-9]*[a-z0-9])?$", var.queue.secret_name)) &&
      can(regex("^[A-Za-z0-9._-]{1,253}$", var.queue.url_key))
    )
    error_message = "queue must provide a credential-free redis/rediss endpoint and a Secret name/key reference."
  }
}

variable "object_storage" {
  description = "S3-compatible object endpoint and logical bucket. Vendor accounts and credentials are external."
  type = object({
    endpoint        = string
    bucket          = string
    evidence_prefix = string
  })
  default = {
    endpoint        = "https://objects.storage.svc.cluster.local"
    bucket          = "releasefoundry-artifacts"
    evidence_prefix = "evidence/a1"
  }

  validation {
    condition = (
      can(regex("^https?://[^@[:space:]]+$", var.object_storage.endpoint)) &&
      can(regex("^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$", var.object_storage.bucket)) &&
      can(regex("^[A-Za-z0-9][A-Za-z0-9._/-]{0,255}$", var.object_storage.evidence_prefix))
    )
    error_message = "object_storage must provide a credential-free HTTP(S) endpoint, bucket, and evidence prefix."
  }
}

variable "identity_endpoints" {
  description = "mTLS relay endpoints. Certificate material remains in the referenced Kubernetes Secret."
  type = object({
    vault_url        = string
    email_relay_url  = string
    sms_relay_url    = string
    mtls_secret_name = string
    mtls_server_name = string
  })
  default = {
    vault_url        = "https://identity-vault.identity.svc.cluster.local/v1/payload"
    email_relay_url  = "https://email-relay.identity.svc.cluster.local/v1/send"
    sms_relay_url    = "https://sms-relay.identity.svc.cluster.local/v1/send"
    mtls_secret_name = "releasefoundry-identity-delivery-mtls"
    mtls_server_name = "identity-relay.internal"
  }

  validation {
    condition = alltrue([
      can(regex("^https://[^@[:space:]]+$", var.identity_endpoints.vault_url)),
      can(regex("^https://[^@[:space:]]+$", var.identity_endpoints.email_relay_url)),
      can(regex("^https://[^@[:space:]]+$", var.identity_endpoints.sms_relay_url)),
      can(regex("^[a-z0-9]([-a-z0-9]*[a-z0-9])?$", var.identity_endpoints.mtls_secret_name)),
      can(regex("^[A-Za-z0-9][A-Za-z0-9.-]{1,252}[A-Za-z0-9]$", var.identity_endpoints.mtls_server_name))
    ])
    error_message = "identity_endpoints require HTTPS URLs, a Secret name, and an mTLS server name."
  }
}

variable "network_egress_cidrs" {
  description = "Explicit egress CIDRs consumed by restrictive NetworkPolicy resources."
  type = object({
    postgres           = list(string)
    queue              = list(string)
    object_storage     = list(string)
    identity_providers = list(string)
  })
  default = {
    postgres           = ["10.20.0.0/24"]
    queue              = ["10.20.1.0/24"]
    object_storage     = ["10.20.2.0/24"]
    identity_providers = ["10.20.3.0/24"]
  }

  validation {
    condition = alltrue(flatten([
      for cidrs in values(var.network_egress_cidrs) : [
        for cidr in cidrs : can(cidrhost(cidr, 0)) && cidr != "0.0.0.0/0" && cidr != "::/0"
      ]
    ])) && alltrue([for cidrs in values(var.network_egress_cidrs) : length(cidrs) > 0])
    error_message = "Every egress lane needs at least one valid CIDR; world-open CIDRs are forbidden."
  }
}

variable "source_binding" {
  description = "Git and supply-chain evidence binding injected into Helm annotations."
  type = object({
    repository        = string
    revision          = string
    tree              = string
    sbom_uri          = string
    sbom_sha256       = string
    provenance_uri    = string
    provenance_sha256 = string
  })
  default = {
    repository        = "https://github.com/3351666087/release-foundry"
    revision          = "0000000000000000000000000000000000000000"
    tree              = "0000000000000000000000000000000000000000"
    sbom_uri          = "urn:releasefoundry:sbom:development-placeholder"
    sbom_sha256       = "0000000000000000000000000000000000000000000000000000000000000000"
    provenance_uri    = "urn:releasefoundry:provenance:development-placeholder"
    provenance_sha256 = "0000000000000000000000000000000000000000000000000000000000000000"
  }

  validation {
    condition = alltrue([
      can(regex("^https://[^[:space:]]+$", var.source_binding.repository)),
      can(regex("^[0-9a-f]{40}$", var.source_binding.revision)),
      can(regex("^[0-9a-f]{40}$", var.source_binding.tree)),
      can(regex("^[0-9a-f]{64}$", var.source_binding.sbom_sha256)),
      can(regex("^[0-9a-f]{64}$", var.source_binding.provenance_sha256)),
      length(var.source_binding.sbom_uri) > 0,
      length(var.source_binding.provenance_uri) > 0
    ])
    error_message = "source_binding must contain a repository, Git SHA/tree, and SHA-256-bound SBOM/provenance references."
  }
}
