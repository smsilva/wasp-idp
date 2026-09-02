# 03 — Access and RBAC

**Pilar WAF principal:** Security ([SEC02 — Identity management](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/identity-management.html)/[SEC03 — Permissions management](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/permissions-management.html) — quem acessa o cluster e com qual poder).

## Duas camadas de autorização no EKS

Acessar o cluster passa por **duas** portas em sequência — confundi-las gera o clássico "minha
credencial AWS funciona mas o kubectl diz que não tenho permissão":

```text
1. AUTENTICAÇÃO AWS  — quem é você na AWS? (IAM/SSO/role)   → identidade AWS válida
2. AUTORIZAÇÃO K8s   — o que essa identidade pode no cluster? (RBAC)  → Access Entry → grupo/role K8s
```

A primeira porta é IAM ([`security/`](../security/)); a segunda é **RBAC do Kubernetes**, e o que liga uma à
outra no EKS moderno é a **Access Entry**.

## `authenticationMode: API` — Access Entries, não aws-auth

O EKS histórico mapeava IAM→RBAC pelo ConfigMap `aws-auth` (editável, sem auditoria, fácil de
quebrar). Esta referência usa **`authenticationMode: API`**: o mapeamento vira **Access Entry**
+ **Access Policy Association**, recursos de API declarativos e auditáveis.

```text
AccessEntry:              principal IAM  <arn>  →  entra no cluster
AccessPolicyAssociation:  <arn>  ganha  AmazonEKSClusterAdminPolicy  no escopo cluster
                          (ou uma policy mais restrita, num namespace específico)
```

Vantagem: quem tem acesso é **listável e versionável** (não escondido num ConfigMap), e revogar
é deletar a Access Entry.

## O creator NÃO ganha admin automático (gotcha estrutural)

Pegadinha que trava o bootstrap: o cluster nasce com `authenticationMode: API` **sem**
`bootstrapClusterCreatorAdminPermissions`. Logo, **quem criou o cluster não tem RBAC nenhum**
até uma Access Entry ser aplicada.

```text
crossplane-poc cria o cluster  →  NÃO tem RBAC  →  kubectl falha com
  "the server has asked for the client to provide credentials"
     →  até a fase que cria a AccessEntry dele estar Ready
```

Consequência operacional: qualquer `kubectl` contra o EKS (inclusive para destravar um add-on
cedo) **falha** antes da fase de acesso. Se precisar de acesso antes, aplicar a Access Entry
**manualmente** primeiro. É intencional (nada de admin implícito), mas precisa ser sabido.

## Dois principais distintos: operador humano e automação

O cluster tem (ao menos) dois consumidores de RBAC, com Access Entries **separadas**:

| Principal | Origem | Access Entry para |
|---|---|---|
| **Operador humano** | SSO (`AWSReservedSSO_*`) | operar/depurar o cluster (admin ou escopado) |
| **Automação (Crossplane)** | IAM user `crossplane-poc` | gerenciar recursos **dentro** do EKS via provider-helm/kubernetes |

São **ARNs diferentes** — o caller SSO que provisiona não é o IAM user que o Crossplane usa
depois para instalar charts. Cada um precisa da sua Access Entry. No modelo faseado, são fases
distintas (o acesso do operador e o `ClusterAuth`/RBAC da automação).

## A ponte Crossplane → EKS remoto

A partir do momento em que o Crossplane gerencia recursos **dentro** do cluster (charts, Objects
K8s), ele precisa de um **kubeconfig com RBAC**:

- Um MR `ClusterAuth` grava o kubeconfig do EKS num **Secret** (`crossplane-system`).
- Para esse kubeconfig ter poder, o IAM user do Crossplane recebe uma **Access Entry de
  cluster-admin** — o principal derivado em runtime (`sts get-caller-identity`), não hardcoded.
- Os `ProviderConfig` de helm/kubernetes apontam para esse Secret → o Crossplane passa a
  aplicar `Release`/`Object` no EKS remoto.

É o mecanismo que faz um Crossplane **fora** da AWS (no Control Plane (k3d)) gerenciar o **interior** de um
cluster EKS — coerente com as roles cross-boundary de [`security/`](../security/).

## Well-Architected — porquê

| Best practice | Como atende |
|---|---|
| **[SEC02-BP01 — Use strong sign-in mechanisms](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/sec_identities_enforce_mechanisms.html)** | Access Entries mapeiam IAM/SSO→RBAC de forma auditável (não aws-auth) |
| **[SEC03-BP01 — Define access requirements](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/sec_permissions_define.html)** | Access Policy pode escopar a namespace, não só cluster-admin |
| **[SEC02 — Identity management](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/identity-management.html)** | creator não ganha RBAC automático; acesso é concessão explícita |
| **OPS** acesso versionável | quem tem acesso é declarativo (Access Entry), não escondido em ConfigMap |

## Próximo

→ [`04-ingress-and-exposure.md`](04-ingress-and-exposure.md): como o tráfego externo chega aos
pods.
