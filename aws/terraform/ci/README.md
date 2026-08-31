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

## Credenciais que sobrevivem ao `apply`: as duas expirações, e como cada uma foi resolvida

O provisionamento de uma região leva 20-30 min (mais, com retries). Duas expirações diferentes
mataram o `workflow_dispatch` no meio antes de o desenho atual fechar — vale entender as duas,
porque a segunda é a que costuma ser confundida com a primeira.

**1. O token OIDC do GitHub vive ~5 min.** A primeira versão do workflow escrevia
`web_identity_token_file` apontando pro arquivo do JWT bruto (`curl` uma vez, salvo em
`/tmp/gha-oidc-token`) e deixava o SDK reautenticar a partir dele a cada renovação de sessão.
Num apply real isso morreu em 5 minutos com `ExpiredTokenException` — confirmado no CloudTrail
(job às 22:08:44, `exp` do token às 22:13:46). O JWT é de uso imediato: serve para *trocar* por
credenciais, não para ficar em disco. Fix: `aws sts assume-role-with-web-identity` **uma vez**,
no início do job, gravando o resultado em `~/.aws/credentials`. O token nunca mais é lido.

**2. A sessão resultante expira — e o token para renovar já não existe.** Trocar por credenciais
de 1h só empurra o problema: quando a hora acaba, não há como renovar (o JWT de 5 min morreu há
muito). A saída é fazer a sessão **fonte** durar o job inteiro:

- A sessão da `cicd` nasce de `AssumeRoleWithWebIdentity`, cujo `DurationSeconds` vai de 900s até
  o `MaxSessionDuration` **da role** ([doc da STS](https://docs.aws.amazon.com/STS/latest/APIReference/API_AssumeRoleWithWebIdentity.html)),
  que aceita de 1h a 12h. **O teto de 1h do role chaining não se aplica a ela** — esse teto vale
  para `AssumeRole` a partir de credenciais de role, não para web identity. Daí
  `max_session_duration = 21600` (6h, o teto de um job em runner hospedado pelo GitHub) na role
  e `--duration-seconds 21600` na troca.
- A sessão da `network` **continua capada em 1h**, porque essa sim é role chaining
  (`source_profile = cicd`): *"When you use role chaining, the session duration is limited to one
  hour, regardless of the maximum session duration setting configured for individual roles"*.
  A diferença é que isso deixou de ser fatal: quando ela expira, o SDK simplesmente chama
  `AssumeRole` de novo usando as credenciais da `cicd`, que ainda estão vivas. O cap continua
  existindo; ele só não interrompe mais nada.

Vale para o `terraform` e também para os providers `kubernetes`/`helm`, que autenticam por
`exec` chamando `aws eks get-token --profile ...` a cada recurso — todos leem a mesma cadeia.

## Gotcha de teste: `override_resource` não propaga para recurso sob provider aliasado

`terraform test` com `mock_provider` funciona normalmente para o provider default, mas
`override_resource` sobre um recurso declarado com `provider = aws.network` (a role `network`
desta raiz) não propagou o atributo fixado para os consumidores desse recurso — nem sob
`command = plan` nem sob `command = apply`, testado nas duas formas. Contorno usado em
`tests/roles.tftest.hcl` (run `cicd_pode_assumir_a_role_network`): comparar o campo `Resource`
da policy diretamente contra `aws_iam_role.network.arn` (igualdade de referência, não
substring do nome) — os dois leem o mesmo atributo computado do mock, então são iguais mesmo
sendo um valor sintético, e a asserção prova a referência sem depender do override.
