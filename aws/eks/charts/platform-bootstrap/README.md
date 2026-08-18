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
| **100–120** | **Network** (XR + RBAC + waiter) | `10-vpc`, `20-subnets`, `30-network-access` | ✅ esta fatia |
| **200–220** | **Cluster** (EnvironmentConfig + XR + waiter) | `40-iam`, `50-eks`, `60-nodegroup`, `65/68`, `70/72/74` | ⬜ futuro |
| **300–310** | **ArgoCDInstance** (XR + waiter) → resto via GitOps | `80`–`98`, `100`–`106` (ESO, external-dns, ALB, istio, cert-manager) | ⬜ futuro |

Dentro de um grupo: `N00` = XR (recurso normal), `N10` = RBAC do waiter (hook), `N20` =
Job waiter (hook). Os hooks de um grupo têm weight = o próprio número do arquivo.

**Por que o waiter precisa ser hook (e não um recurso comum):** `helm install` não espera
readiness de um recurso normal — só espera um **Job hook** chegar a `Complete`. Um `apply` de
XR retorna na hora (o XR existe, mas ainda não reconciliou). O Job `kubectl wait` só completa
quando o XR fica `Ready`, e o Helm bloqueia nele — é isso que dá a barreira observável.

## Ordem entre XRs (quando houver mais de um) — decisão adiada

Com só `Network`, não há conflito. Ao somar `Cluster`, decide-se entre:

- **XR+waiter ambos como hooks** com pesos crescentes → garante *ordem de apply* (Network
  Ready antes de Cluster ser criado), mas exige `resource-policy`/`delete-policy` para o
  teardown não deixar XR órfão; ou
- **XRs normais + confiar no Crossplane** para a ordem (o `Cluster` referencia o `Network` e
  só reconcilia quando ele está pronto) — waiters dão só barreira observável, não ordem de
  apply.

Ver `../../../docs/network/07-mapa-crossplane.md` e o `HANDOFF.md`.

## Uso

```bash
# render / validação offline (sem tocar o cluster nem a AWS)
helm template pb aws/eks/charts/platform-bootstrap

# validação server-side (contra o cluster; NÃO cria nada) — helm < 3.13:
helm template pb aws/eks/charts/platform-bootstrap --namespace crossplane-system \
  | kubectl apply --dry-run=server -f -

# install real — CRIA a VPC + subnets + NAT na conta hub (CUSTO). O hook bloqueia
# até a Network ficar Ready.
helm install pb aws/eks/charts/platform-bootstrap --namespace crossplane-system

# teardown — deleta o XR → Crossplane destrói os recursos AWS
helm uninstall pb --namespace crossplane-system
```

Pré-requisitos: hub Crossplane de pé (providers + functions + ProviderConfig) e o XRD +
Composition da `Network` aplicados (`../../resources/network/`). Ver `aws/CLAUDE.md`.

## Valores (`values.yaml`)

| Campo | Default | Nota |
|---|---|---|
| `network.id` | `net01` | ≤5 alfanum; deriva external-names e label de cruzamento |
| `network.prefix` | `poc-eks` | prefixo de naming |
| `network.region` | `us-east-1` | |
| `network.vpcCidrSecondOctet` | `1` | N em `10.<N>.0.0/16` (supernet `10.0.0.0/12`) |
| `waiter.image` | `bitnami/kubectl:1.31` | imagem com `kubectl` |
| `waiter.timeout` | `600s` | timeout do `kubectl wait` (NAT domina) |
