# ci/ — GitHub Actions: trust OIDC, configuração e workflows

Documento único da automação, dos dois lados. **Lado AWS:** esta raiz T0, aplicada uma vez por um
admin humano com os profiles `cicd`/`network` — mesma disciplina de `state-backend/` —, que cria um
`aws_iam_openid_connect_provider` do GitHub Actions na conta `cicd` mais uma role por conta.
**Lado GitHub:** as variables e secrets do repositório, o GitHub App que dá acesso ao composite
action privado, o próprio action e os três workflows, com exemplos de execução via `gh`.

Os workflows moram em `.github/workflows/` — o GitHub exige esse caminho. A documentação deles é
aqui.

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
6. Criar o GitHub App e configurar `APP_ID`/`APP_PRIVATE_KEY` — ver "O GitHub App", abaixo.

## As duas identidades, que não se confundem

Todo workflow atravessa **duas** autenticações independentes, e falha nas duas de formas parecidas
o bastante para confundir:

| | Autentica o quê | Mecanismo | Onde configurar |
|---|---|---|---|
| **GitHub App** | O runner lendo o repositório **privado** `wasp-gitops`, de onde vem o composite action | Installation token de curta duração, gerado por `actions/create-github-app-token` | Secrets `APP_ID` + `APP_PRIVATE_KEY` |
| **OIDC → AWS** | O runner falando com a AWS (duas contas) | `AssumeRoleWithWebIdentity` + role chaining | Variables `CICD_ROLE_ARN` + `NETWORK_ROLE_ARN` |

A primeira falha **antes** de qualquer step rodar (`uses:` não resolve); a segunda falha no
primeiro comando `aws`/`terraform`.

## Repository variables

São variables, não secrets, porque nenhuma delas é sigilosa — ARN de role e nome de bucket são
identificadores, e o controle de acesso está no trust policy e na policy do bucket, não no fato de
o valor ser desconhecido.

| Variable | Por que existe |
|---|---|
| `CICD_ROLE_ARN` | Role assumida via OIDC na conta `cicd`. É a **única** que confia no provider OIDC do GitHub; é dela que a sessão do job inteiro nasce. Aplica `module.cell`. |
| `NETWORK_ROLE_ARN` | Role na conta `network`, assumida **por encadeamento** a partir da `cicd`. Aplica `module.hub` (TGW, Client VPN, ALB de ingress) e cria o SAML provider do Client VPN. Não confia no OIDC — só na `cicd`. |
| `STATE_BUCKET` | Bucket do state remoto. Existe como variable porque os scripts o descobrem por `aws organizations describe-organization`, chamada que exige a management account — permissão que o runner **não** tem e não deve ter. Passar o nome pronto evita conceder acesso à Organization inteira para ler um identificador. |

## Repository secrets

| Secret | Conteúdo | Por que existe |
|---|---|---|
| `APP_ID` | ID numérico do GitHub App | Identifica o App na geração do installation token. |
| `APP_PRIVATE_KEY` | Chave privada PEM do App | Assina o JWT que troca por um installation token. **É a credencial de verdade** deste par — rotacionar aqui é rotacionar o acesso ao `wasp-gitops`. |
| `SAML_METADATA_XML` | Conteúdo de `variables/saml-metadata.xml` | `module.hub` faz `file(var.saml_metadata_path)` a **todo plan**, inclusive os de um destroy. O arquivo é gitignored (identifica a instância do Identity Center), então o runner o materializa a partir daqui. Não é gerado: aplicação SAML do Identity Center não é Terraform (a `CreateApplication` API só cria aplicações OAuth 2.0 customizadas), o XML vem de um passo de console. |

**Rotação do certificado do Identity Center invalida o `SAML_METADATA_XML`** e exige atualizá-lo à
mão — issue #51.

## O GitHub App, e por que ele é necessário

O composite action `aws/setup` mora em `smsilva/wasp-gitops`, que é **privado**. O `GITHUB_TOKEN`
de um workflow de repositório público não alcança repositório privado, nem do mesmo dono — então
`uses: smsilva/wasp-gitops/actions/aws/setup@main` falha na resolução do action, antes de qualquer
step executar.

Solução em vigor (PR #52): um GitHub App (`wasp-idp-actions-reader`) com **Contents: Read** no
`wasp-gitops`, instalado na conta. O workflow gera um installation token de curta duração, faz
`checkout` do repo privado para dentro da árvore de trabalho e referencia o action por **caminho
local**:

```yaml
- name: Generate App Token for wasp-gitops
  id: app-token
  uses: actions/create-github-app-token@v1
  with:
    app-id: ${{ secrets.APP_ID }}
    private-key: ${{ secrets.APP_PRIVATE_KEY }}
    owner: ${{ github.repository_owner }}
    repositories: wasp-gitops

- name: Checkout wasp-gitops (private action repo)
  uses: actions/checkout@v4
  with:
    repository: smsilva/wasp-gitops
    token: ${{ steps.app-token.outputs.token }}
    path: .github/actions/wasp-gitops

- name: Setup AWS auth, SAML, Terraform
  uses: ./.github/actions/wasp-gitops/actions/aws/setup   # caminho local, não repo@ref
```

O `repositories: wasp-gitops` no token escopa a permissão a esse único repositório, mesmo que o App
esteja instalado em mais.

Alternativa não adotada: tornar o action acessível pela configuração *Actions → General → Access*
do `wasp-gitops`. Funciona, mas é permissão implícita e invisível no código — quem lê o workflow
não descobre por que ele funciona.

## O composite action `aws/setup`

Preâmbulo comum, extraído para não existir em três cópias (refatoração de `cd8698f`). Fonte:
`wasp-gitops/actions/aws/setup/action.yaml`.

**Inputs:** `cicd_role_arn`, `network_role_arn`, `role_session_name`, `saml_metadata_xml`
(obrigatórios), `terraform_version` (default `1.15.0`). **Output:** `egress_ip` — IPv4 público do
runner.

Quatro steps, nesta ordem:

1. **`configure-oidc`** — busca o JWT OIDC do runner e o troca **uma vez** por credenciais estáticas
   da `cicd` (`--duration-seconds 21600`), gravando `~/.aws/credentials` e um `~/.aws/config` com o
   profile `network` encadeado (`source_profile = cicd`). O porquê das duas expirações está na
   seção "Credenciais que sobrevivem ao `apply`", abaixo.
2. **`write-saml-metadata`** — grava o secret em `aws/terraform/variables/saml-metadata.xml`. O
   script `save-file` **falha se a variável estiver vazia**, em vez de escrever arquivo vazio: um
   XML vazio passaria pela validação de tamanho do provider como erro muito mais adiante.
3. **`discover-egress-ip`** — `curl https://checkip.amazonaws.com`, com validação de formato IPv4.
   É este IP que vira `--public-cidr <ip>/32` nos scripts, restringindo o endpoint público da API
   do EKS ao runner. A validação não é zelo: um portal cativo ou resposta HTML devolveria 200 com
   corpo inválido, e o CIDR malformado só falharia dentro do `apply`.
4. **`setup-terraform`** — `hashicorp/setup-terraform@v3`.

## Workflows

Os três são `workflow_dispatch` puro — nada roda em `push`. A `region` nunca tem default nos dois
destrutivos: escolher a região é decisão, não conveniência.

### `provision-region.yml`

Provisiona hub + célula. Chama `scripts/up-02-region --with-cell --public-cidr <egress>/32`, que faz
**um único plan/apply** de `module.hub` e `module.cell` juntos.

O apply do zero ser único não é detalhe de estilo: `depends_on` é aresta de grafo, e um apply
fragmentado por `-target` não prova ordenação nenhuma. Foi assim que a race de Pod Identity do EBS
CSI ficou escondida (issue #52, PR #61).

O segundo step, `Close public endpoint`, roda com `if: always()` — no caminho de falha o endpoint
público fica mesmo aberto, e fechá-lo é justamente o que não pode depender de sucesso. Ele é
**cleanup**, não apply completo: `-target` no cluster, e no-op quando não há célula em state.

Custo: a célula custa ~US$ 165/mês além do hub (~US$ 110/mês). **Não deixar de pé entre sessões.**

### `teardown-region.yml`

Destrói `module.cell` com `-target=module.cell`; **o hub fica de pé**. Chama `scripts/down-cell`,
que abre o endpoint público antes do destroy (o refresh precisa alcançar a API) e o fecha no step
final, também com `if: always()` e o mesmo guard de state.

O corte é `hub | célula`, nunca `rede | cluster`: Terraform destrói em ordem reversa só dentro do
mesmo state, e esse corte sobrevive ao TGW — a AWS recusa deletar TGW com attachment vivo.

### `recover-lock.yml`

Recuperação de lock de state órfão (`Error acquiring the state lock`), quando um apply morre no
meio. Roda `terraform force-unlock -force <lock_id>` e em seguida um `plan` para revisão humana.

**Ler o plan é obrigatório**, e o workflow emite um `::notice::` dizendo isso: um plan propondo
**criar** recurso que deveria existir significa que o apply morto deixou recurso fora do state — e
aí a recuperação é `terraform import`, não `force-unlock`. Ver `../CLAUDE.md`, seção "State".

> **Nunca foi executado, e tem dois defeitos conhecidos** — ver "Limitações conhecidas", abaixo.

## Executando via `gh`

```bash
# Provisionar us-east-1 (hub + célula)
gh workflow run provision-region.yml --ref main -f region=us-east-1

# Destruir a célula de us-east-1 (o hub fica de pé)
gh workflow run teardown-region.yml --ref main -f region=us-east-1

# Recuperar um lock órfão
gh workflow run recover-lock.yml --ref main \
  -f region=us-east-1 \
  -f lock_id=8f3a1c9e-4b7d-11ef-9c2a-0242ac120002
```

`--ref main` é obrigatório, e não por convenção: o trust policy da role `cicd` restringe o claim
`sub` a `ref:refs/heads/main` (issue #48). Disparar de um branch resolve o workflow normalmente e
falha no `AssumeRoleWithWebIdentity`, com uma mensagem que não menciona branch nenhum. **Merge antes
de validar em CI** — não há caminho de teste em branch.

Acompanhando a execução:

```bash
# Descobrir o id do run recém-disparado
gh run list --workflow=provision-region.yml --limit 1 \
  --json databaseId,status,headSha --jq '.[]|.databaseId,.status,.headSha'

# Status sem baixar o log inteiro
gh api repos/smsilva/wasp-idp/actions/runs/<run_id> \
  --jq '.status+" / "+(.conclusion//"running")'

# Grep no log completo (o log de um provisionamento passa de 10 MB)
gh run view <run_id> --log | grep -E "Apply complete|Destroy complete|Error:"

# Cancelar
gh run cancel <run_id>
```

Um provisionamento leva 20-30 min e um teardown ~8 min; sondar em intervalos de ~5 min é suficiente.

## Limitações conhecidas

- **`recover-lock.yml` ainda referencia o action privado direto** —
  `uses: smsilva/wasp-gitops/actions/aws/setup@main`. O fix do App token (PR #52) tocou apenas
  `provision-region.yml` e `teardown-region.yml`; este ficou para trás e vai falhar na resolução do
  action. Nunca apareceu porque o workflow nunca foi executado.
- **`recover-lock.yml` cria só o symlink de `values.auto.tfvars`**, não o de `saml-metadata.xml`.
  Como `module.hub` faz `file(var.saml_metadata_path)` em todo plan, o `terraform plan` do step de
  revisão falha por arquivo ausente — mesma causa que derrubou o teardown na run `33512301706` e foi
  corrigida no `down-cell` pelo PR #58. Ele também duplica o `ln`/`init` em vez de usar
  `scripts/lib`, que é onde essa lógica passou a viver.
- **Endpoint público fica aberto se o job morrer antes do step de fechamento** — issue #49. O
  `if: always()` cobre falha de step, não cancelamento nem morte do runner.

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

## Manter este arquivo verdadeiro

| O que mudou | Onde atualizar aqui |
|---|---|
| Variable/secret novo, ou mudança de propósito de um existente | As duas tabelas — e a coluna "por que existe", que é o que impede alguém remover a variable por parecer redundante |
| Step novo no `aws/setup` (repo `wasp-gitops`) | A lista numerada dos quatro steps |
| Workflow novo, ou mudança na flag que um script recebe | A seção do workflow **e** o exemplo de `gh` |
| Recurso novo nesta raiz, ou mudança de trust/permissão | Passo a passo, e a seção de permissões |
| Defeito encontrado e corrigido | Sai de "Limitações conhecidas"; a narrativa vai para `../../docs/lessons-learned/` |

Este é o documento **único** da automação — os dois lados moram aqui de propósito. A tentativa de
separar em `terraform/github/README.md` durou um PR: ninguém lembra que existe um segundo arquivo,
e duas fontes garantem que uma esteja errada.
