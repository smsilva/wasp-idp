# Defer IPAM adoption

**Status:** Proposto — pendente do teste greenfield em `us-west-2`

> Não aceitar antes disso. O spike de `us-east-1` provou o cenário **brownfield** e encontrou um
> defeito real, mas o argumento contrário (o custo de adotar **salta** quando a primeira VPC nasce
> fora do pool) só pode ser pesado depois de o fluxo de dia zero ser exercitado. Ver
> `aws/terraform/spikes/ipam/greenfield-us-west-2.tfvars`.

## Contexto

A alocação de CIDR deste repo é uma tabela markdown mais um literal nos `locals` de cada raiz regional. [REL02-BP05](https://docs.aws.amazon.com/wellarchitected/latest/reliability-pillar/rel_planning_network_topology_non_overlap_ip.html) lista *"relying on manual IP address management processes, such as spreadsheets"* entre os anti-patterns e abre a implementation guidance com *"make use of an IPAM, such as the Amazon VPC IP Address Manager"*. A [issue #15](https://github.com/smsilva/wasp-idp/issues/15) pediu a avaliação: de quem seria o escopo, o que aconteceria com as spokes já alocadas, e quando fazer.

O desenho técnico já existia em [`aws/docs/network/08-ipam.md`](../../aws/docs/network/08-ipam.md). O que faltava eram os números e a verificação dos fatos contra a doc oficial — e **duas afirmações daquele documento estavam erradas**, ambas na direção de fazer o IPAM parecer mais barato do que é.

**Fatos apurados em 2026-09-01:**

- **Não existe recorte Free Tier.** Pool no escopo privado é recurso de Advanced Tier, independentemente de quantas regiões. `create-ipam.html`: no Free Tier *"the only IPAM feature that will be available across operating Regions is Public IP insights"*; e a lista de pré-requisitos para voltar de Advanced a Free (`mod-ipam-tier.html`) exige apagar *private scope pools*, escopos privados não-default, pools com locale ≠ home region e alocações cross-account — a definição invertida do que só existe no Advanced. O caso deste repo cai em Advanced por três motivos independentes.
- **Custo medido, não estimado:** US$ 0,00027 por IP ativo/hora ≈ US$ 0,197/mês por IP. A Organization inteira tem **7 IPs ativos** com só `module.hub` de pé (`describe-network-interfaces` nas 4 contas × 2 regiões) ⟹ **US$ 1,38/mês**. Com a célula de pé, ~40 IPs (~US$ 8/mês); 10 células em 2 regiões, ~340 (~US$ 67/mês). O custo escala com a frota de **pods** (o VPC CNI pré-aloca IPs secundários por nó), não com o número de VPCs.
- **O IPAM admin não pode ser a management account** — regra do serviço, não preferência de desenho.
- **`auto_import` e alocação explícita não são alternativas.** `aws_vpc_ipam_pool_cidr_allocation` reserva o espaço mas não vincula VPC alguma; quem adota VPC existente é `auto_import`, que por sua vez não está disponível em pool sem `locale`.
- **Nenhum dos cinco gatilhos de `08-ipam.md` disparou:** 4 blocos alocados de 15, 2 regiões, decisão de tenant isolado em aberto, onboarding não automatizado, nenhum CIDR fora do plano descoberto.
- **REL02-BP05 declara o *level of risk* como Medium**, não High.

## Decisão

**Adiar a adoção do IPAM.** As três perguntas da issue #15 ficam respondidas de antemão, para que a adoção futura não recomece do zero:

1. **Dono do escopo:** conta `network` (Connectivity Account) como delegated admin, home region `us-east-1`, operating regions `us-east-1` + `us-west-2`, escopo privado default para o espaço roteável, pools compartilhados por RAM. A management account está excluída por regra da AWS. Um segundo escopo privado — a primitiva que sustenta CIDR repetido entre tenants que não se falam — só quando a decisão 2 de `aws/docs/tenancy/` for tomada.
2. **Spokes já alocadas:** adoção, nunca realocação. `auto_import` no pool regional adota as VPCs existentes sem recriá-las; allocation explícita reserva o que não tem recurso (o `10.0.0.0/16` da Organization). Nada é re-endereçado.
3. **Quando:** quando um dos gatilhos de `08-ipam.md` disparar. O mais provável continua sendo a decisão de tenant isolado, que depende de desenho e não de crescimento.

**Duas coisas são feitas agora, porque adiá-las é que sairia caro:**

- **A supernet passa a ser alocada por região, em `/14` contíguos** (`us-east-1` = `10.0.0.0/14`, `us-west-2` = `10.4.0.0/14`), amendando o [ADR 0003](0003-supernet-cidr-allocation.md). Um pool regional exige `locale`, e **locale é imutável**: sem bloco contíguo por região, adotar o IPAM depois exigiria re-endereçar VPC — exatamente o que a adoção deveria evitar. `us-west-2` saiu de `10.3`/`10.4` para `10.4`/`10.5` enquanto aquela raiz tinha **zero recursos aplicados**.
- **Um modelo mínimo executável fica versionado** em [`aws/terraform/spikes/ipam/`](../../aws/terraform/spikes/ipam/), com sete provas declaradas. A decisão de adiar é tomada com o desenho provado, não imaginado.

## O que o spike ensinou, e que nenhuma leitura de doc teria produzido

O modelo mínimo foi aplicado de verdade em 2026-09-01 e **reprovou a premissa central de `08-ipam.md`**: a de que a migração é "de processo de alocação, não de endereço", e portanto mecânica e segura.

A VPC de prova nasceu com `10.1.0.0/24` — **dentro de `10.1.0.0/16`, a VPC do hub que estava de pé**. O IPAM entregou espaço já ocupado, em outra conta, para redes que se falam pelo TGW. `auto_import` é assíncrono e a alocação não espera por ele: quinze minutos depois, `10.1.0.0/16` continuava não importada, embora o IPAM já a tivesse **descoberto** (14 recursos listados por `get-ipam-discovered-resource-cidrs`). *Descoberto* e *alocado* são estados distintos, e só o segundo bloqueia o espaço.

E o dano se fixa: pela regra da própria AWS, uma VPC cujo CIDR **cobre** uma alocação existente não pode mais ser auto-importada. Uma alocação prematura **envenena o pool**, e a adoção do legado deixa de ser possível sem intervenção manual.

**Consequência normativa para quando um gatilho disparar** — a adoção é em fases separadas por verificação, nunca num `apply` só:

1. criar IPAM e pools, **sem nenhum recurso que aloque**;
2. **reservar cada bloco legado** por `aws_vpc_ipam_pool_cidr_allocation` explícita — síncrono, determinístico e revisável em PR, ao contrário da descoberta;
3. confirmar por `get-ipam-pool-allocations` que os blocos entraram;
4. só então liberar alocação dinâmica.

Isso inverte o papel que a avaliação inicial atribuía à allocation explícita: ela não é só para espaço sem recurso (o `10.0.0.0/16` da Organization) — é a **barreira** que torna a adoção segura.

O que **não** se confirmou como problema: criar um IPAM sobre uma árvore Terraform viva não a perturba. `terraform plan -target=module.hub` em `regions/us-east-1/` deu `0 to add, 1 to change, 0 to destroy`, e a única mudança é drift pré-existente e já conhecido. O critério "adoção, não realocação" se sustenta — o que falha é o *timing* da adoção, não a premissa de não re-endereçar.

### O defeito é de brownfield, e some no dia zero

Delimitação que importa para não generalizar demais: **a race só existe porque havia VPC pré-existente para adotar.** Numa Organization nova, o IPAM nasce antes de qualquer VPC — não há nada a importar, `auto_import` deixa de ser relevante, e toda VPC nasce alocando do pool. O modo de falha simplesmente não ocorre.

Isso separa dois cenários que a avaliação inicial tratava como um só:

| | Greenfield (Organization nova) | Brownfield (o estado deste repo) |
|---|---|---|
| VPCs a adotar | nenhuma | 2 no supernet, mais as default |
| `auto_import` | irrelevante | é a race |
| Ordem obrigatória | criar IPAM antes da primeira VPC | as quatro fases acima |
| Risco de colisão na adoção | **nenhum** | alto, e o dano se fixa |

Consequência: **o custo de adotar IPAM cresce com o tempo**, e não de forma suave — ele salta no instante em que a primeira VPC nasce fora do pool. Isso é um argumento *contra* adiar, e é o mais forte que existe do outro lado da decisão. O que sustenta adiar mesmo assim é que a adoção brownfield **é possível**, só exige a sequência disciplinada acima; e que hoje são 2 blocos a adotar, não 20.

**Existe uma terceira coisa que o dia zero limparia de graça e que hoje é dívida:** toda conta nasce com VPC default `172.31.0.0/16`, idêntica em todas as contas — 6 alcançáveis nesta Organization, todas sobrepostas entre si por construção. Rastreado em issue própria, e independente do IPAM.

## Consequências

O anti-pattern de REL02-BP05 permanece em aberto, **conscientemente e com plano** — que é a diferença entre gap registrado e dívida no escuro. O risco Medium da própria BP é o que sustenta essa resposta: fosse High, adiar não seria defensável.

**O risco concreto não é o IPAM ausente — é a colisão entre regiões.** Os CIDRs são literais nos `locals` de cada raiz e a única asserção existente compara hub vs célula **dentro da mesma raiz**. Digitar em `us-east-1` um bloco que pertence a `us-west-2` passa nos 14 módulos da regressão offline, e a colisão só aparece quando as duas regiões se falarem pelo TGW. Isso é fechável **sem** IPAM, por tabela de alocação única consumida por todas as raízes mais asserção de unicidade cruzada, e é rastreado em issue própria.

Ao adotar, o que se joga fora é código: `vpcCidrSecondOctet`, as validações de supernet em `src/hub`/`src/cell` e o teste de octeto. Perder código que o serviço faz melhor é ganho.

Enquanto o spike estiver aplicado, o slot de IPAM da conta `network` está ocupado (só existe um por conta/região) e a Organization inteira é monitorada — o `destroy` é parte do experimento, não uma limpeza opcional.
