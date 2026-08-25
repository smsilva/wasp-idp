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
├── OU: Security
│   ├── log-archive                       ← trail organizacional (tópico 7)
│   └── security-tooling                  ← delegated admin de GuardDuty/Config
├── OU: Infrastructure
│   ├── network                           ← Connectivity Account, papel "Hub" (tópico 0)
│   └── shared-services                   ← opcional (DNS resolver, AD, imagens)
├── OU: Workloads
│   ├── OU: NonProd
│   │   ├── Project A NonProd Account     ← 1 spoke (ou mais) do projeto A
│   │   └── Project N NonProd Account
│   └── OU: Production
│       ├── Project A Prod Account
│       └── Project N Prod Account
└── OU: Sandbox (opcional)
    └── contas de experimentação, DESCONECTADAS da rede (sem attachment no TGW)
```

- **OU Security**: contas que **recebem e analisam** — nunca hospedam workload. A separação
  entre `log-archive` (armazena) e `security-tooling` (investiga) existe para que quem lê o
  log não possa apagá-lo (tópico 7).
- **OU Infrastructure**: recursos compartilhados de plataforma. Guardrails mais restritivos (menos
  serviços habilitados, sem acesso público além do estritamente necessário). A conta de
  auditoria **não** mora aqui: quem opera a rede não deve poder apagar o rastro do que fez.
- **OU Workloads**: onde os projetos vivem, **separada por SDLC stage** (`NonProd` e
  `Production`) — é a recomendação do whitepaper *Organizing Your AWS Environment Using
  Multiple Accounts*: uma conta por workload **e por ambiente**. Guardrails de baseline
  (região permitida, IMDSv2 obrigatório, etc.) — ver tópico 2, com `Production` podendo
  receber SCPs adicionais.
- **OU Sandbox**: conceito **distinto** de `NonProd` — não é "o ambiente de teste do
  projeto", é a conta de brincar: sem dado real, sem conexão com a rede (nenhum attachment
  no TGW do hub), limite de gasto próprio. `NonProd` valida o caminho para produção;
  `Sandbox` não valida nada, só explora. Opcional nesta referência.

### Por que uma conta por ambiente, e não um ambiente por VPC

A **conta** é o único limite forte da AWS: quota de serviço, SCP, IAM e billing são todos
por conta. NonProd e Production na mesma conta compartilham quota de vCPU/EIP (um teste
esgota a produção) e qualquer role mal escopada atravessa o ambiente.

## Criando as OUs

```bash
scripts/create-organizational-unit-structure
```

Idempotente — cria `Security`, `Infrastructure`, `Workloads` e, dentro de `Workloads`,
`NonProd` e `Production`. Equivalente manual:

```bash
root_id="$(aws organizations list-roots --query 'Roots[0].Id' --output text)"

aws organizations create-organizational-unit \
  --parent-id "${root_id}" --name Infrastructure
```

### Renomear uma OU não quebra nada

`update-organizational-unit` troca só o nome — o **Id da OU não muda**, então SCPs
anexadas, contas-membro e qualquer referência por Id continuam válidas:

```bash
scripts/rename-organizational-unit --name Sandbox --parent Workloads --new-name NonProd
```

Já **conta-membro** é o oposto: o nome muda via `account put-account-name`
(`scripts/rename-account`, exige trusted access de `account.amazonaws.com`), mas o **e-mail
do root user** — a identidade única da conta em toda a AWS — só muda pelo fluxo de root, no
console da própria conta. Por isso vale acertar o e-mail na criação.

## Billing consolidado

Com `feature-set ALL`, o billing de todas as contas-membro é consolidado na management
account automaticamente — nenhuma configuração extra. Detalhe de tagging por projeto/custo:
`05-billing-e-tags.md`.

## Well-Architected — porquê

| Best practice | Como atende |
|---|---|
| **OPS** delegação por unidade | OUs separam Security, Infrastructure e Workloads — guardrails e operação diferentes por natureza |
| **[SEC01-BP01](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/sec_securely_operate_multi_accounts.html)** fundação de Organization | `feature-set ALL` é pré-requisito para todo o resto do domínio de segurança de contas |

## Próximo

→ [`02-guardrails-scp.md`](02-guardrails-scp.md): guardrails preventivos por OU.