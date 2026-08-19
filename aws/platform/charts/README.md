# platform/charts — hub / spoke / cluster

Três charts Helm que provisionam a topologia hub-and-spoke, **um release por célula**. Cada
chart aplica seu(s) XR(s) como recurso(s) normal(is) (helm upgrade reconcilia, helm uninstall
dispara o teardown AWS via Crossplane) + um Job **waiter** como hook que bloqueia o `helm
install` até o XR ficar `Ready` (barreira observável).

Substituem o antigo `platform-bootstrap` (nome confuso: "bootstrap" já era o setup das contas
AWS). Aqui é provisionamento contínuo da topologia.

## As 3 camadas

| Chart | O que é | XR(s) | Conta |
|-------|---------|-------|-------|
| `hub` | rede de conectividade regional (1 por região) | `Network` (`providerConfigName: hub`) | hub |
| `spoke` | rede spoke anexada ao hub; **pode** hospedar um cluster ou outros recursos | `Network` (`providerConfigName: sandbox`) | spoke |
| `cluster` | EKS que **aterrissa** num spoke | `EnvironmentConfig` + `Cluster` | herda do spoke |

**spoke ≠ cluster:** um spoke é uma célula de rede; um cluster é um workload que aterrissa
nela. Um spoke existe sem cluster (uninstall do cluster não derruba o spoke).

## Identidade (`--set name=`)

O `metadata.name` do XR é a identidade (Crossplane v2, sem `spec.id`). **O cluster e o spoke
que ele consome DEVEM ter o mesmo `name`** — é o label que casa as subnets. Gere com
`../../eks/scripts/random-id`.

```bash
ID=$(aws/eks/scripts/random-id)     # ex.: ha13c
```

## Pré-requisitos (bootstrap do hub, uma vez)

1. Crossplane no k3d + providers + functions (`../../eks/scripts/install-*`).
2. `configure-aws-creds` → Secret `aws-iam-credential` + ProviderConfig `hub`.
3. `configure-account-access --name sandbox --account-id <id>` → ProviderConfig `sandbox`
   (cross-account, assumeRoleChain).
4. XRDs + Compositions aplicados (`../../eks/resources/{network,cluster}/`).

## Ordem de instalação

```bash
# hub (rede de conectividade) — nome legível
helm install hub-us-east-1 aws/platform/charts/hub \
  --namespace crossplane-system --set name=hub-us-east-1

# spoke (rede na conta sandbox) — nome aleatório
ID=$(aws/eks/scripts/random-id)
helm install spoke-$ID aws/platform/charts/spoke \
  --namespace crossplane-system --set name=$ID

# cluster (EKS aterrissando no spoke) — MESMO name do spoke. CUSTO ALTO, ~28-30 min.
helm install cluster-$ID aws/platform/charts/cluster \
  --namespace crossplane-system --set name=$ID \
  --set providerConfigName=sandbox \
  --set crossplaneArn=arn:aws:iam::<sandboxAccountId>:role/crossplane-sandbox
```

Cluster longo (~30 min): rodar em background (o helm bloqueia no waiter). O Crossplane
continua reconciliando mesmo se o `helm install` for interrompido.

## ⚠️ Gotcha: `crossplaneArn` de um cluster no spoke

É a **role assumida na conta spoke** (`arn:aws:iam::<sandboxAccount>:role/crossplane-sandbox`),
**não** o user da hub. O `ClusterAuth` gera o kubeconfig autenticando como essa role (via
`providerConfigName: sandbox` → assumeRoleChain), então é ela que precisa do `AccessEntry`
admin. ARN errado → a ponte Crossplane→EKS (provider-helm/kubernetes) não alcança o cluster.

## Teardown

```bash
helm uninstall cluster-$ID spoke-$ID hub-us-east-1 --namespace crossplane-system
```

Deleta os XRs → Crossplane destrói os recursos AWS. Uninstall por célula isola o blast radius
(derrubar um spoke não afeta o hub nem outros spokes).

## Validação offline (custo zero)

```bash
helm template hub-x aws/platform/charts/hub --set name=hub-us-east-1
crossplane render <xr> ../../eks/resources/<kind>/composition.yaml ../../eks/providers/functions.yaml
```

`crossplane render` confirma external-names, label `env=<name>` e `providerConfigRef.name` sem
tocar a AWS. Para o Cluster, passar o EnvironmentConfig via `--extra-resources`.
