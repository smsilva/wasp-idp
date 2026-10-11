# Compose: a database and role on the shared PostgreSQL instance in namespace shared-db.
terraform {
  required_version = ">= 1.5"
  required_providers {
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = ">= 2.37.1"
    }
    postgresql = {
      source  = "cyrilgdn/postgresql"
      version = "1.25.0"
    }
  }
}

variable "context" {
  description = "Radius Recipe context."
  type        = any
}

locals {
  database = replace("${var.context.application.name}_${var.context.resource.name}_${var.context.environment.name}", "-", "_")
  username = local.database
  password = var.context.resource.properties.password
}

data "kubernetes_secret" "admin" {
  metadata {
    name      = "postgres-admin"
    namespace = "shared-db"
  }
}

provider "postgresql" {
  host     = "postgres.shared-db.svc.cluster.local"
  port     = 5432
  username = "postgres"
  password = data.kubernetes_secret.admin.data["POSTGRES_PASSWORD"]
  sslmode  = "disable"
}

resource "postgresql_role" "app" {
  name     = local.username
  login    = true
  password = local.password
}

resource "postgresql_database" "app" {
  name  = local.database
  owner = postgresql_role.app.name
}

output "result" {
  value = {
    values = {
      host     = "postgres.shared-db.svc.cluster.local"
      port     = 5432
      database = postgresql_database.app.name
      username = postgresql_role.app.name
    }
  }
}
