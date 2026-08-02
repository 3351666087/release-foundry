locals {
  placeholder_digests = toset([
    "sha256:d11aa1b5a977de20a601f45500420e543f3be22fbee21b4c19254165a45d77b9",
    "sha256:75973ade13ec20d39b2d175be0b467351a7a5a93e5540580817318f89b38bdfb",
    "sha256:880482f0bcdcec25c5e7fada9aadf2d15824412f4553aceaa73f30885ccc5841",
    "sha256:bc71da90a0577f2f441783c0292e871947f36df46df948c727c1019992632a17",
    "sha256:5b6c85334c7950eb5d9a1290246a06e6d5e590eece41253953df6d57b37d9919",
  ])
  image_digests = {
    for name, reference in var.image_refs : name => split("@", reference)[1]
  }
  deployment_contract = {
    schema_version = "releasefoundry.a1.kubernetes_deployment.v1"
    environment    = var.environment
    release = {
      name                   = var.release_name
      namespace              = var.namespace
      chart_path             = var.chart_path
      kubernetes_context_ref = var.kubernetes_context_ref
    }
    images   = var.image_refs
    replicas = var.replicas
    endpoints = {
      postgres = {
        host     = var.postgres.host
        port     = var.postgres.port
        database = var.postgres.database
        user     = var.postgres.user
        secret_ref = {
          name                   = var.postgres.secret_name
          dsn_key                = var.postgres.dsn_key
          migration_password_key = var.postgres.migration_password_key
        }
      }
      queue = {
        endpoint = var.queue.endpoint
        secret_ref = {
          name = var.queue.secret_name
          key  = var.queue.url_key
        }
      }
      object_storage  = var.object_storage
      identity_relays = var.identity_endpoints
    }
    network_egress_cidrs = var.network_egress_cidrs
    source_binding       = var.source_binding
    orchestrator = {
      kind                 = "kubernetes"
      package_manager      = "helm"
      vendor_accounts      = "external-operator-owned"
      vendor_provisioning  = false
      secret_values_stored = false
    }
  }
}

check "production_immutable_images" {
  assert {
    condition = (
      var.environment != "production" ||
      (
        !var.allow_placeholder_digests &&
        alltrue([for digest in values(local.image_digests) : !contains(local.placeholder_digests, digest)])
      )
    )
    error_message = "Production requires non-placeholder immutable image digests and allow_placeholder_digests=false."
  }
}

check "production_source_binding" {
  assert {
    condition = (
      var.environment != "production" ||
      (
        var.source_binding.revision != "0000000000000000000000000000000000000000" &&
        var.source_binding.tree != "0000000000000000000000000000000000000000" &&
        var.source_binding.sbom_sha256 != "0000000000000000000000000000000000000000000000000000000000000000" &&
        var.source_binding.provenance_sha256 != "0000000000000000000000000000000000000000000000000000000000000000"
      )
    )
    error_message = "Production requires a real Git revision/tree and generated SBOM/provenance digests."
  }
}

check "production_replica_floor" {
  assert {
    condition = (
      var.environment != "production" ||
      (var.replicas.api >= 3 && var.replicas.worker >= 3 && var.replicas.identity_delivery >= 3)
    )
    error_message = "Production requires at least three replicas for API, worker, and identity delivery."
  }
}

check "production_tls_endpoints" {
  assert {
    condition = (
      var.environment != "production" ||
      (
        startswith(var.object_storage.endpoint, "https://") &&
        startswith(var.queue.endpoint, "rediss://")
      )
    )
    error_message = "Production object storage must use HTTPS and queue transport must use rediss."
  }
}

resource "terraform_data" "deployment_contract" {
  input = local.deployment_contract
}
