# Fase 3 — `src/cell` ligada ao hub por output

Move a `control-plane/` (04) para `src/cell` e a liga ao `module.hub` por referência. Os sete data
sources que a camada 04 usa hoje para achar o hub morrem — seis viram variável alimentada por output,
e só a subzona do Route 53 continua data source, porque pertence à raiz `dns/`, que é externa.

**Pré-requisito:** fase 2 fechada, com o hub aplicado da raiz `regions/us-east-1/` e o túnel do
Client VPN conectando. O apply desta fase **não completa sem o túnel** — os providers `helm` e
`kubernetes` falam com o API server a partir desta máquina, e o endpoint é privado.

---

## Uma consequência a encarar antes de começar

Com a célula dentro da raiz, o estado desejado da raiz **sempre inclui a célula**. Depois de
`terraform destroy -target=module.cell`, um `terraform plan` puro volta a propor criar os ~60
recursos da célula. Isso não é drift nem bug: é o `-target` sendo um desvio deliberado do estado
desejado, exatamente como a HashiCorp o descreve.

Consequências práticas, que os scripts da Task 4 têm de tornar visíveis em vez de esconder:

- **"Plan limpo" deixa de ser o estado de repouso da região.** O repouso noturno é "hub aplicado,
  célula deliberadamente fora", e nenhum `plan` diz isso — quem confere o estado usa
  `terraform state list`, não o plan.
- **`up-02-region` sem argumento sobe a célula junto**, e a célula custa ~US$ 165/mês. O default do
  script tem de ser o hub sozinho, com a célula atrás de uma opção explícita — o mesmo desenho que o
  `up-all` já usa com `--with-control-plane`.

Foi o custo aceito no ADR 0014 ao escolher `-target` em vez da flag `cell_enabled`. Está registrado
lá; aqui ele vira requisito de script.

---

### Task 1: `src/cell` com a interface fechada

**Files:**
- Create: `aws/terraform/src/cell/main.tf` (de `control-plane/main.tf`)
- Create: `aws/terraform/src/cell/variables.tf`
- Create: `aws/terraform/src/cell/outputs.tf`
- Create: `aws/terraform/src/cell/versions.tf`
- Move: `control-plane/tests/*.tftest.hcl` → `src/cell/tests/`

**Interfaces:**
- Consumes: os outputs de `src/hub` fechados na fase 2 — `vpc_id`, `vpc_cidr_block`,
  `transit_gateway_id`, `transit_gateway_route_table_id`, `transit_gateway_attachment_id`,
  `alb_arn`, `alb_listener_arn`, `alb_dns_name`, `alb_zone_id`.
- Produces: as variáveis abaixo e os outputs de aceite (`cell_services_url`, `cell_ingress_fqdn`,
  `cluster_name`, `kubeconfig_command`), que a raiz repassa.
- Produces, **obrigatoriamente**: `cluster_endpoint` e `cluster_ca_data`, hoje lidos direto de
  `module.cluster` em `control-plane/providers.tf`. Com o cluster dentro de `src/cell`, os providers
  `kubernetes` e `helm` da raiz não alcançam mais um submódulo aninhado — os dois valores têm de
  atravessar como output do módulo, senão a Task 2 não compila:

  ```hcl
  output "cluster_endpoint" {
    description = "Endpoint da API do EKS. A raiz configura os providers kubernetes e helm com ele."
    value       = module.cluster.cluster_endpoint
  }

  output "cluster_ca_data" {
    description = "CA do cluster, base64. Par obrigatorio do endpoint na configuracao dos providers."
    value       = module.cluster.cluster_ca_data
  }
  ```

- [ ] **Regionalizar o `name` da célula (invariante).** `var.name` tem default `"control-plane"` e
  prefixa, entre outras coisas, **cinco roles de IAM** (`-load-balancer-controller`, `-ebs-csi`,
  `-external-secrets`, `-crossplane`, e a do nodegroup) e **dois nomes no Route 53**
  (`*.<name>.<subzona>` e `services.<name>.<subzona>`). IAM é global por conta e a subzona é uma só
  para a Organization: duas células com o mesmo `name` em duas regiões colidem — IAM com
  `EntityAlreadyExists`, Route 53 sobrescrevendo em silêncio.

  Tirar o default e obrigar a raiz a compor:

  ```hcl
  variable "name" {
    description = <<-EOT
      Nome da celula. Prefixo de todos os recursos, incluindo cinco roles de IAM e dois records do
      Route 53 — os dois namespaces GLOBAIS da conta. Tem de ser unico na Organization inteira, nao
      so na regiao, por isso a raiz o compoe com a regiao e nao ha default aqui.
    EOT
    type        = string
  }
  ```

  E na raiz, `regions/<r>/main.tf`: `name = "control-plane-${local.region}"`.

  `local.listener_rule_priority = 1 + parseint(substr(sha256(var.name), 0, 4), 16) % 50000` continua
  válido e melhora: o hash passa a diferir entre regiões. A prioridade é por listener e cada região
  tem o seu ALB, então não havia colisão — mas dois nomes iguais mascarariam um conflito real quando
  a segunda célula da *mesma* região chegar.

As seis variáveis novas que substituem data source, e nada mais — o resto de `control-plane/
variables.tf` atravessa como está:

```hcl
# --------------------------------------------------------------------------------------
# O hub, por referencia. Cada uma destas substitui um data source que a camada 04 usava para
# redescobrir por tag ou nome o que a camada 03 tinha acabado de criar. A diferenca nao e de
# estilo: com a referencia, a ordem de apply e de destroy passa a ser aresta do grafo, e os
# dois incidentes de `dial tcp <ip-privado>:443: i/o timeout` (2026-08-27 e 2026-08-28) eram
# arestas que faltavam por as duas pontas nao estarem no mesmo grafo.
# --------------------------------------------------------------------------------------

variable "hub_vpc_id" {
  description = "VPC hub. Era data.aws_vpc.hub, filtrada por tag:Name."
  type        = string
}

variable "hub_vpc_cidr_block" {
  description = <<-EOT
    CIDR da VPC hub. E a origem que o security group do cluster autoriza em 443: o Client VPN faz
    SNAT, entao o trafego do tunel chega a celula com origem AQUI, nao no client CIDR. Comprovado
    com pacote no 2.3 — liberar o client CIDR nao passa, liberar a VPC hub passa.
  EOT
  type        = string
}

variable "transit_gateway_id" {
  description = "TGW do hub. Era data.aws_ec2_transit_gateway.hub, filtrado por tag:Name = poc-hub-tgw."
  type        = string
}

variable "hub_transit_gateway_route_table_id" {
  description = "Route table do HUB — onde o attachment desta celula e propagado para o hub aprender a rota de volta. Era data.aws_ec2_transit_gateway_route_table.hub."
  type        = string
}

variable "hub_transit_gateway_attachment_id" {
  description = <<-EOT
    Attachment da propria VPC hub — o que esta celula propaga para a route table DELA, para
    aprender a rota ate o hub e, atras dele, ate o cliente VPN. Era
    data.aws_ec2_transit_gateway_vpc_attachment.hub.

    NAO confundir com o attachment desta celula: as duas propagacoes (spoke_to_hub e hub_to_spoke)
    nao podem ser trocadas entre si, e ha teste de mutacao especifico cobrindo isso.
  EOT
  type        = string
}

variable "hub_alb_listener_arn" {
  description = "Listener :443 compartilhado do ALB do hub. Era data.aws_lb_listener.hub_https, achado a partir de data.aws_lb.hub_ingress por nome."
  type        = string
}

variable "hub_alb_dns_name" {
  description = "Alvo do registro A alias desta celula. MUDA a cada recriacao do ALB — por isso vem por referencia, nunca fixado."
  type        = string
}

variable "hub_alb_zone_id" {
  description = "Zone id canonica do ALB, par obrigatorio do dns_name num registro alias."
  type        = string
}
```

- [ ] **Step 1: criar o módulo e mover os blocos**

```bash
cd /home/silvios/git/wasp-idp/aws/terraform
mkdir --parents src/cell/tests
git mv control-plane/main.tf     src/cell/main.tf
git mv control-plane/variables.tf src/cell/variables.tf
git mv control-plane/outputs.tf   src/cell/outputs.tf
git mv control-plane/tests/composition.tftest.hcl      src/cell/tests/
git mv control-plane/tests/ingress-alb.tftest.hcl      src/cell/tests/
git mv control-plane/tests/isolation.tftest.hcl        src/cell/tests/
git mv control-plane/tests/spoke-attachment.tftest.hcl src/cell/tests/
```

`providers.tf` **não** se move: os quatro providers (`aws`, `aws.network`, `kubernetes`, `helm`)
passam a ser configurados na raiz e recebidos pelo módulo. Em `src/cell/versions.tf`, declarar as
configuration aliases que o módulo exige:

```hcl
terraform {
  required_providers {
    aws = {
      source                = "hashicorp/aws"
      version               = "~> 6.0"
      configuration_aliases = [aws.network]
    }
    kubernetes = { source = "hashicorp/kubernetes", version = "~> 3.0" }
    helm       = { source = "hashicorp/helm", version = "~> 3.0" }
  }
}
```

Conferir as constraints contra o `versions.tf` da `control-plane/` antes de escrever: **módulo novo
herda a constraint da raiz que o consome, não a do registry**, e uma divergência faz o `init` da raiz
falhar com `no available releases match the given constraints` enquanto o `terraform test` do módulo
continua verde contra o `.terraform/modules` antigo.

- [ ] **Step 2: trocar os seis data sources por variável**

Em `src/cell/main.tf`, apagar os blocos `data "aws_vpc" "hub"`, `data "aws_ec2_transit_gateway"
"hub"`, `data "aws_ec2_transit_gateway_route_table" "hub"`, `data "aws_ec2_transit_gateway_vpc_
attachment" "hub"`, `data "aws_lb" "hub_ingress"` e `data "aws_lb_listener" "hub_https"`, e
substituir as referências:

| Antes | Depois |
|---|---|
| `data.aws_vpc.hub.id` | `var.hub_vpc_id` |
| `data.aws_vpc.hub.cidr_block` | `var.hub_vpc_cidr_block` |
| `data.aws_ec2_transit_gateway.hub.id` | `var.transit_gateway_id` |
| `data.aws_ec2_transit_gateway_route_table.hub.id` | `var.hub_transit_gateway_route_table_id` |
| `data.aws_ec2_transit_gateway_vpc_attachment.hub.id` | `var.hub_transit_gateway_attachment_id` |
| `data.aws_lb_listener.hub_https.arn` | `var.hub_alb_listener_arn` |
| `data.aws_lb.hub_ingress.dns_name` / `.zone_id` | `var.hub_alb_dns_name` / `var.hub_alb_zone_id` |

`data "aws_route53_zone" "subzone"` **fica**: a zona é da raiz `dns/`, externa a esta raiz, e
descobri-la por nome é o mecanismo certo para o que outra raiz possui.

Os `depends_on` que hoje apontam para `module.network` mais os seis recursos do TGW ficam **como
estão**. A lição de 2026-08-28 continua valendo dentro do módulo: os consumidores da API declaram
`depends_on` na rede, nunca o contrário, e a aresta serve às duas direções porque o destroy percorre
o mesmo grafo ao contrário. O que muda é que a aresta hub→célula deixa de precisar existir: ela é
derivada da referência a `var.transit_gateway_id`.

- [ ] **Step 3: ajustar os testes movidos**

Em cada arquivo de `src/cell/tests/`, os `override_data` dos seis data sources removidos viram
valores no bloco `variables`:

```hcl
variables {
  name                               = "control-plane"
  base_domain                        = "exemplo.com"
  network_account_id                 = "000000000000"
  target_account_ids                 = ["000000000000"]
  hub_vpc_id                         = "vpc-00000000000000001"
  hub_vpc_cidr_block                 = "10.1.0.0/16"
  transit_gateway_id                 = "tgw-00000000000000001"
  hub_transit_gateway_route_table_id = "tgw-rtb-00000000000000001"
  hub_transit_gateway_attachment_id  = "tgw-attach-00000000000000001"
  hub_alb_listener_arn               = "arn:aws:elasticloadbalancing:us-east-1:000000000000:listener/app/poc-hub-ingress/0000000000000001/0000000000000001"
  hub_alb_dns_name                   = "poc-hub-ingress-000000000.us-east-1.elb.amazonaws.com"
  hub_alb_zone_id                    = "Z35SXDOTRQ7X7K"
}
```

`hub_vpc_cidr_block` precisa ser um CIDR **real**: a regra de 443 o usa em `cidr_ipv4`, que tem
validação client-side, e um valor sintético do mock (`oz8pk32m`) derruba o plan de todos os arquivos
da suíte — a mordida já documentada em `aws/terraform/CLAUDE.md`.

- [ ] **Step 4: rodar a suíte do módulo**

```bash
cd /home/silvios/git/wasp-idp/aws/terraform/src/cell
terraform init -backend=false && terraform test -no-color 2>&1 | tail -25
```

Esperado: `Success!` com a mesma contagem de runs que a `control-plane/` tinha.

- [ ] **Step 5: commit**

```bash
cd /home/silvios/git/wasp-idp
git add aws/terraform/src/cell aws/terraform/control-plane
git commit -m "feat(terraform): extrair src/cell da camada control-plane

Os seis data sources que redescobriam o hub por tag e por nome viram variavel.
A subzona do Route 53 continua data source: pertence a raiz dns/.

Refs #36"
```

---

### Task 2: `module.cell` na raiz, e a ligação provada em teste

**Files:**
- Modify: `aws/terraform/regions/us-east-1/main.tf`
- Modify: `aws/terraform/regions/us-east-1/variables.tf`
- Modify: `aws/terraform/regions/us-east-1/outputs.tf`
- Modify: `aws/terraform/regions/us-east-1/tests/composition.tftest.hcl`

**Interfaces:**
- Consumes: `src/cell` da Task 1 e `src/hub` da fase 2.
- Produces: os outputs de aceite da região, consumidos pelos scripts da Task 4.

- [ ] **Step 1: escrever o teste que falha — a célula lê o hub, não um valor fixo**

Acrescentar a `regions/us-east-1/tests/composition.tftest.hcl`. **Dois runs com valores diferentes**,
porque um `override_module` sozinho passaria mesmo se a célula tivesse o valor fixo no código igual
ao injetado — é a armadilha já comprovada com `name_servers`:

```hcl
run "cell_reads_the_transit_gateway_from_the_hub" {
  command = plan

  override_data {
    target = data.aws_availability_zones.this
    values = { names = ["us-east-1a", "us-east-1b"] }
  }

  override_module {
    target = module.hub
    outputs = {
      vpc_id                        = "vpc-aaaaaaaaaaaaaaaa1"
      vpc_cidr_block                = "10.1.0.0/16"
      private_subnet_ids            = ["subnet-aaaa1", "subnet-aaaa2"]
      public_subnet_ids             = ["subnet-bbbb1", "subnet-bbbb2"]
      transit_gateway_id            = "tgw-aaaaaaaaaaaaaaaa1"
      transit_gateway_route_table_id = "tgw-rtb-aaaaaaaaaaaaaaaa1"
      transit_gateway_attachment_id = "tgw-attach-aaaaaaaaaaaaaaaa1"
      alb_arn                       = "arn:aws:elasticloadbalancing:us-east-1:000000000000:loadbalancer/app/poc-hub-ingress/aaaa1"
      alb_listener_arn              = "arn:aws:elasticloadbalancing:us-east-1:000000000000:listener/app/poc-hub-ingress/aaaa1/aaaa1"
      alb_dns_name                  = "hub-aaaa1.us-east-1.elb.amazonaws.com"
      alb_zone_id                   = "Z35SXDOTRQ7X7K"
      alb_security_group_id         = "sg-aaaa1"
      client_vpn_endpoint_id        = "cvpn-endpoint-aaaa1"
      client_vpn_dns_name           = "aaaa1.cvpn.us-east-1.amazonaws.com"
      authorized_group_ids          = ["00000000-0000-0000-0000-000000000000"]
    }
  }

  assert {
    condition     = module.cell.transit_gateway_id_in_use == "tgw-aaaaaaaaaaaaaaaa1"
    error_message = "a celula tem de usar o TGW que o hub produziu"
  }
}

run "cell_follows_a_different_hub" {
  command = plan

  override_data {
    target = data.aws_availability_zones.this
    values = { names = ["us-east-1a", "us-east-1b"] }
  }

  override_module {
    target = module.hub
    outputs = {
      # os mesmos campos do run acima, com valores DIFERENTES — repetir por inteiro, nao
      # referenciar o run anterior: nenhum valor fixo no codigo satisfaz os dois.
      vpc_id                        = "vpc-ccccccccccccccc9"
      vpc_cidr_block                = "10.9.0.0/16"
      private_subnet_ids            = ["subnet-cccc1", "subnet-cccc2"]
      public_subnet_ids             = ["subnet-dddd1", "subnet-dddd2"]
      transit_gateway_id            = "tgw-ccccccccccccccc9"
      transit_gateway_route_table_id = "tgw-rtb-ccccccccccccccc9"
      transit_gateway_attachment_id = "tgw-attach-ccccccccccccccc9"
      alb_arn                       = "arn:aws:elasticloadbalancing:us-east-1:000000000000:loadbalancer/app/poc-hub-ingress/cccc9"
      alb_listener_arn              = "arn:aws:elasticloadbalancing:us-east-1:000000000000:listener/app/poc-hub-ingress/cccc9/cccc9"
      alb_dns_name                  = "hub-cccc9.us-east-1.elb.amazonaws.com"
      alb_zone_id                   = "Z35SXDOTRQ7X7K"
      alb_security_group_id         = "sg-cccc9"
      client_vpn_endpoint_id        = "cvpn-endpoint-cccc9"
      client_vpn_dns_name           = "cccc9.cvpn.us-east-1.amazonaws.com"
      authorized_group_ids          = ["00000000-0000-0000-0000-000000000000"]
    }
  }

  assert {
    condition     = module.cell.transit_gateway_id_in_use == "tgw-ccccccccccccccc9"
    error_message = "o TGW tem de vir do hub, nao estar fixo no codigo da celula"
  }

  assert {
    condition     = module.cell.api_authorized_cidr == "10.9.0.0/16"
    error_message = "o SG do cluster tem de autorizar 443 a partir do CIDR da VPC HUB — o Client VPN faz SNAT"
  }
}
```

`src/cell/outputs.tf` precisa expor os dois valores que essas asserções leem — são os únicos campos
onde a ligação é observável em tempo de plan:

```hcl
output "transit_gateway_id_in_use" {
  description = "O TGW que esta celula anexou. Existe para a raiz assertar que ele veio do hub, nao de valor fixo."
  value       = var.transit_gateway_id
}

output "api_authorized_cidr" {
  description = "Origem autorizada em 443 no SG do cluster. Existe pela mesma razao do output acima."
  value       = var.hub_vpc_cidr_block
}
```

- [ ] **Step 2: rodar e ver falhar**

```bash
cd /home/silvios/git/wasp-idp/aws/terraform/regions/us-east-1
terraform test -no-color -filter=tests/composition.tftest.hcl 2>&1 | tail -30
```

Esperado: falha em `module.cell` inexistente (`Reference to undeclared module`).

- [ ] **Step 3: acrescentar `module.cell` e os providers dele**

Em `regions/us-east-1/main.tf`, depois de `module "hub"`:

```hcl
# Os providers kubernetes e helm sao configurados a partir de outputs de module.cell e aplicados no
# mesmo terraform apply: a configuracao do provider so precisa estar resolvida na hora de configura-lo,
# ja no apply. O que NAO pode e data source desses providers no plan — por isso o platform-bootstrap
# e resource, nunca data.
provider "kubernetes" {
  host                   = module.cell.cluster_endpoint
  cluster_ca_certificate = base64decode(module.cell.cluster_ca_data)

  exec {
    api_version = "client.authentication.k8s.io/v1beta1"
    command     = "aws"
    args        = ["eks", "get-token", "--cluster-name", module.cell.cluster_name, "--region", local.region, "--profile", var.aws_profile]
  }
}

# No provider helm 3.x o kubernetes deixou de ser bloco e virou atributo — note o `=`.
provider "helm" {
  kubernetes = {
    host                   = module.cell.cluster_endpoint
    cluster_ca_certificate = base64decode(module.cell.cluster_ca_data)

    exec = {
      api_version = "client.authentication.k8s.io/v1beta1"
      command     = "aws"
      args        = ["eks", "get-token", "--cluster-name", module.cell.cluster_name, "--region", local.region, "--profile", var.aws_profile]
    }
  }
}

module "cell" {
  source = "../../src/cell"

  providers = {
    aws         = aws
    aws.network = aws.network
    kubernetes  = kubernetes
    helm        = helm
  }

  name               = "control-plane"
  vpc_cidr           = local.cell_vpc_cidr
  availability_zones = local.availability_zones

  base_domain        = var.base_domain
  subzone_label      = var.subzone_label
  network_account_id = var.network_account_id
  target_account_ids = var.target_account_ids

  # O hub, por referencia. Cada linha aqui e um data source que morreu do outro lado.
  hub_vpc_id                         = module.hub.vpc_id
  hub_vpc_cidr_block                 = module.hub.vpc_cidr_block
  transit_gateway_id                 = module.hub.transit_gateway_id
  hub_transit_gateway_route_table_id = module.hub.transit_gateway_route_table_id
  hub_transit_gateway_attachment_id  = module.hub.transit_gateway_attachment_id
  hub_alb_listener_arn               = module.hub.alb_listener_arn
  hub_alb_dns_name                   = module.hub.alb_dns_name
  hub_alb_zone_id                    = module.hub.alb_zone_id
}
```

E acrescentar a `regions/us-east-1/variables.tf` as duas variáveis que faltavam:

```hcl
variable "network_account_id" {
  description = "Conta que hospeda a VPC hub. Declarada em variables/values.tfvars."
  type        = string
}

variable "target_account_ids" {
  description = "Contas onde o Crossplane cria recursos, via assume role. Declaradas em variables/values.tfvars."
  type        = list(string)
}
```

- [ ] **Step 4: repassar os outputs de aceite**

Em `regions/us-east-1/outputs.tf`:

```hcl
output "cell_services_url" {
  description = <<-EOT
    O aceite da regiao inteira: um curl NESTA url, da internet, sem tunel e sem -k, tem de devolver
    200. A cadeia que ele prova e ALB do hub -> TGW -> NLB interno -> Envoy -> pod.
  EOT
  value       = module.cell.cell_services_url
}

output "kubeconfig_command" {
  value = module.cell.kubeconfig_command
}

output "client_vpn_endpoint_id" {
  value = module.hub.client_vpn_endpoint_id
}

output "client_vpn_dns_name" {
  value = module.hub.client_vpn_dns_name
}
```

- [ ] **Step 5: guard offline contra colisão de nome de release**

`mock_provider "helm"` **não** simula a key `(namespace, name)` de releases: duas releases com o mesmo
nome passam verdes offline e só explodem no apply real com `cannot re-use a name that is still in
use`. Já aconteceu com `target_group_binding` e o gateway do `ingress_istio`. Acrescentar ao
`composition.tftest.hcl` da raiz:

```hcl
run "helm_release_names_do_not_collide" {
  command = plan

  override_data {
    target = data.aws_availability_zones.this
    values = { names = ["us-east-1a", "us-east-1b"] }
  }

  assert {
    condition     = length(toset(module.cell.helm_release_names)) == length(module.cell.helm_release_names)
    error_message = "duas releases com o mesmo nome no mesmo namespace: o mock nao pega isso, o apply real morre com 'cannot re-use a name that is still in use'"
  }
}
```

E em `src/cell/outputs.tf`, a lista que ele assere — montada de `"<namespace>/<name>"` de cada
`helm_release` do módulo, para que a colisão seja detectada pelo par certo, não só pelo nome:

```hcl
output "helm_release_names" {
  description = "Par namespace/nome de cada release desta celula. Existe so para o guard offline de colisao — o mock_provider do helm nao mantem estado de releases."
  value = compact([
    local.install_load_balancer_controller ? "kube-system/aws-load-balancer-controller" : "",
    local.install_ingress_istio ? "istio-system/istio-base" : "",
    local.install_ingress_istio ? "istio-system/istiod" : "",
    local.install_ingress_istio ? "istio-ingress/istio-ingress-gateway" : "",
    local.install_target_group_binding ? "istio-ingress/cell-target-group-binding" : "",
    local.install_httpbin ? "httpbin/httpbin" : "",
    local.install_external_secrets ? "external-secrets/external-secrets" : "",
    local.install_argocd ? "argocd/argo-cd" : "",
    local.install_crossplane ? "crossplane-system/crossplane" : "",
  ])
}
```

Conferir cada par contra o `name`/`namespace` real de cada `module` de helm em `src/cell/main.tf`
antes de escrever — uma lista que não reflete os releases de verdade é um guard que não guarda nada.

- [ ] **Step 6: rodar a suíte da raiz e provar a mutação**

```bash
cd /home/silvios/git/wasp-idp/aws/terraform/regions/us-east-1
terraform init -backend=false && terraform test -no-color 2>&1 | tail -25
```

Esperado: `Success!`. Depois, mutar: trocar `transit_gateway_id = module.hub.transit_gateway_id` por
`transit_gateway_id = "tgw-aaaaaaaaaaaaaaaa1"` (o valor do primeiro run) e rodar de novo.

Esperado: `cell_follows_a_different_hub` **falha**. Se passar, a asserção é vazia. Conferir com
`git diff` que a mutação foi aplicada antes de concluir qualquer coisa, e desfazê-la depois.

- [ ] **Step 7: commit**

```bash
cd /home/silvios/git/wasp-idp
git add aws/terraform/regions aws/terraform/src/cell
git commit -m "feat(terraform): ligar module.cell aos outputs do module.hub

Dois runs com valores diferentes provam que o TGW e o CIDR do hub vem por
referencia, nao de valor fixo. Guard offline de colisao de nome de release.

Refs #36"
```

---

### Task 3: apply real, aceite ponta a ponta e o destroy da célula

**Files:**
- nenhum. O artefato é o state e as duas direções do grafo provadas.

**Interfaces:**
- Consumes: a raiz da Task 2.
- Produces: a prova que o ADR 0014 exige — **ordenação só se dá por boa depois de um apply E um
  destroy reais**, porque `terraform test` não assere grafo.

- [ ] **Step 1: preflight**

```bash
cd /home/silvios/git/wasp-idp
for p in personal network cicd; do echo "=== ${p} ==="; aws sts get-caller-identity --profile "${p}" --output json; done
aws-vpn-client get-connection-status --profile-name hub
```

O status tem de dizer `Connected`. Sem túnel o apply **não completa** — não é hardening quebrado, é o
preço consciente da postura privada.

- [ ] **Step 2: planejar e conferir o que o plan propõe**

```bash
cd /home/silvios/git/wasp-idp/aws/terraform/regions/us-east-1
terraform init -reconfigure -backend-config="bucket=tfstate-$(aws organizations describe-organization --profile personal --query Organization.Id --output text)"
terraform plan -no-color -out=/tmp/region-cell.tfplan 2>&1 | tail -40
terraform show -no-color /tmp/region-cell.tfplan | grep --count '^  # '
```

Conferir: os recursos do hub **não** aparecem (já aplicados na fase 2); os da célula aparecem, na casa
dos 60. Hub sendo recriado aqui significa que a fase 2 aplicou de uma árvore diferente — parar e
investigar antes de aplicar.

- [ ] **Step 3: aplicar, pelo usuário, em background**

```
! cd aws/terraform/regions/us-east-1 && nohup terraform apply -no-color /tmp/region-cell.tfplan > /tmp/apply-cell.log 2>&1 < /dev/null & disown
```

Anunciar `/tmp/apply-cell.log` assim que disparar. ~13 min.

- [ ] **Step 4: o aceite da célula — a cadeia inteira, sem `-k`**

```bash
cd /home/silvios/git/wasp-idp/aws/terraform/regions/us-east-1
url="$(terraform output -raw cell_services_url)"
echo "${url}"
dig +short "$(echo "${url}" | sed 's|https://||; s|/$||')"
curl --silent --show-error --fail "${url}" | head -5
```

Na ordem em que quebram: `dig` resolve o host → certificado do listener aceita o SNI → os dois target
groups (célula e hub) `healthy` → `curl` público sem `-k` devolve 200. **O host é `services.`, nunca
`app.`** — qualquer outro nome sob o wildcard cai no `fixed-response` 404 do listener, e o sintoma é
indistinguível de rota faltando no cluster.

- [ ] **Step 5: provar a outra direção do grafo — o destroy da célula**

Esta é a metade que os dois incidentes de 2026-08-27/28 mostraram não ser derivável do apply. Pelo
usuário:

```
! cd aws/terraform/regions/us-east-1 && nohup terraform destroy -no-color -auto-approve -target=module.cell > /tmp/destroy-cell.log 2>&1 < /dev/null & disown
```

Esperado: a célula inteira some e **o hub permanece**. Conferir:

```bash
cd /home/silvios/git/wasp-idp/aws/terraform/regions/us-east-1
terraform state list | grep --count '^module\.hub\.'    # > 0
terraform state list | grep --count '^module\.cell\.'   # 0
aws ec2 describe-transit-gateways --profile network --region us-east-1 --output json > /tmp/tgw.json
```

Um `dial tcp <ip-privado>:443: i/o timeout` no destroy significa que a rota até o endpoint privado foi
cortada antes de os objetos Kubernetes saírem — a mesma mordida de 2026-08-27. Recuperação:
`terraform state rm` dos objetos presos (são só objetos da API do Kubernetes, sem contraparte AWS
própria) e reaplicar o destroy. Registrar o achado em `aws/docs/known-broken.md` antes de corrigir.

- [ ] **Step 6: registrar as duas direções provadas**

Em `aws/terraform/CLAUDE.md`, na seção de `depends_on`, acrescentar a data e o resultado dos dois
sentidos. A frase que hoje diz "a do destroy ainda não [está provada]" fica falsa depois deste passo —
atualizar, não acrescentar ao lado.

- [ ] **Step 7: commit**

```bash
cd /home/silvios/git/wasp-idp
git add aws/terraform/CLAUDE.md aws/docs/known-broken.md
git commit -m "docs: registrar apply e destroy reais da regiao us-east-1

Refs #36"
```

---

### Task 4: os scripts da região

**Files:**
- Create: `aws/terraform/scripts/up-02-region`
- Create: `aws/terraform/scripts/down-cell`
- Modify: `aws/terraform/scripts/up-all`

**Interfaces:**
- Consumes: a raiz aplicável da Task 3.
- Produces: os comandos que a fase 4 documenta no `README.md`.

- [ ] **Step 1: `up-02-region` — hub por default, célula por opção explícita**

Molde dos `up-NN` atuais: `source lib`, `show_usage`, opções longas, 2 espaços, `"${variavel}"`
sempre entre aspas. O corpo:

```bash
set -e

require_tools aws jq terraform

root="${terraform_directory}/regions/${region}"
[ -d "${root}" ] || fail "missing root: ${root}"

values_file="${terraform_directory}/variables/values.tfvars"
[ -f "${values_file}" ] \
  || fail "missing ${values_file}. Copy variables/values.tfvars.example and fill in the identity values — see variables/README.md."

state_bucket="$(discover_state_bucket "${org_profile}")"
terraform_init "${root}" "${state_bucket}"

# The cell costs ~US$ 165/month and needs the Client VPN tunnel connected: the helm and kubernetes
# providers talk to the API server from this machine. Without --with-cell only the hub is applied,
# which is the region's resting state.
if [ "${with_cell}" == "true" ]; then
  terraform_plan_and_apply "${root}" "region-${region}" "${assume_yes}"
else
  step "Cell: skipped (~US\$ 165/month)"
  log "include it with --with-cell when that is the intent, and connect the tunnel first"
  (cd "${root}" && terraform apply -no-color -target=module.hub -input=false ${assume_yes:+-auto-approve})
fi
```

O `-target=module.hub` no caminho default é o espelho do `-target=module.cell` do teardown, e a razão
é a mesma: o estado desejado da raiz inclui a célula, e subir só o hub é um desvio deliberado. O
`show_usage` tem de dizer isso em voz alta, não escondê-lo.

- [ ] **Step 2: `down-cell` — o teardown noturno**

```bash
set -e

require_tools terraform

root="${terraform_directory}/regions/${region}"
state_bucket="$(discover_state_bucket "${org_profile}")"
terraform_init "${root}" "${state_bucket}"

cells="$( (cd "${root}" && terraform state list) | grep --count '^module\.cell\.' || true)"

if [ "${cells}" -eq 0 ]; then
  log "no cell resources in the state of ${region} — nothing to tear down"
  exit 0
fi

cat >&2 <<EOF

About to destroy ${cells} resource(s) of module.cell in ${region}.

The hub STAYS UP (TGW, Client VPN, ALB): that is the point of -target here, and
also why terraform prints a warning saying -target is not for routine use. The
region's desired state includes the cell, so a plain 'terraform plan' after this
will propose creating it again. That is not drift.

EOF
```

Seguido da confirmação (`read -r -p`, recusando qualquer coisa que não seja `yes` quando não houver
`--yes`) e do `destroy -target=module.cell` com log em `logs/` e `PIPESTATUS[0]`, como o `lib` já faz.

- [ ] **Step 3: reescrever `up-all` para três camadas**

A sequência passa de cinco para três: `up-00-state-backend` → `up-01-dns` → `up-02-region`. Atualizar
`show_usage` (a tabela de dependências, os custos e as opções `--with-connectivity`/
`--with-control-plane`, que viram `--with-cell`) e o corpo. A renumeração de `up-02-dns` para
`up-01-dns` é da fase 4, junto com a remoção das raízes antigas — até lá o `up-all` chama o nome
antigo.

- [ ] **Step 4: exercitar os dois scripts em `--help` e no caminho de erro**

```bash
cd /home/silvios/git/wasp-idp/aws/terraform
scripts/up-02-region --help
scripts/down-cell --help
mv variables/values.tfvars /tmp/values.tfvars.backup
scripts/up-02-region --yes ; echo "exit=${?}"
mv /tmp/values.tfvars.backup variables/values.tfvars
```

Esperado: saída não-zero com a mensagem sobre `values.tfvars`, antes de qualquer `terraform init`.

- [ ] **Step 5: commit**

```bash
cd /home/silvios/git/wasp-idp
git add aws/terraform/scripts
git commit -m "feat(terraform): scripts up-02-region e down-cell

O caminho default sobe so o hub; a celula exige --with-cell. down-cell explica o
-target em vez de esconde-lo.

Refs #36"
```

---

## Aceite da fase 3

- [ ] Nenhum data source em `src/cell` aponta para recurso do hub; os seis viraram variável, e só
      `data.aws_route53_zone.subzone` sobrevive (pertence à raiz `dns/`).
- [ ] O teste de composição prova a ligação com **dois runs de valores diferentes**, e a mutação que
      fixa o TGW no código deixa um deles vermelho.
- [ ] O guard offline de colisão de nome de release existe e assere pares `namespace/nome` reais.
- [ ] `curl` público, sem túnel e sem `-k`, em `cell_services_url` devolve 200.
- [ ] `terraform destroy -target=module.cell` derruba a célula e **deixa o hub de pé** — verificado em
      `terraform state list`, não presumido.
- [ ] `aws/terraform/CLAUDE.md` registra as duas direções do grafo provadas, com data.
- [ ] **(invariante)** `grep -rn 'us-east-1' aws/terraform/src/cell` não devolve nada fora de fixture
      de teste.
- [ ] **(invariante)** `variable "name"` de `src/cell` **não tem default**, e a raiz o compõe com
      `local.region`. Um default region-free é a segunda região colidindo em cinco roles de IAM.
- [ ] **(invariante)** um `terraform plan` da raiz com `local.region` trocado à mão para `us-west-2`
      e os dois CIDR trocados resolve sem erro de nome duplicado. Desfazer depois — é sonda, não
      mudança; a `us-west-2` de verdade é a fase 4.
