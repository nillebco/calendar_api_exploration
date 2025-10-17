output "client_id" {
  description = "Azure AD application (client) ID"
  value       = azuread_application.graph_app.client_id
}

output "service_principal_object_id" {
  description = "Service principal object ID for the app"
  value       = azuread_service_principal.graph_app_sp.id
}

output "tenant_id" {
  description = "Tenant ID"
  value       = data.azuread_client_config.current.tenant_id
}

output "application_password" {
  description = "Application password for the app"
  value       = azuread_application_password.graph_app_sp.value
  sensitive   = true
}