# CLAUDE.md — `tenancy/` (Domínio: Tenancy & SaaS)

> Índice do domínio de **Tenancy** — quanta infraestrutura é compartilhada entre clientes e onde
> está a fronteira que impede um de alcançar o outro. Ordem de leitura = ordem dos arquivos.
> Corpo genérico (placeholders `<...>`).

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

## Sequência de decisão (não é sequência de provisionamento)

Ao contrário dos outros domínios, este não provisiona nada — decide. A ordem importa porque cada
passo restringe o seguinte:

```text
① Definir os TIERS comerciais do produto (standard / premium / enterprise)
② Escolher o modelo por tier: pool, bridge ou silo   ← nunca um modelo único para o produto
③ Calcular o piso de custo do tier siloado → confirmar que o ticket o suporta
④ Definir os PERFIS DE RESIDÊNCIA oferecidos (US, EU, BR…) — não regiões por cliente
⑤ Criar uma OU por perfil de residência, com SCP de região própria
⑥ Decidir se spoke de tenant participa do roteamento central (define se CIDR é único ou repetido)
⑦ Só então: provisionar contas de tenant (→ ../accounts/03-provisioning.md)
```

- **② antes de ③** evita a armadilha de escolher silo por instinto e descobrir a margem depois.
- **④ antes de ⑤** porque a OU é a unidade de SCP: perfil definido depois vira reorganização da
  árvore.
- **⑥ antes de ⑦** porque CIDR é a única decisão irreversível da cadeia.

## Relação com o resto do repo

- **Consome** `../accounts/` (estrutura de OU, provisionamento de conta, SCP baseline) e
  `../network/01-cidr-addressing.md` (o plano cujo teto este domínio calcula).
- **Serve** `../security/08-control-plane-identity.md` (a SCP de OU é a primeira linha de
  contenção regional) e o desenho de plataforma em `../../../decisions.md`.
- **Vocabulário:** "hub" aqui é sempre **papel topológico** de rede, nunca nome de conta nem hub
  de identidade — a distinção que `../CLAUDE.md` marca como a confusão mais cara da doc.
- **Convergência com `decisions.md` §3:** os dois descrevem o mesmo desenho com vocabulários
  diferentes (silo/pool/bridge vs. célula/densidade). A tabela de reconciliação está em
  [`00-models.md`](00-models.md) — nenhum contradiz o outro.

## Estado atual vs. alvo (resumo)

- **Hoje:** nada de tenancy implementado. Não há tenant, tier, OU de geografia nem conta de
  cliente. A Organization tem `Workloads/NonProd` e `Workloads/Production` genéricas
  (`../accounts/CLAUDE.md`).
- **Alvo:** tiers definidos com modelo por tier; OUs por perfil de residência com SCP de região;
  conta por tenant só nos tiers que a economia sustenta; alocação de CIDR que não colapse em 15.
- **Este domínio é o mais adiantado em relação ao código** — é desenho, não retrato. Diferente de
  `../accounts/`, nada aqui foi aplicado numa conta real.

## Decisões em aberto

| # | Decisão | Por que está aberta | Custo de adiar |
|---|---|---|---|
| 1 | **Quais tiers o produto oferece** e qual modelo (pool/bridge/silo) em cada | Decisão comercial, não técnica | Bloqueia 2–4 abaixo; toda estimativa de custo por tenant fica sem base |
| 2 | **Spoke de tenant participa do roteamento central?** | Depende de como o control plane alcança a spoke (API pública vs. rede privada) | Define se CIDR de tenant é único ou repetido — a única decisão irreversível da cadeia (`03-cidr.md`) |
| 3 | **Perfis de residência oferecidos** (quais jurisdições) | Depende do mercado-alvo | Definir depois vira reorganização da árvore de OUs, com janela sem SCP durante o move |
| 4 | **IPAM agora ou octeto calculado** | Só vale se 2 for "único"; hoje seria trabalho possivelmente descartável | `decisions.md` §7 registra "IPAM cedo" como armadilha — o custo aparece no ambiente 8, não no 2 |
| 5 | **`04-crossplane-map.md` deste domínio** — não escrito de propósito | Depende do schema do registry de tenants (`decisions.md` §11, decisão 1) | Nenhum hoje; o mapa sem o registry seria especulação. **Ausência é deliberada, não esquecimento** |

## Fontes

- [SaaS Lens](https://docs.aws.amazon.com/wellarchitected/latest/saas-lens/saas-lens.html) —
  lens oficial, publicada 2023-04-04, disponível no Lens Catalog do Well-Architected Tool.
- [Silo, Pool, and Bridge Models](https://docs.aws.amazon.com/wellarchitected/latest/saas-lens/silo-pool-and-bridge-models.html)
  — os três modelos e suas definições.
- [Tenant Isolation](https://docs.aws.amazon.com/wellarchitected/latest/saas-lens/tenant-isolation.html)
  — por que cruzar a fronteira de tenant é evento potencialmente irrecuperável.
- `../../../decisions.md` §3 — o mesmo modelo pela lente de célula/densidade.
