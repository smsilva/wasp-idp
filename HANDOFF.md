# HANDOFF

## Why

Exercitar a PoC AWS EKS-via-Crossplane (arquitetura de referência hub-and-spoke) na conta AWS
pessoal do Silvio, genérica, antes de qualquer ambiente corporativo. `aws/` foi genericizada a
partir de um exemplo interno (placeholders `<...>` para valores por-conta/segredos; valores
genéricos concretos como `platform.example.com`/`poc-eks` onde o token é YAML/Crossplane
executável). Valores reais ficam em `CLAUDE.local.md` (gitignored); os valores de identidade das camadas
Terraform vivem em `aws/terraform/variables/values.tfvars` gitignored, carregado por cada raiz via
symlink `values.auto.tfvars` (ver `aws/terraform/variables/README.md` e o
[ADR 0014](docs/adr/0014-single-regional-root-composing-hub-and-cell-modules.md), que escolheu o
formato tfvars no lugar do `values.yaml` previsto no [ADR 0013](docs/adr/0013-consolidate-local-values-yaml.md)).

Decisões de arquitetura que orientam esta frente (sequência de provisionamento, escopo fino do
Terraform, alocação de CIDR, ingress centralizado, etc.) vivem em [`docs/adr/`](docs/adr/README.md)
— ler antes de propor mudança de rumo, não rederivar do zero.

### VPN

O desenho assume `Site-to-Site VPN` por cliente ([ADR 0005](docs/adr/0005-site-to-site-vpn-per-client.md)).

## Vocabulário (ler antes de qualquer coisa)

"hub" cobria três eixos independentes e a ambiguidade custou tempo. Dois foram renomeados; só o
topológico mantém o termo:

| Eixo | Nome correto | Nome antigo |
|---|---|---|
| **Conta AWS** de conectividade | `network` — Connectivity Account, OU `Infrastructure` | "conta hub", profile `hub`, ProviderConfig `hub` |
| **Papel topológico** de rede | `hub` — único uso legítimo. Par de `spoke`; chart `platform/charts/hub`, VPC hub, TGW | (inalterado) |
| **Control plane** Crossplane (k3d) | **Control Plane** / `control-plane` | "hub k3d", `poc-eks-hub-config` |
| **Conta** do Control Plane | `cicd`, na OU `Deployments` | `platform` |

`network` é canônico no whitepaper *Organizing Your AWS Environment Using Multiple Accounts*, no
AWS SRA e no Landing Zone Accelerator. A AWS **não** nomeia contas como "Hub".

O chart `platform/charts/hub` **não** foi renomeado de propósito: ali "hub" é topologia, e
`network` colidiria com o XR `Network` que ele renderiza.

O prefixo `poc-idp/` no Secrets Manager (`poc-idp/crossplane-poc-credentials`) é o nome real de um
secret na AWS, não apelido do cluster — **não renomear**.

**Hierarquia de fontes AWS:** **WAF** diz *por quê* isolar por conta e **nomeia zero contas e
zero OUs**; o **whitepaper** nomeia OUs (`Security`, `Infrastructure`, `Workloads`, `Sandbox`,
`Deployments`, …); o **SRA** nomeia contas (`Shared Services`, `Network`, …). Tabela em
`aws/docs/accounts/01-organizations-and-ous.md`.

## Estado atual

Não presumir o que está de pé pelo handoff — conferir sempre:

```bash
cd aws/terraform
for m in state-backend dns regions/us-east-1 regions/us-west-2; do
  printf '%-32s %s\n' "${m}" "$( (cd "${m}" && terraform state list 2>/dev/null | grep -vc '^data\.') )"
done
k3d cluster list
```

**2026-08-30 (fase 4):** as raízes antigas (`network-foundation/`, `connectivity/`, `control-plane/`)
e os scripts `up-01`/`up-03`/`up-04` foram apagados do disco e do bucket de state — o conteúdo vive
em `src/hub`/`src/cell`, consumidos por `regions/<região>/`. `regions/us-west-2/` existe (`plan`
verde, sem recursos aplicados). Scripts renumerados: `up-00-state-backend`, `up-01-dns`,
`up-02-region`. `aws/terraform/README.md` reflete a sequência — fonte de verdade para custo/ordem.

**2026-08-31 (run 8 do `provision-region.yml`):** `regions/us-east-1/` esteve **de pé de verdade**
por algumas horas — 123 recursos aplicados (hub + célula: EKS, TGW, Client VPN, os 6 helm
releases), provisionados pelo próprio workflow de CI, não por uma sessão manual. Validou o
workflow de ponta a ponta (fecha a #41).

**2026-08-31 (mesma sessão, depois): região inteira derrubada** — `terraform destroy` sem
`-target` na raiz, 120 recursos destruídos, `terraform state list` confirma 0. Custo parou. Duas
lacunas descobertas nessa destroy manual (nenhuma delas presente no `provision-region.yml`, que já
resolve as duas via `--public-cidr`/CI role bootstradora do cluster):
endpoint público fechado bloqueando o *refresh* do `destroy` sem VPN (mesma classe de bug do run 7,
mas local) e RBAC do EKS (`Unauthorized`) porque só a role `github-actions-provision` — quem
bootstrapou o cluster — tinha `AccessEntry`; concedido um `AccessEntry` temporário de
cluster-admin à `OrganizationAccountAccessRole` local só para a destroy conseguir apagar os
objetos Kubernetes, destruído junto com o cluster. Issue **#52** criada para revalidar
`provision-region.yml` do zero (região já vazia) — board #6, label `private-access-ingress`.

Túnel do Client VPN conecta com o `.ovpn` exportado do endpoint corrente
(`aws-vpn-client get-connection-status --profile-name hub-<região>` — o profile leva a região no
nome porque cada região tem o próprio endpoint). Com o hub derrubado, o endpoint não existe mais —
reexportar depois de reaplicar.

## Em progresso agora

**Backlog completo e priorização: GitHub Project.**

```bash
gh project item-list 6 --owner smsilva --format json    # board inteiro
gh issue list -R smsilva/wasp-idp --label private-access-ingress --state open
```

Board: https://github.com/users/smsilva/projects/6

**Convenção de branch: uma por FASE**, `feat/private-access-phase-<n>` — não por passo. A issue
**#41** (workflow GitHub Actions para provisionar hub e célula) está **fechada**: as três fatias
(design, workflow, validação real) implementadas, mergeadas em `main` e validadas por
`workflow_dispatch` real (run 8, verde de ponta a ponta) em 2026-08-31 — narrativa em
[`docs/archived/index.md`](docs/archived/index.md), tema "GitHub Actions CI". Issue #47 (teto de
1h nas sessões de CI) fechada junto, pela causa raiz e não por aceitação do limite.

#37 fechada e movida para `Done` no board em 2026-08-31 (critério satisfeito pelo clone limpo da
fase 4); #36 fechada em 2026-08-30.

**Plano de execução da fase corrente:**
`docs/superpowers/plans/2026-08-29-regional-root-hub-and-cell-modules/` — um arquivo por fase
(`README.md` + `01`–`05`). Fases 1-3 fechadas — `module.cell` compõe com `module.hub` na raiz
regional, apply e destroy reais provados. Fase 4 (`04-cleanup-and-docs.md`) **fechada**: raízes
antigas apagadas (Task 1), `regions/us-west-2/` criada e o invariante provado (Task 2), scripts
renumerados (Task 3), `README.md`/`HANDOFF.md` reescritos, regressão offline completa (14 módulos,
`Success!` em todos) (Task 4). #21 fechada (absorvida por #36/ADR 0014); #36 já fechada em sessão
anterior. **Clone limpo rodado e achou dois bugs reais, corrigidos nesta sessão:**
`state-backend/terraform.tfvars` faltava nos Pré-requisitos do README (corrigido — documentado);
`up-01-dns` tinha um `generate-tfvars` residual (escrevia `dns/terraform.tfvars` próprio e checava
colisão de NS no Azure ANTES do `init`) que travava um clone/máquina nova mesmo com a delegação já
aplicada e tracked no state remoto — removido, `dns/` passou a ler só de `values.auto.tfvars` como
qualquer outra raiz desde a ADR 0014. Os scripts `up-01-dns`/`up-02-region` agora criam os symlinks
`values.auto.tfvars`/`saml-metadata.xml` sozinhos (`ensure_symlink` em `scripts/lib`) — antes o
README só documentava criá-los à mão na seção "Nova região", nada cobria clone/máquina nova de uma
região já existente. Critério de aceite da #37 ("árvore final aplica do zero seguindo só o
README") **satisfeito** — clone limpo chegou ao `plan` verde em `dns/` e aplicou/destruiu
`module.hub` de `us-east-1` de ponta a ponta sem consultar mais nada.

**Cuidado ao repetir o teste de clone limpo:** `up-02-region --region <r> --yes` **sem**
`--with-cell` já é um `apply` real (`-target=module.hub -auto-approve`), não um `plan` — um erro
desta sessão foi rodar esse comando pensando estar só testando o script, e ele recriou o hub
`us-east-1` de verdade (42 recursos, destruído de volta na sequência). Para testar só o `plan` do
comportamento de um script, usar `terraform plan` direto na raiz, nunca o script `up-*` com
`--yes`.

**#40** (acesso administrativo único a qualquer hub regional — hoje é preciso trocar de túnel Client
VPN por região) segue no backlog, sem trabalho iniciado. A #41 **não** ficou bloqueada por ela: a
spec de 2026-08-31 resolveu o acesso do runner pelo break-glass do endpoint público restrito a CIDR,
sem depender do desenho da #40. Ambas com label `private-access-ingress`, no board #6.

A frente `regional-root-hub-and-cell-modules` (branch `feat/regional-root-hub-cell`) está pronta
para revisão/integração em `main`.

A frente anterior, `docs/superpowers/plans/2026-08-26-private-access-and-ingress/`, está concluída
— ver `docs/archived/index.md`.

## Referências (ler sob demanda, não de uma vez)

| Precisa de... | Vá para |
|---|---|
| Por que uma decisão de arquitetura foi tomada | [`docs/adr/`](docs/adr/README.md) |
| Achado/limitação ainda válida, ainda não resolvida | [`aws/docs/known-broken.md`](aws/docs/known-broken.md) |
| Pergunta em aberto, sem decisão | [`aws/docs/open-questions.md`](aws/docs/open-questions.md) |
| Lição já corrigida, mas que vale para camada futura | [`aws/docs/lessons-learned/`](aws/docs/lessons-learned/) |
| Narrativa de entrega concluída | [`docs/archived/index.md`](docs/archived/index.md) |
| O que falta fazer, priorizado | GitHub Project #6 (link acima) |
| Sequência de provisionamento e dicionário de recursos | `docs/superpowers/specs/2026-08-27-provisioning-sequence.md` |

## How to Resume

**Primeiro comando — o SSO cai sozinho e leva os três profiles juntos** (`network` e `cicd`
assumem role a partir de `personal`):

```bash
for p in personal network cicd; do
  echo "=== ${p} ==="
  aws sts get-caller-identity --profile "${p}" --output json
done
```

`--query` devolve lixo nesta máquina (wrapper `rtk`, ver `CLAUDE.local.md`) — usar `--output json`
e ler o `Account`/`Arn` inteiro. Erro de profile inexistente ou ARN vazio ⟹
`! aws sso login --profile personal` (abre navegador; o agente não roda). A sessão do `az` expira
**independentemente** — conferir com `az account show`.

**Nada está de pé agora** (`us-east-1` destruída nesta sessão — 0 recursos, conferir com o comando
de "Estado atual" acima antes de presumir). Subir de novo:

```bash
cd aws/terraform/scripts && ./up-02-region --region us-east-1 --yes
```

**Derrubar (rotina, todo dia, quando a célula estiver de pé):**

```bash
cd aws/terraform/scripts && ./down-cell --region us-east-1 --yes
```

`down-cell` destrói só `module.cell` (`-target`), mantendo o hub de pé. Derrubar a região inteira
(hub incluso) é `terraform destroy` sem `-target` na raiz `regions/<região>/` — não é rotina, sem
script próprio de propósito. Se o destroy morrer com `dial tcp <ip-privado>:443: i/o timeout`, a
aresta de `depends_on` está errada, não é falha de credencial — recuperação: `terraform state rm`
dos objetos Kubernetes presos + reaplicar o `destroy`.

**Continuar com as camadas de pé exige o túnel conectado** (a API do cluster só existe por ele):

```bash
aws-vpn-client get-connection-status --profile-name hub   # tem de dizer "Connected"
! aws-vpn-client connect --profile-name hub               # abre navegador; precisa ser o usuário
```

**Nada garante que sobrevive entre sessões/máquinas** — `aws-vpn-client --version` (6.0.1 esperado;
`latest` entrega 5.4.1 sem CLI) e a existência de `saml-metadata.xml` precisam ser conferidos
sempre, nunca presumidos. `~/trash/hub.ovpn` de sessões anteriores está sempre inválido (DNS name
muda a cada recriação da 03) — reexportar sempre.

**Subir o ambiente** — a sequência completa (preencher `variables/values.tfvars` → `up-all` →
exportar/importar `.ovpn` → conectar → `up-all --with-cell` → provar; sem passo de geração de
tfvars), com custo e dependência por camada, vive em `aws/terraform/README.md`. **Ler de lá, não
daqui.**

**Verificar a célula ponta a ponta.** Desde 2026-08-29 (branch `feat/terraform-cluster-addons`)
**nenhum `helm` manual é necessário** — `up-02-region --with-cell` entrega a célula inteira, e o checkout de
`wasp-gitops` deixou de estar no caminho:

| Chart | Onde vive |
|---|---|
| `aws-load-balancer-controller` | `src/helm/modules/aws-load-balancer-controller` |
| `base`, `istiod`, `gateway` (ClusterIP) + o `Gateway` CR | `src/helm/modules/ingress-istio`, Istio 1.30.4 upstream |
| `TargetGroupBinding` | `src/helm/modules/target-group-binding`, chart local |
| `httpbin` + `VirtualService` | `src/helm/modules/httpbin`, chart local, `go-httpbin` 2.21.0 |

**Ainda não exercitado na AWS** — os quatro módulos passam offline e o apply real é o aceite que
falta. Ordem em que quebra, e o que cada ponto significa:

```bash
terraform -chdir=aws/terraform/regions/us-east-1 output cell_services_url   # https://services.<célula>.<subzona>/
```

`dig` no host → certificado no listener → os dois target groups (spoke e hub) `healthy` → `curl`
público sem `-k`.

**O host é `services.`, não `app.`** — qualquer outro nome sob o wildcard cai no `fixed-response`
404 do listener do ALB, e o sintoma é indistinguível de rota faltando no cluster.

**Regressão offline** (~3-4 min, rodar em background):

```bash
cd aws/terraform
for m in src/network src/state-backend src/pod-identity src/cluster src/nodegroup src/ingress \
         src/hub src/cell \
         src/helm/modules/aws-load-balancer-controller \
         src/helm/modules/external-secrets src/helm/modules/argo-cd src/helm/modules/crossplane \
         regions/us-east-1 regions/us-west-2 dns; do
  (cd "${m}" && terraform init -backend=false >/dev/null && terraform test)
done
```

**Preflight antes de subir qualquer coisa:**

```bash
aws-vpn-client --version                              # 6.0.1 — ausente ⟹ alguém instalou por `latest`
systemctl is-active aws-client-vpn-daemon.service
terraform -chdir=aws/terraform/regions/us-east-1 init -backend-config="bucket=tfstate-o-e4r8ndteju"
```

`terraform apply`/`destroy` rodam por `! <comando>` — o classifier de auto-mode bloqueia para o
agente; `apply` sem tty falha de propósito, usar `--yes` quando não houver terminal. Plano salvo
não sobrevive à expiração de credencial — replanejar, não reaproveitar.

**Reproduzir o Control Plane k3d, se necessário:**

```bash
k3d cluster list                       # confirmar antes de assumir
aws/eks/scripts/install-crossplane     # k3d "control-plane" (1 server) + Crossplane
aws/eks/scripts/install-providers --timeout 900s
aws/eks/scripts/install-functions      # OBRIGATÓRIO: toda Composition é mode: Pipeline

set -a; source <(AWS_PROFILE=network aws secretsmanager get-secret-value \
  --secret-id poc-idp/crossplane-poc-credentials --region us-east-1 \
  --query SecretString --output text \
  | jq -r '"AWS_ACCESS_KEY_ID=" + .aws_access_key_id, "AWS_SECRET_ACCESS_KEY=" + .aws_secret_access_key'); set +a
aws/eks/scripts/configure-aws-creds
aws/eks/scripts/configure-account-access --name wasp-nonprod --account-id <spoke-account-id>
```

Pré-requisitos: VPN corporativa **desconectada** (senão o pull de `xpkg.upbound.io` falha com
`x509` e depois `connection reset`) e SSO admin ativo.

**Lição operacional:** nunca deixar um `apply`/`destroy` de vários minutos dependurado numa chamada
síncrona de ferramenta — usar `nohup ... > log 2>&1 < /dev/null & disown` (os scripts `up-NN` já
fazem isso). Um processo morto no meio não impede recuperação, mas custa tempo evitável.

## Open Questions

- **#40** segue investigação em aberto, sem trabalho iniciado — ver o corpo da issue para os
  ângulos já mapeados.

## Next Steps

1. #40 segue no backlog do board #6, sem trabalho iniciado.

## Completed Work

Narrativa detalhada de cada entrega concluída vive em `docs/archived/<tema>/<passo>.md`, indexada
em [`docs/archived/index.md`](docs/archived/index.md).

> Before trusting anything time-sensitive above, run `git status`, `git diff`, and `git log` against the base branch.
