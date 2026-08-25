mock_provider "aws" {}

variables {
  name                 = "test-eso"
  cluster_name         = "test-cluster"
  namespace            = "external-secrets"
  service_account_name = "external-secrets"
}

run "trust_exige_assume_role_e_tag_session" {
  command = plan

  assert {
    condition     = strcontains(aws_iam_role.this.assume_role_policy, "sts:AssumeRole")
    error_message = "trust policy sem sts:AssumeRole: ${aws_iam_role.this.assume_role_policy}"
  }

  assert {
    condition     = strcontains(aws_iam_role.this.assume_role_policy, "sts:TagSession")
    error_message = "trust policy sem sts:TagSession — Pod Identity nao funciona sem ela: ${aws_iam_role.this.assume_role_policy}"
  }

  assert {
    condition     = strcontains(aws_iam_role.this.assume_role_policy, "pods.eks.amazonaws.com")
    error_message = "principal do trust deveria ser pods.eks.amazonaws.com: ${aws_iam_role.this.assume_role_policy}"
  }
}

run "association_amarra_namespace_e_service_account" {
  command = plan

  assert {
    condition     = aws_eks_pod_identity_association.this.namespace == "external-secrets"
    error_message = "namespace da association: esperado external-secrets, recebido ${aws_eks_pod_identity_association.this.namespace}"
  }

  assert {
    condition     = aws_eks_pod_identity_association.this.service_account == "external-secrets"
    error_message = "service account da association: esperado external-secrets, recebido ${aws_eks_pod_identity_association.this.service_account}"
  }

  assert {
    condition     = aws_eks_pod_identity_association.this.cluster_name == "test-cluster"
    error_message = "cluster da association: esperado test-cluster, recebido ${aws_eks_pod_identity_association.this.cluster_name}"
  }
}

run "policy_inline_ausente_nao_cria_recurso" {
  command = plan

  assert {
    condition     = length(aws_iam_role_policy.this) == 0
    error_message = "sem policy_json nao deveria existir aws_iam_role_policy, recebido ${length(aws_iam_role_policy.this)}"
  }
}

run "managed_policies_geram_um_attachment_cada" {
  command = plan

  variables {
    managed_policy_arns = [
      "arn:aws:iam::aws:policy/service-role/AmazonEBSCSIDriverPolicy",
      "arn:aws:iam::aws:policy/ReadOnlyAccess",
    ]
  }

  assert {
    condition     = length(aws_iam_role_policy_attachment.managed) == 2
    error_message = "esperados 2 attachments, recebidos ${length(aws_iam_role_policy_attachment.managed)}"
  }
}