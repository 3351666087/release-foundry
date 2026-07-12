output "deployment_contract" {
  description = "Validated, public-safe input contract for the A1 Helm deployment."
  value       = terraform_data.deployment_contract.output
}

output "helm_release_coordinates" {
  description = "Operator-owned release coordinates; no kubeconfig credentials are read by this module."
  value = {
    release_name           = var.release_name
    namespace              = var.namespace
    chart_path             = var.chart_path
    kubernetes_context_ref = var.kubernetes_context_ref
  }
}

output "immutable_image_refs" {
  description = "OCI references passed to the Helm values generation step."
  value       = var.image_refs
}

output "vendor_resources_provisioned" {
  description = "This contract module intentionally does not create cloud, database, queue, object-store, or payment vendor accounts."
  value       = false
}

output "secret_values_stored" {
  description = "Only Kubernetes Secret name/key references are modeled."
  value       = false
}
