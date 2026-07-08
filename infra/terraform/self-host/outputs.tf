output "deployment_contract_version" {
  description = "Static contract version for this self-host scaffold."
  value       = null_resource.deployment_contract.triggers.contract_version
}

output "component_names" {
  description = "Logical component names for provider-specific adapters."
  value       = { for key, resource in null_resource.component : key => resource.triggers.name }
}

output "runtime_environment" {
  description = "Non-secret runtime environment contract. Secret values are references only."
  value       = local.runtime_env
}

output "public_ingress_enabled" {
  description = "Whether provider adapters should create public ingress."
  value       = var.enable_public_ingress
}
