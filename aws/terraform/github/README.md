# GitHub Actions — configuração, workflows e execução

Como a automação deste repositório autentica na AWS e o que cada workflow faz. Complementa
[`../ci/README.md`](../ci/README.md), que é o **lado AWS** (a raiz Terraform que cria o provider
OIDC e as duas roles). Aqui fica o **lado GitHub**: variables, secrets, o GitHub App, o composite
action compartilhado e os três workflows — com exemplos de execução via `gh`.

Os workflows moram em `.github/workflows/` (o GitHub exige esse caminho); esta pasta é só a
documentação deles.

## As duas identidades, que não se confundem

Todo workflow atravessa **duas** autenticações independentes, e falha nas duas de formas
parecidas o bastante para confundir:

| | Autentica o quê | Mecanismo | Onde configurar |
|---|---|---|---|
| **GitHub App** | O runner lendo o repositório **privado** `wasp-gitops`, de onde vem o composite action | Installation token de curta duração, gerado por `actions/create-github-app-token` | Secrets `APP_ID` + `APP_PRIVATE_KEY` |
| **OIDC → AWS** | O runner falando com a AWS (duas contas) | `AssumeRoleWithWebIdentity` + role chaining | Variables `CICD_ROLE_ARN` + `NETWORK_ROLE_ARN` |

A primeira falha **antes** de qualquer step rodar (`uses:` não resolve); a segunda falha no
primeiro comando `aws`/`terraform`.

## Repository variables

Settings → Secrets and variables → Actions → **Variables**. São variables, não secrets, porque
nenhuma delas é sigilosa — ARN de role e nome de bucket são identificadores, e o controle de
acesso está no trust policy e na policy do bucket, não no fato de o valor ser desconhecido.

| Variable | Origem do valor | Por que existe |
|---|---|---|
| `CICD_ROLE_ARN` | `terraform output -raw cicd_role_arn` em `../ci/` | Role assumida via OIDC na conta `cicd`. É a **única** que confia no provider OIDC do GitHub; é dela que a sessão do job inteiro nasce. Aplica `module.cell`. |
| `NETWORK_ROLE_ARN` | `terraform output -raw network_role_arn` em `../ci/` | Role na conta `network`, assumida **por encadeamento** a partir da `cicd`. Aplica `module.hub` (TGW, Client VPN, ALB de ingress) e cria o SAML provider do Client VPN. Não confia no OIDC — só na `cicd`. |
| `STATE_BUCKET` | `tfstate-<organization-id>` | Bucket do state remoto. Existe como variable porque os scripts o descobrem por `aws organizations describe-organization`, chamada que exige a management account — permissão que o runner **não** tem e não deve ter. Passar o nome pronto evita conceder acesso à Organization inteira para ler um identificador. |

## Repository secrets

Settings → Secrets and variables → Actions → **Secrets**.

| Secret | Conteúdo | Por que existe |
|---|---|---|
| `APP_ID` | ID numérico do GitHub App | Identifica o App na geração do installation token. |
| `APP_PRIVATE_KEY` | Chave privada PEM do App | Assina o JWT que troca por um installation token. **É a credencial de verdade** deste par — rotacionar aqui é rotacionar o acesso ao `wasp-gitops`. |
| `SAML_METADATA_XML` | Conteúdo de `variables/saml-metadata.xml` | `module.hub` faz `file(var.saml_metadata_path)` a **todo plan**, inclusive os de um destroy. O arquivo é gitignored (identifica a instância do Identity Center), então o runner o materializa a partir daqui. Não é gerado: aplicação SAML do Identity Center não é Terraform (a `CreateApplication` API só cria aplicações OAuth 2.0 customizadas), o XML vem de um passo de console. |

**Rotação do certificado do Identity Center invalida o `SAML_METADATA_XML`** e exige atualizá-lo
à mão — issue #51.

## O GitHub App, e por que ele é necessário

O composite action `aws/setup` mora em `smsilva/wasp-gitops`, que é **privado**. O `GITHUB_TOKEN`
de um workflow de repositório público não alcança repositório privado, nem do mesmo dono — então
`uses: smsilva/wasp-gitops/actions/aws/setup@main` falha na resolução do action, antes de
qualquer step executar.

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

O `repositories: wasp-gitops` no token escopa a permissão a esse único repositório, mesmo que o
App esteja instalado em mais.

Alternativa não adotada: tornar o action acessível pela configuração
*Actions → General → Access* do `wasp-gitops`. Funciona, mas é permissão implícita e invisível no
código — quem lê o workflow não descobre por que ele funciona.

## O composite action `aws/setup`

Preâmbulo comum, extraído para não existir em três cópias (refatoração de `cd8698f`). Fonte:
`wasp-gitops/actions/aws/setup/action.yaml`.

**Inputs:** `cicd_role_arn`, `network_role_arn`, `role_session_name` (obrigatórios),
`saml_metadata_xml` (obrigatório), `terraform_version` (default `1.15.0`).

**Output:** `egress_ip` — IPv4 público do runner.

Quatro steps, nesta ordem:

1. **`configure-oidc`** — busca o JWT OIDC do runner e o troca **uma vez** por credenciais
   estáticas da `cicd` (`--duration-seconds 21600`), gravando `~/.aws/credentials` e um
   `~/.aws/config` com o profile `network` encadeado (`source_profile = cicd`). O porquê das duas
   expirações — o JWT de ~5 min e o cap de 1h do role chaining — está em
   [`../ci/README.md`](../ci/README.md), seção "Credenciais que sobrevivem ao `apply`". Resumo:
   deixar `web_identity_token_file` apontando para o JWT mata o apply em 5 min com
   `ExpiredTokenException`; a sessão da `network` continua capada em 1h, mas isso deixou de ser
   fatal porque o SDK a re-deriva da `cicd`, que vive 6h.
2. **`write-saml-metadata`** — grava o secret em `aws/terraform/variables/saml-metadata.xml`.
   O script `save-file` **falha se a variável estiver vazia**, em vez de escrever arquivo vazio:
   um XML vazio passaria pela validação de tamanho do provider como erro muito mais adiante.
3. **`discover-egress-ip`** — `curl https://checkip.amazonaws.com`, com validação de formato
   IPv4. É este IP que vira `--public-cidr <ip>/32` nos scripts, restringindo o endpoint público
   da API do EKS ao runner. A validação não é zelo: um portal cativo ou resposta HTML devolveria
   200 com corpo inválido, e o CIDR malformado só falharia dentro do `apply`.
4. **`setup-terraform`** — `hashicorp/setup-terraform@v3`.

## Workflows

Os três são `workflow_dispatch` puro — nada roda em `push`. A `region` nunca tem default nos dois
destrutivos: escolher a região é decisão, não conveniência.

### `provision-region.yml`

Provisiona hub + célula. Chama `scripts/up-02-region --with-cell --public-cidr <egress>/32`, que
faz **um único plan/apply** de `module.hub` e `module.cell` juntos.

O apply do zero ser único não é detalhe de estilo: `depends_on` é aresta de grafo, e um apply
fragmentado por `-target` não prova ordenação nenhuma. Foi assim que a race de Pod Identity do
EBS CSI ficou escondida (issue #52, PR #61).

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

> **Este workflow nunca foi executado e tem dois defeitos conhecidos** — ver "Limitações
> conhecidas", abaixo.

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
falha no `AssumeRoleWithWebIdentity`, com uma mensagem que não menciona branch nenhum. **Merge
antes de validar em CI** — não há caminho de teste em branch.

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

Um provisionamento leva 20-30 min e um teardown ~8 min; sondar em intervalos de ~5 min é
suficiente.

## Limitações conhecidas

- **`recover-lock.yml` ainda referencia o action privado direto** —
  `uses: smsilva/wasp-gitops/actions/aws/setup@main`. O fix do App token (PR #52) tocou apenas
  `provision-region.yml` e `teardown-region.yml`; este ficou para trás e vai falhar na resolução
  do action. Nunca apareceu porque o workflow nunca foi executado.
- **`recover-lock.yml` cria só o symlink de `values.auto.tfvars`**, não o de `saml-metadata.xml`.
  Como `module.hub` faz `file(var.saml_metadata_path)` em todo plan, o `terraform plan` do step de
  revisão falha por arquivo ausente — mesma causa que derrubou o teardown na run `33512301706` e
  foi corrigida no `down-cell` pelo PR #58. Ele também duplica o `ln`/`init` em vez de usar
  `scripts/lib`, que é onde essa lógica passou a viver.
- **Endpoint público fica aberto se o job morrer antes do step de fechamento** — issue #49. O
  `if: always()` cobre falha de step, não cancelamento nem morte do runner.
- **Roles de CI usam `PowerUserAccess` + inline de IAM** — fallback declarado, não descuido; ver
  [`../ci/README.md`](../ci/README.md).

## Manter este arquivo verdadeiro

| O que mudou | Onde atualizar aqui |
|---|---|
| Variable/secret novo, ou mudança de propósito de um existente | As duas tabelas — e a coluna "por que existe", que é o que impede alguém remover a variable por parecer redundante |
| Step novo no `aws/setup` (repo `wasp-gitops`) | A lista numerada dos quatro steps |
| Workflow novo, ou mudança na flag que um script recebe | A seção do workflow **e** o exemplo de `gh` |
| Defeito encontrado e corrigido | Sai de "Limitações conhecidas"; a narrativa vai para `../../docs/lessons-learned/` |

O lado AWS — trust OIDC, as duas roles, thumbprint, duração de sessão — mora em
[`../ci/README.md`](../ci/README.md). Não duplicar: duas fontes garantem que uma esteja errada.
