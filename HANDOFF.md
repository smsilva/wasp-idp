# HANDOFF

## Why

Exercitar a PoC AWS EKS-via-Crossplane (arquitetura de referência hub-and-spoke) na conta AWS
pessoal do Silvio, genérica, antes de qualquer ambiente corporativo. `aws/` foi genericizada a
partir de um exemplo interno (placeholders `<...>` para valores por-conta/segredos; valores
genéricos concretos como `platform.example.com`/`poc-eks` onde o token é YAML/Crossplane
executável). Valores reais ficam em `CLAUDE.local.md` (gitignored); consolidação em
`variables/values.yaml` gitignored planejada, ver [ADR 0013](docs/adr/0013-consolidate-local-values-yaml.md).

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
for m in control-plane connectivity/us-east-1 dns network-foundation/us-east-1; do
  printf '%-32s %s\n' "${m}" "$( (cd "${m}" && terraform state list 2>/dev/null | grep -vc '^data\.') )"
done
k3d cluster list
```

Custo por camada, ordem de subida/derrubada e as armadilhas dos scripts: `aws/terraform/README.md`
(fonte da verdade — não duplicar números aqui). Regra fixa: **a camada `connectivity/` (03) é um
nível T1 que fica de pé de propósito durante o dia** — não presumir resíduo e destruir sem checar
([ADR 0009](docs/adr/0009-hub-alb-lives-in-connectivity-layer.md)).

## Em progresso agora

**Backlog completo e priorização: GitHub Project.**

```bash
gh project item-list 6 --owner smsilva --format json    # board inteiro
gh issue list -R smsilva/wasp-idp --label private-access-ingress --state open
```

Board: https://github.com/users/smsilva/projects/6

**Convenção de branch: uma por FASE**, `feat/private-access-phase-<n>` — não por passo. Branch
corrente: `feat/private-access-phase-3`.

**Plano de execução da fase corrente:**
`docs/superpowers/plans/2026-08-26-private-access-and-ingress/` — um arquivo por fase (`README.md`
+ `01`–`04`). Ler o `README.md` mais a fase corrente, não o plano inteiro.

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

**Subir o ambiente** — a sequência completa (7 passos: `up-all` → `up-03` → exportar/importar
`.ovpn` → conectar → `generate-tfvars --force` → `up-04` → provar), com custo e dependência por
camada, vive em `aws/terraform/README.md`. **Ler de lá, não daqui.**

**Verificar a célula ponta a ponta** (Terraform + lado cluster). A migração dos charts para o
Terraform está em curso na branch `feat/terraform-cluster-addons`; o que já migrou sai do `up-04`
e não deve ser instalado à mão:

| Chart | Onde vive hoje |
|---|---|
| `aws-load-balancer-controller` | **Terraform** (`src/helm/modules/aws-load-balancer-controller`) |
| `istio-base`, `istio-discovery`, `istio-gateway` (ClusterIP, NÃO LoadBalancer) | helm do checkout local, a migrar |
| `httpbin`, `aws-target-group-binding` | helm do checkout local, a migrar |

```bash
cd ~/git/wasp-gitops/infrastructure/charts   # o que ainda não migrou, na ordem acima
```

`targetGroupARN`/`vpcId` vêm do ConfigMap `platform-bootstrap` (`crossplane-system`) e do
`terraform state` da 04 — nunca de um values file colado (o ARN muda a cada recriação). Verificar
na ordem em que quebra: `terraform output cell_ingress_fqdn` → `dig` → certificado no listener →
os dois target groups (spoke e hub) `healthy` → `curl` público sem `-k`. **O host é `services.`,
não `app.`**

**Regressão offline** (156 testes, 15 diretórios, ~3-4 min, rodar em background):

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
