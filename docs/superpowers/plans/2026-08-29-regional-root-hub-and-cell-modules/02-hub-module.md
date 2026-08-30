# Fase 2 — `src/hub` e a raiz `regions/us-east-1/`

Colapsa `network-foundation/us-east-1/` (01) e `connectivity/us-east-1/` (03) num módulo só,
consumido por uma raiz regional. Ao fim desta fase a região tem o hub de pé, aplicado da raiz nova,
e a célula ainda não existe — que é um estado legítimo, o mesmo em que a `us-west-2` vai ficar.

**Pré-requisito:** fase 1 fechada e o `values.tfvars` de pé. A extração assume que nenhum valor é
descoberto.

**A regra que governa esta fase:** o módulo recebe por variável só o que a raiz decide; tudo que é
produto de outro recurso do próprio módulo vira referência interna. Os quatro data sources que a
`connectivity/` usa hoje para achar a VPC hub e suas subnets (`data.aws_vpc.hub`,
`data.aws_subnets.hub_private`, `data.aws_subnets.hub_public`, mais os dois `data.aws_route_table.*`)
**desaparecem**: dentro de `src/hub` a VPC é do próprio módulo, e `module.network` já expõe tudo
aquilo como output.

---

### Task 1: `src/hub` com a interface fechada

**Files:**
- Create: `aws/terraform/src/hub/main.tf` (de `connectivity/us-east-1/main.tf` + a chamada de `module "hub_network"` da `network-foundation/us-east-1/main.tf`)
- Create: `aws/terraform/src/hub/variables.tf`
- Create: `aws/terraform/src/hub/outputs.tf`
- Create: `aws/terraform/src/hub/versions.tf`

**Interfaces:**
- Consumes: `src/network` (já existe), com `name`, `vpc_cidr`, `availability_zones`,
  `enable_nat_gateway`, `tags`.
- Produces: a interface abaixo. **As fases 3 e 4 dependem destes nomes exatos** — a célula lê o hub
  só por eles.

`aws/terraform/src/hub/variables.tf`:

```hcl
variable "name" {
  description = "Nome do hub. Prefixo de todos os recursos e base das tags de descoberta."
  type        = string
  default     = "poc-hub"
}

variable "vpc_cidr" {
  description = "CIDR da VPC hub. Um /16 dentro do supernet 10.0.0.0/12 — N=0 e reservado a Organization."
  type        = string
}

variable "availability_zones" {
  description = "AZs da regiao. Duas: o Client VPN associa uma target network por AZ."
  type        = list(string)
}

variable "supernet" {
  description = <<-EOT
    A malha inteira, uma rota so. Rota e TOPOLOGIA — o que existe e e alcancavel; nao cresce com
    celula. O que cresce com celula e authorization rule, que e POLITICA.

    Decisao irreversivel documentada em aws/docs/network/01-cidr-addressing.md.
  EOT
  type        = string
  default     = "10.0.0.0/12"
}

variable "base_domain" {
  description = "Dominio raiz sob o qual a camada dns/ delegou a subzona. Sem default: identidade, e o repo e publico."
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$", var.base_domain))
    error_message = "base_domain deve ser um nome de dominio sem ponto final nem esquema (ex.: exemplo.com)."
  }
}

variable "subzone_label" {
  description = "Rotulo da subzona delegada. Tem de casar com o da raiz dns/."
  type        = string
  default     = "nonprod"
}

variable "client_cidr_block" {
  description = "Faixa de onde saem os IPs dos clientes do Client VPN. FORA do supernet de proposito, e imutavel depois de o endpoint existir."
  type        = string
  default     = "100.64.0.0/22"
}

variable "operator_group_ids" {
  description = "IDs (UUID) dos grupos do Identity Center com authorization rule para o supernet. Lista vazia com manage_authorization ligado e ERRO."
  type        = list(string)
}

variable "manage_authorization" {
  description = "Desliga as authorization rules. Tunel sobe e nada trafega — nao e estado de repouso."
  type        = bool
  default     = true
}

variable "saml_metadata_path" {
  description = "Caminho do metadata XML da aplicacao SAML do Identity Center, relativo a RAIZ que chama este modulo. Passo de console: a API CreateApplication so cria aplicacao OAuth 2.0."
  type        = string
}

variable "spoke_account_ids" {
  description = "Contas as quais o TGW e compartilhado via RAM, para que cada uma crie o proprio attachment."
  type        = list(string)
}

variable "tags" {
  description = "Tags acrescentadas aos recursos do hub."
  type        = map(string)
  default     = {}
}
```

`aws/terraform/src/hub/outputs.tf` — **esta é a superfície que a célula consome**, e cada output aqui
é um data source que morre do outro lado na fase 3:

```hcl
output "vpc_id" {
  description = "VPC hub. Substitui data.aws_vpc.hub na celula."
  value       = module.network.vpc_id
}

output "vpc_cidr_block" {
  description = "CIDR da VPC hub. E a origem que o security group do cluster autoriza em 443 — o Client VPN faz SNAT, entao o trafego chega com origem AQUI, nao no client CIDR."
  value       = module.network.vpc_cidr_block
}

output "private_subnet_ids" {
  description = "Subnets privadas do hub. Target networks do Client VPN."
  value       = module.network.private_subnet_ids
}

output "public_subnet_ids" {
  description = "Subnets publicas do hub. Onde o ALB de ingress vive."
  value       = module.network.public_subnet_ids
}

output "transit_gateway_id" {
  description = "Substitui data.aws_ec2_transit_gateway.hub na celula."
  value       = aws_ec2_transit_gateway.hub.id
}

output "transit_gateway_route_table_id" {
  description = "Route table do HUB. A da celula nasce no proprio modulo da celula. Substitui data.aws_ec2_transit_gateway_route_table.hub."
  value       = aws_ec2_transit_gateway_route_table.hub.id
}

output "transit_gateway_attachment_id" {
  description = "Attachment da propria VPC hub — o que a celula propaga para a route table dela. Substitui data.aws_ec2_transit_gateway_vpc_attachment.hub."
  value       = aws_ec2_transit_gateway_vpc_attachment.hub.id
}

output "alb_arn" {
  description = "ALB publico do hub. Substitui data.aws_lb.hub_ingress."
  value       = aws_lb.hub.arn
}

output "alb_listener_arn" {
  description = "Listener :443 compartilhado. Cada celula anexa o proprio certificado por SNI e a propria rule. Substitui data.aws_lb_listener.hub_https."
  value       = aws_lb_listener.https.arn
}

output "alb_dns_name" {
  description = "Alvo dos registros A alias das celulas. MUDA a cada recriacao do ALB."
  value       = aws_lb.hub.dns_name
}

output "alb_zone_id" {
  description = "Zone id canonica do ALB, par obrigatorio do dns_name num registro alias."
  value       = aws_lb.hub.zone_id
}

output "alb_security_group_id" {
  description = "SG do ALB."
  value       = aws_security_group.alb.id
}

output "client_vpn_endpoint_id" {
  value = aws_ec2_client_vpn_endpoint.hub.id
}

output "client_vpn_dns_name" {
  description = "Hostname que o client usa. MUDA a cada recriacao — nunca cachear um .ovpn."
  value       = aws_ec2_client_vpn_endpoint.hub.dns_name
}

output "authorized_group_ids" {
  description = "Grupos com authorization rule. Vazio significa tunel que sobe e nao trafega."
  value       = [for rule in aws_ec2_client_vpn_authorization_rule.operators : rule.access_group_id]
}
```

- [ ] **Step 1: criar o esqueleto do módulo e provar que o `init` funciona**

```bash
cd /home/silvios/git/wasp-idp/aws/terraform
mkdir --parents src/hub/tests
cp connectivity/us-east-1/versions.tf src/hub/versions.tf
```

Do `versions.tf` copiado, **remover o bloco `backend "s3"`** se houver — módulo não tem backend — e
manter só `required_version` e `required_providers`. Escrever `variables.tf` e `outputs.tf` com o
conteúdo acima, e um `main.tf` mínimo (só o `locals`) para o `init` passar:

```bash
cd src/hub && terraform init -backend=false
```

Esperado: `Terraform has been successfully initialized!`. Um `unknown provider` aqui significa
`versions.tf` incompleto — o erro clássico de inicializar diretório que ainda só tem testes.

- [ ] **Step 2: mover os recursos, trocando data source por referência interna**

De `connectivity/us-east-1/main.tf`, mover para `src/hub/main.tf` os 26 blocos de `resource`
(TGW, RAM, attachment do hub, ACM do VPN, SAML provider, Client VPN e suas rotas/rules, SG do ALB,
ALB, ACM default, listeners) e o `locals`. Traduções obrigatórias:

| Em `connectivity/` | Em `src/hub` |
|---|---|
| `local.name` | `var.name` |
| `local.supernet` | `var.supernet` |
| `data.aws_vpc.hub.id` | `module.network.vpc_id` |
| `data.aws_vpc.hub.cidr_block` | `module.network.vpc_cidr_block` |
| `data.aws_subnets.hub_private.ids` | `module.network.private_subnet_ids` |
| `data.aws_subnets.hub_public.ids` | `module.network.public_subnet_ids` |
| `data.aws_route_table.hub_private` / `hub_public` | outputs de route table id do `src/network` |
| `provider "aws"` inline | some — o provider é da raiz, passado por `providers = { aws = aws.network }` |

Acrescentar no topo a chamada que era a `network-foundation/`:

```hcl
module "network" {
  source = "../network"

  name               = var.name
  vpc_cidr           = var.vpc_cidr
  availability_zones = var.availability_zones

  # Sem TGW nada roteia pelo hub: os nos saem pelo NAT da propria VPC da celula. Ligar aqui
  # custaria ~US$ 32/mes servindo zero trafego. Ha teste cobrindo a ausencia do EIP.
  enable_nat_gateway = false

  tags = merge(var.tags, { role = "hub" })
}
```

Se `src/network` não expõe os ids das route tables, acrescentar os outputs lá — é o que substitui
`data.aws_route_table.hub_private`/`hub_public`.

- [ ] **Step 3: mover os testes e apontá-los para o módulo**

```bash
cd /home/silvios/git/wasp-idp/aws/terraform
git mv connectivity/us-east-1/tests/private-access.tftest.hcl src/hub/tests/
git mv connectivity/us-east-1/tests/hub-ingress.tftest.hcl    src/hub/tests/
git mv connectivity/us-east-1/tests/ingress.tftest.hcl        src/hub/tests/
git mv connectivity/us-east-1/tests/spoke-attachment.tftest.hcl src/hub/tests/
git mv connectivity/us-east-1/tests/fixtures                  src/hub/tests/fixtures
```

Em cada arquivo movido: os `override_data` dos quatro data sources que morreram (`data.aws_vpc.hub`,
`data.aws_subnets.*`, `data.aws_route_table.*`) viram `override_module { target = module.network }`
com os mesmos valores — o que era descoberto agora é produzido pelo submódulo. As asserções sobre
`data.aws_vpc.hub.cidr_block` passam a ler `module.network.vpc_cidr_block`.

- [ ] **Step 4: rodar a suíte do módulo**

```bash
cd /home/silvios/git/wasp-idp/aws/terraform/src/hub
terraform init -backend=false && terraform test -no-color 2>&1 | tail -20
```

Esperado: `Success!` com a mesma contagem de runs que a `connectivity/` tinha. Run que desapareceu é
cobertura perdida, não simplificação — se um teste não faz mais sentido no módulo, escrever por que
no arquivo em vez de apagar em silêncio.

- [ ] **Step 5: commit**

```bash
cd /home/silvios/git/wasp-idp
git add aws/terraform/src/hub aws/terraform/src/network
git commit -m "feat(terraform): extrair src/hub das camadas network-foundation e connectivity

VPC hub, TGW, Client VPN e ALB num modulo so. Os quatro data sources que
achavam a VPC hub por tag morrem: dentro do modulo a VPC e do proprio grafo.

Refs #36"
```

---

### Task 2: a raiz `regions/us-east-1/`

**Files:**
- Create: `aws/terraform/regions/us-east-1/main.tf`
- Create: `aws/terraform/regions/us-east-1/variables.tf`
- Create: `aws/terraform/regions/us-east-1/outputs.tf`
- Create: `aws/terraform/regions/us-east-1/versions.tf`
- Create: `aws/terraform/regions/us-east-1/tests/composition.tftest.hcl`

**Interfaces:**
- Consumes: `src/hub` da Task 1 e o `values.tfvars` da fase 1.
- Produces: a raiz onde `module.cell` entra na fase 3, e o par de providers que os dois módulos usam.

- [ ] **Step 1: escrever os providers, que são a decisão estrutural da raiz**

`aws/terraform/regions/us-east-1/main.tf`, no topo:

```hcl
# A raiz da regiao. Dois providers, porque a regiao tem duas contas: o hub vive na `network` e a
# celula na `cicd`. O provider DEFAULT e o da celula — assim um recurso sem provider explicito cai
# na conta da celula, que e o caso comum, e o hub e sempre explicito.
#
# ADR 0007 continua valendo: recurso da conta network com ciclo de vida de celula (certificado
# wildcard, target group, listener rule) mora no modulo da celula, com provider aliasado.
provider "aws" {
  region  = local.region
  profile = var.aws_profile

  default_tags {
    tags = {
      "managed-by" = "terraform"
      "layer"      = "region"
    }
  }
}

provider "aws" {
  alias   = "network"
  region  = local.region
  profile = var.network_profile

  default_tags {
    tags = {
      "managed-by" = "terraform"
      "layer"      = "region"
    }
  }
}

locals {
  # Regiao e CIDRs sao decisao de desenho documentada em aws/docs/network/01-cidr-addressing.md,
  # nao identidade: inline aqui, como a network-foundation ja fazia. N=0 e reservado a Organization.
  region        = "us-east-1"
  hub_vpc_cidr  = "10.1.0.0/16"
  cell_vpc_cidr = "10.2.0.0/16"

  # Duas AZs: o Client VPN associa uma target network por AZ e o NLB interno da celula fixa um IP
  # privado por AZ.
  availability_zones = slice(data.aws_availability_zones.this.names, 0, 2)
}

data "aws_availability_zones" "this" {
  state = "available"
}

module "hub" {
  source = "../../src/hub"

  providers = {
    aws = aws.network
  }

  name               = "poc-hub"
  vpc_cidr           = local.hub_vpc_cidr
  availability_zones = local.availability_zones

  base_domain        = var.base_domain
  subzone_label      = var.subzone_label
  operator_group_ids = var.operator_group_ids
  spoke_account_ids  = var.spoke_account_ids
  saml_metadata_path = var.saml_metadata_path
}
```

- [ ] **Step 2: `variables.tf` da raiz — só identidade e profiles**

```hcl
variable "base_domain" {
  description = <<-EOT
    Dominio raiz sob o qual a camada dns/ delegou a subzona.

    SEM DEFAULT de proposito: e valor por-conta num repo publico, e a ausencia faz o plan falhar
    com uma mensagem que diz o que falta — em vez de herdar o dominio de outra conta. Declarado em
    variables/values.tfvars, carregado por values.auto.tfvars.
  EOT
  type        = string

  validation {
    condition     = length(var.base_domain) > 0 && !endswith(var.base_domain, ".") && length(split(".", var.base_domain)) >= 2
    error_message = "base_domain deve ser um dominio sem ponto final, com ao menos dois labels, recebido ${var.base_domain}."
  }
}

variable "subzone_label" {
  description = "Label da subzona delegada pela camada dns/. `sandbox` NAO e ambiente de teste — o de teste e nonprod."
  type        = string
  default     = "nonprod"
}

variable "aws_profile" {
  description = "Profile local com acesso a conta cicd, dona da celula. Provider default desta raiz."
  type        = string
  default     = "cicd"
}

variable "network_profile" {
  description = "Profile local com acesso a conta network, dona da VPC hub, do TGW e do ALB."
  type        = string
  default     = "network"
}

variable "operator_group_ids" {
  description = "IDs (UUID) dos grupos do Identity Center com authorization rule no Client VPN."
  type        = list(string)
}

variable "spoke_account_ids" {
  description = "Contas as quais o TGW e compartilhado via RAM. Uma por celula."
  type        = list(string)
}

variable "saml_metadata_path" {
  description = "Caminho do metadata XML da aplicacao SAML, relativo a esta raiz. Passo de console."
  type        = string
  default     = "saml-metadata.xml"
}
```

`network_account_id` e `target_account_ids` entram na fase 3, junto com `module.cell`. Até lá o
`values.tfvars` os traz e a raiz os ignora com warning — esperado, é o preço do arquivo único.

- [ ] **Step 3: `versions.tf` com o backend e a key própria**

Copiar de `connectivity/us-east-1/versions.tf`, trocando só a `key`:

```hcl
terraform {
  backend "s3" {
    # bucket entra por -backend-config: o nome real carrega o id da Organization.
    key     = "regions/us-east-1/terraform.tfstate"
    region  = "us-east-1"
    profile = "network"
    encrypt = true
  }
}
```

`profile` DENTRO do bloco `backend` — o backend é inicializado antes de o provider ser configurado e
não herda `profile` do bloco `provider`.

- [ ] **Step 4: o symlink do tfvars e o do metadata SAML**

```bash
cd /home/silvios/git/wasp-idp/aws/terraform/regions/us-east-1
ln --symbolic ../../variables/values.tfvars values.auto.tfvars
ln --symbolic ../../connectivity/us-east-1/saml-metadata.xml saml-metadata.xml
git check-ignore values.auto.tfvars saml-metadata.xml
```

Esperado: as duas linhas ecoadas. O symlink do metadata é temporário — a fase 4 move o arquivo para
cá quando a `connectivity/` for apagada.

- [ ] **Step 5: o teste de composição da raiz**

`aws/terraform/regions/us-east-1/tests/composition.tftest.hcl` — nesta fase ele cobre só o que a raiz
decide (as AZs e os CIDRs); a ligação hub→célula entra na fase 3:

```hcl
mock_provider "aws" {}
mock_provider "aws" { alias = "network" }

variables {
  base_domain        = "exemplo.com"
  operator_group_ids = ["00000000-0000-0000-0000-000000000000"]
  spoke_account_ids  = ["000000000000"]
  saml_metadata_path = "../../src/hub/tests/fixtures/saml-metadata.xml"
}

run "hub_gets_the_first_two_availability_zones" {
  command = plan

  override_data {
    target = data.aws_availability_zones.this
    values = {
      names = ["us-east-1a", "us-east-1b", "us-east-1c"]
    }
  }

  assert {
    condition     = toset(module.hub.private_subnet_ids) != toset([])
    error_message = "o hub tem de nascer com subnets privadas — sao as target networks do Client VPN"
  }
}

run "hub_and_cell_cidrs_do_not_overlap" {
  command = plan

  override_data {
    target = data.aws_availability_zones.this
    values = {
      names = ["us-east-1a", "us-east-1b"]
    }
  }

  # Nao ha funcao de containment de CIDR no Terraform; a comparacao de octeto e o caminho, o mesmo
  # padrao ja usado na validacao do client_cidr_block.
  assert {
    condition     = split(".", local.hub_vpc_cidr)[1] != split(".", local.cell_vpc_cidr)[1]
    error_message = "hub e celula nao podem dividir o mesmo /16 do supernet"
  }
}
```

- [ ] **Step 6: rodar e commitar**

```bash
cd /home/silvios/git/wasp-idp/aws/terraform/regions/us-east-1
terraform init -backend=false && terraform test -no-color 2>&1 | tail -20
```

Esperado: `Success!`, 2 runs.

```bash
cd /home/silvios/git/wasp-idp
git add aws/terraform/regions
git commit -m "feat(terraform): criar a raiz regional us-east-1 com module.hub

Dois providers (celula na cicd como default, hub na network aliasado), regiao e
CIDRs inline, identidade vindo do values.tfvars unico.

Refs #36"
```

---

### Task 3: destruir a 01/03 e subir o hub da raiz nova

**Files:**
- nenhum. Esta task é operação na AWS, e o artefato dela é o state.

**Interfaces:**
- Consumes: a raiz da Task 2.
- Produces: o hub aplicado sob a key `regions/us-east-1/terraform.tfstate`, que a fase 3 estende.

O ADR 0014 decide não migrar state: a `connectivity/` está com zero recursos e a
`network-foundation/` tem 13 sem dado e sem custo por hora. O corte é destruir e reaplicar.

- [ ] **Step 1: confirmar o ponto de partida antes de destruir nada**

```bash
cd /home/silvios/git/wasp-idp/aws/terraform
for m in control-plane connectivity/us-east-1 network-foundation/us-east-1; do
  printf '%-32s %s\n' "${m}" "$( (cd "${m}" && terraform state list 2>/dev/null | grep -vc '^data\.') )"
done
```

Esperado: `0`, `0` ou mais (a 03 pode estar de pé desde a fase 1), `13`. **Uma linha `0` na
`network-foundation` significa credencial caída, não camada vazia** — conferir com
`aws sts get-caller-identity --profile network --output json` antes de concluir qualquer coisa.

- [ ] **Step 2: derrubar a 03, se estiver de pé, e depois a 01**

Pelo usuário, nesta ordem (o TGW não deleta com attachment vivo):

```
! aws/terraform/connectivity/us-east-1/scripts/destroy
! cd aws/terraform/network-foundation/us-east-1 && nohup terraform destroy -no-color -auto-approve > /tmp/destroy-01.log 2>&1 < /dev/null & disown
```

Anunciar `/tmp/destroy-01.log` assim que disparar, não só quando terminar.

- [ ] **Step 3: aplicar a raiz nova**

```bash
cd /home/silvios/git/wasp-idp/aws/terraform/regions/us-east-1
terraform init -reconfigure -backend-config="bucket=$(aws organizations describe-organization --profile personal --query Organization.Id --output text | sed 's/^/tfstate-/')"
terraform plan -no-color -out=/tmp/region-us-east-1.tfplan
```

Conferir no plan que **não** aparecem `aws_nat_gateway` nem `aws_eip` — o hub é `enable_nat_gateway
= false` de propósito, e um NAT ali custaria ~US$ 32/mês servindo zero tráfego.

Depois, pelo usuário:

```
! cd aws/terraform/regions/us-east-1 && nohup terraform apply -no-color /tmp/region-us-east-1.tfplan > /tmp/apply-region.log 2>&1 < /dev/null & disown
```

- [ ] **Step 4: provar que o hub serve, não só que aplicou**

```bash
cd /home/silvios/git/wasp-idp/aws/terraform/regions/us-east-1
terraform output
aws ec2 export-client-vpn-client-configuration \
  --client-vpn-endpoint-id "$(terraform output -raw client_vpn_endpoint_id)" \
  --profile network --region us-east-1 --output text > /tmp/hub.ovpn
```

E, pelo usuário, `! aws-vpn-client import-profile --profile-name hub --config-path /tmp/hub.ovpn` e
`! aws-vpn-client connect --profile-name hub`, até
`aws-vpn-client get-connection-status --profile-name hub` dizer `Connected`.

O `.ovpn` de sessões anteriores está sempre inválido — o DNS name muda a cada recriação do endpoint.
Reexportar sempre.

- [ ] **Step 5: registrar o estado no `HANDOFF.md`**

Uma linha no "Estado atual": a região `us-east-1` passou a ser uma raiz só, com o hub aplicado e a
célula ainda fora. O comando de conferência do `HANDOFF.md` lista as raízes antigas — atualizar a
lista, senão a próxima sessão lê `0` em `connectivity/` e conclui a coisa errada.

- [ ] **Step 6: commit**

```bash
cd /home/silvios/git/wasp-idp
git add HANDOFF.md
git commit -m "docs: registrar o hub aplicado da raiz regional

Refs #36"
```

---

## Aceite da fase 2

- [ ] `src/hub` passa `terraform test` com a mesma cobertura que a `connectivity/` tinha, e nenhum
      `data.aws_vpc.hub` / `data.aws_subnets.*` / `data.aws_route_table.*` sobrevive nele.
- [ ] `regions/us-east-1/` planeja e aplica com `terraform plan` puro — sem `-var-file`, sem passo de
      geração.
- [ ] O hub está de pé aplicado da raiz nova, com TGW, ALB e Client VPN, e **sem NAT Gateway**.
- [ ] O túnel do Client VPN conecta com o `.ovpn` exportado do endpoint corrente.
- [ ] `.terraform/modules/modules.json` da raiz lista `hub` e `hub.network` — módulo ausente ali
      significa teste da raiz rodando contra árvore velha.
