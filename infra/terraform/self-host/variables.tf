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
  description = "Container image for the Ashr A1 API/control-plane runtime."
  type        = string
  default     = "ashr/a1-python-runtime:local"
}

variable "worker_image" {
  description = "Container image for the Ashr A1 queue/replay worker runtime."
  type        = string
  default     = "ashr/a1-python-runtime:local"
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

variable "postgres_storage_gb" {
  description = "Requested Postgres storage size for provider-specific implementations."
  type        = number
  default     = 20
}

variable "object_store_bucket" {
  description = "Logical artifact bucket/container name."
  type        = string
  default     = "ashr-local-artifacts"
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
