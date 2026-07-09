locals {
  name_prefix = "ashr-${var.environment}"

  runtime_env = {
    ASHR_RUNTIME_ENV          = "self-host"
    ASHR_DATABASE_URL_REF     = "postgres_connection_from_secret_manager"
    ASHR_REDIS_URL_REF        = "redis_connection_from_secret_manager"
    ASHR_OBJECT_STORE_BUCKET  = var.object_store_bucket
    ASHR_OBJECT_STORE_URL_REF = "object_store_endpoint_from_provider"
  }

  components = {
    api = {
      image    = var.api_image
      replicas = var.api_replicas
      port     = 8080
      command  = "services.api.control_plane:serve_control_plane_http"
    }
    worker = {
      image    = var.worker_image
      replicas = var.worker_replicas
      command  = "python -m services.api.cli replay-queued"
    }
    postgres = {
      engine     = "postgres"
      version    = "16"
      storage_gb = var.postgres_storage_gb
    }
    redis = {
      engine  = "redis"
      version = "7"
    }
    object_store = {
      bucket = var.object_store_bucket
    }
  }
}

resource "null_resource" "deployment_contract" {
  triggers = {
    environment           = var.environment
    region                = var.region
    api_image             = var.api_image
    worker_image          = var.worker_image
    api_replicas          = tostring(var.api_replicas)
    worker_replicas       = tostring(var.worker_replicas)
    object_store_bucket   = var.object_store_bucket
    enable_public_ingress = tostring(var.enable_public_ingress)
    contract_version      = "ashr.a1.self_host.runtime.v1"
  }
}

resource "null_resource" "component" {
  for_each = local.components

  triggers = {
    name     = "${local.name_prefix}-${each.key}"
    contract = jsonencode(each.value)
  }
}
