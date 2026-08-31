mock_provider "aws" {}
mock_provider "aws" { alias = "network" }

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

run "network_trust_confia_so_na_role_cicd_nunca_direto_no_github" {
  command = plan

  # Mesmo gotcha do primeiro run: aws_iam_role.network.assume_role_policy referencia
  # aws_iam_role.cicd.arn, computed de outro recurso novo — fixar para ficar known no plan.
  override_resource {
    target          = aws_iam_role.cicd
    override_during = plan
    values = {
      arn = "arn:aws:iam::123456789012:role/github-actions-provision"
    }
  }

  assert {
    condition     = strcontains(aws_iam_role.network.assume_role_policy, "\"Action\":\"sts:AssumeRole\"")
    error_message = "trust da role network deveria ser sts:AssumeRole simples: ${aws_iam_role.network.assume_role_policy}"
  }

  # Mutacao consciente: esta asercao FALHARIA se alguem, por engano, desse trust direto
  # do OIDC do GitHub tambem a network — o desenho exige que so a cicd confie no GitHub.
  assert {
    condition     = !strcontains(aws_iam_role.network.assume_role_policy, "token.actions.githubusercontent.com")
    error_message = "trust da role network NAO deveria citar o OIDC do GitHub: ${aws_iam_role.network.assume_role_policy}"
  }

  assert {
    condition     = !strcontains(aws_iam_role.network.assume_role_policy, "AssumeRoleWithWebIdentity")
    error_message = "trust da role network NAO deveria usar AssumeRoleWithWebIdentity: ${aws_iam_role.network.assume_role_policy}"
  }
}
