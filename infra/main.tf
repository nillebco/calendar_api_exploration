terraform {
  required_providers {
    azuread = {
      source  = "hashicorp/azuread"
      version = ">= 2.48.0"
    }
  }
}

provider "azuread" {}

data "azuread_client_config" "current" {}

# Microsoft Graph service principal in the tenant
data "azuread_service_principal" "msgraph" {
  display_name = "Microsoft Graph"
}

resource "azuread_application" "graph_app" {
  display_name = var.display_name
  # fallback_public_client_enabled = true

  web {
    redirect_uris = [
      "http://localhost:8400/callback",
    ]
  }

  # Request delegated permissions from Microsoft Graph
  required_resource_access {
    resource_app_id = data.azuread_service_principal.msgraph.client_id

    dynamic "resource_access" {
      for_each = toset([
        "Calendars.ReadWrite",
        "offline_access",
        "User.Read",
      ])
      content {
        id   = data.azuread_service_principal.msgraph.oauth2_permission_scope_ids[resource_access.value]
        type = "Scope"
      }
    }
  }
}

resource "azuread_service_principal" "graph_app_sp" {
  client_id = azuread_application.graph_app.client_id
}

# Grant tenant-wide admin consent (domain grant) for the delegated scopes above
resource "azuread_service_principal_delegated_permission_grant" "domain_grant" {
  service_principal_object_id          = azuread_service_principal.graph_app_sp.object_id
  resource_service_principal_object_id = data.azuread_service_principal.msgraph.object_id
  claim_values                         = ["Calendars.ReadWrite", "offline_access", "User.Read"]
}

resource "azuread_application_password" "graph_app_sp" {
  application_id = azuread_application.graph_app.id
}
