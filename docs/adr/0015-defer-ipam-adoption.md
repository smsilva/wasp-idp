# Defer IPAM adoption

**Status:** Aceito

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

## Consequências

O anti-pattern de REL02-BP05 permanece em aberto, **conscientemente e com plano** — que é a diferença entre gap registrado e dívida no escuro. O risco Medium da própria BP é o que sustenta essa resposta: fosse High, adiar não seria defensável.

**O risco concreto não é o IPAM ausente — é a colisão entre regiões.** Os CIDRs são literais nos `locals` de cada raiz e a única asserção existente compara hub vs célula **dentro da mesma raiz**. Digitar em `us-east-1` um bloco que pertence a `us-west-2` passa nos 14 módulos da regressão offline, e a colisão só aparece quando as duas regiões se falarem pelo TGW. Isso é fechável **sem** IPAM, por tabela de alocação única consumida por todas as raízes mais asserção de unicidade cruzada, e é rastreado em issue própria.

Ao adotar, o que se joga fora é código: `vpcCidrSecondOctet`, as validações de supernet em `src/hub`/`src/cell` e o teste de octeto. Perder código que o serviço faz melhor é ganho.

Enquanto o spike estiver aplicado, o slot de IPAM da conta `network` está ocupado (só existe um por conta/região) e a Organization inteira é monitorada — o `destroy` é parte do experimento, não uma limpeza opcional.
