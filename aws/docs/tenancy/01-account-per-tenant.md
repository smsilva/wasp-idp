# 01 — Account per Tenant (the silo taken to the AWS account)

**Pilar WAF principal:** Cost Optimization + Security
([SEC01-BP01 — Separate workloads using accounts](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/sec_securely_operate_multi_accounts.html)).

## O que a conta entrega como fronteira de tenant

Levar o silo ([`00-models.md`](00-models.md)) até a conta AWS é a forma
mais forte de isolamento que a AWS oferece. A conta é o **único** limite que é simultaneamente:

- **IAM** — nenhuma policy da conta A alcança recurso da conta B sem trust explícito.
- **Cota** — o tenant não consome EIP/vCPU/VPC de outro tenant.
- **SCP** — guardrail preventivo por OU, imune a admin da própria conta.
- **Billing** — custo por tenant sem depender de disciplina de tagging.

Nada disso exige código da aplicação. É o argumento real do silo por conta: o isolamento não
depende de o time acertar um `WHERE tenant_id = ?`.

## O piso de custo (a conta que decide o tier)

Uma spoke dedicada por tenant custa, **antes de qualquer workload**:

| Item | Ordem de grandeza | Observação |
|---|---|---|
| Control plane EKS | ~US$ 73/mês | Por cluster, independente de uso |
| NAT Gateway | ~US$ 33/mês + tráfego | Por AZ, se saída privada for exigida |
| Baseline (endpoints, observabilidade, attachment de TGW) | dezenas de US$/mês | Cresce com o rigor de rede |

Piso realista: **~US$ 150/mês por tenant-região**. Consequência direta:

- Cliente enterprise de US$ 20k/mês → o piso é ruído; silo é trivialmente viável.
- Cliente de US$ 200/mês → o piso come a margem; silo é prejuízo.

**É esta conta, não preferência arquitetural, que define onde cai a linha entre os tiers.**
Números correlatos (região de plataforma ociosa, Network Firewall) estão em
[`decisions.md`](../../../decisions.md), §10.

## Escala: onboarding é pré-requisito, não melhoria

- **Quota de contas** da Organization nasce baixa e sobe por ticket. Planejar o aumento antes de
  precisar dele — o pedido não é instantâneo.
- **`create-account` tem rate limit** e é assíncrono (`describe-create-account-status`).
- **A conta não nasce na OU de destino** — nasce na Root e é movida depois. Na janela entre os
  dois passos a SCP da OU **não vale** ([`accounts/03-provisioning.md`](../accounts/03-provisioning.md)).
- **Conta nova não está no portal SSO** — o único gancho é a `OrganizationAccountAccessRole` até
  um permission set ser atribuído ([`accounts/04-cross-account-access.md`](../accounts/04-cross-account-access.md)).

Cada um desses passos é trivial uma vez e insustentável cem vezes. Conta por tenant **exige**
onboarding automatizado desde o primeiro cliente; não é otimização para depois.

## Offboarding é o lado pior (e o menos lembrado)

Criar contas é limitado; **fechar** é mais limitado ainda. A AWS restringe quantas contas podem
ser fechadas por janela de tempo (percentual da base, em janela móvel). Efeitos com churn:

- Contas de clientes que saíram acumulam em estado suspenso, aguardando janela.
- Enquanto suspensas, continuam contando para a quota da Organization.
- A árvore de OUs acumula resíduo que não é lixo (ainda existe) nem ativo (ninguém usa).

Isso se soma a uma limitação já registrada em [`decisions.md`](../../../decisions.md), §7: o recurso `Account` do
provider-aws **não deleta de verdade** — o fechamento é assíncrono e sujeito a essa cota, então
`deletionPolicy: Orphan` é obrigatório e o recurso passa a ser uma representação parcial da
realidade. Account vending declarativo via XRD é território de Control Tower/AFT ou pipeline
dedicado, não de Crossplane.

**Consequência de desenho:** se o produto tem tier self-service com churn alto, **não** coloque
esse tier em conta própria. Reserve conta por tenant para tiers com contrato e ciclo longo.

## Quando NÃO usar conta por tenant

| Sinal | Modelo melhor |
|---|---|
| Ticket mensal na ordem do piso de custo | pool |
| Churn alto / trial self-service | pool (o limite de fechamento vira dívida operacional) |
| Exigência é isolamento de **dado**, não de compute | bridge — tabela/schema dedicado em cluster compartilhado |
| Milhares de tenants previstos | pool; conta por tenant não escala nessa cardinalidade |
| Exigência é residência geográfica | conta por tenant **não resolve** — é OU por geografia ([`02-ou-per-geography.md`](02-ou-per-geography.md)) |

## Uma conta serve todas as regiões

Erro comum de leitura: supor que um tenant com workload em duas regiões precisa de duas contas.
**Não.** Conta AWS é global; região é dimensão dentro dela. O tenant ganha uma segunda VPC, não
uma segunda conta. Detalhe em [`accounts/00-strategy.md`](../accounts/00-strategy.md), seção "Conta não tem
região", e a consequência para IAM em [`security/08-control-plane-identity.md`](../security/08-control-plane-identity.md).

O que **sim** varia por região é o consumo de CIDR — e é aí que o plano de endereçamento estoura
([`03-cidr.md`](03-cidr.md)).

## Well-Architected — porquê

| Best practice | Como atende |
|---|---|
| **[SEC01-BP01 — Separate workloads using accounts](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/sec_securely_operate_multi_accounts.html)** | Conta como fronteira de tenant no tier que a exige — isolamento que não depende de código de aplicação |
| **[SaaS Lens — Tenant Isolation](https://docs.aws.amazon.com/wellarchitected/latest/saas-lens/tenant-isolation.html)** | A fronteira é infraestrutural e verificável, não uma cláusula `WHERE` |
| **COST** — custo por tier explícito | O piso por tenant-região é calculado e vira critério de tier, não surpresa de fatura |
| **OPS** — onboarding/offboarding como processo | Automação declarada pré-requisito; limite de fechamento tratado no desenho, não no incidente |

## Próximo

→ [`02-ou-per-geography.md`](02-ou-per-geography.md): por que a lista de regiões de um tenant é
propriedade da **OU**, e não do cliente.
