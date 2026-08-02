variable "environment" {
  description = "Deployment environment label used for naming self-host resources."
  type        = string
  default     = "dev"
}

variable "region" {
  description = "Operator-selected region label. This skeleton does not bind to a cloud provider."
  type        = string
  default     = "local"
}

variable "api_image" {
  description = "Container image for the ReleaseFoundry A1 API/control-plane runtime."
  type        = string
  default     = "releasefoundry/a1-python-runtime:local"
}

variable "worker_image" {
  description = "Container image for the ReleaseFoundry A1 queue/replay worker runtime."
  type        = string
  default     = "releasefoundry/a1-python-runtime:local"
}

variable "api_replicas" {
  description = "Desired API replica count for a real orchestrator adapter."
  type        = number
  default     = 1

  validation {
    condition     = var.api_replicas >= 1
    error_message = "api_replicas must be at least 1."
  }
}

variable "worker_replicas" {
  description = "Desired worker replica count for a real orchestrator adapter."
  type        = number
  default     = 1

  validation {
    condition     = var.worker_replicas >= 0
    error_message = "worker_replicas must be zero or greater."
  }
}

variable "billing_webhook_replicas" {
  description = "Desired billing webhook receiver replica count for provider-specific adapters. The receiver stores public-safe event metadata only."
  type        = number
  default     = 1

  validation {
    condition     = var.billing_webhook_replicas >= 0
    error_message = "billing_webhook_replicas must be zero or greater."
  }
}

variable "postgres_storage_gb" {
  description = "Requested Postgres storage size for provider-specific implementations."
  type        = number
  default     = 20
}

variable "object_store_bucket" {
  description = "Logical artifact bucket/container name."
  type        = string
  default     = "releasefoundry-local-artifacts"
}

variable "object_store_endpoint_ref" {
  description = "Reference to the object-store endpoint supplied by the operator or provider adapter; never a credential value."
  type        = string
  default     = "secret://dev/releasefoundry/object-store-endpoint"
}

variable "object_store_access_key_ref" {
  description = "Reference to the object-store access key location. Keep the actual key outside Terraform state."
  type        = string
  default     = "secret://dev/releasefoundry/object-store-access-key"
}

variable "object_store_secret_key_ref" {
  description = "Reference to the object-store secret key location. Keep the actual secret outside Terraform state."
  type        = string
  default     = "secret://dev/releasefoundry/object-store-secret-key"
}

variable "object_evidence_prefix" {
  description = "Object-store prefix for A1 worker evidence and artifact manifests."
  type        = string
  default     = "evidence/a1/self-host"
}

variable "postgres_dsn_secret_ref" {
  description = "Reference to the Postgres DSN secret. The scaffold stores only this ref, not the DSN value."
  type        = string
  default     = "secret://dev/releasefoundry/postgres-dsn"
}

variable "billing_provider_secret_ref" {
  description = "Reference to the hosted billing provider API secret. The scaffold stores only this ref."
  type        = string
  default     = "secret://dev/releasefoundry/billing-provider-secret"
}

variable "billing_webhook_secret_ref" {
  description = "Reference to the billing webhook signing secret. The scaffold stores only this ref."
  type        = string
  default     = "secret://dev/releasefoundry/billing-webhook-secret"
}

variable "allowed_origins" {
  description = "CORS origins for the API surface. Keep empty for private self-host defaults."
  type        = list(string)
  default     = []
}

variable "enable_public_ingress" {
  description = "Whether a provider adapter should expose public ingress. Defaults private."
  type        = bool
  default     = false
}
