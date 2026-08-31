# ci/ — trust OIDC GitHub → AWS

Raiz T0, aplicada uma vez por um admin humano com os profiles `cicd`/`network` — mesma
disciplina de `state-backend/`. Cria o que o workflow `.github/workflows/provision-region.yml`
usa para autenticar: um `aws_iam_openid_connect_provider` do GitHub Actions na conta `cicd`,
mais uma role por conta.

## Passo a passo

1. `terraform init -backend-config="bucket=$(aws organizations describe-organization --profile personal --query Organization.Id --output text | sed 's/^/tfstate-/')"`
2. `terraform plan` — revisar antes de aplicar; é IAM em duas contas.
3. `terraform apply`
4. Ler as duas ARNs de saída e configurar no repositório GitHub (Settings → Secrets and variables → Actions → Variables):

   | Variable | Valor |
   |---|---|
   | `CICD_ROLE_ARN` | `terraform output -raw cicd_role_arn` |
   | `NETWORK_ROLE_ARN` | `terraform output -raw network_role_arn` |
   | `STATE_BUCKET` | `tfstate-<organization-id>` (mesmo valor do passo 1, sem o `terraform.tfstate` da key) |

5. Configurar o secret `SAML_METADATA_XML` (Settings → Secrets and variables → Actions → Secrets) com o conteúdo de `variables/saml-metadata.xml` — ver `aws/terraform/README.md` para de onde esse arquivo vem.

## Por que trust só na `cicd`, e a `network` confia só na `cicd`

Ver `docs/superpowers/specs/2026-08-31-github-actions-provisioning-workflow-design.md`, seção
"Trust: OIDC só na cicd, network confia na cicd". Resumo: um único provider OIDC evita duplicar
URL/`client_id_list`/condições em duas contas, e espelha a cadeia que já existe operacionalmente
(`personal` → `network`/`cicd`).

## Por que `thumbprint_list` fica vazio

A AWS valida o endpoint JWKS pela própria biblioteca de CAs raiz confiáveis; para o GitHub, um
thumbprint configurado *"is retained in the configuration but not used for verification"* — ver
[OIDC provider thumbprint list (IAM)](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_providers_create_oidc_verify-thumbprint.html).
Fixar um aqui só cria uma armadilha de rotação de certificado, por zero segurança a mais.

## Permissões: `PowerUserAccess` + inline (fallback declarado, não descuido)

As duas roles usam `PowerUserAccess` mais um inline escopado para IAM (que `PowerUserAccess`
exclui por desenho da AWS) e para o `sts:AssumeRole` encadeado. Derivar o escopo fino por módulo
— o que `module.hub` e `module.cell` de fato criam — é trabalho futuro; ver a issue de
"least-privilege das roles de CI" (aberta junto com este workflow).

## Limitação: role chaining trava a sessão em 1h

A role `network` encadeia de `cicd` (`source_profile`). A doc da IAM é explícita: *"When you use
role chaining, the session duration is limited to one hour, regardless of the maximum session
duration setting configured for individual roles"* — nenhum `max_session_duration` levanta esse
teto. O `apply` da célula leva 20-30 min; a margem existe, mas é fina. Ver issue dedicada.

## Gotcha real: o token OIDC do GitHub não sobrevive ao `apply`

A primeira versão do workflow escrevia `web_identity_token_file` apontando pro arquivo do token
OIDC bruto (curl uma vez, salvo em `/tmp/gha-oidc-token`) e deixava o SDK reautenticar a partir
dele a cada renovação de sessão. Isso quebrou num `workflow_dispatch` real: o token do GitHub tem
vida curta (~5 min) — bem menos que os 20-30 min de um `up-02-region --with-cell` — e a primeira
renovação de sessão no meio do apply falhou com `ExpiredTokenException`, matando o `terraform
apply` no meio e deixando recursos órfãos fora do state até a correção. Fix: trocar o token OIDC
por credenciais estáticas da `cicd` **uma vez**, via `aws sts assume-role-with-web-identity
--duration-seconds 3600`, gravadas em `~/.aws/credentials`; a `network` encadeia dessas
credenciais estáticas (`source_profile = cicd` em `~/.aws/config`), sem nunca reler o token OIDC.
Isso não elimina a limitação de 1h acima — só evita expirar bem antes dela.

## Gotcha de teste: `override_resource` não propaga para recurso sob provider aliasado

`terraform test` com `mock_provider` funciona normalmente para o provider default, mas
`override_resource` sobre um recurso declarado com `provider = aws.network` (a role `network`
desta raiz) não propagou o atributo fixado para os consumidores desse recurso — nem sob
`command = plan` nem sob `command = apply`, testado nas duas formas. Contorno usado em
`tests/roles.tftest.hcl` (run `cicd_pode_assumir_a_role_network`): comparar o campo `Resource`
da policy diretamente contra `aws_iam_role.network.arn` (igualdade de referência, não
substring do nome) — os dois leem o mesmo atributo computado do mock, então são iguais mesmo
sendo um valor sintético, e a asserção prova a referência sem depender do override.
