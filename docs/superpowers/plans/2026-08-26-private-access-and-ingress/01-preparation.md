# Phase 1 — Preparation

Grátis ou quase, e independe de tudo o resto. Pode ser feita a qualquer momento, inclusive antes de
decidir qualquer coisa das fases seguintes.

| # | Passo | Nível | Custo | Aceite |
|---|---|---|---|---|
| `1.1` | ~~Tags~~ **Teste** das tags `kubernetes.io/role/{elb,internal-elb}` em `src/network` | — | zero | `terraform test` offline — **feito** |
| `1.2` | `generate-tfvars` descobre o IP público → `public_access_cidrs = ["<ip>/32"]` | — | zero | teste offline **feito**; os dois critérios que exigem apply real **pendentes** |
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

## `1.2` — `/32` no `public_access_cidrs` — **código e teste feitos, apply real pendente**

Restringir o endpoint ao IP público corrente é a **maior redução de superfície da lista**, custa zero
e **não quebra o apply do laptop** — que é o que sustenta a operação até o `2.5`.

Entregue em três lugares, com a fronteira escolhida de propósito:

| Onde | O que | Por que ali |
|---|---|---|
| `src/cluster` | recusa lista vazia **quando o endpoint público está ligado**; recusa CIDR sem prefixo | é a **semântica da AWS** (vazio = `0.0.0.0/0`): a armadilha existe para qualquer chamador, presente ou futuro |
| `control-plane` | variável **sem default**, e recusa `0.0.0.0/0` mesmo explícito | é a **política da célula**, não da AWS. Abrir exige editar a validação — ato visível em diff, não valor num `tfvars` gitignored |
| `scripts/generate-tfvars` | descobre o IP em `checkip.amazonaws.com` e escreve o `/32` | o script já existe para descobrir antes de gerar arquivo |

**Sem default é a decisão que fecha o `Known Broken 3`.** Omitir a variável era o caminho silencioso
para expor a API ao mundo; agora omitir é erro de validação, antes de qualquer chamada à AWS.

Opção `--public-access-cidr` (repetível) desliga a descoberta — para quando o apply rodar de outro
lugar (CodeBuild, runner de CI) ou para acrescentar o CIDR do Client VPN no `2.5`.

### O que ainda não foi verificado

Os outros dois critérios de aceite — *apply do laptop segue funcionando* e *a API recusa de outro
IP* — **exigem a camada 2 de pé** (~US$ 165/mês). Ficam para a próxima vez que ela subir, junto com
`2.x`. O que está provado é o comportamento offline: 6 mutações rodadas, 6 capturadas.

### Achados do passo

- **Condição de `validation` tem de referenciar a própria variável.** Trocar a condição por `true`
  para testar mutação não produz teste vermelho — produz erro de configuração, e nenhum run executa.
  Mutação de validação precisa **enfraquecer** a condição (`length(...) >= 0`), não removê-la.
- **`can(cidrhost(c, 0))` é validador de CIDR suficiente:** aceita `203.0.113.10/32`, recusa
  `203.0.113.10` sem prefixo, `/33` e octeto acima de 255. Verificado no `terraform console`, não
  presumido.
- **A invariante do módulo torna o fio do root impossível de cortar em silêncio:** apagar o
  `public_access_cidrs = var.public_access_cidrs` do root deixa a lista vazia e a validação do módulo
  derruba o plan. Só uma mutação que passa um CIDR **válido mas errado** isola a asserção do root —
  e é ela que justifica a asserção existir.
- **`curl | tr` engole a falha do `curl`:** o exit code do pipeline é o do `tr`. Sem pipe, e
  `--fail` para transformar HTTP ≥ 400 em exit code (verificado: exit 22 num 404 real).
- **Exit code do `curl` não basta:** portal cativo e proxy que intercepta devolvem HTML com HTTP 200.
  O formato do que voltou é validado, senão o HTML entraria no `tfvars`.

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
