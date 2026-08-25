# 02 — OU por Geografia (residência de dados como estrutura, não como campo)

**Pilar WAF principal:** Security
([SEC01-BP03 — Identify and validate control objectives](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/sec_securely_operate_control_objectives.html)).

## A restrição de onde tudo isto nasce

**SCP atacha em OU ou em conta — não em tenant, nem em tag.** Tecnicamente é possível atachar em
conta individual, mas gerenciar centenas de attachments diretos é insustentável: cada conta nova
exige um attachment próprio, e não há como verificar a política de uma população de contas
olhando um lugar só.

Portanto: **todo guardrail que varia por cliente tem de virar uma dimensão da árvore de OUs.**
Essa é a restrição que decide o desenho, e ela é estrutural — não se resolve com automação.

## O erro: "cada cliente escolhe suas regiões"

Parece flexibilidade comercial legítima. Mas se a lista de regiões é propriedade do cliente, cada
combinação distinta exige sua própria OU:

```
Cliente A: us-east-1                      → OU #1
Cliente B: us-east-1, us-west-2           → OU #2
Cliente C: eu-west-1                      → OU #3
Cliente D: us-east-1, eu-west-1           → OU #4
Cliente E: us-east-1, us-west-2, sa-east-1 → OU #5
...
```

Cresce como o conjunto das partes das regiões suportadas, não como o número de clientes. Com 6
regiões, há 63 combinações possíveis. A árvore de OUs deixa de descrever a organização e passa a
descrever o histórico comercial — e cada SCP nova tem de ser replicada em N OUs.

## O padrão: agrupar por perfil de residência

Inverta a propriedade. O cliente **não escolhe regiões**; escolhe um **perfil de residência de
dados**, e a plataforma o posiciona na OU correspondente.

```text
Workloads/
├── Tenants-US/       SCP: aws:RequestedRegion ∈ { us-east-1, us-west-2 }
│   ├── tenant-<a>
│   └── tenant-<b>
├── Tenants-EU/       SCP: aws:RequestedRegion ∈ { eu-west-1, eu-central-1 }
│   └── tenant-<c>            ← exigência GDPR de residência
└── Tenants-BR/       SCP: aws:RequestedRegion ∈ { sa-east-1 }
    └── tenant-<d>            ← exigência LGPD de residência
```

Propriedades que isso compra:

- **Número de OUs é limitado pelos perfis oferecidos** (3–5), não pela base de clientes.
- **SCP nova entra em N lugares conhecidos**, não em N contas.
- **O perfil é vendável** — "residência na UE" é uma linha de contrato, enquanto
  "`eu-west-1` + `eu-central-1`" é detalhe de implementação que você não quer congelar em
  contrato.
- **Auditoria fica trivial:** "quais tenants podem tocar dado fora da UE?" é uma consulta à
  árvore, não a N policies.

Cliente que pede combinação exótica é **exceção comercial** — trate como tal (OU própria,
custo próprio), não como caso base.

## Conecta com o guardrail que já existe

O baseline deste repo já aplica **"Restringir região"** nas OUs de workload
(`../accounts/02-guardrails-scp.md`). Este tópico não introduz um mecanismo novo: mostra que
aquele guardrail é **o eixo pelo qual as OUs de tenant devem ser particionadas**, em vez de uma
lista única aplicada a todas.

```json
{
  "Effect": "Deny",
  "NotAction": [ "<serviços-globais-que-precisam-de-us-east-1>" ],
  "Resource": "*",
  "Condition": {
    "StringNotEquals": { "aws:RequestedRegion": [ "<região-1>", "<região-2>" ] }
  }
}
```

> **Cuidado com os serviços globais.** IAM, Organizations, Route 53, CloudFront e ACM-para-
> CloudFront respondem em `us-east-1` independentemente de onde o tenant vive. Uma SCP de região
> sem `NotAction` para eles quebra a conta inteira — inclusive o provisionamento. A lista de
> exceções faz parte da policy, não é um detalhe de ajuste posterior.

## Por que não resolver com tag em vez de OU

Tentador: `Condition` em `aws:PrincipalTag/residency` ou `aws:ResourceTag`. Problemas:

- **Tag é mutável por quem tem permissão de tag** — o guardrail passa a depender de outro
  guardrail que impeça a alteração da tag, e a cadeia fica frágil.
- **Nem toda action suporta condição de tag**; a cobertura é irregular por serviço.
- **Recurso criado sem tag** escapa, salvo se houver SCP exigindo tag na criação — mais uma
  policy para manter correta.

OU é imutável do ponto de vista da conta-membro: nenhuma identidade **dentro** da conta pode
mover a própria conta de OU. Essa é exatamente a propriedade que um guardrail de residência
precisa. Tag serve para **alocação de custo** (`../accounts/05-billing-e-tags.md`), não para
fronteira de compliance.

## Consequência para o control plane

Um control plane regional que provisiona spokes de tenant fica **abaixo** da SCP da OU do tenant
no momento em que age naquela conta. Isso é desejável: mesmo que o Crossplane receba um XR com a
região errada, a SCP nega. É a razão pela qual a SCP em OU é a **primeira** linha de contenção
regional, à frente de qualquer condição em role — detalhe em
`../security/08-identidade-do-control-plane.md`.

## Well-Architected — porquê

| Best practice | Como atende |
|---|---|
| **[SEC01-BP03 — Identify and validate control objectives](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/sec_securely_operate_control_objectives.html)** | Residência de dados vira objetivo de controle verificável na árvore de OUs, não cláusula de contrato sem enforcement |
| **[SEC01-BP01 — Separate workloads using accounts](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/sec_securely_operate_multi_accounts.html)** | Conta isola o tenant; a OU acima dela aplica o perfil de jurisdição |
| **[SaaS Lens — Tenant Isolation](https://docs.aws.amazon.com/wellarchitected/latest/saas-lens/tenant-isolation.html)** | A fronteira geográfica é preventiva (SCP), não detectiva |
| **OPS** — cardinalidade de política controlada | Número de OUs cresce com perfis oferecidos, não com a base de clientes |

## Próximo

→ [`03-cidr-e-tenancy.md`](03-cidr-e-tenancy.md): por que região × tenant esgota o plano de
endereçamento, e por que tenant isolado talvez não precise de CIDR único.
