mock_provider "aws" {}

run "cicd_trust_exige_oidc_do_github_com_aud_e_sub_corretos" {
  command = plan

  # aws_iam_role.cicd.assume_role_policy referencia aws_iam_openid_connect_provider.github.arn
  # (outro recurso novo) — sem fixar o computed, o valor fica "known after apply" mesmo sob
  # mock_provider, e a asserção de conteúdo não avalia. Ver aws/terraform/CLAUDE.md, "Asserção
  # entre dois computados e impossivel offline".
  override_resource {
    target          = aws_iam_openid_connect_provider.github
    override_during = plan
    values = {
      arn = "arn:aws:iam::123456789012:oidc-provider/token.actions.githubusercontent.com"
    }
  }

  assert {
    condition     = strcontains(aws_iam_role.cicd.assume_role_policy, "sts:AssumeRoleWithWebIdentity")
    error_message = "trust da role cicd deveria usar AssumeRoleWithWebIdentity: ${aws_iam_role.cicd.assume_role_policy}"
  }

  assert {
    condition     = strcontains(aws_iam_role.cicd.assume_role_policy, "\"token.actions.githubusercontent.com:aud\":\"sts.amazonaws.com\"")
    error_message = "trust da role cicd sem a condicao StringEquals de aud: ${aws_iam_role.cicd.assume_role_policy}"
  }

  assert {
    condition     = strcontains(aws_iam_role.cicd.assume_role_policy, "\"token.actions.githubusercontent.com:sub\":\"repo:smsilva/wasp-idp:ref:refs/heads/*\"")
    error_message = "trust da role cicd sem a condicao StringLike de sub esperada: ${aws_iam_role.cicd.assume_role_policy}"
  }
}

run "oidc_provider_sem_thumbprint_fixo" {
  # command = apply, nao plan: thumbprint_list e computed e nao setado na config — sob
  # mock_provider fica "known after apply" ate o recurso ser efetivamente aplicado (mock).
  command = apply

  assert {
    condition     = length(aws_iam_openid_connect_provider.github.thumbprint_list) == 0
    error_message = "thumbprint_list deveria ficar vazio/omitido de proposito — ver ci/README.md"
  }

  assert {
    condition     = aws_iam_openid_connect_provider.github.url == "https://token.actions.githubusercontent.com"
    error_message = "url do provider OIDC incorreta: ${aws_iam_openid_connect_provider.github.url}"
  }

  assert {
    condition     = contains(aws_iam_openid_connect_provider.github.client_id_list, "sts.amazonaws.com")
    error_message = "client_id_list deveria conter sts.amazonaws.com: ${jsonencode(aws_iam_openid_connect_provider.github.client_id_list)}"
  }
}
