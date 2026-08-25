# 00 — Modelos de Tenancy (silo, pool, bridge)

**Pilar WAF principal:** a **[SaaS Lens](https://docs.aws.amazon.com/wellarchitected/latest/saas-lens/saas-lens.html)**
do Well-Architected — lens oficial (publicada em 2023-04-04, disponível no Lens Catalog do
Well-Architected Tool). Ela não substitui os pilares: cobre o que é **específico de workload
SaaS multi-tenant**, organizado em cinco áreas conceituais.

## Por que existe uma lens só para isto

Os seis pilares perguntam "esta arquitetura é segura/confiável/eficiente?". Um SaaS
multi-tenant tem uma pergunta a mais, que nenhum pilar faz: **quanto de infraestrutura é
compartilhado entre clientes, e onde está a fronteira que impede um de alcançar o outro?**

A lens é explícita sobre a gravidade disso em
[Tenant Isolation](https://docs.aws.amazon.com/wellarchitected/latest/saas-lens/tenant-isolation.html):
cruzar essa fronteira "would represent a significant and potentially unrecoverable event for a
SaaS business". Não é um bug com severidade — é um evento do qual o negócio pode não voltar.

## Os três modelos

A lens nomeia três padrões em
[Silo, Pool, and Bridge Models](https://docs.aws.amazon.com/wellarchitected/latest/saas-lens/silo-pool-and-bridge-models.html):

| Modelo | Definição | Custo por tenant | Isolamento |
|---|---|---|---|
| **Silo** | Tenant recebe **recursos dedicados** — stack de infra independente, ou pelo menos banco próprio | Alto (piso fixo por tenant) | Máximo — a fronteira é a própria infra |
| **Pool** | Tenants **compartilham** recursos; multi-tenancy clássica, com escala e economia de escala | Baixo (amortizado) | Lógico — namespace, claim, row-level, quota |
| **Bridge** | **Misto**: parte do sistema em silo, parte em pool | Intermediário | Varia por componente |

O bridge não é indecisão — a lens o descreve como reconhecimento de que "SaaS businesses aren't
always exclusively silo or pool". Um microserviço pode ir para silo pelo **perfil regulatório do
dado** ou por **noisy neighbor**, enquanto outro fica pooled por **agilidade e custo**. A decisão
é por componente, não pelo produto inteiro.

## A restrição que a AWS impõe ao silo (e que é fácil perder)

Este é o ponto mais importante da página da lens, e o mais fácil de violar sem perceber:

> mesmo com recursos dedicados, um ambiente silo **continua dependendo de identidade,
> onboarding e experiência operacional compartilhados** — todos os tenants gerenciados e
> deployados pelo mesmo mecanismo.

A lens diz que é isso que **diferencia SaaS de managed service**: se cada cliente ganha seu
próprio pipeline, sua própria versão e seu próprio fluxo de onboarding, você não tem um SaaS com
tier dedicado — tem N produtos com um cliente cada, e o custo operacional cresce linear com a
base de clientes.

É a mesma regra que o desenho de plataforma deste repo já havia registrado por conta própria
(`../../../decisions.md`, §3): *"mesmo artefato, mesmo pipeline, mesma observabilidade; a única
variável é quantos tenants entram"*. A lens dá o vocabulário oficial; §3 dá o teste prático.

## Reconciliando os dois vocabulários

`decisions.md` §3 e esta lens descrevem o mesmo desenho com palavras diferentes:

| `decisions.md` §3 | SaaS Lens | Observação |
|---|---|---|
| Célula com N tenants | **pool** | Densidade > 1 |
| Célula com 1 tenant | **silo** | Densidade = 1; mesmo artefato |
| "pooled e dedicado são o mesmo desenho com densidade variável" | **bridge** aplicado à camada de compute | A lens chega ao mesmo lugar por outro caminho |
| "compute e dados são eixos separados" | bridge por componente | Cluster pooled + tabela dedicada é bridge canônico |

**Nenhum dos dois contradiz o outro.** Use "silo/pool/bridge" ao conversar com a AWS ou citar a
lens; use "célula/densidade" ao falar de raio de impacto interno.

## O que a lens NÃO diz

A lens **não prescreve silo**. Ela apresenta os três modelos como escolha condicionada a fatores
"regulatory, competitive, strategic, cost efficiency, and market". A leitura de que "isolamento
máximo é sempre melhor" é a armadilha: silo universal transfere o custo do isolamento para a sua
margem, em todos os tenants, inclusive nos que nunca pediram isolamento.

O caminho recomendado é **tiering**: o modelo é escolhido por **tier comercial**, não uma vez
para todo o produto.

```
Tier standard    → pool     (isolamento lógico; a maioria dos clientes)
Tier premium     → bridge   (dado dedicado, compute compartilhado)
Tier enterprise  → silo     (infra dedicada; paga por isso explicitamente)
```

Onde a linha entre os tiers cai é uma conta, não uma preferência — o piso de custo de um tenant
siloado está em [`01-conta-por-tenant.md`](01-conta-por-tenant.md).

## Well-Architected — porquê

| Best practice | Como atende |
|---|---|
| **[SaaS Lens — Tenant Isolation](https://docs.aws.amazon.com/wellarchitected/latest/saas-lens/tenant-isolation.html)** | A fronteira de tenant é decisão explícita e documentada por tier, não emergente do código |
| **[SaaS Lens — Silo, Pool, and Bridge Models](https://docs.aws.amazon.com/wellarchitected/latest/saas-lens/silo-pool-and-bridge-models.html)** | Vocabulário oficial adotado; bridge por componente em vez de escolha única para o produto |
| **[SEC01-BP01 — Separate workloads using accounts](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/sec_securely_operate_multi_accounts.html)** | Quando o tier exige silo, a fronteira é a conta — não uma convenção de nomes |
| **COST** — custo por tenant é decisão de tier | O modelo é escolhido pela economia do tier, não por preferência arquitetural |

## Próximo

→ [`01-conta-por-tenant.md`](01-conta-por-tenant.md): quando o silo vira **uma conta AWS por
tenant** — piso de custo, quotas e o problema do offboarding.
