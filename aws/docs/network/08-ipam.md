# 08 — IP Address Manager

**Pilar WAF principal:** Reliability
([REL02-BP05 — Enforce non-overlapping private IP address ranges in all private address spaces where they are connected](https://docs.aws.amazon.com/wellarchitected/latest/reliability-pillar/rel_planning_network_topology_non_overlap_ip.html)).

> **Decisão: adiar a adoção.** Tomada em 2026-09-01, issue #15, registrada na
> [ADR 0015](../../../docs/adr/0015-defer-ipam-adoption.md). O plano vigente continua sendo o octeto
> calculado em [`01-cidr-addressing.md`](01-cidr-addressing.md).
>
> **Este documento não é teoria.** O desenho foi aplicado numa conta real duas vezes — uma em
> `us-east-1` (com VPC existente) e uma em `us-west-2` (sem) — e destruído. Os números, tempos e
> falhas abaixo são medidos. O código está em `aws/terraform/spikes/ipam/`, com as provas e seus
> resultados no README de lá.
>
> **Duas afirmações da versão anterior deste arquivo estavam erradas** e foram corrigidas: o corte
> Free/Advanced e o papel do `auto_import`. Ambas faziam o IPAM parecer mais barato e mais simples
> do que é.

## Resumo

O que o IPAM faz: você para de escolher o CIDR e passa a pedir um tamanho. O serviço devolve um
bloco livre e mantém o registro de quem tem o quê, através de contas e regiões.

Por que ainda não adotamos:

- Nenhum dos cinco gatilhos abaixo disparou. São 4 blocos alocados de 15 possíveis.
- Custaria US$ 1,38/mês hoje. Barato, mas o valor entregue com 4 blocos é quase nulo.
- REL02-BP05 classifica o risco de não ter IPAM como **Medium**, não High.

O argumento contra adiar, que é real e está registrado: **o custo de adotar sobe em degrau, não em
rampa.** Ele salta no instante em que a primeira VPC nasce fora do pool. Hoje são 2 VPCs a adotar em
`us-east-1` e nenhuma em `us-west-2` — o menor volume que este repo jamais terá.

## O que foi medido

### Tempos

Números de aplicar e destruir o desenho completo. Importam porque uma VPC alocada por IPAM não se
comporta como uma VPC comum, e o desvio é grande o bastante para quebrar orçamento de janela de
manutenção e teto de tempo de CI.

| Operação | Tempo |
|---|---|
| Criar IPAM, escopo, 3 pools, 3 CIDRs de pool, RAM share | **segundos** (o apply inteiro, sem a VPC, fecha em ~1 min) |
| **Criar** uma VPC com `ipv4_ipam_pool_id` | **4m22s** |
| **Destruir** a mesma VPC | **18m29s** e **27m29s** em duas medições — varia muito; orçar pelo pior caso |
| Destruir todo o resto (IPAM, pools, RAM, delegação) | **~1 min somados** |
| Delegar/remover o IPAM admin da Organization | 1–2 s |

Três consequências práticas:

1. **A VPC domina o tempo, e por larga margem.** 18m29s contra ~1 min de todo o resto. Ao orçar um
   apply ou destroy, o número que conta é o de VPCs, não o de recursos.
2. **A VPC desaparece da AWS muito antes de o Terraform seguir em frente.** Durante o destroy,
   `describe-vpcs` já devolvia `InvalidVpcID.NotFound` enquanto o log ainda dizia
   `Still destroying...`. O provider está esperando a **desalocação no IPAM**, que é assíncrona.
   Parece travado e não está.
3. **Nunca rodar esses comandos de forma síncrona.** Use
   `nohup <comando> > log 2>&1 < /dev/null & disown`. Ao diagnosticar um que pareça parado, conferir
   `pgrep -af terraform` **sem truncar a saída** — um `| head -3` escondeu o processo vivo nesta
   sessão e produziu um diagnóstico errado.

**O que exatamente está lento, verificado durante o destroy:** a VPC já não existe
(`describe-vpcs` → `InvalidVpcID.NotFound`), mas `get-ipam-pool-allocations` ainda lista a alocação
apontando para o id da VPC morta. O Terraform espera o IPAM **reciclar uma alocação órfã**.

Isso tem uma consequência que não é óbvia: **durante esses ~18 minutos o bloco fica retido no pool,
sem nenhuma VPC usando.** Numa recriação rápida — destroy seguido de apply — a VPC nova recebe um
bloco **diferente**, porque o antigo ainda está reservado.

> **CIDR alocado por IPAM não é estável entre recriações.** Com CIDR literal no código, recriar uma
> VPC devolve sempre o mesmo bloco. Com IPAM, não. Qualquer coisa que dependa do endereço — regra de
> security group escrita à mão, rota estática, allowlist de terceiro, peer externo — passa a ser
> frágil. É mais um argumento a favor do *prefix list resolver* (abaixo): referenciar prefix list
> em vez de CIDR literal deixa de ser conveniência e vira requisito.

### Custo

A cobrança do Advanced Tier é por **IP ativo**: *"an IP address or a prefix associated with an
Elastic Network Interface (ENI) that is attached to a resource"*. Não é por pool, VPC ou alocação.

**US$ 0,00027 por IP ativo/hora = US$ 0,197/mês por IP.**

Medição de 2026-09-01 (`describe-network-interfaces` nas 4 contas × 2 regiões, com só `module.hub`
de pé):

| Cenário | IPs ativos | Custo/mês |
|---|---|---|
| Só o hub de `us-east-1` | **7** (medido) | **US$ 1,38** |
| Hub + célula | ~40 (estimado) | ~US$ 8 |
| 10 células × 2 regiões | ~340 (estimado) | ~US$ 67 |

**O custo escala com pods, não com VPCs.** O VPC CNI pré-aloca IPs secundários por nó (~12 num
`t3.medium` com `WARM_ENI_TARGET` default), e cada um conta. É por isso que o número é desprezível
numa PoC e não-trivial num cluster grande.

Duas letras miúdas:

- Integrado à Organization, o IPAM cobra por IP ativo **em todas as contas membro que monitora**,
  não só nas que alocam de pool. Reduzir exige
  [excluir OUs](https://docs.aws.amazon.com/vpc/latest/ipam/exclude-ous.html). O delegated admin
  nunca é excluído, mesmo dentro de uma OU excluída.
- O *metering mode* `resource-owner`
  ([cost distribution](https://docs.aws.amazon.com/vpc/latest/ipam/ipam-enable-cost-distro.html))
  **redistribui** a cobrança para a conta dona do IP. Não reduz. E trava por 7 dias depois de
  habilitado (24h para desistir).

### O defeito encontrado: o IPAM entregou um CIDR já em uso

Este é o achado principal, e não estava em nenhuma documentação.

Em `us-east-1`, com a VPC hub `10.1.0.0/16` **de pé**, o pool devolveu **`10.1.0.0/24`** para uma
VPC nova em outra conta. Duas VPCs sobrepostas, em contas que se falam pelo TGW. Exatamente a
colisão que o IPAM existe para impedir.

**Causa:** `auto_import` é assíncrono e a alocação não espera por ele. O Terraform criou o pool e
pediu o CIDR segundos depois. Nenhuma VPC existente tinha sido importada, então o pool via
`10.0.0.0/14` inteiro como livre.

Não foi falha de descoberta. `get-ipam-discovered-resource-cidrs` já listava 14 recursos, incluindo
a VPC hub e suas 4 subnets. **Descoberto e alocado são estados diferentes, e só o segundo reserva
espaço.** Quinze minutos depois, o `/16` continuava não importado.

**E o dano se fixa.** Pela regra da AWS, uma VPC cujo CIDR *cobre* uma alocação existente não pode
mais ser auto-importada. A alocação `/24` prematura tornou a adoção do `/16` impossível. Uma
alocação antes da hora **envenena o pool**.

### O mesmo código em região vazia: limpo

Repetido em `us-west-2`, onde nenhuma VPC nossa existe:

| | `us-east-1` (com VPC existente) | `us-west-2` (região vazia) |
|---|---|---|
| CIDR devolvido | `10.1.0.0/24` | `10.4.0.0/24` |
| Já estava em uso? | **sim**, sob `10.1.0.0/16` | não |
| Adoção do legado | falhou; pool envenenado | não se aplica |
| Alocações no pool ao fim | 1 (a colidente) | 1 (correta) |

**O defeito é da migração, não do serviço.** Quando o IPAM entra antes da primeira VPC, ele funciona
como anunciado. Quando entra depois, a janela entre "pool criado" e "legado importado" é perigosa.

As VPCs default (`172.31.0.0/16`) apareceram no inventário nas duas rodadas e ficaram fora dos
pools, como esperado — estão fora do supernet. São assunto da issue #67.

### O que criar um IPAM não quebra

`terraform plan -target=module.hub` em `regions/us-east-1/` durante o spike:
`0 to add, 1 to change, 0 to destroy` — e a única mudança era drift pré-existente e já conhecido
(`aws_iam_saml_provider.client_vpn`).

Criar IPAM, pools e alocações sobre uma árvore Terraform viva **não a perturba**. Nenhuma VPC foi
recriada. O critério "adoção, não realocação" se sustenta; o que falha é o *timing*.

## Como adotar, quando chegar a hora

**Nunca num `terraform apply` só.** A sequência abaixo existe por causa do defeito acima.

1. **Criar IPAM e pools, sem nada que aloque.** Nenhum `aws_vpc` com `ipv4_ipam_pool_id`, nenhuma
   alocação dinâmica.
2. **Reservar cada bloco legado** com `aws_vpc_ipam_pool_cidr_allocation` explícita. Isso é
   síncrono, determinístico e revisável em PR — ao contrário da descoberta.
3. **Confirmar** por `get-ipam-pool-allocations` que cada bloco entrou.
4. **Só então** liberar alocação dinâmica.

O passo 2 é o que inverte o papel da allocation explícita: ela não serve só para espaço sem recurso
(como o `10.0.0.0/16` da Organization) — ela é a **barreira** que torna a adoção segura.

**Pré-requisito já pago:** a supernet foi reagrupada por região em `/14` contíguos
(`us-east-1` = `10.0.0.0/14`, `us-west-2` = `10.4.0.0/14`) em 2026-09-01. Um pool regional exige
`locale`, e **locale é imutável** — um plano alocado por ordem de criação não tem bloco contíguo por
região, e a adoção passaria a exigir re-endereçar VPC. `us-west-2` saiu de `10.3`/`10.4` para
`10.4`/`10.5` enquanto tinha zero recursos. Ver [ADR 0003](../../../docs/adr/0003-supernet-cidr-allocation.md).

## O modelo: escopo → pool top-level → pool regional → pool por finalidade

IPAM não é um registro de CIDRs. É uma árvore de delegação de espaço, e cada nível responde a uma
pergunta diferente.

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

### Escopo: a peça que resolve o CIDR repetido

Da doc: *"scopes enable you to reuse IP addresses across multiple unconnected networks without
causing IP address overlap or conflict."*

É a saída que [`../tenancy/03-cidr.md`](../tenancy/03-cidr.md) defende para spoke de tenant isolado.
Sem IPAM, "CIDR repetido" é uma convenção na cabeça de quem aloca. Com IPAM, é um escopo separado, e
a ferramenta para de acusar sobreposição porque sabe que aquelas redes não se falam.

É a melhor razão para adotar o IPAM neste desenho, e não tem nada a ver com escala.

### Pool top-level e regional, e o `locale`

- **Pool top-level não tem locale.** Só segura o bloco e subdivide. Não se aloca VPC dele.
- **Pool regional tem `locale`, e locale é IMUTÁVEL.** Só se aloca para VPC cuja região casa com o
  locale. É o que impede que erro de região vire CIDR fora do lugar.
- Pool com locale diferente da home region **continua alocando durante indisponibilidade da home
  region**. Isso é disponibilidade, não conveniência.
- Profundidade máxima: **10 níveis**. Quota de **50 pools por escopo** (ajustável).
- **Só existe um IPAM por conta/região.** Um experimento ocupa o slot.

> **Regras não são herdadas:** *"the allocation rules for the Regional pool are not inherited from
> the top-level pool. If you do not apply any rules here, there will be no allocation rules set for
> the pool."* Regra definida no topo e esquecida no filho = filho sem regra nenhuma.

### Regras de alocação: onde a política vira mecanismo

| Regra | Efeito |
|---|---|
| `allocation_min_netmask_length` / `max` | piso e teto do tamanho do bloco |
| `allocation_default_netmask_length` | o que sai quando o chamador não pede tamanho |
| `allocation_resource_tags` | **só aloca para recurso que tenha a tag exigida** |
| `auto_import` | adota CIDRs pré-existentes que caiam no espaço do pool |

A terceira é a que separa IPAM de planilha: ela transforma "cada tenant tem seu bloco" de convenção
em **condição de alocação**. **Verificado no mecanismo**, criando uma VPC sem a tag exigida:

```
Error: creating EC2 VPC: ... api error InvalidParameterValue:
The resource is missing one or more of the resource tags required by the IPAM pool.
```

A recusa vem do `CreateVpc`, antes de qualquer recurso existir. Um `apply` que esqueça a tag não
pega o bloco errado — ele falha. É a única coisa desta lista que um arquivo markdown de alocação
nunca conseguirá fazer.

> **A regra vale na CRIAÇÃO, não na atualização.** Remover a tag de uma VPC que já foi criada e já
> alocou seu bloco **não** dispara erro nenhum: a condição não é reavaliada. Ao testar isso, é
> preciso forçar a recriação (`-replace`), senão o teste passa e se conclui, errado, que a regra não
> funciona.

> **Regra do pai não vale para recurso do filho:** *"Allocation rules apply only to the managed
> resources within that pool. The rules do not apply to resources in pools within a pool."* A
> política tem de ser escrita no pool que **aloca**, não no que contém.

### `auto_import`: quatro comportamentos que mudam o desenho

De [`create-top-ipam.html`](https://docs.aws.amazon.com/vpc/latest/ipam/create-top-ipam.html):

1. **Indisponível se o `Locale` é `None`** — só existe no pool regional, nunca no top-level.
2. Importa **independentemente de compliance**. O recurso entra e pode virar `noncompliant`.
3. Em sobreposição, importa **só o maior CIDR**; com CIDRs idênticos, importa **um aleatoriamente**.
4. Uma VPC **não** pode ser importada se sobrepõe alocação já existente no pool. É esta regra que
   fixa o dano descrito acima.

**`auto_import` e alocação explícita são complementares, não alternativas.**
`aws_vpc_ipam_pool_cidr_allocation` reserva um CIDR "prevenindo uso pelo IPAM" — bloqueia o espaço,
mas **não vincula VPC alguma**. Quem cria o vínculo rastreável é o `auto_import`, ou criar a VPC já
com `ipv4_ipam_pool_id`.

### Como o consumo acontece

Não se escolhe o CIDR; pede-se um tamanho:

```hcl
resource "aws_vpc" "spoke" {
  ipv4_ipam_pool_id   = var.spoke_pool_id
  ipv4_netmask_length = 22          # em vez de cidr_block = "10.2.0.0/16"
}
```

Consequência para este repo: **`vpcCidrSecondOctet` e as validações de supernet deixam de existir**.
O XRD `Network`, as validações de `vpc_cidr` em `src/hub`/`src/cell`, o teste de octeto — tudo isso
é reimplementação artesanal do que o pool faz. É simplificação, não camada extra.

### Multi-conta: delegated admin + RAM

1. **Delegar uma conta membro como IPAM admin** — aqui, a conta `network`. **Regra do serviço, não
   preferência:** [`enable-integ-ipam.html`](https://docs.aws.amazon.com/vpc/latest/ipam/enable-integ-ipam.html)
   — *"The IPAM account must be an AWS Organizations member account. You cannot use the AWS
   Organizations management account as the IPAM account."* O
   [pattern oficial da AWS](https://docs.aws.amazon.com/prescriptive-guidance/latest/patterns/multi-region-ipam-architecture.html)
   assume o mesmo: *"a network hub or network management account"*.
2. Habilitar por `enable-ipam-organization-admin-account` **ou pelo console do IPAM**. Fazê-lo pelo
   console/CLI do **Organizations** não cria a service-linked role `AWSServiceRoleForIPAM`, e sem
   ela o IPAM não monitora nada.
3. **Compartilhar o pool por RAM.** A permissão é granular: alocar CIDR ≠ administrar o pool. A
   conta spoke aloca sem ver nem alterar o plano.

O toggle `aws_ram_sharing_with_organization` já está ligado (em [`terraform/dns/`](../../terraform/dns/)) — o
pré-requisito mais chato já estava pago, e o RAM share funcionou de primeira nas duas rodadas.

**Delegar é ação org-wide.** Cria a service-linked role em **todas** as contas membro, e o IPAM
passa a monitorar (e cobrar) a Organization inteira.

### O que a tabela manual não dá

- **Resource discovery** varre as contas e mostra CIDRs que ninguém registrou. Provado: achou 14
  recursos na conta `network`, incluindo subnets e EIPs que nenhuma tabela lista.
- **Estado de conformidade por alocação** — CIDR que viola a regra aparece como `noncompliant`.
- **Métricas CloudWatch por pool**: "o pool passou de 80%" vira alarme, não descoberta no `apply`.
- **Histórico de atribuição**: quem teve `10.2.0.0/16` antes do `cicd`? Hoje só o git log sabe, por
  acidente.

### Prefix list resolver (Advanced)

Mantém prefix lists sincronizadas com CIDRs do IPAM, e prefix list é o que se referencia em route
table e security group. Ataca um problema que este repo já tem: a rota do supernet e as regras de SG
carregam CIDR literal, e mover um bloco significa caçar todos os lugares onde foi escrito à mão.

## Free Tier vs. Advanced Tier

> **Corrigido em 2026-09-01.** A versão anterior dizia que o corte era o *locale* e que o Free Tier
> "atenderia a uma prova de conceito de uma região só". **Falso.** Pool no escopo privado é Advanced
> Tier, independentemente de quantas regiões.

| | Free | Advanced |
|---|---|---|
| Pools no **escopo privado** (IPv4 privado) | **não** | sim |
| Escopo privado adicional (não-default) | **não** | sim |
| Pools com locale ≠ home region | **não** | sim |
| Alocação para conta que não é o IPAM owner (RAM) | **não** | sim |
| Features através de operating regions | só **Public IP insights** | todas |
| Prefix list resolver, IP history, integrações | não | sim |
| Cobrança | sem custo | **US$ 0,197/mês por IP ativo** |

Três fontes convergem:

- [`create-ipam.html`](https://docs.aws.amazon.com/vpc/latest/ipam/create-ipam.html): *"If you are
  creating an IPAM in the Free Tier […] the only IPAM feature that will be available across
  operating Regions is Public IP insights."*
- [`mod-ipam-tier.html`](https://docs.aws.amazon.com/vpc/latest/ipam/mod-ipam-tier.html): para voltar
  de Advanced a Free é preciso apagar *private scope pools*, escopos privados não-default, pools com
  locale diferente da home region e alocações cross-account. É a definição invertida do Advanced.
- Tabela **IPAM** na [página de preços da VPC](https://aws.amazon.com/vpc/pricing/): *Private IPv4
  management* e *Share IPAM pools with AWS accounts* ausentes do Free.

O caso deste repo cai em Advanced por **três motivos independentes** (IPv4 privado, multi-conta,
multi-região). Não há decisão de tier a tomar — há uma conta a pagar.

**Nota operacional:** `tier` é modificável in-place (`modify-ipam`), mas o downgrade exige apagar
tudo da lista acima primeiro. Um destroy pela metade trava o downgrade. `cascade = true` no
`aws_vpc_ipam` resolve isso — e foi o que garantiu destroy limpo nas duas rodadas.

## Quando adotar: gatilhos, não calendário

| Gatilho | Por quê |
|---|---|
| **Decidir por "CIDR repetido para tenant isolado"** | é o escopo adicional; fazer à mão é manter duas contabilidades paralelas |
| Terceira região entrar | a tabela manual ganha um eixo que não representa bem |
| Passar de ~20 blocos alocados | "quem tem qual bloco" deixa de caber na cabeça de uma pessoa |
| Onboarding de tenant virar automatizado | alocação por API é pré-requisito; escolher octeto à mão não automatiza |
| Um CIDR fora do plano ser descoberto | resource discovery deixa de ser luxo |

Nenhum disparou. O primeiro é o mais provável, porque depende de uma decisão de desenho já em aberto
(decisão 2 de [`../tenancy/CLAUDE.md`](../tenancy/CLAUDE.md)), não de crescimento.

**Um gatilho novo, que só apareceu depois de medir:** se `us-west-2` for aplicada, o repo passa de 2
para 4 VPCs a adotar, e ganha uma segunda região em estado brownfield. Adotar **antes** de aplicar
`us-west-2` é estritamente mais barato do que depois.

## Well-Architected

| Best practice | Como se relaciona |
|---|---|
| **[REL02-BP05 — Enforce non-overlapping private IP address ranges](https://docs.aws.amazon.com/wellarchitected/latest/reliability-pillar/rel_planning_network_topology_non_overlap_ip.html)** | recomenda IPAM nominalmente e cita "relying on manual IP address management processes, such as spreadsheets" como anti-pattern — que é o que fazemos. **Gap consciente**, com os gatilhos acima como plano. A BP declara *level of risk* **Medium**; fosse High, adiar não seria defensável |
| **[REL02-BP03 — Ensure IP subnet allocation accounts for expansion and availability](https://docs.aws.amazon.com/wellarchitected/latest/reliability-pillar/rel_planning_network_topology_ip_subnet_allocation.html)** | regras de netmask por pool tornam "tamanho por finalidade" mecanismo em vez de convenção |
| **[SEC05-BP01 — Create network layers](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/sec_network_protection_create_layers.html)** | escopo separado = espaço roteável e espaço isolado deixam de ser distinção informal |

O [SaaS Lens](https://docs.aws.amazon.com/wellarchitected/latest/saas-lens/tenant-isolation.html) não
prescreve endereçamento — ele diz que *"the strategies and approaches to achieving this isolation are
not universal"*. A ligação com este documento é indireta: se o modelo de tenancy for silo por
VPC/conta, o número de blocos cresce rápido e o escopo separado do IPAM passa a ser a primitiva
certa.

## Próximo

→ Índice do domínio: [`CLAUDE.md`](CLAUDE.md). Plano de endereçamento vigente:
[`01-cidr-addressing.md`](01-cidr-addressing.md). Teto que motiva a discussão:
[`../tenancy/03-cidr.md`](../tenancy/03-cidr.md). Código e provas do experimento:
[`terraform/spikes/ipam/README.md`](../../terraform/spikes/ipam/README.md).
