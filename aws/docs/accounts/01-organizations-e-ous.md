# 01 — AWS Organizations e OUs

**Pilar WAF principal:** Operational Excellence (agrupamento e delegação por unidade
organizacional).

## AWS Organizations em uma frase

Um serviço, gratuito, que agrupa múltiplas contas AWS sob uma única **management account**,
permitindo billing consolidado, políticas aplicadas em massa (SCPs, tópico 2) e criação
programática de novas contas (tópico 3).

## Habilitar a Organization

Na conta que será a management account (tópico 0):

```bash
aws organizations create-organization --feature-set ALL
```

`--feature-set ALL` é **obrigatório** para esta referência — o modo `CONSOLIDATED_BILLING`
(default legado) não permite SCPs nem a maioria dos guardrails de segurança. Se a
Organization já existir em modo consolidado, é possível fazer upgrade para `ALL`
(`enable-all-features`), mas exige aceite de cada conta-membro existente.

## Organizational Units (OUs) — a estrutura recomendada

OUs são pastas dentro da Organization; SCPs se aplicam a uma OU inteira de uma vez. Estrutura
mínima para esta referência:

```text
Root
├── OU: Infra
│   └── Hub / Connectivity Account        ← tópico 0, papel "Hub"
├── OU: Workloads
│   ├── Project A Account                 ← 1 spoke (ou mais) do projeto A
│   ├── Project B Account
│   └── Project N Account
└── OU: Sandbox (opcional)
    └── contas de experimentação, sem SCP de produção
```

- **OU Infra**: recursos compartilhados de plataforma. Guardrails mais restritivos (menos
  serviços habilitados, sem acesso público além do estritamente necessário).
- **OU Workloads**: onde os projetos vivem. Guardrails de baseline (região permitida, IMDSv2
  obrigatório, etc.) — ver tópico 2.
- **OU Sandbox**: opcional, para explorar sem risco de vazar para produção — SCPs mais
  permissivas, mas isoladas.

Crescer o número de OUs (ex.: `Workloads/Prod`, `Workloads/Dev`) é decisão de cada adoção —
esta referência assume o mínimo que já demonstra o padrão.

## Criando as OUs

```bash
aws organizations create-organizational-unit \
  --parent-id <root-id> --name Infra

aws organizations create-organizational-unit \
  --parent-id <root-id> --name Workloads
```

`<root-id>` vem de `aws organizations list-roots --query 'Roots[0].Id'`.

## Billing consolidado

Com `feature-set ALL`, o billing de todas as contas-membro é consolidado na management
account automaticamente — nenhuma configuração extra. Detalhe de tagging por projeto/custo:
`05-billing-e-tags.md`.

## Well-Architected — porquê

| Best practice | Como atende |
|---|---|
| **OPS** delegação por unidade | OUs separam Infra de Workloads — guardrails e operação diferentes por natureza |
| **SEC01-BP01** fundação de Organization | `feature-set ALL` é pré-requisito para todo o resto do domínio de segurança de contas |

## Próximo

→ [`02-guardrails-scp.md`](02-guardrails-scp.md): guardrails preventivos por OU.