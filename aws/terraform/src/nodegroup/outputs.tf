output "node_group_names" {
  description = "Nomes dos node groups criados."
  value       = [for group in aws_eks_node_group.this : group.node_group_name]
}
