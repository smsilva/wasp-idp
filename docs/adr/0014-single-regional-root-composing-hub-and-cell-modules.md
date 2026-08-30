# Single regional root composing hub and cell modules

**Status:** Aceito

## Contexto

A camada Terraform está hoje partida em cinco raízes com states próprios — `state-backend/` (00),
`network-foundation/<região>/` (01), `dns/` (02), `connectivity/<região>/` (03) e `control-plane/`
(04). O acoplamento entre elas não é por referência: cada raiz **redescobre** o que a anterior criou,
por data source (`data.aws_vpc.hub` por tag `Name`, `data.aws_lb.hub_ingress` por nome,
`data.aws_ec2_transit_gateway.hub` por tag) e por dois scripts `scripts/generate-tfvars` (390 + 582
linhas) que consultam a AWS CLI e escrevem um `terraform.tfvars` gitignored, pré-requisito de
`up-03` e `up-04`.

Três custos já pagos, todos consequência dessa fronteira:

1. **O tfvars gerado envelhece em silêncio.** Em 2026-08-29 `base_domain` entrou na `control-plane/`
   sem default; o `terraform.tfvars` já existente deixou de satisfazer a config e o `up-04` morreu
   com `No value for required variable` **depois** do plan — um erro que não aponta para o passo de
   geração. É o que motivou a issue #36.

2. **A ordem de destruição é manual e já quebrou duas vezes.** O attachment do TGW da célula vive no
   state da 04 e a AWS recusa deletar TGW com attachment vivo, então a ordem 04→03 é obrigatória e
   está escrita em prosa no `HANDOFF.md`, não no grafo. Os dois incidentes de `dial tcp
   <ip-privado>:443: i/o timeout` (2026-08-27 no destroy, 2026-08-28 no apply) são da mesma família:
   arestas que o Terraform derivaria sozinho tiveram de ser escritas à mão como `depends_on` porque
   as duas pontas não estão no mesmo grafo.

3. **Valores de identidade ficam espalhados.** Domínio, ids de conta e UUIDs de grupo do Identity
   Center vivem em dois `terraform.tfvars` gerados mais o `CLAUDE.local.md`, sem um inventário único
   — o problema que a issue #21 e o [ADR 0013](0013-consolidate-local-values-yaml.md) atacam.

## Decisão

**Hub e célula passam a ser módulos compostos numa raiz única por região,
`aws/terraform/regions/<região>/`.**

A cardinalidade que a raiz reflete é a real:

```
regions/us-east-1/
  module.hub    1  — VPC hub, TGW, Client VPN, ALB + listener :443 compartilhado
  module.cell   N  — VPC spoke, EKS, NLB interno; cada célula anexa seu certificado
                     por SNI e sua listener rule no ALB do hub
```

| Hoje | Depois |
|---|---|
| `network-foundation/<região>/` (01) + `connectivity/<região>/` (03) | `src/hub` — chamado como `module.hub` |
| `control-plane/` (04) | `src/cell` — chamado como `module.cell` |
| `state-backend/` (00), `dns/` (02) | **inalteradas** — raízes próprias |

**Uma célula só, por enquanto.** `module "cell"` é um bloco singular, não `for_each` sobre um mapa —
a segunda célula é quem paga o custo de generalizar, e um `moved` cobre a transição. Que a
`priority` da listener rule já seja derivada de hash do nome da célula, falhando alto na colisão,
é o que mantém N > 1 possível sem ser construído agora.

A célula consome o hub por **output de módulo**, não por data source: `module.hub.transit_gateway_id`
no lugar de `data.aws_ec2_transit_gateway.hub`, `module.hub.alb_listener_arn` no lugar de
`data.aws_lb_listener.hub_https`, e assim por diante. Data source continua sendo o mecanismo para o
que é externo à raiz — a subzona que a `dns/` (02) delegou, por exemplo.

`state-backend/` e `dns/` ficam de fora porque não compartilham o ciclo de vida da região: a 00
guarda o mapa de tudo e tem `prevent_destroy`; a 02 mexe na Organization inteira
(`aws_ram_sharing_with_organization`, sob a management account) e é T0 permanente.

**Um único `variables/values.tfvars` gitignored** alimenta as raízes regionais, com os valores de
**identidade** (por-conta, não versionáveis) declarados à mão: `base_domain`, `operator_group_ids`,
`spoke_account_ids`, `target_account_ids`, `network_account_id`. Valor **estrutural** — região, CIDR
do hub e das células, nome do hub, versão do Kubernetes — fica inline na raiz ou como default de
variável, seguindo a convenção que a `network-foundation/` já usa e a alocação documentada em
`aws/docs/network/01-cidr-addressing.md`. Isso absorve a issue #21 e substitui o `values.yaml` do
ADR 0013 por um formato que o Terraform lê direto.

**Os dois `scripts/generate-tfvars` são removidos.** A metade de descoberta perde a razão de existir
— o que ela descobria ou virou referência entre módulos, ou é declarado à mão. A metade de validação
cai por redundância: a existência da VPC hub, do ALB e da subzona já falha no plan pelos próprios
data sources e pelas referências de módulo.

**O teardown da célula é `terraform destroy -target=module.cell`.** A célula continua descartável sem
levar o hub junto, e a ordem interna passa a ser derivada do grafo em vez de escrita em prosa.

## Consequências

**Isto revisa o [ADR 0007](0007-state-boundary-follows-lifecycle.md) na fronteira hub × célula.**
Aquele ADR diz que a fronteira de state segue o ciclo de vida, e hub (T1, de pé durante o dia) e
célula (T2, sobe e desce) têm ciclos diferentes — pela regra de 0007 seriam states distintos. A regra
continua válida para o que 0007 decidiu de fato (recurso da conta `network` com ciclo de vida de
célula mora no state da célula, via provider aliasado); o que muda é que a separação **entre** hub e
célula deixa de ser paga em state e passa a ser paga em `-target`. O que se compra com isso são as
arestas do grafo — o custo dos dois incidentes de ordenação foi maior que o de um state
compartilhado.

**`-target` vira rotina, e a HashiCorp o documenta como escape hatch excepcional.** Consequência
aceita de olhos abertos: o comando de teardown noturno passa a ser
`terraform destroy -target=module.cell`, e todo `-target` imprime um aviso dizendo que não é para uso
rotineiro. A alternativa (dois states) reintroduziria a redescoberta que este ADR existe para matar.

**O blast radius de um apply cresce.** Um erro na raiz alcança hub e célula ao mesmo tempo, e o state
único fica maior. O contrapeso é que hub e célula já se derrubavam mutuamente na prática — só que por
ordem manual, sem o Terraform saber.

**Os testes migram das raízes para os módulos.** Os sete arquivos `.tftest.hcl` de
`connectivity/us-east-1/tests/` e `control-plane/tests/` passam a exercitar `src/hub` e `src/cell`; a
raiz regional fica com um teste de composição, que é o único lugar onde a ligação hub→célula por
output é assertável.

**O state atual não é migrado.** `connectivity/` e `control-plane/` estão com zero recursos (T1 e T2,
descartáveis por desenho, confirmado em 2026-08-29). Só a `network-foundation/` tem recursos vivos —
VPC, subnets, IGW e route tables, sem dado nenhum e sem custo por hora — então o corte é limpo:
destruir a 01 e aplicar a raiz nova do zero, em vez de cirurgia de `moved`/`import` para adotar
recursos que custam minutos para recriar.

**`regions/us-west-2/` nasce sem `module.cell` aplicado.** Um hub sozinho é exatamente o que a
`network-foundation/us-west-2/` é hoje, e o `-target` do teardown é o mesmo mecanismo que mantém essa
região só com o hub.

## Rejeitados

- **Manter as camadas e só trocar o `generate-tfvars` por um tfvars à mão** — o desenho original da
  issue #36. Resolve o sintoma 1 e deixa 2 e 3 de pé: a redescoberta por data source e a ordem de
  destruição em prosa continuam.
- **Duas raízes lendo o mesmo tfvars, com a célula consumindo o hub por `terraform_remote_state`** —
  preserva o blast radius separado e o `destroy` por camada, mas mantém o acoplamento por leitura de
  state alheio e não devolve nenhuma aresta ao grafo.
- **`module.cell` com `count = var.cell_enabled ? 1 : 0`, derrubado virando a flag** — poria o estado
  desejado no tfvars em vez de num comando, mas obriga `one()`/`[0]` em todo output da célula e
  esconde num arquivo de valores uma decisão que é operacional, não de configuração.
- **Uma raiz única para todas as regiões** — colide com a regra já vigente de uma raiz por região
  (`aws/terraform/CLAUDE.md`): alternar backend com `init -reconfigure` mistura regiões e nada no
  Terraform pega o erro.
