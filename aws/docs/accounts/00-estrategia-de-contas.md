# 00 — Estratégia de Contas

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
| **Hub / Connectivity Account** | 1 (por região, se multi-região) | Transit Gateway, VPN Connections, RAM shares — os recursos compartilhados de `../network/` | Workloads de projeto |
| **Project Account** | 1 por projeto | A(s) spoke(s) daquele projeto — VPC, subnets, EKS, apps | Recursos de outro projeto |

> **A regra mais importante deste tópico:** a conta de gerência **nunca** hospeda
> workload. É a recomendação nº1 da AWS para Organizations — reduzir o escopo da conta mais
> privilegiada ao mínimo possível (só administra, não roda nada). Ver `01-organizations-e-ous.md`.

## Por que não "uma conta por ambiente" em vez de "uma conta por projeto"?

Ambas são válidas; a escolha depende do eixo de isolamento que mais importa:

| Eixo | Quando escolher |
|---|---|
| **Por projeto** (esta referência) | Blast radius e billing por time/produto importam mais que por estágio (dev/prod). Cada projeto pode ter múltiplos ambientes como spokes distintos dentro da mesma conta, ou contas próprias por ambiente — decisão do projeto, não da plataforma. |
| **Por ambiente** | Quando compliance exige separação regulatória rígida entre dev/staging/prod (ex.: PCI-DSS). |

Nada impede combinar: conta por projeto **e** spoke por ambiente dentro dela. A referência
não prescreve isso — é decisão de cada projeto.

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
| **[SEC01-BP02 — Secure account root user and properties](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/sec_securely_operate_aws_account.html)** | Cada conta nasce com um root indestrutível e imune a SCP; o plano para ele é o passo ⑦ (`04-acesso-cross-account.md`) |
| **OPS** menor superfície privilegiada | Management account sem workload reduz o que uma falha ali pode afetar |
| **REL/COST** isolamento de cota e billing | Cotas de serviço e custo são por conta, não globais |

## Próximo

→ [`01-organizations-e-ous.md`](01-organizations-e-ous.md): como estruturar a Organization
em si — OUs, billing consolidado.