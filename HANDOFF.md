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
for m in control-plane connectivity/us-east-1 dns network-foundation/us-east-1 regions/us-east-1; do
  printf '%-32s %s\n' "${m}" "$( (cd "${m}" && terraform state list 2>/dev/null | grep -vc '^data\.') )"
done
k3d cluster list
```

**2026-08-30:** `connectivity/us-east-1` e `network-foundation/us-east-1` foram destruídas de
propósito (ADR 0014, fase 2 da frente `regional-root-hub-and-cell-modules`) e devem dar `0` — não é
resíduo, é a camada 01+03 tendo virado `src/hub`, consumido por `regions/us-east-1/` (`module.hub`),
já aplicado dali. Túnel do Client VPN conecta com o `.ovpn` exportado do endpoint corrente
(`aws-vpn-client get-connection-status --profile-name hub-us-east-1`, o profile leva a região no
nome porque a `us-west-2` terá o próprio). `control-plane/` continua de pé como raiz antiga (código
morto, sem apply próprio) — vira `module.cell` na fase 3, que já fechou: `regions/us-east-1/` compôs
`module.hub` + `module.cell`, um apply real da célula (78 recursos) foi feito e destruído de volta
(`terraform destroy -target=module.cell`), com o hub (43 recursos) de pé.

A rodada de fix da revisão final da fase 3 (7 Important + minors) fechou nesta sessão, direto no
controller — o dispatch original (subagent dedicado) morreu por rate limit sem nenhum progresso.
Um `terraform plan` real (`-target=module.hub`, sem apply) confirmou: a regionalização do FQDN do
certificado default do ALB (`*.us-east-1.nonprod.<domínio>`) propõe trocar o certificado, a
validação DNS-01 e o listener (`3 to add, 1 to change, 3 to destroy`) — **plano salvo mas não
aplicado**, decisão do usuário sobre quando trocar o cert live; o fix de conta da AZ não propôs
nenhuma mudança (o risco era latente, nunca se manifestou). As três raízes velhas
(`connectivity/`, `network-foundation/`, `control-plane/`) só somem do disco na fase 4;
`up-01`/`up-03`/`up-04` recusam rodar (guard `fail`, aponta para `up-02-region`).

Custo por camada, ordem de subida/derrubada e as armadilhas dos scripts: `aws/terraform/README.md`
(fonte da verdade — não duplicar números aqui, e ainda não reflete a raiz regional nova). Regra
fixa: **a camada `connectivity/` (03) é um nível T1 que fica de pé de propósito durante o dia** —
regra que migrou para `regions/<r>/` → `module.hub` (T1) com a fase 2
([ADR 0009](docs/adr/0009-hub-alb-lives-in-connectivity-layer.md)).

## Em progresso agora

**Backlog completo e priorização: GitHub Project.**

```bash
gh project item-list 6 --owner smsilva --format json    # board inteiro
gh issue list -R smsilva/wasp-idp --label private-access-ingress --state open
```

Board: https://github.com/users/smsilva/projects/6

**Convenção de branch: uma por FASE**, `feat/private-access-phase-<n>` — não por passo. Branch
corrente: `feat/regional-root-hub-cell`, executando a frente `regional-root-hub-and-cell-modules`
(issue #37; #36 fechada em 2026-08-30 — a fase 1 sozinha já satisfazia o critério dela).

**Plano de execução da fase corrente:**
`docs/superpowers/plans/2026-08-29-regional-root-hub-and-cell-modules/` — um arquivo por fase
(`README.md` + `01`–`05`). Fases 1-3 fechadas — `module.cell` compõe com `module.hub` na raiz
regional, apply e destroy reais provados, 8 dos 9 itens do aceite da fase 3 marcados (o pendente
é a sonda `us-west-2`, dispensada por custo — a prova offline equivalente já existe em
`src/hub/tests/regional-naming.tftest.hcl`). Rodada de fix da revisão final de branch
(`ef000ad..6de2552`, 7 Important + minors) também fechada. Ledger da fase 3
`.superpowers/sdd/03-cell-module/progress.md` ainda não foi limpo (workspace SDD, gitignored) —
apagar quando não precisar mais dele.

**Próximo passo: fase 4** (`04-cleanup-and-docs.md`, ainda não iniciada) — apagar
`network-foundation/`, `connectivity/`, `control-plane/` e os scripts `up-01`/`up-03`/`up-04`
(states já confirmados vazios nas três), mover `connectivity/us-east-1/saml-metadata.xml.example`
→ `variables/`, criar `regions/us-west-2/`, reescrever `aws/terraform/README.md` para a sequência
nova de verdade (hoje só tem um banner apontando pra lá, o corpo ainda descreve a sequência
antiga), renumerar `up-02-dns` → `up-01-dns`. Só depois disso o critério de aceite da #37 ("árvore
final aplica do zero seguindo só o README") fica satisfeito.

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

**Primeiro comando — ler a issue escolhida, com o corpo já enriquecido:**

```bash
gh issue view 7 -R smsilva/wasp-idp
```

Antes de escrever qualquer Terraform para ela, checar em `CLAUDE.local.md` se a GitHub App já tem
`.pem`/App ID/Installation ID promovidos ao Secrets Manager da conta `cicd` — se não, isso é o
passo zero.

**Segundo comando — o SSO cai sozinho e leva os três profiles juntos** (`network` e `cicd`
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

**Derrubar (ordem obrigatória):**

```bash
cd aws/terraform/control-plane && ./scripts/destroy        # PRIMEIRO
cd ../connectivity/us-east-1 && ./scripts/destroy           # só depois
```

O TGW attachment da spoke vive no state da control-plane; a AWS recusa deletar TGW com attachment
vivo. Se o `destroy` morrer com `dial tcp <ip-privado>:443: i/o timeout`, a aresta está errada, não
é falha de credencial — recuperação: `terraform state rm` dos objetos Kubernetes presos + reaplicar
o `destroy`.

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
`up-03` → exportar/importar `.ovpn` → conectar → `up-04` → provar; sem passo de geração de tfvars),
com custo e dependência por camada, vive em `aws/terraform/README.md`. **Ler de lá, não daqui.**

**Verificar a célula ponta a ponta.** Desde 2026-08-29 (branch `feat/terraform-cluster-addons`)
**nenhum `helm` manual é necessário** — o `up-04` entrega a célula inteira, e o checkout de
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
terraform -chdir=aws/terraform/control-plane output cell_services_url   # https://services.<célula>.<subzona>/
```

`dig` no host → certificado no listener → os dois target groups (spoke e hub) `healthy` → `curl`
público sem `-k`.

**O host é `services.`, não `app.`** — qualquer outro nome sob o wildcard cai no `fixed-response`
404 do listener do ALB, e o sintoma é indistinguível de rota faltando no cluster.

**Regressão offline** (~3-4 min, rodar em background):

```bash
cd aws/terraform
for m in src/network src/state-backend src/pod-identity src/cluster src/nodegroup src/ingress \
         src/helm/modules/aws-load-balancer-controller \
         src/helm/modules/external-secrets src/helm/modules/argo-cd src/helm/modules/crossplane \
         network-foundation/us-east-1 network-foundation/us-west-2 control-plane dns \
         connectivity/us-east-1; do
  (cd "${m}" && terraform init -backend=false >/dev/null && terraform test)
done
```

**Preflight antes de subir qualquer coisa:**

```bash
aws-vpn-client --version                              # 6.0.1 — ausente ⟹ alguém instalou por `latest`
systemctl is-active aws-client-vpn-daemon.service
terraform -chdir=aws/terraform/control-plane init -backend-config="bucket=tfstate-o-e4r8ndteju"
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

## Completed Work

Narrativa detalhada de cada entrega concluída vive em `docs/archived/<tema>/<passo>.md`, indexada
em [`docs/archived/index.md`](docs/archived/index.md).

> Before trusting anything time-sensitive above, run `git status`, `git diff`, and `git log` against the base branch.
