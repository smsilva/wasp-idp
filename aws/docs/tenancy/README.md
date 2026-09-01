# `tenancy/` — Domain: Tenancy & SaaS

Índice de leitura. Convenções e regras ficam em [`CLAUDE.md`](CLAUDE.md).

## O que este domínio entrega

A decisão de **densidade**: quantos tenants por unidade de infraestrutura, e qual fronteira
sustenta o isolamento em cada tier comercial. É o domínio que traduz uma exigência de negócio
("este cliente exige residência na UE", "este cliente paga por cluster dedicado") em estrutura de
conta, OU e endereçamento.

Ortogonal a `../accounts/`: aquele decide **como a Organization é estruturada**; este decide
**quantos clientes cabem em cada peça** e **qual eixo justifica separá-los**. Ortogonal a
`../network/`: aquele decide por onde o tráfego passa; este decide se dois tenants podem
compartilhar bloco de endereço.

**Referência primária:** a [SaaS Lens](https://docs.aws.amazon.com/wellarchitected/latest/saas-lens/saas-lens.html)
do Well-Architected — lens oficial para workloads SaaS multi-tenant, complementar aos pilares.

## Tópicos

| # | Arquivo | Assunto | Pilar WAF principal |
|---|---|---|---|
| 0 | [`00-models.md`](00-models.md) | SaaS Lens: silo / pool / bridge; a exigência de identidade e pipeline compartilhados mesmo no silo; tiering por tier comercial | [SaaS Lens](https://docs.aws.amazon.com/wellarchitected/latest/saas-lens/saas-lens.html) |
| 1 | [`01-account-per-tenant.md`](01-account-per-tenant.md) | Silo levado à conta AWS: piso de custo ~US$150/mês por tenant-região; quota e rate limit de criação; limite de **fechamento** e o churn | Cost Optimization / Security |
| 2 | [`02-ou-per-geography.md`](02-ou-per-geography.md) | SCP atacha em OU ⇒ residência de dados vira dimensão da árvore; perfil de residência em vez de lista de regiões por cliente | Security ([SEC01-BP03 — Identify and validate control objectives](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/sec_securely_operate_control_objectives.html)) |
| 3 | [`03-cidr.md`](03-cidr.md) | Região × tenant esgota o `/12` em 15 spokes; tenant isolado talvez não precise de CIDR único | Reliability ([REL02 — Plan your network topology](https://docs.aws.amazon.com/wellarchitected/latest/reliability-pillar/plan-your-network-topology.html)) |
