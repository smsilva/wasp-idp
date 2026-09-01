# 08 — IP Address Manager

**Pilar WAF principal:** Reliability
([REL02-BP05 — Enforce non-overlapping private IP address ranges in all private address spaces where they are connected](https://docs.aws.amazon.com/wellarchitected/latest/reliability-pillar/rel_planning_network_topology_non_overlap_ip.html)).

> **Nada aqui está aplicado numa conta.** Este arquivo registra o desenho de IPAM hierárquico e o
> critério de quando adotá-lo. O plano vigente continua sendo o octeto calculado em
> [`01-cidr-addressing.md`](01-cidr-addressing.md).
>
> **Decisão tomada em 2026-09-01 (issue #15):** adiar a adoção, com gatilhos declarados —
> [ADR 0015](../../../docs/adr/0015-defer-ipam-adoption.md). Um **modelo mínimo executável** que
> prova o desenho ponta a ponta vive em `aws/terraform/spikes/ipam/`: código versionado, aplicado
> uma vez para produzir evidência, e destruído. Os fatos deste arquivo foram reconferidos contra a
> doc oficial nessa passagem, e **duas afirmações estavam erradas** — ver os avisos de correção nas
> seções de tier e de `auto_import`.

## Por que isto deixou de ser opcional na argumentação

A tabela de alocação de CIDR deste repo — quem tem qual `/16` — é mantida à mão, num arquivo
markdown. REL02-BP05 lista **"relying on manual IP address management processes, such as
spreadsheets"** entre os *common anti-patterns*, e a implementation guidance da mesma best
practice abre com **"make use of an IPAM, such as the Amazon VPC IP Address Manager"**.

Ou seja: a tabela manual não é um atalho neutro que se troca por IPAM quando der vontade — é um
anti-pattern nomeado. O que sustenta mantê-la hoje é **timing**, não mérito (ver
`../../../decisions.md` §7, "IPAM cedo" como armadilha conhecida). A distinção importa porque
muda o que se está decidindo: não é *se*, é *quando*.

## O modelo: escopo → pool top-level → pool regional → pool por finalidade

IPAM não é um registro de CIDRs. É uma **árvore de delegação de espaço**, e cada nível existe
para responder a uma pergunta diferente.

```text
IPAM (criado numa região "home", com operating regions declaradas)
│
├── Escopo PRIVADO (default)            ← o espaço roteável: 10.0.0.0/12 hoje
│   └── Pool top-level  10.0.0.0/12     ← sem locale: é só contêiner, não aloca a recurso
│       ├── Pool regional us-east-1     ← locale: us-east-1  (imutável)
│       │   ├── Pool "hub"              ← regra: só /16, tag role=hub
│       │   └── Pool "spoke"            ← regra: /16..../22, tag obrigatória tenant=<id>
│       │       └── alocação → VPC da spoke A
│       └── Pool regional us-west-2     ← locale: us-west-2
│
├── Escopo PRIVADO ADICIONAL (criado por nós)  ← o espaço NÃO roteável
│   └── Pool "tenant isolado" 172.16.0.0/12    ← repetido de propósito entre tenants
│
└── Escopo PÚBLICO (default)            ← BYOIP / EIP; não usamos
```

### Escopo — a peça que resolve o CIDR repetido

Da doc: *"scopes enable you to reuse IP addresses across multiple unconnected networks without
causing IP address overlap or conflict."*

Isto é exatamente a saída que [`../tenancy/03-cidr.md`](../tenancy/03-cidr.md) defende para spoke
de tenant isolado — e o IPAM tem uma primitiva de primeira classe para ela. **Sem IPAM, "CIDR
repetido" é uma convenção que vive na cabeça de quem aloca; com IPAM, é um escopo separado, e a
ferramenta para de acusar sobreposição porque sabe que aquelas redes não se falam.** É o
argumento mais forte a favor do IPAM neste desenho, e não tem a ver com escala.

### Pool top-level e regional — e o `locale`

- **Pool top-level não tem locale.** Ele só segura o bloco e o subdivide. Não se aloca VPC dele.
- **Pool regional tem `locale`, e o locale é IMUTÁVEL.** Só se aloca CIDR para uma VPC a partir de
  um pool cujo locale casa com a região da VPC. É o que impede que um erro de região vire um CIDR
  fora do lugar — a mesma classe de erro que hoje é evitada por "uma raiz Terraform por região"
  em `../../terraform/README.md`.
- Pool com locale diferente da home region do IPAM **continua alocando durante uma indisponibilidade
  da home region**. Isso é propriedade de disponibilidade, não conveniência.
- Profundidade máxima da hierarquia: **10 níveis** por default.

> **Pegadinha registrada na própria doc da AWS:** *"the allocation rules for the Regional pool are
> **not inherited** from the top-level pool. If you do not apply any rules here, there will be no
> allocation rules set for the pool."* Regra definida no topo e esquecida no filho = pool filho
> sem nenhuma regra. Não é herança, é repetição.

### Regras de alocação — onde a política vira mecanismo

Cada pool aceita restrições que o IPAM aplica **na hora de alocar**:

| Regra | Efeito |
|---|---|
| `allocation_min_netmask_length` / `max` | piso e teto do tamanho do bloco (ex.: nada menor que `/24`, nada maior que `/16`) |
| `allocation_default_netmask_length` | o que sai quando o chamador não pede tamanho |
| `allocation_resource_tags` | **só aloca para recurso que tenha a tag exigida** (ex.: `tenant=<id>`) |
| `auto_import` | adota CIDRs pré-existentes que caiam no espaço do pool |

A terceira é a mais subestimada: ela transforma "cada tenant tem seu bloco" de convenção em
**condição de alocação**. Um `terraform apply` que esqueça a tag não pega um bloco errado — ele
falha.

> **Regra definida no pai não vale para recurso do filho:** *"Allocation rules apply only to the
> managed resources within that pool. The rules do not apply to resources in pools within a pool."*
> Junto com a pegadinha de não-herança acima, isso significa que a política tem de ser escrita no
> pool que **aloca**, não no que contém.

#### `auto_import`: quatro comportamentos que a doc nomeia e que mudam o desenho

Levantados de [`create-top-ipam.html`](https://docs.aws.amazon.com/vpc/latest/ipam/create-top-ipam.html):

1. **Não está disponível se o `Locale` é `None`** — ou seja, só no pool **regional**, nunca no
   top-level. Isso amarra quem adota: é o pool regional que importa as VPCs existentes.
2. Importa **independentemente de compliance** — o recurso entra e pode aparecer como
   `noncompliant` logo depois.
3. Em sobreposição, importa **só o maior CIDR**; com CIDRs idênticos, importa **um aleatoriamente**.
4. Uma VPC **não** pode ser auto-importada se sobrepõe uma alocação que já existe no pool.

**`auto_import` e alocação explícita não são alternativas — são complementares.** O
`aws_vpc_ipam_pool_cidr_allocation` "reserva um CIDR, prevenindo uso pelo IPAM": ele **bloqueia o
espaço**, mas não vincula VPC alguma ao pool. Quem cria o vínculo rastreável (a VPC aparecer como
alocação, com estado de compliance) é `auto_import`, ou criar a VPC já com `ipv4_ipam_pool_id`.
Logo: `auto_import` para adotar VPC existente; allocation explícita para espaço reservado que **não
tem recurso** (o `10.0.0.0/16` da Organization).

### Como o consumo acontece

Não se escolhe mais o CIDR; **pede-se um tamanho**. No Terraform:

```hcl
resource "aws_vpc" "spoke" {
  ipv4_ipam_pool_id   = var.spoke_pool_id
  ipv4_netmask_length = 22          # em vez de cidr_block = "10.2.0.0/16"
}
```

Consequência direta para este repo: **`vpcCidrSecondOctet` e as validações de supernet deixam de
existir**. O XRD `Network`, as validações de `vpc_cidr` nas camadas 2 e 3, o teste de regex de
supernet — tudo isso é reimplementação artesanal do que o pool faz. É simplificação, não camada
extra.

### Multi-conta: delegated admin + RAM

1. Integrar o IPAM com a Organization e **delegar uma conta membro como IPAM admin** — pelo
   desenho deste repo, a conta `network` (Connectivity Account), não a management. **Isso não é
   preferência de desenho, é regra do serviço:**
   [`enable-integ-ipam.html`](https://docs.aws.amazon.com/vpc/latest/ipam/enable-integ-ipam.html) —
   *"The IPAM account must be an AWS Organizations member account. You cannot use the AWS
   Organizations management account as the IPAM account."* O pattern oficial da AWS
   ([multi-Region IPAM com Terraform](https://docs.aws.amazon.com/prescriptive-guidance/latest/patterns/multi-region-ipam-architecture.html))
   assume o mesmo: *"a network hub or network management account that will serve as the IPAM
   delegated administrator"*. Habilitar tem de ser feito por `enable-ipam-organization-admin-account`
   (ou pelo console do IPAM) — fazê-lo pelo console/CLI do **Organizations** não cria a
   service-linked role `AWSServiceRoleForIPAM`, e sem ela o IPAM não monitora nada.
2. **Compartilhar o pool por RAM** com a OU ou com as contas de spoke. A permissão do RAM é
   granular: alocar CIDR do pool ≠ administrar o pool.
3. A conta da spoke passa a alocar do pool compartilhado **sem** poder ver ou alterar o plano.

O RAM já está ligado a nível de Organization neste repo (`aws_ram_sharing_with_organization`, em
`../../terraform/dns/`, registrado em `../../terraform/CLAUDE.md`) — o pré-requisito mais chato
já está pago.

### Descoberta e conformidade — o que a tabela manual nunca dá

- **Resource discovery** varre as contas e mostra CIDRs em uso que **ninguém registrou**. A tabela
  markdown só sabe o que alguém lembrou de escrever nela.
- **Estado de conformidade por alocação**: um CIDR que viola a regra do pool aparece como
  *noncompliant* em vez de simplesmente existir.
- **Métricas CloudWatch por pool** (utilização) com alarme — "o pool de spokes passou de 80%"
  vira alerta, não descoberta no `apply` que falha.
- **Histórico de atribuição** de um CIDR ao longo do tempo: quem teve `10.2.0.0/16` antes do
  `cicd`? Hoje isso só existe no git log do `HANDOFF.md`, por acidente.

### IPAM prefix list resolver (Advanced)

Mantém **prefix lists** sincronizadas com CIDRs vindos do IPAM, e prefix list é o que se referencia
em route table e security group. Vale registrar porque ataca um problema que este repo já tem
nomeado: hoje a rota do supernet e as regras de SG carregam CIDR literal, e ampliar ou mover um
bloco significa caçar todos os lugares onde ele foi escrito à mão.

## Free Tier vs. Advanced Tier — o corte que importa

> **Corrigido em 2026-09-01 (issue #15).** Este trecho dizia que o corte era o *locale* dos pools e
> que o Free Tier "atenderia a uma prova de conceito de uma região só". **É falso.** Pool no escopo
> privado é recurso de Advanced Tier, independentemente de quantas regiões — não existe recorte
> Free Tier para este desenho.

| | Free Tier | Advanced Tier |
|---|---|---|
| Pools no **escopo privado** (IPv4 privado) | **não** | sim |
| Escopo privado adicional (não-default) | **não** | sim |
| Pools com locale ≠ home region | **não** | sim |
| Alocação para conta que não é o IPAM owner (RAM) | **não** | sim |
| Features através de operating regions | só **Public IP insights** | todas |
| Prefix list resolver, IP history, integrações | não | sim |
| Cobrança | sem custo | **US$ 0,00027 por IP ativo/hora ≈ US$ 0,197/mês por IP** |

Três fontes oficiais convergem, e vale citar porque é o fato que decide:

- [`create-ipam.html`](https://docs.aws.amazon.com/vpc/latest/ipam/create-ipam.html): *"If you are
  creating an IPAM in the Free Tier, you can select multiple operating Regions […] but the only IPAM
  feature that will be available across operating Regions is Public IP insights."*
- [`mod-ipam-tier.html`](https://docs.aws.amazon.com/vpc/latest/ipam/mod-ipam-tier.html) — para
  **voltar** de Advanced a Free é preciso apagar *private scope pools*, escopos privados
  não-default, pools com locale diferente da home region, e alocações para contas que não sejam o
  IPAM owner. Essa lista é a definição invertida do que só existe no Advanced.
- Tabela da **IPAM** na [página de preços da VPC](https://aws.amazon.com/vpc/pricing/): *Private
  IPv4 management* e *Share IPAM pools with AWS accounts* ambos ausentes do Free Tier.

O caso deste repo (IPv4 privado + multi-conta + multi-região) cai em Advanced por **três motivos
independentes**. Não há decisão a tomar sobre tier: há uma conta a pagar.

### Quanto custa, medido nesta conta

A cobrança é por **IP ativo** — *"an IP address or a prefix associated with an Elastic Network
Interface (ENI) that is attached to a resource"* — não por pool, VPC ou alocação. Medição real de
2026-09-01 (`describe-network-interfaces` nas 4 contas × 2 regiões, com só `module.hub` de pé):

| Cenário | IPs ativos | Custo/mês |
|---|---|---|
| Só o hub de `us-east-1` de pé | **7** (medido) | **US$ 1,38** |
| Hub + célula de pé | ~40 (estimado) | ~US$ 8 |
| 10 células × 2 regiões | ~340 (estimado) | ~US$ 67 |

A estimativa da célula é dominada pelo **VPC CNI**: cada nó mantém ENIs com IPs secundários
pré-alocados (~12 por `t3.medium` no `WARM_ENI_TARGET` default), então o custo do IPAM escala com a
frota de pods, não com o número de VPCs. É a razão de o número ficar não-trivial num cluster grande
e desprezível numa PoC.

Duas letras miúdas que mudam a conta:

- Integrado à Organization, o IPAM **cobra por IP ativo que monitora em todas as contas membro**,
  não só nas que alocam de pool. Mitigável por
  [OU exclusion](https://docs.aws.amazon.com/vpc/latest/ipam/exclude-ous.html) — excluir a OU
  `Sandbox`, por exemplo. O delegated admin nunca é excluído, mesmo dentro de OU excluída.
- O *metering mode* `resource-owner`
  ([cost distribution](https://docs.aws.amazon.com/vpc/latest/ipam/ipam-enable-cost-distro.html))
  **redistribui** a cobrança para a conta dona do IP, não reduz — e trava por 7 dias depois de
  habilitado (24h para desistir).

## Quando adotar — gatilhos, não calendário

Adotar por antecipação é a armadilha que `decisions.md` §7 registra. Os gatilhos concretos:

| Gatilho | Por quê |
|---|---|
| **Decidir por "CIDR repetido para tenant isolado"** | é o escopo adicional do IPAM; fazer isso à mão é manter duas contabilidades paralelas |
| Terceira região entrar | a tabela manual passa a ter um eixo que ela não representa bem |
| Passar de ~20 blocos alocados | é o ponto em que "quem tem qual bloco" deixa de caber na cabeça de uma pessoa |
| Onboarding de tenant virar automatizado | alocação por API é pré-requisito; escolher octeto à mão não automatiza |
| Um CIDR alocado fora do plano ser descoberto | o resource discovery deixa de ser luxo |

Nenhum deles disparou. **O primeiro é o mais provável**, porque depende de uma decisão de desenho
já em aberto (decisão 2 de [`../tenancy/CLAUDE.md`](../tenancy/CLAUDE.md)), não de crescimento.

## Custo de migrar depois

Baixo, e vale dizer por quê — é o que sustenta adiar sem culpa:

- `auto_import` **adota** CIDRs existentes que caiam no espaço do pool. VPC já criada não precisa
  ser recriada para entrar no IPAM.
- A migração é de **processo de alocação**, não de endereço. Nada é re-endereçado.
- O que se joga fora é código: as validações de supernet e o `vpcCidrSecondOctet`. Perder código
  que o serviço faz melhor é ganho.

Isso é o oposto do CIDR em si, que é irreversível. **Adiar IPAM é barato; adiar a decisão de
supernet não era.**

> **Uma parte NÃO é barata de adiar, e foi paga em 2026-09-01:** o pool regional exige `locale`, e
> **locale é imutável**. Um plano de endereçamento que aloque por ordem de criação, e não por
> região, não tem bloco contíguo por região — e aí a adoção do IPAM passa a exigir re-endereçar VPC,
> que é justamente o que a adoção deveria evitar. Foi o caso aqui: `us-west-2` estava em
> `10.3`/`10.4`, com o `10.3` dentro do `/14` de `us-east-1`. Corrigido para `10.4`/`10.5` enquanto
> a raiz tinha zero recursos. **Agrupar por região é pré-requisito de adiar com segurança**, não
> parte da adoção.

## Well-Architected — porquê

| Best practice | Como se relaciona |
|---|---|
| **[REL02-BP05 — Enforce non-overlapping private IP address ranges in all private address spaces where they are connected](https://docs.aws.amazon.com/wellarchitected/latest/reliability-pillar/rel_planning_network_topology_non_overlap_ip.html)** | recomenda IPAM nominalmente; a tabela manual é o anti-pattern que a BP cita. **Gap consciente**, com os gatilhos acima como plano. A BP declara *level of risk* **Medium** — dado que calibra a urgência: não é High, e é por isso que adiar com gatilhos é resposta legítima em vez de dívida aceita no escuro |
| **[REL02-BP03 — Ensure IP subnet allocation accounts for expansion and availability](https://docs.aws.amazon.com/wellarchitected/latest/reliability-pillar/rel_planning_network_topology_ip_subnet_allocation.html)** | regras de netmask por pool tornam "tamanho por finalidade" mecanismo em vez de convenção |
| **[SEC05-BP01 — Create network layers](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/sec_network_protection_create_layers.html)** | escopo separado = espaço roteável e espaço isolado deixam de ser distinção informal |

## Próximo

→ Volta ao índice do domínio: [`CLAUDE.md`](CLAUDE.md). Para o plano de endereçamento vigente
(octeto calculado), [`01-cidr-addressing.md`](01-cidr-addressing.md); para o teto que motiva a
discussão, [`../tenancy/03-cidr.md`](../tenancy/03-cidr.md).
