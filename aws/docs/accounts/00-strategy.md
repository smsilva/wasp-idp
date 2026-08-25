# 00 — Account Strategy

**Pilar WAF principal:** Operational Excellence (OPS — organização de contas como unidade de
isolamento) + Security ([SEC01 — Security foundations](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/security.html)).

## Por que multi-account (e não uma conta só com muitas VPCs)

Uma conta AWS é a unidade **atômica** de isolamento na AWS: cotas de serviço, billing,
blast radius de uma credencial vazada, limite de compliance — tudo é por conta. Colocar
tudo numa conta só significa que:

- Um limite de cota (ex.: VPCs por região, Elastic IPs) vira um **limite arquitetural
  global**, não por projeto.
- Uma credencial comprometida em um projeto expõe **todos** os projetos.
- Billing não separa naturalmente por time/projeto — exige tagging manual disciplinado
  (e tagging é opcional; a conta é obrigatória).
- IAM cresce sem fronteira — políticas ficam genéricas ("Role X pode fazer Y em qualquer
  recurso da conta") em vez de escopadas por natureza.

**Decisão:** modelo **multi-account gerenciado por AWS Organizations**, seguindo o padrão de
referência da AWS (Control Tower / Landing Zone Accelerator, ainda que esta PoC não use
essas ferramentas diretamente — os princípios são os mesmos).

## Papéis de conta nesta referência

| Papel | Quantas | Hospeda | Nunca hospeda |
|---|---|---|---|
| **Management Account** (gerência) | 1 | A Organization em si: OUs, SCPs, billing consolidado, IAM Identity Center | **Nenhum workload.** Nem VPC, nem EC2, nem Crossplane. |
| **`network`** (Connectivity Account) | **1, para todas as regiões** | O(s) Hub(s) — Transit Gateway, VPN Connections, RAM shares de `../network/`. Um conjunto desses recursos **por região**, todos na mesma conta | Workloads de projeto |
| **`log-archive`** | 1 | Bucket de auditoria do trail organizacional (`07-cloudtrail-and-log-archive.md`) | Qualquer coisa além de logs |
| **Control plane / plataforma** | 1 por ambiente | A spoke privilegiada que roda EKS + Crossplane + ArgoCD e provisiona as demais spokes (`../compute/00-cluster-as-spoke.md`) | Workload de aplicação de tenant |
| **Project / workload account** | 1 por projeto **por ambiente** | A(s) spoke(s) daquele projeto-ambiente — VPC, subnets, EKS, apps | Recursos de outro projeto ou de outro ambiente |

> **A regra mais importante deste tópico:** a conta de gerência **nunca** hospeda
> workload. É a recomendação nº1 da AWS para Organizations — reduzir o escopo da conta mais
> privilegiada ao mínimo possível (só administra, não roda nada). Ver `01-organizations-and-ous.md`.

## Conta não tem região

Uma conta AWS é **global**. Região é uma dimensão *dentro* dela, não um eixo de particionamento
entre contas. Consequências que costumam ser lidas ao contrário:

- A conta `network` é **uma só** mesmo com hub em três regiões — o que se repete por região é o
  conjunto Hub VPC + TGW + egress, não a conta.
- IAM é global: uma role criada numa conta vale para qualquer região dela. Logo **não existe**
  "role de us-east-1" — se você quer contenção regional, ela vem de condição
  (`aws:RequestedRegion`) ou de SCP, nunca de conta separada.
- Um projeto que expande para uma segunda região **continua na mesma conta**; ganha outra VPC,
  não outra conta.

Criar conta por região só se justifica quando o eixo real é outro (residência de dados,
compliance por jurisdição) — e nesse caso o agrupamento correto é por **perfil de residência**
via OU, não por região solta. Ver `../tenancy/02-ou-per-geography.md`.

## Conta por projeto **e** por ambiente

A referência prescreve **uma conta por projeto por ambiente** (`<projeto>-nonprod`,
`<projeto>-prod`) — não é decisão delegada ao projeto. A razão: a conta é o **único** limite
forte simultâneo de cota, SCP, IAM e billing. Ambiente separado por VPC dentro de uma conta
compartilha todos os quatro, então "prod" e "nonprod" competem pela mesma cota de EIP e caem
sob a mesma SCP.

O eixo por projeto e o eixo por ambiente **não competem** — compõem:

| Eixo | O que isola |
|---|---|
| **Por projeto** | Blast radius e billing por time/produto; cota de um projeto não vira teto de outro |
| **Por ambiente** | Guardrail diferenciado (SCP mais restritiva em prod), cota independente, e a garantia de que um erro em nonprod não alcança prod por IAM |

Dentro de cada conta projeto-ambiente, cada cluster continua sendo uma spoke própria — a
granularidade fina segue em `../network/00-topology.md`.

## Bootstrap: a "conta vazia" que você já tem

A primeira conta que você loga (a que criou ao abrir a AWS) é, por padrão, uma conta
standalone. Para virar o ponto de partida desta referência, ela precisa:

1. Ter **AWS Organizations habilitado com `ALL` features** (não só consolidated billing) —
   sem isso, SCPs (guardrails) não funcionam.
2. **Nunca receber workload depois disso** — a partir do momento em que vira management
   account, ela só cria/gerencia outras contas.

Se a conta que você já usa **já tem recursos residentes** (workloads de outros domínios), ela
**não deve** virar a management account desta referência — crie a Organization a partir dela,
mas mova os workloads existentes para uma conta-membro própria, ou comece do zero com uma
conta nova dedicada a ser a gerência.

## Well-Architected — porquê

| Best practice | Como atende |
|---|---|
| **[SEC01-BP01 — Separate workloads using accounts](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/sec_securely_operate_multi_accounts.html)** | A conta como unidade de isolamento — multi-account desde o início, não como retrofit |
| **[SEC01-BP02 — Secure account root user and properties](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/sec_securely_operate_aws_account.html)** | Cada conta nasce com um root indestrutível e imune a SCP; o plano para ele é o passo ⑦ (`04-cross-account-access.md`) |
| **OPS** menor superfície privilegiada | Management account sem workload reduz o que uma falha ali pode afetar |
| **REL/COST** isolamento de cota e billing | Cotas de serviço e custo são por conta, não globais |

## Próximo

→ [`01-organizations-and-ous.md`](01-organizations-and-ous.md): como estruturar a Organization
em si — OUs, billing consolidado.