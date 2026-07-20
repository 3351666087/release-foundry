run "development_contract_is_provider_neutral" {
  command = plan

  assert {
    condition     = output.vendor_resources_provisioned == false
    error_message = "The deployment contract must not pretend to provision vendor resources."
  }

  assert {
    condition     = output.secret_values_stored == false
    error_message = "The deployment contract must retain only Secret name/key references."
  }

  assert {
    condition     = alltrue([for reference in values(output.immutable_image_refs) : strcontains(reference, "@sha256:")])
    error_message = "Every image must remain digest-pinned."
  }
}

run "production_rejects_placeholder_release" {
  command = plan

  variables {
    environment               = "production"
    allow_placeholder_digests = false
    replicas = {
      api               = 3
      worker            = 4
      identity_delivery = 3
    }
    queue = {
      endpoint    = "rediss://redis.queue.svc.cluster.local:6379/0"
      secret_name = "ashr-runtime-secrets"
      url_key     = "queue-url"
    }
  }

  expect_failures = [
    check.production_immutable_images,
    check.production_source_binding,
  ]
}
