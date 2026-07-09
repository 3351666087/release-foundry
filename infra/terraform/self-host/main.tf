locals {
  name_prefix = "ashr-${var.environment}"

  runtime_env = {
    ASHR_RUNTIME_ENV                 = "self-host"
    ASHR_DATABASE_URL_REF            = var.postgres_dsn_secret_ref
    ASHR_REDIS_URL_REF               = "secret://${var.environment}/ashr/redis-url"
    ASHR_OBJECT_STORE_BUCKET         = var.object_store_bucket
    ASHR_OBJECT_STORE_URL_REF        = var.object_store_endpoint_ref
    ASHR_OBJECT_STORE_ACCESS_KEY_REF = var.object_store_access_key_ref
    ASHR_OBJECT_STORE_SECRET_KEY_REF = var.object_store_secret_key_ref
    ASHR_OBJECT_EVIDENCE_PREFIX      = var.object_evidence_prefix
    ASHR_BILLING_PROVIDER_SECRET_REF = var.billing_provider_secret_ref
    ASHR_BILLING_WEBHOOK_SECRET_REF  = var.billing_webhook_secret_ref
    ASHR_QUOTA_LEDGER_TABLE          = "ashr_quota_ledger"
    ASHR_ARTIFACT_MANIFEST_TABLE     = "ashr_artifact_manifests"
    ASHR_WORKER_JOBS_TABLE           = "ashr_worker_jobs"
  }

  components = {
    api = {
      image    = var.api_image
      replicas = var.api_replicas
      port     = 8080
      command  = "services.api.control_plane:serve_control_plane_http"
    }
    worker = {
      image         = var.worker_image
      replicas      = var.worker_replicas
      command       = "long-running queue worker"
      mode          = "long-running"
      queue         = "ashr_worker_jobs"
      lease_seconds = 300
      evidence_writes = {
        object_store_bucket = var.object_store_bucket
        object_prefix       = var.object_evidence_prefix
        manifest_table      = "ashr_artifact_manifests"
        quota_table         = "ashr_quota_ledger"
      }
    }
    billing_webhook = {
      image                = var.api_image
      replicas             = var.billing_webhook_replicas
      port                 = 8788
      receiver_mode        = "webhook-only"
      provider_secret      = var.billing_provider_secret_ref
      webhook_secret       = var.billing_webhook_secret_ref
      quota_ledger_table   = "ashr_quota_ledger"
      billing_ledger_table = "ashr_billing_ledger"
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
      bucket          = var.object_store_bucket
      endpoint_ref    = var.object_store_endpoint_ref
      access_key_ref  = var.object_store_access_key_ref
      secret_key_ref  = var.object_store_secret_key_ref
      evidence_prefix = var.object_evidence_prefix
      public_access   = false
    }
    quota_ledger = {
      table             = "ashr_quota_ledger"
      covers_operations = ["run.upload", "trace.ingest", "artifact.manifest", "worker.job.enqueue", "worker.job.complete", "billing.webhook.ingest"]
      tenant_isolation  = "required"
    }
  }
}

resource "null_resource" "deployment_contract" {
  triggers = {
    environment              = var.environment
    region                   = var.region
    api_image                = var.api_image
    worker_image             = var.worker_image
    api_replicas             = tostring(var.api_replicas)
    worker_replicas          = tostring(var.worker_replicas)
    billing_webhook_replicas = tostring(var.billing_webhook_replicas)
    object_store_bucket      = var.object_store_bucket
    object_evidence_prefix   = var.object_evidence_prefix
    enable_public_ingress    = tostring(var.enable_public_ingress)
    contract_version         = "ashr.a1.self_host.commercial_runtime.v2"
  }
}

resource "null_resource" "component" {
  for_each = local.components

  triggers = {
    name     = "${local.name_prefix}-${each.key}"
    contract = jsonencode(each.value)
  }
}
