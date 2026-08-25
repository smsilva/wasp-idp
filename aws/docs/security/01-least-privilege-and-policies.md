# 01 — Least Privilege and Policies

**Pilar WAF principal:** Security ([SEC03 — Permissions management](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/permissions-management.html)).

## Menor privilégio em uma frase

Conceda **apenas** as ações necessárias, **apenas** nos recursos necessários, e nada além.
Toda concessão a mais é superfície de ataque e blast radius de erro humano. Na prática:
começar do zero e adicionar o que falta (baseado em negações reais), não começar de
`AdministratorAccess` e tentar remover depois.

## As quatro camadas de "o quê"

Uma ação só é permitida se sobreviver a **todas** as camadas aplicáveis. Da mais externa à
mais interna:

```text
SCP (teto da conta/OU)          ← ../accounts/02 — nega mesmo para Administrator
  └─ Permission Boundary        ← teto máximo de uma identidade específica
       └─ Identity policy       ← o que a role/user de fato concede
            └─ Resource policy   ← o que o recurso-alvo aceita (tópico 3)
```

- **SCP** e **boundary** são **tetos** (só restringem, nunca concedem).
- **Identity policy** é a concessão efetiva.
- A ação passa se: `Allow` na identity policy **E** dentro do boundary **E** dentro do SCP
  **E** (se houver resource policy) permitida por ela. Qualquer `Deny` explícito vence tudo.

## Escopar por ARN, não por wildcard

O gap entre uma policy segura e uma perigosa quase sempre é o `Resource`:

```json
{
  "Effect": "Allow",
  "Action": ["iam:GetRole", "iam:CreateRole", "iam:DeleteRole", "iam:PutRolePolicy"],
  "Resource": "arn:aws:iam::<account-id>:role/<prefix>-*"
}
```

`Resource: "*"` daria à automação poder sobre **qualquer** role da conta — incluindo as de
outros times. Escopando a `<prefix>-*` (ex.: `poc-eks-*`), a automação só alcança **as suas
próprias** roles. É exatamente o padrão da inline policy `CrossplaneEksRoleManagement` desta
PoC (ver apêndice) — a regra imutável "só ADICIONAR recursos isolados" vira um filtro de ARN.

## Permission boundaries — o teto de uma identidade

Uma **permission boundary** é uma policy que define o **máximo** que uma role/user pode ter,
independentemente do que suas identity policies concedem. Uso central: **delegar a criação de
roles sem delegar escalada de privilégio**.

- Sem boundary: quem pode `iam:CreateRole` pode criar uma role `AdministratorAccess` e
  assumi-la → escalada.
- Com boundary: exige-se (via condição `iam:PermissionsBoundary`) que toda role criada carregue
  a boundary → a role nova nunca excede o teto, mesmo que a policy anexada seja ampla.

```json
{
  "Effect": "Allow",
  "Action": "iam:CreateRole",
  "Resource": "arn:aws:iam::<account-id>:role/<prefix>-*",
  "Condition": {
    "StringEquals": {
      "iam:PermissionsBoundary": "arn:aws:iam::<account-id>:policy/<boundary-name>"
    }
  }
}
```

## Managed vs. inline — quando cada uma

| Tipo | Quando usar | Exemplo na PoC |
|---|---|---|
| **AWS managed** | permissões amplas e estáveis mantidas pela AWS | `PowerUserAccess` no `crossplane-poc` |
| **Customer managed** | policy reusável entre várias identidades, versionada | boundary compartilhada por várias roles |
| **Inline** | uma policy 1:1 com **uma** identidade, deve morrer com ela | `CrossplaneEksRoleManagement` (só da automação) |

Inline é o certo quando a policy **não faz sentido sem** aquela identidade — some junto quando
a identidade é deletada, sem lixo órfão.

## O antipadrão `PowerUserAccess` e o custo do pragmatismo

`PowerUserAccess` é `AllowAll` com `NotAction: iam:*` — cobre EC2/VPC/EKS mas **exclui todo o
namespace IAM**. Nesta PoC ele é pragmático (a automação precisa de muitos serviços), mas o
preço é: ele **não** é menor privilégio, e a lacuna de IAM teve de ser preenchida por uma
inline **escopada** (`poc-eks-*`) em vez de abrir `iam:*` inteiro. O caminho para o alvo é
substituir `PowerUserAccess` por uma customer-managed policy que lista só os serviços que a
automação realmente usa — quando o inventário de ações estiver estável (tópico 6 mostra como
descobri-lo via CloudTrail/Access Analyzer).

## Well-Architected — porquê

| Best practice | Como atende |
|---|---|
| **[SEC03-BP01 — Define access requirements](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/sec_permissions_define.html)** | policies escopadas por ARN `<prefix>-*`, não `Resource: "*"` |
| **[SEC03-BP02 — Grant least privilege access](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/sec_permissions_least_privileges.html)** | condição `iam:PermissionsBoundary` limita criação de role |
| **[SEC03-BP04 — Reduce permissions continuously](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/sec_permissions_continuous_reduction.html)** | trilha via Access Analyzer/CloudTrail (tópico 6) para enxugar `PowerUserAccess` |
| **[SEC03-BP07 — Analyze public and cross-account access](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/sec_permissions_analyze_cross_account.html)** | boundary + escopo de ARN contêm o alcance |

## Próximo

→ [`02-cross-account-roles.md`](02-cross-account-roles.md): como uma conta age em outra sem
duplicar credenciais.
