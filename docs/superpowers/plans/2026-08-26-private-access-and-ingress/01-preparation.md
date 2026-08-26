# Phase 1 — Preparation

Grátis ou quase, e independe de tudo o resto. Pode ser feita a qualquer momento, inclusive antes de
decidir qualquer coisa das fases seguintes.

| # | Passo | Nível | Custo | Aceite |
|---|---|---|---|---|
| `1.1` | ~~Tags~~ **Teste** das tags `kubernetes.io/role/{elb,internal-elb}` em `src/network` | — | zero | `terraform test` offline — **feito** |
| `1.2` | `generate-tfvars` descobre o IP público → `public_access_cidrs = ["<ip>/32"]` | — | zero | teste offline; apply do laptop segue funcionando; API recusa de outro IP |
| `1.3` | Raiz `dns/`: hosted zone `nonprod.<domínio>` + delegação NS no Azure, dois providers | T0 | ~US$ 0,50/mês | `dig NS nonprod.<domínio>` responde pelos name servers do Route 53 |

## `1.1` — tags de descoberta do LBC — **FEITO**

**A premissa do passo estava errada.** O plano registrava que `src/network` não aplicava
`kubernetes.io/role/elb` nas públicas nem `kubernetes.io/role/internal-elb` nas privadas. As duas
estão no módulo desde `b32eb68`, o commit inicial dele — o achado veio da leitura do desenho de
referência, não do código. Não havia bug a corrigir.

O que faltava era o **critério de aceite**: nenhum dos dois arquivos de teste olhava tag alguma. Uma
tag pode desaparecer num refactor de `merge` sem quebrar nada visível, e a quebra só apareceria na
fase 3, longe da causa. Entregue `tests/tags.tftest.hcl`, 4 runs:

| Run | Protege contra |
|---|---|
| `as_subnets_publicas_carregam_a_tag_de_elb_externo` | perder `role/elb` |
| `as_subnets_privadas_carregam_a_tag_de_elb_interno` | perder `role/internal-elb` |
| `as_tags_de_papel_nao_se_cruzam` | aplicar as duas às duas famílias — pior que a ausência, porque falha em runtime e não no apply |
| `tags_do_chamador_convivem_com_as_tags_de_papel` | inverter a ordem do `merge` e deixar `var.tags` vencer |

**Quatro mutações rodadas, quatro capturas**, cada uma pela asserção pretendida. Todo `alltrue` vem
com contagem ao lado: `alltrue([])` é `true`, e é a armadilha já registrada em
`aws/terraform/CLAUDE.md`.

Duas decisões que o passo fechou:

- **A tag `kubernetes.io/cluster/<nome>` não entra.** Opcional a partir do LBC `2.1.2`, serve só para
  desempatar entre clusters que compartilham a VPC. Aqui é um cluster por VPC spoke, e o módulo não
  conhece nome de cluster. Inverte se isso mudar.
- **As tags de papel não têm fallback.** O LBC, ao contrário do controller in-tree, **não examina
  route table** para deduzir público/privado ([doc do
  EKS](https://docs.aws.amazon.com/eks/latest/userguide/network-load-balancing.html)) — daí o teste,
  e não só o comentário no `main.tf`.

## `1.2` — `/32` no `public_access_cidrs`

Hoje o endpoint da API do EKS aceita `0.0.0.0/0` (`public_access_cidrs = []`, e vazio significa o
mundo). Restringir ao IP público corrente é a **maior redução de superfície da lista**, custa zero e
**não quebra o apply do laptop** — que é o que sustenta a operação até o `2.5`.

Com IP dinâmico isso quebra; a mitigação natural é o `generate-tfvars` descobrir o IP corrente, já
que ele existe justamente para descobrir coisas na AWS antes de gerar arquivo.

## `1.3` — raiz `aws/terraform/dns/`, com dois providers

Subzona delegada, não o domínio inteiro: **`nonprod.wasp.silvios.me`** para o Route 53, na conta
`network`. O apex continua no Azure DNS, então a trilha Azure não migra nada.

Nomes resultantes: cluster em `<id>.nonprod.<domínio>`, aplicações em `app.<id>.nonprod.<domínio>`,
certificado wildcard `*.<id>.nonprod.<domínio>`. Um ambiente novo é uma subzona nova delegada do
mesmo jeito — e cada uma é sua própria fronteira de permissão.

O label `nonprod` foi escolhido sobre `sandbox` porque `Sandbox` já tem sentido fixado no vocabulário
do repo — conta de brincar, desconectada da rede — e o ambiente de teste do projeto é
`<projeto>-nonprod`.

**A delegação é código, não passo manual.** A raiz usa dois providers:

```hcl
provider "aws"     { profile = var.network_profile, region = "us-east-1" }
provider "azurerm" { features {} }

resource "aws_route53_zone" "nonprod" {
  name = "nonprod.${var.base_domain}"
  lifecycle { prevent_destroy = true }
}

# a delegação, do lado Azure, cabeada direto nos name servers que a AWS acabou de dar
resource "azurerm_dns_ns_record" "delegation" {
  name                = "nonprod"
  zone_name           = var.base_domain
  resource_group_name = var.azure_dns_resource_group
  ttl                 = 300
  records             = aws_route53_zone.nonprod.name_servers
}
```

Destruir a raiz remove o registro NS no Azure junto — sem resíduo apontando para name servers que não
existem mais.

**Raiz própria, sem região na state key**, por dois motivos: hosted zone pública é **global**, então
não cabe em `network-foundation/<região>/`; e se a zona morasse em `connectivity/` (destruído toda
noite) ela renasceria com **name servers novos** todo dia — com a delegação automatizada isso até se
corrigiria sozinho, mas a propagação de NS não é instantânea e o edge ficaria intermitente sem
motivo. Zona é T0: ~US$ 0,50/mês, `prevent_destroy`, e a automação existe para quando a recriação
*for* necessária, não como licença para recriar.

**Ganho de permissão:** a subzona delegada é a fronteira de blast radius do DNS — o external-dns
dentro do cluster recebe acesso só a ela, e não tem como tocar o apex. Com o domínio inteiro
delegado, essa separação não existiria.

**Risco dos dois providers no mesmo state:** sem credencial Azure válida, o `plan` falha mesmo para
mudança que só toca AWS. Manter o recurso de delegação atrás de um `local.manage_delegation` para
poder desligar sem editar o resto.
