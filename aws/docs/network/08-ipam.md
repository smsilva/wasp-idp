# 08 — IP Address Manager

**Pilar WAF principal:** Reliability
([REL02-BP05 — Enforce non-overlapping private IP address ranges in all private address spaces where they are connected](https://docs.aws.amazon.com/wellarchitected/latest/reliability-pillar/rel_planning_network_topology_non_overlap_ip.html)).

> **Nada aqui está implementado.** Este arquivo registra o desenho de IPAM hierárquico e o
> critério de quando adotá-lo. O plano vigente continua sendo o octeto calculado em
> [`01-cidr-addressing.md`](01-cidr-addressing.md). O que muda com este registro é que a decisão
> passa a ter forma concreta em vez de ser uma linha numa tabela de alternativas.

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
   desenho deste repo, a conta `network` (Connectivity Account), não a management.
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

| | Free Tier | Advanced Tier |
|---|---|---|
| Locale dos pools | **só a home region do IPAM** | qualquer operating region |
| Cobrança | sem custo de IPAM | **por IP ativo por hora** (conferir na página de preços da VPC) |
| Prefix list resolver, integrações | não | sim |

**O corte de locale é o que decide.** Este repo já tem hub em `us-east-1` e `us-west-2` — duas
regiões — logo o Free Tier não atende ao desenho multi-região; ele atenderia a uma prova de
conceito de uma região só. E a cobrança do Advanced é **por IP ativo**, não por pool ou por VPC:
o custo escala com o tamanho da frota, o que o torna barato num ambiente de PoC e não-trivial num
ambiente com muitos nós.

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

## Well-Architected — porquê

| Best practice | Como se relaciona |
|---|---|
| **[REL02-BP05 — Enforce non-overlapping private IP address ranges in all private address spaces where they are connected](https://docs.aws.amazon.com/wellarchitected/latest/reliability-pillar/rel_planning_network_topology_non_overlap_ip.html)** | recomenda IPAM nominalmente; a tabela manual é o anti-pattern que a BP cita. **Gap consciente**, com os gatilhos acima como plano |
| **[REL02-BP03 — Ensure IP subnet allocation accounts for expansion and availability](https://docs.aws.amazon.com/wellarchitected/latest/reliability-pillar/rel_planning_network_topology_ip_subnet_allocation.html)** | regras de netmask por pool tornam "tamanho por finalidade" mecanismo em vez de convenção |
| **[SEC05-BP01 — Create network layers](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/sec_network_protection_create_layers.html)** | escopo separado = espaço roteável e espaço isolado deixam de ser distinção informal |

## Próximo

→ Volta ao índice do domínio: [`CLAUDE.md`](CLAUDE.md). Para o plano de endereçamento vigente
(octeto calculado), [`01-cidr-addressing.md`](01-cidr-addressing.md); para o teto que motiva a
discussão, [`../tenancy/03-cidr.md`](../tenancy/03-cidr.md).
