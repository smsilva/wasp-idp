# Cost allocation drill down

Desejo do usuário (2026-10-08, opinião pessoal a validar): além das categorias (infra, IA) e da hierarquia (tenant → produto → app → recurso), o custo deveria ter drill down pelas entidades do catálogo (**Domain**, **System**, **Component**) e por **User** e **Group**. Este tópico avalia a viabilidade antes de virar slide.

## Por que faz sentido

- O catálogo já declara essas entidades e o dono de cada uma (`spec.owner: group:...`, `spec.system`, `spec.domain`): ver [`backstage-catalog.md`](backstage-catalog.md) e `idp/catalog/communication/catalog-info.yaml`. Custo por entidade do catálogo é o mesmo vocabulário que o dev usou para declarar a app; não é uma taxonomia nova de FinOps.
- A meta é 100% do custo atribuível ao tenant sem ferramental; sem tag, parte do custo só é atribuível por convenção de nome (de resource group, por exemplo) e o custo de LLM fica numa linha única. Atribuir por entidade do catálogo é o passo seguinte ao "por tenant".

## Viabilidade por dimensão

| Dimensão | Infra (AWS) | IA (LiteLLM) | Veredito |
|---|---|---|---|
| Tenant | Conta AWS dedicada: a fatura da conta já é o custo, sem tag | Team/organization por tenant | Viável, é a meta de atribuição por tenant |
| Domain / System / Component | Tag em todo recurso, propagada pela Composition a partir do claim (o XR já conhece app e ambiente); pods do EKS por label | Tag por request ou key por Component | Viável, depende de tag obrigatória no provisionamento |
| Group (dono) | Tag `owner` = `spec.owner` do catálogo | Team do LiteLLM | Viável |
| User | Recurso de infra não é consumido por uma pessoa; no máximo "quem pediu" | Dimensão nativa (user / key owner) | Viável para IA; fraco para infra |

Dimensões de spend do LiteLLM proxy: key, internal user, team, end user (customer), tags e organization ([docs](https://docs.litellm.ai/docs/proxy/cost_tracking)).

## Bloqueios e custos conhecidos

- **Ativação de cost allocation tags é na management (payer) account.** Vale para tags de recurso e para labels do Kubernetes no *split cost allocation data* do EKS ([AWS](https://docs.aws.amazon.com/cur/latest/userguide/split-cost-allocation-data-kubernetes-labels.html)). Nesta conta não administramos a Organization (management account de outro dono): toda tag nova vira pedido ao TI. Tags levam até 24 h para aparecer e mais 24 h para ativar.
- **Limites da AWS:** 50 tags user-defined por recurso, 500 por payer account; no EKS, até 50 labels por pod entram como tag (ordem alfabética, o resto é descartado).
- **Custo compartilhado não tem dono natural:** control plane do EKS, NAT, cluster central de observabilidade. Precisa de regra de rateio declarada, senão o drill down soma menos que a fatura.
- **Alternativa a avaliar (não verificada aqui):** alocação dentro do cluster (OpenCost/Kubecost) por label de pod, sem depender da management account. Não cobre recurso fora do cluster (RDS, S3).

## Perguntas em aberto

- Mapeamento da hierarquia tenant → produto → app → recurso para o catálogo: produto = System? app = Component? Onde entra o Domain (acima do tenant ou do produto)?
- User em infra vale a pena, ou só em IA?
- O time de TI aceita ativar um conjunto fixo de tags (`domain`, `system`, `component`, `owner`, `tenant`) na payer account?

## Uso na apresentação

- Slide de custo / FinOps: "custo no vocabulário do catálogo": tenant → System → Component, com Group como dono e User só em IA. Mensagem: o catálogo que o dev declara é o mesmo eixo do drill down.
- Fitness function candidata: % do custo atribuível por tag de catálogo (ver [`fitness-functions.md`](fitness-functions.md)).
