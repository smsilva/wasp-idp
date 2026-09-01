# EKS access entries — como o acesso ao cluster funciona

## O problema que resolve

Um cluster EKS recém-criado com `authenticationMode = API` **não tem admin nenhum** além de
quem o criou. Sem access entries, `kubectl` falha com:

```
the server has asked for the client to provide credentials
```

Isso acontece porque o EKS recebe o token IAM, extrai o ARN do principal, e consulta a
lista de access entries do cluster — se o ARN não está lá, o acesso é negado.

## Authentication mode

O cluster usa `authenticationMode = API` (definido em `src/cluster/main.tf`). Isso
significa que:

- **Toda** autorização passa por access entries (a API do EKS)
- O legacy `aws-auth` ConfigMap é **ignorado**
- Não existe fallback — se o ARN não está numa access entry, não entra

O modo `API_AND_CONFIG_MAP` (não usado aqui) permitiria os dois mecanismos, mas é
transitório de migração.

## Quem tem acesso hoje

| Principal | ARN | Como entra |
|---|---|---|
| **Role de CI** (GitHub Actions) | `arn:aws:iam::270222614208:role/github-actions-provision` | `bootstrap_cluster_creator_admin_permissions = true` — o criador do cluster ganha admin automático |
| **OrganizationAccountAccessRole** (conta `cicd`) | `arn:aws:iam::270222614208:role/OrganizationAccountAccessRole` | `admin_principal_arns` no `values.tfvars` → `access_entries` no Terraform (#56) |

O `bootstrap_cluster_creator_admin_permissions` é um argumento do Terraform que concede
acesso de cluster-admin ao principal IAM que criou o cluster. É um atalho de bootstrap:
sem ele, nem a role de CI conseguiria instalar helm charts depois de criar o cluster.

O `admin_principal_arns` é a lista de ARNs **adicionais** que viram access entries de
cluster-admin. A conversão acontece no `regions/*/main.tf`:

```hcl
access_entries = { for arn in var.admin_principal_arns : arn => {
  principal_arn = arn
  policy_arn    = "arn:aws:eks::aws:cluster-access-policy/AmazonEKSClusterAdminPolicy"
  access_scope  = "cluster"
} }
```

## Access policy × Access scope

Cada access entry tem dois componentes:

### Access policy

Um template de permissões Kubernetes mantido pela AWS. Os principais:

| Policy | O que permite |
|---|---|
| `AmazonEKSClusterAdminPolicy` | Cluster-admin completo (equivale a `system:masters`) |
| `AmazonEKSAdminPolicy` | Admin, mas sem acesso a nós e namespaces do sistema |
| `AmazonEKSEditPolicy` | Edit (CRUD de workloads, sem RBAC) |
| `AmazonEKSViewPolicy` | Read-only |

Para este cluster, `admin_principal_arns` sempre usa `AmazonEKSClusterAdminPolicy` — é
admin de verdade.

### Access scope

Define o **alcance** da policy:

| Scope | Significado |
|---|---|
| `cluster` | A policy vale para o cluster inteiro (todos os namespaces) |
| `namespace` | Restrito a namespaces específicos |

O `admin_principal_arns` usa escopo `cluster`.

## O que NÃO funciona

### Grupos do Identity Center (diretamente)

A API `CreateAccessEntry` aceita **ARN de principal IAM** (user ou role). Ela **não**
aceita GroupId do Identity Center. Para dar acesso a um grupo, é preciso:

1. Criar um **account assignment** do grupo numa conta AWS com um permission set
2. Isso provisiona uma role IAM `AWSReservedSSO_<PermissionSet>_<hash>` na conta
3. O **ARN dessa role** é o que entra na access entry

Esse caminho é a issue #71.

### Usuários IAM (humanos) diretamente

A mesma lógica: o `principalArn` pode ser `arn:aws:iam::<account>:user/<name>`, mas o
recomendado é usar roles (assumidas via SSO), não users com access keys de longo prazo.

## Perfis AWS × Access entries

| Profile | Conta | Role assumida | ARN que chega ao EKS | Tem access entry? |
|---|---|---|---|---|
| `cicd` | `270222614208` | `OrganizationAccountAccessRole` | `arn:aws:iam::270222614208:role/OrganizationAccountAccessRole` | ✅ Sim (#56) |
| `personal` | `221047292361` | `AWSReservedSSO_*` (SSO direto) | `arn:aws:sts::221047292361:assumed-role/AWSReservedSSO_*` | ❌ Não |
| CI (`github-actions-provision`) | `270222614208` | OIDC → role do GitHub | `arn:aws:iam::270222614208:role/github-actions-provision` | ✅ Sim (criador) |

Isso explica por que `--profile cicd` funciona e `--profile personal` não: o EKS vê ARNs
diferentes, e só o da `OrganizationAccountAccessRole` está na lista de access entries.

## Ver também

- [Access entries — doc oficial AWS](https://docs.aws.amazon.com/eks/latest/userguide/access-entries.html)
- [Access policy permissions](https://docs.aws.amazon.com/eks/latest/userguide/access-policy-permissions.html)
- [#56](https://github.com/smsilva/wasp-idp/issues/56) — implementação de `admin_principal_arns`
- [#71](https://github.com/smsilva/wasp-idp/issues/71) — `admin_group_ids` (grupos do Identity Center)
- [Client VPN operations](client-vpn-operations.md) — como chegar ao cluster quando o endpoint público está fechado