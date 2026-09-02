# 01 — AWS Organizations and OUs

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

## Qual fonte responde o quê (hierarquia de referências)

Três documentos AWS distintos são citados nesta doc, e **cada um responde uma pergunta
diferente**. Confundi-los produz claim sem fonte:

| Fonte | Responde | Não responde |
|---|---|---|
| **Well-Architected Framework** ([SEC01-BP01](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/sec_securely_operate_multi_accounts.html)) | *por quê* isolar por conta; desenhar OUs; landing zone; guardrails | **Nome de conta ou de OU** — nenhum. A própria BP delega ao whitepaper |
| **Whitepaper *Organizing Your AWS Environment Using Multiple Accounts*** ([Recommended OUs](https://docs.aws.amazon.com/whitepapers/latest/organizing-your-aws-environment/recommended-ous-and-accounts.html)) | nomes de **OU**: `Security`, `Infrastructure`, `Workloads`, `Sandbox`, `Deployments`, `Exceptions`, `Transitional`, `Suspended`, `Policy Staging` | detalhe de quais serviços vão em cada conta |
| **AWS SRA** (prescriptive guidance) | nomes e conteúdo de **conta**: ex. [Shared Services](https://docs.aws.amazon.com/prescriptive-guidance/latest/security-reference-architecture/shared-services.html) na OU `Infrastructure` | escolhas de topologia de rede |

**Regra:** ao citar um nome de conta ou OU, citar o whitepaper ou o SRA — **não** o WAF. O WAF
não nomeia contas.

## Organizational Units (OUs) — a estrutura recomendada

OUs são pastas dentro da Organization; SCPs se aplicam a uma OU inteira de uma vez. Estrutura
mínima para esta referência:

```text
Root
├── OU: Security
│   ├── log-archive                       ← trail organizacional (tópico 7)
│   └── security-tooling                  ← delegated admin de GuardDuty/Config
├── OU: Infrastructure
│   └── network                           ← Connectivity Account, papel "Hub" (tópico 0)
├── OU: Deployments                       ← orquestração de deploy cross-account
│   └── cicd                              ← Control Plane: EKS + Crossplane + ArgoCD
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
  O whitepaper é explícito: *"**No application accounts or application workloads** are intended
  to exist within this OU"*.
  - **Contas canônicas desta OU**, nomeadas pelo whitepaper: **Backup**, **Identity**,
    **Network**, **Operations Tooling**, **Monitoring**, **Shared Services**. Só `network`
    existe aqui hoje; os outros são slots reconhecidos, não pendências.
  - **Sem variantes de ambiente.** O whitepaper: *"it does **not** generally make sense to have
    production and non-production variants of these accounts within the Infrastructure OU"*. Se
    um caso exigir nonprod, ele *"should be treated like any other application"* e ir para a OU
    `Workloads`.
- **OU Deployments**: a conta do **Control Plane** — Crossplane + ArgoCD que provisionam infra
  nas outras contas. Definição do whitepaper: *"contains resources and workloads that support how
  you **build, validate, promote, and release changes to your workloads**"*.
  - **Por que conta própria, e não dentro de um workload:** o whitepaper dá três motivos; o que
    encaixa aqui é *"**CD pipelines affect non-production and production workload environments**
    — ... if you manage your CI/CD capabilities in your production workload environments, then
    you must allow the production workload environments to access your non-production
    environments"*. O Control Plane provisiona em `<projeto>-nonprod` **e** `<projeto>-prod`;
    numa conta de workload, uma ganharia acesso à outra.
  - **Uma conta só, tratada como produção.** *"we recommend that you use a set of **production
    deployment accounts**"* e *"CI jobs and CD pipeline build stages ... perform these activities
    in a **production environment**"*. Não existe `cicd-nonprod`: o Control Plane é produção
    mesmo quando provisiona ambientes de teste.
  - É onde vive a identidade mais privilegiada da Org depois da management
    ([`security/08-control-plane-identity.md`](../security/08-control-plane-identity.md)), por isso SCP própria.
  - Classificada como *Advanced OU* no whitepaper — opcional, mas é a definição exata do papel.
  - **O nome `cicd` é convenção deste repo.** O whitepaper **não** prescreve nome de conta para
    esta OU — usa descrições (*"production deployment accounts"*, *"your CI/CD accounts"*).
    Escolhido por proximidade com esse vocabulário e para não colidir com `control-plane`, que
    nomeia o **cluster** (ver [`CLAUDE.md`](../../CLAUDE.md), seção de vocabulário).
- **OU Workloads**: onde os projetos vivem, **separada por SDLC stage** (`NonProd` e
  `Production`) — é a recomendação do whitepaper *Organizing Your AWS Environment Using
  Multiple Accounts*: uma conta por workload **e por ambiente**. Guardrails de baseline
  (região permitida, IMDSv2 obrigatório, etc.) — ver tópico 2, com `Production` podendo
  receber SCPs adicionais.
- **OU Sandbox**: conceito **distinto** de `NonProd` — não é "o ambiente de teste do
  projeto", é a conta de brincar: sem dado real, sem conexão com a rede (nenhum attachment
  no TGW do hub), limite de gasto próprio. `NonProd` valida o caminho para produção;
  `Sandbox` não valida nada, só explora. Opcional nesta referência.

### Se houver tenants externos: OU por perfil de residência

A estrutura acima particiona `Workloads` por **SDLC stage**, o que é correto para projetos
próprios. Com **clientes externos**, aparece um segundo eixo, e ele não pode ser um campo por
conta: **SCP atacha em OU**, então a lista de regiões permitidas a um cliente tem de ser uma
propriedade da árvore.

O agrupamento correto é por **perfil de residência de dados** (`Tenants-US`, `Tenants-EU`,
`Tenants-BR`), não por cliente — agrupar por cliente faria o número de OUs crescer com as
combinações de regiões vendidas, não com a base. Desenho completo, incluindo a armadilha dos
serviços globais na SCP de região, em [`tenancy/02-ou-per-geography.md`](../tenancy/02-ou-per-geography.md).

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
`05-billing-and-tags.md`.

## Well-Architected — porquê

| Best practice | Como atende |
|---|---|
| **OPS** delegação por unidade | OUs separam Security, Infrastructure e Workloads — guardrails e operação diferentes por natureza |
| **[SEC01-BP01 — Separate workloads using accounts](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/sec_securely_operate_multi_accounts.html)** | `feature-set ALL` é pré-requisito para todo o resto do domínio de segurança de contas |

## Próximo

→ [`02-scp-guardrails.md`](02-scp-guardrails.md): guardrails preventivos por OU.