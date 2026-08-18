# platform-bootstrap

Chart Helm que orquestra os XRs de plataforma (`../../resources/`) em **sequência**, usando
**Helm hooks** como barreira de readiness — um `provision-eks` nativo do Helm, sem script
bash externo.

> **Exploração (2026-08-18).** Fatia atual: **só `Network`**. O padrão de hook está provado
> ponta a ponta em dry-run; somar `Cluster` (e a ordem entre XRs) é o próximo passo.

## Padrão: XR = recurso normal · waiter = hook

A decisão de ciclo de vida que molda o chart:

| Recurso | Tipo no Helm | Porquê |
|---|---|---|
| **XR `Network`** (`100-network.yaml`) | **recurso normal** do release | `helm upgrade` reconcilia mudanças (ex.: CIDR); `helm uninstall` deleta o XR → Crossplane faz **teardown da VPC/NAT** na AWS. Se fosse hook, viraria órfão no uninstall (recurso AWS cobrando). |
| **RBAC do waiter** (`110-waiter-rbac.yaml`) | **hook** (`post-install,post-upgrade`, weight `110`) | SA + ClusterRole dedicado (menor privilégio: `get/list/watch` só no tipo `networks`) + binding, todos efêmeros. Não usa `crossplane-view` (que daria read em todos os tipos Crossplane). |
| **Job waiter** (`120-wait-network.yaml`) | **hook** (weight `120`) | Roda `kubectl wait ... --for=condition=Ready`. O Helm **bloqueia** no Job → é a barreira. `hook-delete-policy: before-hook-creation,hook-succeeded` não deixa lixo. |

### Esquema de numeração

Grupos de 100 por XR, passos de 10 dentro do grupo — o `hook-weight` acompanha o número do
arquivo, então inserir/ajustar uma fase é só escolher um número no vão. Mapeia as 25 fases
do chart faseado antigo (`../../chart/`) para poucos XRs de alto nível:

| Faixa | Grupo | Fases antigas que colapsa | Estado |
|---|---|---|---|
| **100–120** | **Network** (XR + RBAC + waiter) | `10-vpc`, `20-subnets`, `30-network-access` | ✅ aplicado (VPC real na hub) |
| **200–230** | **Cluster** (EnvironmentConfig + XR + RBAC + waiter) | `40-iam`, `50-eks`, `60-nodegroup`, `65/68`, `70/72/74` | ✅ escrito, `enabled: false` (não aplicado) |
| **300–310** | **ArgoCDInstance** (XR + waiter) → resto via GitOps | `80`–`98`, `100`–`106` (ESO, external-dns, ALB, istio, cert-manager) | ⬜ futuro |

Dentro de um grupo: `N00` = XR/config (recurso normal), `N10`/`N20` = RBAC do waiter (hook),
`N20`/`N30` = Job waiter (hook). Os hooks de um grupo têm weight = o próprio número do arquivo.
O grupo **200 é opcional** — só renderiza com `cluster.enabled=true` (custo alto do EKS).

**Por que o waiter precisa ser hook (e não um recurso comum):** `helm install` não espera
readiness de um recurso normal — só espera um **Job hook** chegar a `Complete`. Um `apply` de
XR retorna na hora (o XR existe, mas ainda não reconciliou). O Job `kubectl wait` só completa
quando o XR fica `Ready`, e o Helm bloqueia nele — é isso que dá a barreira observável.

## Ordem entre XRs — decisão tomada

Os XRs (`Network`, `Cluster`) são **recursos normais** (ciclo de vida limpo); a ordem real
`Network → Cluster` é garantida pelo **Crossplane**, não pelo Helm: o `Cluster` casa as
subnets do `Network` por label `environment.example.com/env=<id>` e só reconcilia quando
elas existem. Os waiters (hooks, pesos crescentes 120 → 230) dão a **barreira observável**
no `helm install` (a fase 200 espera depois da 100), mas não são o que cria a dependência.
`id` compartilhado entre Network e Cluster nos values é o que amarra os dois.

Ver `../../../docs/network/07-mapa-crossplane.md` e o `HANDOFF.md`.

## Uso

```bash
# render / validação offline (sem tocar o cluster nem a AWS)
helm template pb aws/eks/charts/platform-bootstrap

# validação server-side (contra o cluster; NÃO cria nada) — helm < 3.13:
helm template pb aws/eks/charts/platform-bootstrap --namespace crossplane-system \
  | kubectl apply --dry-run=server -f -

# install real — grupo 100 só: CRIA a VPC + subnets + NAT na conta hub (CUSTO).
# O hook bloqueia até a Network ficar Ready.
helm install pb aws/eks/charts/platform-bootstrap --namespace crossplane-system

# grupo 100 + 200 (EKS): CUSTO ALTO (~US$0,22/h control plane + nodes) e ~28-30 min.
# crossplaneArn real via --set (não versionar o account-id no repo).
helm upgrade pb aws/eks/charts/platform-bootstrap --namespace crossplane-system \
  --set cluster.enabled=true \
  --set cluster.crossplaneArn=arn:aws:iam::<account-id>:user/crossplane-poc

# teardown — deleta os XRs → Crossplane destrói os recursos AWS
helm uninstall pb --namespace crossplane-system
```

Pré-requisitos: hub Crossplane de pé (providers + functions + ProviderConfig) e os XRDs +
Compositions da `Network` (e, p/ o grupo 200, do `Cluster`) aplicados
(`../../resources/{network,cluster}/`). Ver `aws/CLAUDE.md`.

## Valores (`values.yaml`)

| Campo | Default | Nota |
|---|---|---|
| `id` | `net01` | ≤5 alfanum; **compartilhado** Network+Cluster (casa subnets por label) |
| `prefix` | `poc-eks` | prefixo de naming |
| `region` | `us-east-1` | |
| `network.vpcCidrSecondOctet` | `1` | N em `10.<N>.0.0/16` (supernet `10.0.0.0/12`) |
| `cluster.enabled` | `false` | liga o grupo 200 (EKS) — custo alto; deixe `false` até querer o cluster |
| `cluster.crossplaneArn` | `arn:...:<account-id>:user/crossplane-poc` | placeholder; passe o real via `--set` (não versionar) |
| `cluster.nodeGroup.*` | `t3.medium` 3/3/4 | instanceType / desired / min / maxSize |
| `waiter.image` | `registry.k8s.io/kubectl:v1.35.7` | imagem com `kubectl` (oficial k8s; bitnami deixou de resolver no Docker Hub) |
| `waiter.networkTimeout` | `600s` | timeout do wait no XR Network |
| `waiter.clusterTimeout` | `1800s` | timeout do wait no XR Cluster (EKS ~30min) |
| `waiter.timeout` | `600s` | timeout do `kubectl wait` (NAT domina) |
