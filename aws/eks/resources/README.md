# aws/eks/resources — abstração `Environment` (modelo novo, hub/spoke)

> `resources/` é nome **provisório** — trocar por algo melhor depois.

XRDs + Compositions que empacotam o provisionamento de um cluster EKS **por Environment**,
substituindo as 25 fases faseadas de `aws/eks/chart/` + `scripts/provision-eks`. Modelo
decidido no brainstorm `docs/superpowers/specs/2026-08-13-environment-abstracao-brainstorm.md`
. **Convive** com o chart faseado — não o remove.

## Topologia (resumo)

- **HUB** (k3d `k3d-poc-idp` hoje → EKS de management depois): roda o Crossplane que provisiona
  a pegada AWS durável (EKS, VPC, IAM, Route53 subzona+NS) e faz bootstrap do ArgoCD no spoke.
- **SPOKE** (cada Environment): o cluster EKS provisionado; roda ArgoCD (delivery) e, depois,
  Crossplane-no-spoke (AWS do time). Ver o brainstorm para o desenho completo.

## Fatia atual (walk skeleton)

**Objetivo:** 1 CR `Environment` → cluster EKS novo + **ArgoCD Ready** no spoke. A entrega de
infra no spoke (migrar ESO/istio/cert-manager para o ArgoCD) fica para a fatia seguinte.

Esta fatia **NÃO** compõe os Releases de plataforma → evita a race PodIdentity→Release (o ponto
difícil do ADR). O único Release é o ArgoCD (não depende de Pod Identity).

## Componentes

| Arquivo | Papel |
|---|---|
| `network/xrd.yaml` | XRD `Network` — pegada de rede (id, prefix, region; status vpcId+subnetIds) |
| `network/composition.yaml` | 16 MRs: VPC, 4 subnets, IGW, EIP, NAT, 2 RT, 2 routes, 4 RTAs |
| `cluster/xrd.yaml` | XRD `Cluster` — EKS+IAM+ponte (id, prefix, region, nodeGroup; status clusterName/Arn/oidc/kubeconfigSecret) |
| `cluster/composition.yaml` | 14 MRs: 2 Role + 4 RPA, EKS, NodeGroup, ClusterAuth, AccessEntry+APA, 2 PC remotos |
| `environment/xrd.yaml` | XRD `Environment` — contrato externo (id, prefix, region, domain, nodeGroup); status agrega vpcId+clusterName |
| `environment/environmentconfig.yaml` | `EnvironmentConfig` do hub (crossplaneArn) — aplicar 1x, antes do 1º claim; consumido pelo `Cluster` |
| `environment/composition.yaml` | **orquestrador fino**: compõe `Network` + `Cluster` (XR-compõe-XR), repassa id/prefix/region/nodeGroup, agrega status |
| `argocd/xrd.yaml` | XRD `ArgoCDInstance` — satélite par (model-02) que referencia o Environment |
| `argocd/composition.yaml` | cria PC helm próprio do connection secret + Release ArgoCD. Etapa 2 (Usage/model-04) pendente |
| `examples/current/01-network.yaml` | claim `Network` isolado — teste da camada de rede |
| `examples/current/02-cluster.yaml` | claim `Cluster` isolado — consome um Network de mesmo id por label |
| `examples/current/03-environment.yaml` | claim `Environment` (orquestrador) — `id: env01` |
| `examples/current/04-argocd.yaml` | claim `ArgoCDInstance` satélite do env01 |
| `examples/topology/` | proposta ESCOLHIDA (17/08/2026): filhos públicos + spec de topologia (`subnetIds` diretos, `NodeGroup` próprio, `nodeGroups[]` no Environment) — ainda não implementada |
| `examples/proposals/not-chosen-profile-intent/` | proposta DESCARTADA: `Environment.spec` de intenção (`profile`) — arquivado, não implementar |

### Decomposição `Environment` → `Network` + `Cluster`

A Composition monolítica (~768 linhas, ~30 MRs) foi decomposta em 2 abstrações de
responsabilidade única + o `Environment` como orquestrador fino. Refatoração de
**comportamento idêntico** (o claim `Environment` e o resultado provisionado não mudam).
Cruzamento `Network`→`Cluster` por **selector-by-label** (`environment.example.com/env=<id>`,
sem `matchControllerRef`, pois os MRs vivem em XRs distintos). Ver
`docs/superpowers/specs/2026-08-15-decompor-environment-network-cluster-plano.md` e o brainstorm
de 2026-08-14. Enquadramento: Pilar 5 "Composable by design" (PE 2.0), princípios *Modular by
design* + *API-first contracts*.

## Decisões que moldam estes arquivos

- **model-02 (connection secret):** o `Environment` publica um connection secret
  (kubeconfig + id + domain + subzoneId + ARNs); o `ArgoCDInstance` se liga a ele. Idiomático
  Crossplane; reusa a mecânica das fases 72/74.
- **model-04 (Usage):** o `ArgoCDInstance` emite um `Usage`/finalizer que torna o teardown
  gracioso explícito (deletar o ArgoCD antes do Environment).
- **Naming determinístico (Item C):** cluster = `<prefix>-<id>` (default prefix `poc-eks`);
  subzona `<id>.<domain>`; external-names derivados → migração/DR por import/adopt.
- **Motor:** function-patch-and-transform (o que o repo já usa; sem function-kcl nesta fatia).

## Gotchas do modelo novo (a resolver)

- **`crossplaneArn` sem `--set` — DECIDIDO (b):** a AccessEntry/APA de Crossplane (fase 72) exige
  o ARN do IAM user do Crossplane. No chart faseado vinha por `--set crossplaneArn=...`; numa
  Composition NÃO há `--set`. Optamos por **(b) `EnvironmentConfig` do hub**
  (`environment/environmentconfig.yaml`, aplicado uma vez, fora de qualquer claim), injetado no
  pipeline via o step `function-environment-configs` e consumido pelos MRs
  `access-entry-crossplane`/`access-admin-crossplane` com `FromEnvironmentFieldPath`. Trade-off
  aceito conscientemente: uma peça de infra extra (o `EnvironmentConfig` em si) + uma function a
  mais no pipeline (`xpkg.crossplane.io/crossplane-contrib/function-environment-configs`, já
  adicionada em `.claude/skills/kubernetes/assets/crossplane/packages/values-functions.yaml`) —
  compensado por não repetir o ARN em cada claim `Environment` (útil se/quando existir mais de um
  hub ou id provisionado). **Pré-requisito de apply:** `kubectl apply -f
  environment/environmentconfig.yaml` no hub ANTES do primeiro claim.
- **Refs entre MRs:** `matchControllerRef: true` + `matchLabels` (label
  `environment.example.com/role: <papel>` em cada MR) — idiomático em Composition, dispensa
  os nomes `<full>-<sufixo>` frágeis do chart faseado. Naming determinístico via
  `CombineFromComposite(spec.prefix, spec.id)` em `metadata.annotations[crossplane.io/external-name]`.
- **Connection secret (model-02):** o MR `cluster-auth` publica `kubeconfig` (via
  `FromConnectionSecretKey` do ClusterAuth) + `id`/`domain`/`clusterName` (patchados em
  annotations do próprio MR e lidos de volta via `FromFieldPath`) no connection secret do XR —
  as 4 chaves declaradas em `environment/xrd.yaml` → `connectionSecretKeys`.
- **`70-access` (AccessEntry/APA do caller humano SSO) ficou FORA desta Composition** — é
  conveniência de operador (acesso `kubectl` direto ao spoke), não bloqueia Environment+ArgoCD
  Ready. Aplicar à mão via `aws/eks/chart` se precisar.
- **Verbosidade:** ~30 MRs em patch-and-transform é longo (trade-off que o ADR anotou; KCL
  seria mais enxuto, mas esta fatia usa patch-and-transform por decisão do time).

## Status

**Walk-skeleton COMPLETO e validado end-to-end contra AWS real.** Primeiro
Environment: `env01`.

- `environment/composition.yaml` **COMPLETA** — 7 etapas incrementais (VPC/subnets → rede →
  IAM → EKS Cluster → NodeGroup → ponte ClusterAuth+AccessEntry+APA → ProviderConfigs remotos),
  cada uma provisionada de verdade antes da próxima. XR `env01` Ready=True, ~30 MRs Ready.
- `environment/environmentconfig.yaml` — crossplaneArn (decisão b) injetado via
  `function-environment-configs`, validado em provisionamento real.
- `argocd/composition.yaml` **COMPLETA (etapa 1: PC helm próprio + Release argo-cd)** — model-02
  puro: cria o ProviderConfig helm a partir do `environmentConnectionSecretRef` e instala o
  ArgoCD no spoke. Validado: XR `ArgoCDInstance` Ready=True, 7 pods do ArgoCD Running no EKS
  remoto. **Falta:** etapa 2 (Usage/model-04, teardown gracioso).

**Cadeia validada:** 1 CR `Environment` → cluster EKS + ponte → 1 CR `ArgoCDInstance` → ArgoCD
no spoke. Bootstrap do hub: ver `CLAUDE.md` da raiz (seção "Hub k3d para teste AWS").
