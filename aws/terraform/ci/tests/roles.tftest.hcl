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
    condition     = strcontains(aws_iam_role.cicd.assume_role_policy, "\"token.actions.githubusercontent.com:sub\":\"repo:smsilva@287870/wasp-idp@522972834:ref:refs/heads/main\"")
    error_message = "trust da role cicd sem a condicao StringEquals de sub esperada, restrita a main (issue #48, formato qualificado por ID, ver ci/README.md): ${aws_iam_role.cicd.assume_role_policy}"
  }
}

run "cicd_dura_mais_que_uma_hora_para_o_apply_nao_morrer_no_meio" {
  command = plan

  # Mutacao consciente: esta asercao FALHA se alguem devolver a role ao default de 3600s.
  # O apply de uma regiao inteira passa de 1h com folga em retries, e a essa altura o token
  # OIDC do GitHub (~5 min de vida) ja nao existe para renovar nada — a sessao da cicd tem
  # de durar o job inteiro. Ver ci/README.md.
  assert {
    condition     = aws_iam_role.cicd.max_session_duration == 21600
    error_message = "max_session_duration da role cicd deveria ser 21600 (6h, teto do job do GitHub), recebido ${aws_iam_role.cicd.max_session_duration}"
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

run "cicd_pode_assumir_a_role_network" {
  # command = apply, nao plan: a policy inline referencia aws_iam_role.network.arn, computed
  # de um recurso sob o provider aliasado aws.network — override_resource nao propaga o
  # valor fixado para esse atributo neste caso (testado; funciona para recursos sob o
  # provider default, ver os dois runs acima). Apply resolve o computed de verdade.
  command = apply

  # Sem override disponivel, a asercao compara a REFERENCIA em vez do conteudo: o campo
  # Resource da policy tem de ser exatamente o arn resolvido de aws_iam_role.network — ambos
  # leem o mesmo atributo computado, entao sao iguais mesmo sendo um valor sintetico do mock.
  # Prova que a policy aponta para a role network, sem depender do gotcha do override.
  assert {
    condition     = jsondecode(aws_iam_role_policy.cicd_assume_network.policy).Statement[0].Resource == aws_iam_role.network.arn
    error_message = "policy inline da cicd deveria referenciar o arn da role network: ${aws_iam_role_policy.cicd_assume_network.policy} vs ${aws_iam_role.network.arn}"
  }
}
