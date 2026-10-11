# Bind: connection values of an existing database (restored from backup), not managed by Radius.
terraform {
  required_version = ">= 1.5"
}

variable "context" {
  description = "Radius Recipe context."
  type        = any
}

output "result" {
  value = {
    values = {
      host     = "postgres.shared-db.svc.cluster.local"
      port     = 5432
      database = "orders_restored"
      username = "restored_user"
    }
  }
}
