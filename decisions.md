# AWS SaaS Platform — Decisões de Arquitetura e Sequência de Provisionamento

> Documento de handoff. Consolida decisões tomadas em sessões de desenho sobre
> tenancy, células, hub-and-spoke, roteamento global e ordem de provisionamento.
> Destino: agente com acesso aos repositórios locais (`smsilva/wasp-idp`,
> `smsilva/kubernetes`).
>
> Status: rascunho de arquitetura. Nada aqui está implementado por completo.
> Itens marcados **[ABERTO]** ainda não foram decididos.

---

## 1. Vocabulário e modelo mental

### Célula
Instância completa e independente da stack: cluster, dados, filas. Um tenant vive
dentro de exatamente uma célula.

- Escala-se **adicionando células**, não engordando as existentes.
- Célula é definida por **o que quebra junto**, não por fronteira tecnológica.
- **Teste de fronteira:** "se eu derrubar este componente, quais tenants caem?"
  Todos que caírem juntos estão na mesma célula.
- Uma célula vive em **exatamente uma** região.

### Célula ≠ cluster necessariamente
- Dois clusters compartilhando o mesmo RDS/DynamoDB = **uma** célula.
- Na prática, cluster-como-célula é o mapeamento mais limpo: o upgrade do EKS é a
  operação de maior risco, e alinhar a fronteira faz o deploy em ondas sair de graça.

### Cell-based ≠ hub-and-spoke
Camadas diferentes e coexistentes:

| | Trata de | Camada |
|---|---|---|
| Cell-based | Raio de impacto | Aplicação / dados |
| Hub-and-spoke | Conectividade privada | Rede |

### Hierarquia de contenção

```
Global (borda AWS — não é um lugar físico)
└── Região (us-east-1, sa-east-1, …)
     ├── Hub VPC — 1 por região, SÓ REDE, sem workload
     └── Célula 1 … Célula N (cada uma = uma spoke)
```

Raios aninhados: **Região > Célula > AZ**.

---

## 2. Decisão: o hub NÃO tem cluster

**O cluster de plataforma é uma spoke privilegiada, não parte do hub.**

- **Hub** = função de rede: TGW, egress/NAT, firewall, resolver, terminação de VPN.
  Nada executa workload ali. (AWS WAF [REL02-BP04](https://docs.aws.amazon.com/wellarchitected/latest/reliability-pillar/rel_planning_network_topology_prefer_hub_and_spoke.html) + whitepaper "Building a Scalable
  and Secure Multi-VPC AWS Network Infrastructure".)
- **Plataforma** = spoke na account `platform`. Roda auth, discovery, ArgoCD, Crossplane.
- **Cliente** = spoke na account do tenant.

Razões:
1. **Raio de impacto** — upgrade de EKS no hub ameaçaria a conectividade de todas as spokes.
2. **Conta e SCP** — hub na account `network` com SCP proibindo workload.
3. **Simetria** — a spoke de plataforma usa o mesmo caminho de VPC/TGW/IPAM que as
   spokes de cliente. Um mecanismo, não dois.

```
Região us-east-1
├── Hub VPC     (account network)   ── TGW, egress, firewall
├── Spoke: plataforma (account platform)  → auth, discovery, ArgoCD, Crossplane
└── Spoke: cliente A  (account tenant-a)  → workload dedicado
```

Plataforma é spoke por **topologia** e privilegiada por **papel** (control plane
regional). Eixos independentes.

> **Desvio conhecido no código atual:** a branch `feat/aws-hub-bootstrap-network`
> coloca a Hub Network na conta Management. SCP em Root/OU **não afeta a conta de
> gerência** — ela fica sempre sem guardrail. Mover para uma account `network`
> dedicada.

---

## 3. Modelo de tenancy — pooled e dedicado são o mesmo desenho

Pooled e dedicado **não são duas arquiteturas**. São o mesmo desenho com
**densidade variável**:

```
Célula A → N tenants (pooled — menor custo por tenant)
Célula B → N tenants (pooled)
Célula C → 1 tenant  (dedicado / silo)
```

### Regra inviolável
**Mesmo artefato, mesmo pipeline, mesma observabilidade.** A única variável é
quantos tenants entram. No momento em que o cliente dedicado ganhar Terraform
próprio ou fluxo de upgrade diferente, viraram dois produtos.

### Requisitos que o modelo impõe
1. **Mapeamento `tenant → célula` mutável desde o dia 1.** Tenant que cresce migra
   de pooled para dedicado. Hardcoded em DNS ou config = migração vira projeto longo.
2. **Teto testado por célula.** "Quantos tenants cabem" é número medido, não "até doer".
3. **Limites por tenant dentro da pooled.** Célula não resolve noisy neighbor — isso
   continua sendo quota, rate limit e priority class no Istio.

### Compute e dados são eixos separados
Um tenant pode estar em cluster compartilhado com tabela DynamoDB própria. Comum
quando a exigência é isolamento de dados, não de performance.

### Ordem de deploy entre células
Célula interna → pooled menor → pooled maiores → dedicadas por último. O cliente que
paga por cluster dedicado é o que menos tolera ser cobaia.

---

## 4. Roteamento global e discovery

### Erro a evitar
**Global Accelerator é anycast L4 — roteia por proximidade de rede, não sabe quem é
o tenant e não respeita fronteira de dado.** Se o GA levar um usuário de Tóquio ao
cluster de plataforma de Mumbai enquanto a célula dele está em Tóquio, ele autentica
contra um Keycloak com issuer e chave de assinatura diferentes, e o dado de
autenticação atravessou fronteira.

**Regra: a entrada global só pode ser discovery, nunca auth.** Auth acontece na
região-casa do tenant, depois do redirect.

### Fluxo correto

```
wasp.silvios.me              → GA → discovery (stateless, sem PII, replicado)
discovery/tenant?email=...   → devolve o nome estável do tenant
customer1.wasp.silvios.me    → CNAME direto para o NLB da célula (região-casa)
auth.<região>.wasp.silvios.me → login acontece aqui, na plataforma da casa
```

Um único GA, no topo, carregando apenas o discovery.

### Discovery é a dependência global crítica
Se ele cai, ninguém entra. Precisa ser a coisa mais boba do sistema: leitura de
Global Table, sem escrita, com cache e fallback para um bookmark regional pinado
no cliente.

**[ABERTO]** Onde o discovery roda: Lambda@Edge vs. cluster de plataforma de cada
região atrás do GA.

### Europa
Roteamento deve usar **geolocation, não latency-based**, para evitar movimentação
não intencional de dado pessoal entre fronteiras.

---

## 5. Evolutividade — ativo/ativo é propriedade do tenant, não da plataforma

Um cluster de cliente **não precisa estar ativo/ativo desde o início**. Uma região
inicialmente é o padrão.

### A única coisa obrigatória no dia 1: a indireção
O discovery devolve um **nome**, nunca um IP nem uma região hardcoded. O registry
guarda uma lista mesmo com um item só:

```
customer1 → regions: [ap-northeast-1]
customer2 → regions: [us-east-1, eu-central-1]   # depois
```

O discovery lê lista desde o começo. Esse é o custo total de ser evolutivo nessa
dimensão.

### Adiável sem se enterrar

| Item | Por quê |
|---|---|
| GA por tenant | CNAME direto resolve. GA entra na segunda região. |
| Replicação cross-region | Só existe com duas regiões. |
| Global Table | Nasce tabela normal; virar Global Table é operação online. |
| Network Firewall | Slot no desenho, recurso depois. |
| TGW inter-region peering | Só faz sentido com duas regiões. |

### NÃO adiável (vira refatoração)
1. **Nome do tenant sem região embutida no que o usuário vê.**
   `customer1.wasp.silvios.me` ✅ — `customer1-ap-northeast-1` como URL bookmarcável ❌.
   O nome regional pode existir como alvo interno.
2. **TTL curto no DNS do tenant (30–60s).** Com 3600 a primeira migração tem uma
   hora de cauda.
3. **Chave primária do dado incluindo o tenant.** Sem isso não se separa o que
   replica do que não replica.

### Quando a segunda região do tenant aparecer, decidir *por quê*
- **DR** → segunda região passiva, item marcado `standby`. Barato.
- **Latência/soberania** → duas células ativas, dado particionado (não replicado).
  Dois tenants lógicos com faturamento único.
- **Ativo/ativo verdadeiro** → replicação bidirecional, resolução de conflito. Mais
  caro e quase nunca é o que o cliente realmente quer ao pedir.

**[ABERTO]** Qual desses o primeiro cliente grande está comprando — define o desenho
de dado.

---

## 6. Dois registries distintos

| Registry | Conteúdo | Churn | Quem escreve |
|---|---|---|---|
| **Regiões** | Quais regiões de plataforma existem e estão saudáveis | Raro | O próprio módulo regional ao se registrar |
| **Tenants** | email/domínio → tenant → região-casa → célula | Alto | Onboarding |

O discovery lê o **de tenants**. O de regiões serve para healthcheck e failover, e
evita um arquivo central listando regiões (que viraria ponto de contenção).

**[ABERTO]** Schema do registry de tenants — próximo passo de menor esforço e maior
alcance. Campos mínimos: tenant, lista de regiões, status por região, célula dentro
da região.

---

## 7. IaC — qual ferramenta em qual camada

### Eixo de decisão: cardinalidade × churn
Terraform para o que se cria uma vez e revisa com cuidado; Crossplane para o que
alguém pede sob demanda.

| Camada | Cardinalidade | Churn | Ferramenta |
|---|---|---|---|
| Org / accounts | ~5 | quase zero | Terraform |
| Hub regional (VPC, TGW, cluster de plataforma) | 3–6 | baixo | Terraform |
| Spoke / Environment / célula | N crescente | alto | Crossplane |

### Desenho escolhido: híbrido
Terraform entrega um módulo `regional-hub` **fino de propósito** — rede + cluster +
ArgoCD + Crossplane instalados — e para aí. Tudo acima disso é XRD, puxado do git
pelo ArgoCD (app-of-apps).

Descartado: **seed cluster / hub-of-hubs** (Crossplane de um cluster seed provisiona
os hubs regionais). Elegante, mas cria dependência de disponibilidade — seed morto =
nenhum hub novo, e o caminho de recuperação do seed é Terraform de novo. Não elimina
o Terraform, só o esconde.

### Divisão de responsabilidade entre os Crossplanes
- **Crossplane do hub regional** → ciclo de vida da célula (VPC, cluster, zona DNS).
- **Crossplane in-cluster** → recursos de escopo de aplicação.

Se o Crossplane do hub também provisionar recurso de app, ele vira gargalo com raio
de impacto regional e perde-se a autonomia de time.

### Armadilhas de IaC já identificadas
- **Account vending na AWS é ruim de declarar.** `Account` do provider-aws não deleta
  de verdade (fechamento assíncrono, cota por janela de 30 dias). `deletionPolicy:
  Orphan` é obrigatório e o recurso vira mentira parcial. Território de Control
  Tower/AFT ou pipeline dedicado, não de XRD.
- **Azure não tem esse problema** — Subscription Alias é chamada de API. Se houver
  abstração multi-cloud, essa assimetria vaza; decidir cedo se é um XRD comum ou dois.
- **Credencial do Crossplane** → role assumida via **EKS Pod Identity**, com o trust
  criado pelo Terraform junto com a spoke. Substitui o IAM user de longa duração que
  está no código atual (desvio conhecido).
- **Ordem inversa no teardown** — destruir o hub antes das spokes deixa órfão. Usar
  Usage API do Crossplane ou fitness function de guarda.
- **Route 53 recusa deletar zona não-vazia** — workloads têm que sair antes ou o XR
  trava em `Deleting`.
- **VPC IPAM cedo** — alocação de CIDR sem sobreposição vira problema no ambiente 8,
  não no 2. Declarar os locales de todas as regiões previstas de uma vez;
  re-CIDRizar depois é caro.

---

## 8. Sequência de provisionamento

### Fase −1 — Bootstrap da Organization

```
① Login na 1ª conta → vira a conta de GERÊNCIA da Organization
② Habilitar AWS Organizations (all features, não "consolidated billing only")
③ CloudTrail organizacional + conta Log Archive   ← ANTES das OUs
④ Criar OUs: Security, Infrastructure, Workloads/NonProd, Workloads/Production
⑤ Criar a conta Hub/Connectivity → nasce na Root, MOVER para a OU Infrastructure
⑥ Aplicar SCPs baseline na Organization/OUs
⑦ IAM Identity Center (SSO) — permission sets por conta, sem usar root
⑧ Por projeto: create-account em NonProd → validar → só então Production
⑨ Dentro da conta do projeto: provisionar a(s) spoke(s) de rede
```

Notas:
- **③ antes de ④** — sem CloudTrail desde o início, perde-se o rastro do bootstrap.
- **⑤ e ⑧:** `create-account` **não** aceita OU de destino. A conta nasce na Root e
  é movida depois — dois passos, e o SCP da OU não vale na janela entre eles.
- **⑥:** SCP não afeta a conta de gerência. Por isso ela não hospeda nada.

**[DECIDIDO]** No ⑧: uma conta por projeto **por ambiente** (`<projeto>-nonprod` +
`<projeto>-prod`) — a conta é o único limite forte de quota, SCP, IAM e billing.

> **Esta Fase −1 já foi executada.** A sequência autoritativa, com o que foi de fato
> aplicado e os gotchas de API descobertos, vive em `aws/docs/accounts/CLAUDE.md`. O bloco
> acima é o desenho original; onde divergir, a doc do domínio ganha. Duas diferenças já
> conhecidas: os nomes de OU seguem o whitepaper (`Infrastructure`/`NonProd`, não
> `Infra`/`Sandbox`), e as OUs foram criadas **antes** da conta `log-archive`, não depois.

### Fase 0 — Fundação (Terraform, um state, uma vez)
1. Organization, OUs, SCPs (fase acima)
2. Accounts: `network`, `security/log-archive`, `platform`
3. **IPAM** com escopo global e pools por região — declarar os locales previstos agora
4. Hosted zone pública `wasp.silvios.me` (global, na account `platform`)
5. Bucket de state + roles OIDC para CI

### Fase 1 — Âncoras globais vazias
6. **Global Accelerator + listener TCP 443, sem endpoint group** → colhe os 2 IPs
   estáticos anycast. Esse é o artefato que cliente coloca em allowlist e que se
   publica no DNS; quanto antes existir, menos coisa fica bloqueada esperando.
7. Tabela do tenant registry (DynamoDB) — nasce em uma região, vira Global Table
   quando a segunda subir.

### Fase 2 — Primeira região (módulo `regional-hub`)
8. Alocação IPAM da região
9. Hub VPC na account `network`: TGW, egress/NAT, slot do Network Firewall
10. Zona delegada `<região>.wasp.silvios.me` — o registro NS na zona pai é criado
    **pela própria região**, via role cross-account
11. ACM wildcard `*.<região>.wasp.silvios.me` via DNS-01 (depende do 10)
12. Spoke de plataforma: VPC, EKS, ArgoCD + Crossplane instalados finos pelo Terraform
13. NLB/ALB do cluster de plataforma → **a região cria seu próprio endpoint group** no GA

### Fase 3 — Segunda região
Mesmo módulo, input diferente. Adiciona réplica do Global Table e seu endpoint group.

### Fase 4 — TGW inter-region peering
Só existe com duas regiões. É request/accept, precisa de camada própria e regra de
ordem determinística (ex.: a região de nome lexicograficamente menor faz o request).

### Fase 5 — Spokes / células
Via Crossplane do hub regional.

### Princípio que evita gargalo
**A camada global cria só a âncora vazia; cada região se registra nela.** Endpoint
group, registro NS, réplica do Global Table — criados pelo módulo regional,
referenciando o ARN da âncora por remote state.

Exceções inevitáveis (isolar numa camada `inter-region` explícita): peering do TGW
(par simétrico) e a conversão da primeira tabela em Global Table.

---

## 9. A segunda região é um teste, não uma expansão

**Teste objetivo:** rodar o mesmo módulo com input diferente e **zero linha de código
alterada**. Se precisou editar, achou acoplamento.

O que costuma cair:
- **AZ hardcoded** — usar `data.aws_availability_zones` e contar, nunca listar.
- **us-east-1 é anômala** — ACM para CloudFront só existe lá, algumas APIs globais só
  respondem lá. Construir a primeira região lá codifica exceções como se fossem regra.
- **Paridade de serviço** — sa-east-1 não tem tudo que us-east-1 tem, e recebe depois.
- **Cotas são por região e por conta** — EIP, vCPU, VPC. Conta nova nasce no default.
- **IPAM locale** precisa existir antes da alocação, não junto.

Escolher a segunda região **deliberadamente diferente**, não gêmea. `sa-east-1` é boa
adversária (menos AZs úteis, paridade menor, latência real para testar o discovery);
`eu-central-1` traz o eixo de soberania. **Uma das duas, não as duas.**

**Duas regiões provam portabilidade. A terceira não prova mais nada e só custa.**

### Ciclo de vida da região de teste
Uma região de plataforma ociosa custa ~US$ 150–250/mês (control plane EKS, NAT por
AZ, attachment de TGW, endpoint do GA). Então: **provisiona, valida, destrói,
reprovisiona.** O ciclo completo é o que expõe o teardown (ordem inversa, zona não-
vazia, órfão de attachment).

Vira fitness function do **Good Citizen Test**: *"segunda região do zero ao verde em
N minutos, sem intervenção manual"*. Verde = discovery enxerga a região, TLS válido,
ArgoCD sincronizado, Crossplane com provider pronto.

---

## 10. Custos que dominam cedo

| Item | Ordem de grandeza | Observação |
|---|---|---|
| AWS Network Firewall | ~US$ 290/mês por endpoint (1 por AZ) | 2 regiões × 2 AZ ≈ US$ 1.2k/mês antes de qualquer pacote |
| Região de plataforma ociosa | US$ 150–250/mês | Motivo do ciclo provisiona/destrói |
| Control plane EKS | ~US$ 73/mês por cluster | Relevante quando a contagem de células cresce |
| Route 53 Resolver endpoints | 2 ENIs por spoke, cobradas por hora | Com spoke efêmera vira custo fixo relevante |

**Alternativa aos resolver endpoints (avaliada para PoC):** EKS em `public + private`
com allowlist de CIDR, VPN em full tunnel saindo pelo NAT do hub → allowlista um
único EIP em todos os clusters, DNS resolve publicamente, elimina os resolver
endpoints. Menos "puro", controle de acesso continua real, escala sem custo marginal
por spoke.

---

## 11. Decisões em aberto (consolidado)

| # | Decisão | Impacto |
|---|---|---|
| 1 | Schema do registry de tenants | Destrava a indireção; menor esforço, maior alcance |
| 2 | Onde o discovery roda (Lambda@Edge vs. plataforma regional) | Disponibilidade da dependência global crítica |
| 3 | Conta por projeto por ambiente, ou uma por projeto | Estrutura de OU e SCP |
| 4 | Segunda região: `sa-east-1` ou `eu-central-1` | Qual eixo se testa primeiro (paridade vs. soberania) |
| 5 | Hub regional é durável (anos) ou descartável (recriável em 1h) | Define se é Terraform imutável ou precisa de Day-2 |
| 6 | Escopo do identity layer: global ou por célula | Define se o hub regional é falha comum da região |
| 7 | Egress/inspection: centralizado no hub ou distribuído por célula | Custo do Network Firewall × isolamento |
| 8 | Sizing de célula (quantos tenants cabem) | Requer medição, não estimativa |
| 9 | Cloud WAN vs. malha de TGW — a partir de quantas regiões | Só relevante além de ~3 regiões |
| 10 | Contrato de input/output do módulo `regional-hub` | Se for pequeno, a portabilidade se resolve sozinha |

### Sobre a decisão 6
Se `auth` roda no cluster de plataforma e está no **caminho da requisição**, o hub
regional vira falha comum: a célula deixa de ser o cluster e passa a ser a região.
Escolha legítima — mas então o raio de impacto de qualquer upgrade é regional, e não
se deve chamar cluster de célula. Alternativa: auth por célula (mais caro, mais chato
de operar).

---

## 12. Referências AWS

- **[REL02-BP04](https://docs.aws.amazon.com/wellarchitected/latest/reliability-pillar/rel_planning_network_topology_prefer_hub_and_spoke.html)** (Well-Architected, Reliability) — preferência por hub-and-spoke.
  Sem diagramas.
- **Whitepaper "Building a Scalable and Secure Multi-VPC AWS Network
  Infrastructure"** — referência canônica da topologia.
- **"Organizing Your AWS Environment Using Multiple Accounts"** — estrutura de OU.
- **"Network Orchestration for AWS Transit Gateway"** — solução de referência.

---

## 13. Contexto de repositório

- `github.com/smsilva/wasp-idp` — frente de infra AWS. Branch
  `feat/aws-hub-bootstrap-network`, diretório `aws/`. Docs de accounts em
  `aws/docs/accounts/`.
- `github.com/smsilva/kubernetes` — origem do aws-saas-platform.
- Microserviços FastAPI da plataforma: `discovery`, `platform-frontend`,
  `callback-handler`.
- Stack já em uso: EKS, Istio, ALB, WAF, Cognito, DynamoDB, Global Accelerator,
  ArgoCD, external-secrets, external-dns, cert-manager.
- XRD de ambiente: `Environment.wasp.silvios.me/v1`.
- Domínio base: `wasp.silvios.me` (delegado de Azure DNS para Route 53 em parte do
  desenho atual).

### Convergência pendente
O desenho de DNS por ambiente (`xpto21.wasp.silvios.me`, hosted zone delegada por
ambiente, decisão da PoC de Environment) e o desenho de DNS regional
(`<região>.wasp.silvios.me` + `customer1.wasp.silvios.me`) ainda não foram
reconciliados num único esquema de nomes. **Vale fazer isso antes de escrever o
módulo `regional-hub`.**
