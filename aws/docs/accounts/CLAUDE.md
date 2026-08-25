# CLAUDE.md — `accounts/` (Domain: Accounts and Organizations)

> Índice do domínio **Accounts & Organizations** — o container que hospeda a rede
> (`../network/`). Ordem de leitura = ordem dos arquivos. Corpo genérico (placeholders `<...>`).

## O que este domínio entrega

Sair de uma **conta AWS vazia** (a primeira que você loga) e chegar a uma **AWS Organization**
com a estrutura de contas que o hub-and-spoke exige: uma conta de gerência que só administra,
uma **Hub/Connectivity Account** dedicada, e **uma conta por projeto** — cada uma podendo
hospedar 1+ spokes (`../network/00-topology.md`).

## Tópicos

| # | Arquivo | Assunto | Pilar WAF principal |
|---|---|---|---|
| 0 | [`00-strategy.md`](00-strategy.md) | Por que multi-account; papel de cada conta; conta de gerência nunca hospeda workload | Operational Excellence |
| 1 | [`01-organizations-and-ous.md`](01-organizations-and-ous.md) | AWS Organizations, Organizational Units, billing consolidado | Operational Excellence |
| 2 | [`02-scp-guardrails.md`](02-scp-guardrails.md) | Service Control Policies — guardrails preventivos por OU | Security |
| 3 | [`03-provisioning.md`](03-provisioning.md) | Como criar contas de fato: API `create-account`, convenção de e-mail, bootstrap do root | Operational Excellence |
| 4 | [`04-cross-account-access.md`](04-cross-account-access.md) | IAM Identity Center (SSO), permission sets, roles cross-account; nunca usar root | Security |
| 5 | [`05-billing-and-tags.md`](05-billing-and-tags.md) | Billing consolidado, tags de custo por conta/projeto | Cost Optimization |
| 6 | [`06-crossplane-map.md`](06-crossplane-map.md) | O que é (e não é) automatizável via Crossplane; estado atual do PoC vs alvo | — |
| 7 | [`07-cloudtrail-and-log-archive.md`](07-cloudtrail-and-log-archive.md) | Trail organizacional, conta `log-archive`, bucket de auditoria em conta separada | Security |

**Vocabulário:** nomes de OU e de conta seguem o whitepaper *Organizing Your AWS Environment
Using Multiple Accounts* (`Security`, `Infrastructure`, `Workloads/NonProd`,
`Workloads/Production`; conta de rede = `network`). Divergir do whitepaper só com motivo
registrado.

## Sequência de construção (conta vazia → contas prontas)

```text
① Login na 1ª conta (a que você já tem) — ela vira a conta de GERÊNCIA da Organization
② Habilitar AWS Organizations nessa conta (all features, não "consolidated billing only")
③ Criar OUs: Security, Infrastructure, Workloads/NonProd, Workloads/Production
④ Conta log-archive (OU Security) + CloudTrail organizacional   ← ANTES de tudo o mais
⑤ Criar a conta network (Connectivity Account) na OU Infrastructure
⑥ Aplicar SCPs baseline na Organization/OUs (guardrails preventivos)
⑦ Configurar IAM Identity Center (SSO) — permission sets por conta, sem usar root
⑧ Por projeto: create-account em NonProd → validar → só então create-account em Production
⑨ Dentro da conta do projeto: provisionar a(s) spoke(s) de rede (→ domínio network)
```

- **④ o quanto antes** — sem trilha desde o início, perde-se o rastro do próprio bootstrap,
  que é quando se opera com privilégio máximo.
- **⑤ e ⑧:** `create-account` **não** aceita OU de destino — a conta nasce na Root e é movida
  depois. São dois passos, e o SCP da OU não vale na janela entre eles.
- **⑥:** SCP não afeta a conta de gerência. Por isso ela não hospeda nada.
- **⑦ "sem usar root" só é verdade se houver caminho de emergência definido.** Toda conta
  criada em ⑤/⑧ nasce com um root indestrutível e imune a SCP — o único controle é não usá-lo.
  Isso exige um break-glass escrito antes do incidente, não improvisado nele
  (`04-cross-account-access.md`, [SEC03-BP03 — Establish emergency access process](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/sec_permissions_emergency_process.html)).
- **⑧ uma conta por projeto POR AMBIENTE** (`<projeto>-nonprod`, `<projeto>-prod`) — a conta
  é o único limite forte de quota, SCP, IAM e billing (ver `01-organizations-and-ous.md`).

## Scripts (`scripts/`)

Implementação executável dos passos acima. Cada script é idempotente (reaproveita o que já
existir). Só `revoke-permission-set` é destrutivo — pede confirmação e está marcado na tabela. Ver `--help` de cada um para detalhes.

| Script | Cobre o passo | O que faz |
|---|---|---|
| `check` | pré-requisito | Valida `aws`/`jq`, credenciais, feature-set da Organization atual |
| `enable-organization` | ② | `create-organization --feature-set ALL` (ou upgrade se já existir em modo consolidado) |
| `create-organizational-unit-structure` | ③ | Cria `Security`, `Infrastructure`, `Workloads/NonProd`, `Workloads/Production` |
| `enable-service-access --service <principal>` | ④ pré-requisito | Trusted access de um serviço na Org (`cloudtrail.amazonaws.com` para o trail; `account.amazonaws.com` para o `rename-account`) |
| `create-log-archive-bucket` | ④ | Assume role na `log-archive` e cria o bucket de auditoria (BPA, versionamento, SSE, policy do CloudTrail) |
| `create-organization-trail` | ④ | Cria o trail organizacional multi-region + `start-logging` + validação de integridade |
| `create-account --ou {security\|infrastructure\|nonprod\|production}` | ④ ⑤ ⑧ | Cria 1 conta e move para a OU pedida. `--ou production` avisa explicitamente antes de prosseguir |
| `apply-baseline-service-control-policy` | ⑥ | Guardrails do tópico 2: restringe região, exige IMDSv2, nega root, protege CloudTrail/saída da Org |
| `assign-permission-set --account <conta> --user\|--group <principal>` | ⑦ | Cria/reusa permission set do Identity Center e atribui à conta — tira a conta do limbo do switch-role |
| `show-permission-sets [--account <conta>]` | ⑦ verificação | Somente leitura: permission sets existentes e, por conta, quem tem qual acesso |
| `revoke-permission-set --account <conta> --permission-set <ps> --user\|--group <principal>` | ⑦ | Remove uma atribuição (inverso do `assign-permission-set`). **Destrutivo** — pede confirmação salvo `--yes` |
| `rename-account --name <atual> --new-name <novo>` | correção | Renomeia conta-membro via `account put-account-name`. Só o nome; o e-mail do root user **não** muda |
| `rename-organizational-unit --name <atual> --new-name <novo>` | correção | Renomeia OU in-place — o Id não muda, SCPs e contas seguem válidos |

Rodar manualmente via `! <script>` quando decidir aplicar (o classifier de auto-mode pode
bloquear os que criam recursos reais — se bloquear, o usuário roda via `!`).

**Convenção de execução:** ao rodar um script contra uma conta real, atualizar a doc na
sequência ANTES do próximo — o tópico correspondente (gotchas/comandos descobertos) e o
quadro "Estado atual" abaixo. Doc que descreve um estado já superado custa mais caro que doc
ausente: manda executar de novo o que já foi feito, ou pior, o que já mudou de nome.

## Gotchas de API já descobertos

- **Renomear OU é seguro; renomear conta são dois caminhos distintos.**
  `update-organizational-unit` preserva o Id da OU (SCPs e contas seguem válidas). Já a conta
  tem duas identidades independentes:
  - **Nome:** `account put-account-name` (API, cross-account com trusted access).
  - **E-mail do root user** (identidade única da conta em toda a AWS): **não existe API** —
    só pelo fluxo de root no console da própria conta (login como root → Account settings →
    editar e-mail → confirmar nos dois endereços). É trabalhoso, mas **reversível**; já
    executado nesta Organization (`+hub@` → `+network@`). Ainda assim, acertar na criação
    economiza o passo.
- **`put-account-name` cross-account exige trusted access** de `account.amazonaws.com`, que
  **não** vem habilitado por default (`enable-service-access`).
- **`sso-admin list-permission-sets` devolve só ARNs** — achar um permission set pelo nome
  exige `describe-permission-set` em cada ARN. Não existe filtro por nome.
- **`create-account` não aceita OU de destino** — a conta nasce na Root e é movida depois; o
  SCP da OU não vale na janela entre os dois passos.
- **Renomear OU preserva o Id mas quebra script que busca a OU pelo nome.** O rename
  `Infra` → `Infrastructure` deixou `apply-baseline-service-control-policy` procurando uma OU
  inexistente — a query devolvia vazio e o script abortava com mensagem enganosa ("rode
  `create-organizational-unit-structure` primeiro"). Depois de renomear qualquer OU, varrer
  `scripts/` por ocorrências do nome antigo.
- **ARN de managed policy da AWS é `arn:aws:iam::aws:policy/<Nome>`** — `aws:policy`, com
  dois-pontos, não `aws/policy`. A grafia errada só falha no
  `attach-managed-policy-to-permission-set`, **depois** de o permission set já ter sido
  criado: sobra um permission set órfão, sem policy nenhuma.
- **Permission set alterado precisa de `provision-permission-set`** em cada conta onde já
  está atribuído — anexar a policy não propaga sozinho.
- **Trocar o permission set de uma conta são dois passos, não um.** Não existe "update
  assignment": `assign-permission-set` com o novo e `revoke-permission-set` com o antigo.
  Atribuir primeiro evita janela sem acesso.
- **Conta recém-criada não está no portal SSO** — o único gancho é a
  `OrganizationAccountAccessRole` (assumida da management account) até
  `assign-permission-set` rodar. Os scripts que agem dentro de conta-membro
  (`create-log-archive-bucket`) usam essa role, não SSO.

## Decisões em aberto

| # | Decisão | Por que está aberta | Custo de adiar |
|---|---|---|---|
| 1 | **Retenção do bucket de auditoria** — lifecycle rule (Standard → Glacier após N dias, expiração após M anos) | Janela de retenção é decisão de compliance, não técnica | Único custo do CloudTrail que cresce sozinho e para sempre. Baixo hoje (centavos/mês); revisitar antes de o acervo passar de alguns GB |
| 2 | **Atribuição da management account é a usuário, não a grupo** | Herança do bootstrap do Identity Center | Contraria a regra `--group` na conta mais privilegiada; cada pessoa nova exigiria atribuição própria |
| 3 | **Conta `security-tooling`** — slot desenhado, conta não criada | Sem GuardDuty/Config/Security Hub habilitados ainda | Nenhum hoje; vira pré-requisito quando a detecção entrar |
| 4 | **MFA no root** da management account e das contas-membro | Não verificado; `create-account` não configura | Root sem MFA é a credencial mais privilegiada da conta protegida só por senha |
| 5 | **Alarme de uso de root** (CloudTrail → EventBridge → notificação) | Acervo já existe (④); falta a regra | Sem alarme, uso de root é auditoria post-mortem, não controle detectivo |

## Estado atual vs. alvo (resumo)

> **Antes de confiar neste resumo, conferir na API** — ele é retrato datado, não fonte de
> verdade. Árvore de OUs/contas: `list-organizational-units-for-parent` +
> `list-accounts-for-parent` a partir da Root. Acesso: `scripts/show-permission-sets`.

- **Passos ①–⑦ aplicados** numa Organization real (`feature-set=ALL`), com a estrutura de OUs
  e contas do whitepaper: `Security/log-archive`, `Infrastructure/network`,
  `Workloads/NonProd/<projeto>-nonprod`, `Workloads/Production` (vazia). Ids reais em
  `CLAUDE.local.md`.
- **④ CloudTrail organizacional** ativo: trail multi-region com log file validation, bucket
  de auditoria na `log-archive` (BPA, versionamento, SSE-S3, `BucketOwnerEnforced`, deny
  non-TLS). Custo estimado < US$ 1/mês.
- **⑥ SCPs baseline aplicadas** — ver quadro no `02-scp-guardrails.md`.
- **⑦ Identity Center** habilitado: grupo `platform-admins` com `ReadOnlyAccess` na
  `log-archive`; `network` e `<projeto>-nonprod` ainda sem permission set — ver
  `04-cross-account-access.md`. Break-glass **documentado**, controles (MFA no root, alarme de
  uso) **pendentes** — decisões 4 e 5 acima.
- **Pendente:** ⑧ conta de produção do projeto; ⑨ spokes de rede (→ domínio `../network/`).

### Gap conhecido: a conta pré-existente do PoC

A conta AWS que o PoC usava antes desta Organization **não** é dedicada nem isolada — hospeda
infra de outros sistemas. Ela não pode virar a conta `network` da referência sem antes ser
esvaziada: adotar a referência a partir dela exige contas novas na Organization, não
reaproveitar a conta como está.
