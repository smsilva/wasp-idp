# Workflow GitHub Actions para provisionar uma região (issue #41, obstáculos 3 e 4)

Desenho do **trust OIDC GitHub→AWS** (obstáculo 3 da issue #41) e do **workflow em si** (item 3 do "O que fazer"). O obstáculo 2 (acesso de rede do runner ao endpoint privado do EKS) já foi decidido e implementado — ver `2026-08-31-github-actions-runner-private-access-design.md` e a PR #46, mergeada. O obstáculo 1 (aplicação SAML no Identity Center) continua sendo bootstrap de console, uma vez por Organization, e este desenho apenas **consome** o metadata já baixado.

## Escopo

Provisionar uma região inteira — `module.hub` **e** `module.cell` juntos, sempre — a partir de um `workflow_dispatch`. Equivale a `up-02-region --region <r> --with-cell --yes` rodando em CI.

**Decisão explícita:** hub e célula sobem no mesmo disparo, sem gate separado para a célula. Isso divergiu da cautela original da issue #41 ("célula é T2, custo por hora — não pode subir por merge automático"), e a razão é que o gatilho é `workflow_dispatch` manual: já existe um humano decidindo. O que a issue queria evitar (célula subindo por merge automático) continua impossível. **A reavaliar quando o workflow estiver em uso** — registrado como decisão consciente, não esquecimento.

## Princípio que orientou o desenho: nenhuma mudança em Terraform ou nos scripts

O workflow **não** altera `regions/<região>/`, `src/*` ou `scripts/up-*`. `up-02-region` roda verbatim em CI, com os mesmos nomes de profile que usa localmente. Isso mantém a simetria local↔CI exata: a única coisa que muda é a origem da credencial-raiz (token OIDC em vez de sessão SSO humana). Um bug que aparece em CI e não localmente fica, por construção, restrito ao ambiente — não à árvore de código.

## Credencial: profiles escritos em runtime, não `-var` nem `assume_role`

`regions/<região>/main.tf` configura os dois providers por **profile** (`aws_profile = "cicd"` no default, `network_profile = "network"` no aliased). Um runner github-hosted não tem `~/.aws/config`.

A saída é o workflow **escrever** esse arquivo, com os mesmos dois nomes:

```ini
[profile cicd]
role_arn = arn:aws:iam::<cicd-account-id>:role/github-actions-provision
web_identity_token_file = /tmp/gha-oidc-token

[profile network]
role_arn = arn:aws:iam::<network-account-id>:role/github-actions-provision
source_profile = cicd
```

Profile com `web_identity_token_file` + `role_arn`, e um segundo profile encadeando via `source_profile`, é padrão documentado da AWS — a doc do EKS traz exatamente esse par para acesso cross-account de pod ([Cross-account access](https://docs.aws.amazon.com/eks/latest/userguide/cross-account-access.html)).

**Rejeitado: `aws-actions/configure-aws-credentials` sozinho.** Ela exporta credencial por variável de ambiente para **uma** identidade. O provider aliasado `aws.network` precisa de outra, e um profile encadeando de variável de ambiente exigiria `credential_source = Environment` com `role_arn` — o que funciona para a `network`, mas deixa o profile `cicd` sem definição válida (um profile só com `credential_source`, sem `role_arn`, é inválido; com `role_arn` apontando para a própria role seria auto-assume). Duas formas diferentes de resolver o mesmo problema no mesmo arquivo é pior que uma.

**Rejeitado: passar `-var aws_profile=` vazio e usar a cadeia default do SDK.** Depende de o provider AWS tratar string vazia como "não setado", comportamento que não foi verificado, e ainda deixaria a `network` sem resposta.

### Trust: OIDC só na `cicd`, `network` confia na `cicd`

| Conta | Role | Trust |
|---|---|---|
| `cicd` | `github-actions-provision` | `sts:AssumeRoleWithWebIdentity` do provider OIDC do GitHub, com `aud = sts.amazonaws.com` e `sub` casando `repo:smsilva/wasp-idp:ref:refs/heads/*` |
| `network` | `github-actions-provision` | `sts:AssumeRole` apenas da role acima — nenhum trust direto com o GitHub |

Espelha a cadeia que já existe operacionalmente (`personal` → `network`/`cicd` via `OrganizationAccountAccessRole`), trocando só a raiz: token OIDC em vez de SSO. O `aws/docs/security/02-cross-account-roles.md` já estabelece `sts:AssumeRole` com trust escopada como o padrão do repo para cross-account; dois OIDC providers em duas contas não tem precedente aqui e duplicaria a configuração do provider (URL, `client_id_list`, condições do `sub`) em dois lugares.

**`sub` com `refs/heads/*`** (qualquer branch deste repo, nunca fork nem PR) é deliberado: permite validar o workflow antes do merge em `main`. Apertar para `refs/heads/main` é uma linha — dívida consciente, registrada como issue.

**`thumbprint_list` é omitido de propósito.** A doc da IAM: a AWS valida o endpoint JWKS pela própria biblioteca de CAs raiz confiáveis, e só cai no thumbprint como *fallback* quando o IdP usa cert fora dessas CAs. A doc do provider AWS é ainda mais específica: para GitHub (entre outros), *"any configured `thumbprint_list` is retained in the configuration but not used for verification"*. Fixar thumbprint aqui é a armadilha clássica de CI que quebra quando o certificado rotaciona, em troca de zero segurança.

## Onde as roles nascem: raiz `aws/terraform/ci/`

Raiz Terraform própria, T0 permanente, aplicada uma vez por um admin com profile `personal` — mesmo padrão e mesma disciplina de `state-backend/`:

- `aws_iam_openid_connect_provider` (`https://token.actions.githubusercontent.com`, `client_id_list = ["sts.amazonaws.com"]`, sem `thumbprint_list`) na conta `cicd`
- as duas roles + policies
- dois providers: `aws` (profile `cicd`) e `aws.network` (profile `network`)
- state key própria: `ci/terraform.tfstate`
- `terraform test` com `mock_provider`, cobrindo as condições do trust (`aud`, `sub`) **com teste de mutação** — asserção sobre condição de trust que passa mesmo com a condição enfraquecida não prova nada, e este repo já tem histórico de duas asserções vazias descobertas assim (`aws/terraform/CLAUDE.md`)

**Não** via AWS CLI na unha: o que se cria uma vez e se revisa com cuidado é Terraform ([`decisions.md`](../../../decisions.md) §7), e uma mudança futura na condição do `sub` precisa aparecer em diff.

### Permissões

As duas roles precisam do que os módulos que elas aplicam de fato criam — não `AdministratorAccess`:

- **`cicd`** (`module.cell`): VPC/EKS/ELB/Route53/Secrets Manager, IAM escopado aos prefixos de role que `src/cluster` e `src/pod-identity` criam, S3 do bucket de state, e `sts:AssumeRole` na role da `network`
- **`network`** (`module.hub`): VPC/TGW/Client VPN/ACM/ELB/RAM/Route53 e `iam:*SAMLProvider*`

O escopo fino de cada policy é trabalho do plano de implementação: derivar do que os módulos declaram, não copiar `PowerUserAccess` por conveniência. `PowerUserAccess` + inline de IAM é o fallback aceitável para a PoC **se** a derivação fina se mostrar cara — mas registrado como tal, não silenciosamente.

## Identidade em CI: `values.tfvars` versionado, SAML em secret do GitHub

| Arquivo | Antes | Agora | Por quê |
|---|---|---|---|
| `variables/values.tfvars` | gitignored | **versionado** | as contas AWS desta PoC são efêmeras e de teste; versionar elimina toda a maquinaria de materialização em CI. Reverter quando deixarem de ser descartáveis — registrado como issue |
| `variables/saml-metadata.xml` | gitignored | **GitHub encrypted secret** (`SAML_METADATA_XML`), escrito em arquivo no início do job | continua fora do repo (identifica a instância de Identity Center) e evita o custo recorrente de um secret no Secrets Manager (~US$ 0,40/mês) — decisão de custo, explícita |

O symlink `values.auto.tfvars` continua sendo criado pelo próprio `up-02-region` (`ensure_symlink` em `scripts/lib`, já existe) — nada novo.

A alternativa Secrets Manager para o metadata SAML está desenhada em `2026-08-27-saml-metadata-secrets-manager.md` e **não** é o caminho escolhido aqui, por custo.

## `.github/workflows/provision-region.yml`

`workflow_dispatch`, input `region` (default `us-east-1`), um job:

| # | Passo |
|---|---|
| 1 | `permissions: id-token: write`, `contents: read` |
| 2 | checkout |
| 3 | `curl` do JWT em `ACTIONS_ID_TOKEN_REQUEST_URL` → `/tmp/gha-oidc-token`; escreve `~/.aws/config` com os dois profiles |
| 4 | secret `SAML_METADATA_XML` → `aws/terraform/variables/saml-metadata.xml` |
| 5 | descobre o IP de saída (`curl -s https://checkip.amazonaws.com`); **valida que é IPv4 e falha alto** se não for |
| 6 | `up-02-region --region <r> --with-cell --public-cidr <ip>/32 --yes` |
| 7 | `if: always()` — `up-02-region --region <r> --with-cell --close-public-access --yes` |

O passo 5 falhar alto em vez de assumir formato é regra da spec anterior: runners github-hosted não garantem IPv6 estável, e um `/32` malformado viraria `AccessDenied` num lugar distante da causa.

## `.github/workflows/recover-lock.yml`

`workflow_dispatch` com inputs `region` e `lock_id`, **ambos obrigatórios e sem default**: `terraform force-unlock -force <lock_id>` seguido de `plan`, falhando se o plan mostrar recurso duplicado (sinal de órfão fora do state, cuja recuperação é `import` — receita em `aws/terraform/CLAUDE.md`).

**Por que gatilho separado, e não recuperação automática dentro do job principal:** esta sessão (2026-08-31) esbarrou num lock órfão de outra máquina e a decisão certa foi *não* forçar às cegas — só depois de o operador confirmar que nenhum `apply` estava vivo. Automatizar isso dentro do job replicaria exatamente o risco: um lock de execução concorrente seria destravado sem confirmação. Exigir que um humano leia o erro, confirme, e passe o `lock_id` à mão é a barreira, e o `lock_id` obrigatório é o que a torna real. Isso satisfaz o critério de aceite da issue #41 pela via de "documentar por que essa parte ficou de fora" da automação total.

## Mapa de bootstrap: `aws/terraform/bootstrap-checklist.md`

Checklist numerada com checkboxes, do zero até o primeiro dispatch bem-sucedido, dizendo para cada item **quem executa** (admin humano / console / CI) e **onde** o detalhe vive — sem duplicar conteúdo, apontando para `README.md`, `ci/README.md` e os docs de `aws/docs/`:

1. Organization, contas, OUs, Identity Center (`aws/docs/accounts/`)
2. Aprovar a região na SCP
3. `up-00-state-backend`
4. `up-01-dns`
5. Aplicação SAML no Identity Center (console) → `variables/saml-metadata.xml`
6. `terraform apply` da raiz `ci/` (roles OIDC)
7. Secret `SAML_METADATA_XML` no GitHub
8. Primeiro `workflow_dispatch` de `provision-region.yml`

Referenciada de `aws/terraform/README.md`, que continua sendo a sequência executável para operação local. O valor da checklist é ordenação e completude — o atrito real desta frente foi descobrir, uma peça por vez, que faltava `values.tfvars`, faltava o metadata SAML, faltava o symlink. Um passo esquecido custa um `apply` que morre no meio.

## Limitações conhecidas (viram issues)

| Limitação | Detalhe |
|---|---|
| **Role chaining trava a sessão em 1h** | A doc da IAM é explícita: *"When you use role chaining, the session duration is limited to one hour, regardless of the maximum session duration setting configured for individual roles."* O profile `network` encadeia de `cicd`, então **nenhum** `max_session_duration` levanta esse teto. O `apply` da célula leva 20-30 min: a margem existe, mas é fina, e o modo de falha (renovação falhando no meio de um apply) é confuso e longe da causa. Mitigação, se apertar: dar trust OIDC direto à role da `network` em vez de encadear — o que abandona o espelhamento da cadeia atual, e por isso não foi feito agora |
| `sub` aceita `refs/heads/*` | Apertar para `refs/heads/main` depois de o workflow estar validado |
| Endpoint público aberto se o job morrer antes do passo 7 | Já aceito na spec anterior; sem sweep agendado, por decisão explícita |
| `values.tfvars` versionado | Só porque as contas são efêmeras — reverter para gitignored quando deixarem de ser |
| `saml-metadata.xml` em secret do GitHub | Rotação do certificado do Identity Center exige atualizar o secret à mão; sintoma seria falha de validação do Client VPN, longe da causa |

## Fora de escopo

- Mecanismo de acesso privado de produção — issue #45 (CodeBuild, ARC-em-cluster, self-hosted efêmero)
- Acesso administrativo humano multi-região — issue #40
- Migrar os scripts `install-*` do Crossplane ou o GitOps para Actions — escopo é só o Terraform de `aws/terraform/`
- Automatizar a criação da aplicação SAML — impossível via API (`CreateApplication` só cria OAuth 2.0 customizado)
- `down-cell` em CI — o teardown noturno segue local; nada neste desenho impede acrescentar depois

## Referências

- Issue #41 — obstáculos 3 e 4
- `2026-08-31-github-actions-runner-private-access-design.md` — obstáculo 2, implementado na PR #46
- `2026-08-27-terraform-orchestration-tooling.md` — a análise original que identificou os três obstáculos
- `2026-08-27-saml-metadata-secrets-manager.md` — alternativa não escolhida para o metadata
- [ADR 0014](../../adr/0014-single-regional-root-composing-hub-and-cell-modules.md) — a raiz regional que o workflow orquestra
- [Cross-account access (EKS)](https://docs.aws.amazon.com/eks/latest/userguide/cross-account-access.html) — o par de profiles `web_identity_token_file` + `source_profile`
- [OIDC provider thumbprint list (IAM)](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_providers_create_oidc_verify-thumbprint.html) — por que omitir o thumbprint
- [Role sessions (IAM)](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_use_switch-role-console.html) — o cap de 1h do role chaining
