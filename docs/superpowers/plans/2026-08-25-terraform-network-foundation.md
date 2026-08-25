# Terraform Network Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Entregar a camada 1 do módulo de bootstrap — VPC hub na conta `network` e o bucket S3 de state que o Terraform passa a usar — mais o submódulo `src/network` que a camada 2 reusará para a VPC spoke.

**Architecture:** Dois submódulos reusáveis (`src/network`, `src/state-backend`) compostos por uma raiz `network-foundation`. A raiz nasce com state local, cria o próprio bucket e migra o state para ele. `src/network` calcula as subnets a partir do CIDR com `cidrsubnet()` — não herda o hardcode `172.16.x` da Composition de referência.

**Tech Stack:** Terraform 1.15.8, provider `hashicorp/aws ~> 6.0`, framework de teste nativo (`.tftest.hcl` + `mock_provider`), perfil AWS `network` assumindo `OrganizationAccountAccessRole`.

**Spec:** `docs/superpowers/specs/2026-08-25-terraform-bootstrap-module-design.md`

## Global Constraints

- `required_version = ">= 1.15"` em todo módulo; provider `hashicorp/aws` em `~> 6.0`.
- Região: `us-east-1`. É a única região aprovada pela SCP `DenyOutsideApprovedRegions`.
- Supernet `10.0.0.0/12`, um `/16` por VPC. `10.0.0.0/16` (N=0) reservado para a Organization. Hub = `10.1.0.0/16`. Ver `aws/docs/network/01-cidr-addressing.md`. **É a única decisão irreversível da cadeia.**
- Exatamente **2 AZs**. O EKS exige 2 distintas e a lista de subnets do control plane é imutável depois de criado o cluster.
- **Nenhum account id, e-mail ou hosted zone id real em arquivo versionado.** Placeholders `<...>` em `terraform.tfvars.example`; valores reais em `terraform.tfvars` (gitignored) e em `CLAUDE.local.md`.
- Nome de arquivo e H1 de documentação em inglês; corpo em pt-BR.
- `.terraform.lock.hcl` **é** versionado. `.terraform/`, `*.tfstate*` e `terraform.tfvars` não.
- Nenhum `terraform apply` contra a AWS sem autorização explícita do Silvio (Task 5).

---

### Task 1: `src/network` — VPC e subnets calculadas do CIDR

**Files:**
- Create: `aws/terraform/src/network/versions.tf`
- Create: `aws/terraform/src/network/variables.tf`
- Create: `aws/terraform/src/network/main.tf`
- Create: `aws/terraform/src/network/outputs.tf`
- Test: `aws/terraform/src/network/tests/cidr.tftest.hcl`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: nada (primeiro módulo).
- Produces: módulo em `../src/network` com variáveis `name` (string), `vpc_cidr` (string), `availability_zones` (list(string), exatamente 2), `subnet_newbits` (number, default 4), `enable_nat_gateway` (bool, default true), `tags` (map(string), default {}). Outputs `vpc_id`, `vpc_cidr`, `public_subnet_ids` (list), `private_subnet_ids` (list), `control_plane_subnet_ids` (list de 4). Recursos endereçáveis em teste: `aws_vpc.this`, `aws_subnet.public[*]`, `aws_subnet.private[*]`.

- [ ] **Step 1: Escrever o teste que falha**

Criar `aws/terraform/src/network/tests/cidr.tftest.hcl`:

```hcl
# mock_provider: nenhuma chamada à AWS, nenhuma credencial. `command = plan` avalia os
# locals e os argumentos dos recursos, que é onde vive a aritmética de CIDR.
mock_provider "aws" {}

variables {
  name               = "test"
  availability_zones = ["us-east-1a", "us-east-1b"]
}

run "divide_um_slash16_em_quatro_slash20" {
  command = plan

  variables {
    vpc_cidr = "10.1.0.0/16"
  }

  assert {
    condition     = aws_vpc.this.cidr_block == "10.1.0.0/16"
    error_message = "CIDR da VPC deveria ser 10.1.0.0/16, veio ${aws_vpc.this.cidr_block}"
  }

  assert {
    condition     = aws_subnet.public[0].cidr_block == "10.1.0.0/20"
    error_message = "public[0] deveria ser 10.1.0.0/20, veio ${aws_subnet.public[0].cidr_block}"
  }

  assert {
    condition     = aws_subnet.public[1].cidr_block == "10.1.16.0/20"
    error_message = "public[1] deveria ser 10.1.16.0/20, veio ${aws_subnet.public[1].cidr_block}"
  }

  assert {
    condition     = aws_subnet.private[0].cidr_block == "10.1.32.0/20"
    error_message = "private[0] deveria ser 10.1.32.0/20, veio ${aws_subnet.private[0].cidr_block}"
  }

  assert {
    condition     = aws_subnet.private[1].cidr_block == "10.1.48.0/20"
    error_message = "private[1] deveria ser 10.1.48.0/20, veio ${aws_subnet.private[1].cidr_block}"
  }
}

# Prova que a aritmética é derivada do CIDR e não hardcoded — é o gap da Composition de
# referência que este módulo existe para não herdar.
run "acompanha_um_cidr_diferente" {
  command = plan

  variables {
    vpc_cidr = "10.2.0.0/16"
  }

  assert {
    condition     = aws_subnet.public[0].cidr_block == "10.2.0.0/20"
    error_message = "trocar o CIDR deveria mover as subnets; public[0] veio ${aws_subnet.public[0].cidr_block}"
  }

  assert {
    condition     = aws_subnet.private[1].cidr_block == "10.2.48.0/20"
    error_message = "trocar o CIDR deveria mover as subnets; private[1] veio ${aws_subnet.private[1].cidr_block}"
  }
}

run "as_subnets_nao_se_sobrepoem" {
  command = plan

  variables {
    vpc_cidr = "10.1.0.0/16"
  }

  assert {
    condition = length(distinct(concat(
      aws_subnet.public[*].cidr_block,
      aws_subnet.private[*].cidr_block,
    ))) == 4
    error_message = "as 4 subnets deveriam ter CIDRs distintos"
  }
}

run "recusa_cidr_pequeno_demais" {
  command = plan

  variables {
    vpc_cidr = "10.1.0.0/24"
  }

  # Um /24 não cabe 4 subnets de /20 — a validação da variável tem de barrar antes do plan.
  expect_failures = [var.vpc_cidr]
}

run "recusa_numero_errado_de_azs" {
  command = plan

  variables {
    vpc_cidr           = "10.1.0.0/16"
    availability_zones = ["us-east-1a"]
  }

  expect_failures = [var.availability_zones]
}
```

- [ ] **Step 2: Rodar o teste para confirmar que falha**

```bash
cd aws/terraform/src/network
terraform init -backend=false
terraform test
```

Esperado: FAIL — as referências a `aws_vpc.this` e `var.vpc_cidr` não resolvem.

`terraform init` precisa rodar para baixar o schema do provider: `mock_provider` mocka as
chamadas de API, não o schema. Não precisa de credencial.

**Se o `init` recusar o diretório** por não haver nenhum `.tf` fora de `tests/`, criar primeiro
o `versions.tf` do Step 3 e repetir. O teste continua vermelho pelo motivo certo — os recursos
e a variável ainda não existem — e é esse o sinal que interessa.

- [ ] **Step 3: Escrever `versions.tf`**

```hcl
terraform {
  required_version = ">= 1.15"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}
```

- [ ] **Step 4: Escrever `variables.tf`**

```hcl
variable "name" {
  description = "Nome base dos recursos: <name>-vpc, <name>-public-<az>, <name>-rt-private, ..."
  type        = string
}

variable "vpc_cidr" {
  description = <<-EOT
    CIDR da VPC — um /16 do supernet 10.0.0.0/12 (ver aws/docs/network/01-cidr-addressing.md).
    As subnets são DERIVADAS deste valor com cidrsubnet(), nunca fixas.
  EOT
  type        = string

  validation {
    # Precisa caber 2 * length(availability_zones) subnets de (prefixo + subnet_newbits).
    # Com os defaults (2 AZs, newbits 4) o teto é /20 — um /24 não serve.
    condition     = can(cidrhost(var.vpc_cidr, 0)) && tonumber(split("/", var.vpc_cidr)[1]) <= 20
    error_message = "vpc_cidr deve ser um CIDR válido com prefixo /20 ou maior (ex.: 10.1.0.0/16)."
  }
}

variable "availability_zones" {
  description = <<-EOT
    Exatamente 2 AZs. O EKS exige 2 distintas, e a lista de subnets do control plane é
    IMUTÁVEL depois de criado o cluster — mudar aqui depois é recriar o cluster.
  EOT
  type        = list(string)

  validation {
    condition     = length(var.availability_zones) == 2
    error_message = "availability_zones deve conter exatamente 2 AZs."
  }

  validation {
    condition     = length(distinct(var.availability_zones)) == length(var.availability_zones)
    error_message = "as AZs devem ser distintas."
  }
}

variable "subnet_newbits" {
  description = <<-EOT
    Bits somados ao prefixo da VPC para cada subnet. 4 sobre um /16 dá /20 (4094 IPs úteis),
    consumindo 4 dos 16 blocos e deixando 12 livres. /24 seria pequeno para EKS: o VPC CNI
    tira o IP do pod da subnet do nó.
  EOT
  type        = number
  default     = 4
}

variable "enable_nat_gateway" {
  description = <<-EOT
    NAT Gateway + EIP + rota default na route table privada. Desligado, as subnets privadas
    ficam sem saída para a internet. A VPC hub não precisa enquanto não houver TGW — nada
    roteia por ela, e o NAT custaria ~US$ 32/mês servindo zero tráfego.
  EOT
  type        = bool
  default     = true
}

variable "tags" {
  description = "Tags adicionais, mescladas ao Name de cada recurso."
  type        = map(string)
  default     = {}
}
```

- [ ] **Step 5: Escrever `main.tf` — VPC e subnets**

```hcl
locals {
  # Índices 0..n-1 = públicas; n..2n-1 = privadas. Determinístico e derivado do CIDR.
  public_subnets = [
    for index, az in var.availability_zones : {
      az         = az
      cidr_block = cidrsubnet(var.vpc_cidr, var.subnet_newbits, index)
    }
  ]

  private_subnets = [
    for index, az in var.availability_zones : {
      az         = az
      cidr_block = cidrsubnet(var.vpc_cidr, var.subnet_newbits, index + length(var.availability_zones))
    }
  ]
}

resource "aws_vpc" "this" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = merge(var.tags, { Name = "${var.name}-vpc" })
}

resource "aws_subnet" "public" {
  count = length(local.public_subnets)

  vpc_id                  = aws_vpc.this.id
  cidr_block              = local.public_subnets[count.index].cidr_block
  availability_zone       = local.public_subnets[count.index].az
  map_public_ip_on_launch = true

  tags = merge(var.tags, {
    Name = "${var.name}-public-${local.public_subnets[count.index].az}"
    # Auto-discovery de subnet do AWS Load Balancer Controller. Inócuo no hub; obrigatório
    # na spoke, e o submódulo é o mesmo nos dois casos.
    "kubernetes.io/role/elb" = "1"
  })
}

resource "aws_subnet" "private" {
  count = length(local.private_subnets)

  vpc_id            = aws_vpc.this.id
  cidr_block        = local.private_subnets[count.index].cidr_block
  availability_zone = local.private_subnets[count.index].az

  tags = merge(var.tags, {
    Name                              = "${var.name}-private-${local.private_subnets[count.index].az}"
    "kubernetes.io/role/internal-elb" = "1"
  })
}
```

- [ ] **Step 6: Escrever `outputs.tf`**

```hcl
output "vpc_id" {
  description = "Equivalente a Network.status.vpcId na Composition de referência."
  value       = aws_vpc.this.id
}

output "vpc_cidr" {
  value = aws_vpc.this.cidr_block
}

output "public_subnet_ids" {
  value = aws_subnet.public[*].id
}

output "private_subnet_ids" {
  description = "As privadas — destino dos node groups."
  value       = aws_subnet.private[*].id
}

output "control_plane_subnet_ids" {
  description = <<-EOT
    As 4 subnets (públicas + privadas). Equivalente a
    Network.status.subnetIds.controlPlane; é o que o EKS consome.
  EOT
  value = concat(aws_subnet.public[*].id, aws_subnet.private[*].id)
}
```

- [ ] **Step 7: Rodar os testes e confirmar que passam**

```bash
cd aws/terraform/src/network
terraform init -backend=false
terraform fmt -check -recursive
terraform validate
terraform test
```

Esperado: `terraform test` reporta os 5 `run` como `pass`. Se `fmt -check` falhar, rodar `terraform fmt -recursive` e conferir o diff.

- [ ] **Step 8: Adicionar as regras de Terraform ao `.gitignore`**

Acrescentar ao `.gitignore` da raiz do repositório:

```gitignore
# Terraform
**/.terraform/*
*.tfstate
*.tfstate.*
*.tfplan
crash.log
crash.*.log
terraform.tfvars
!terraform.tfvars.example
```

`.terraform.lock.hcl` **não** entra na lista — o lock é versionado de propósito, é o que fixa o hash do provider.

- [ ] **Step 9: Commit**

```bash
git add .gitignore aws/terraform/src/network
git commit -m "feat(terraform): add src/network with CIDR-derived subnets

As subnets saem de cidrsubnet() sobre o CIDR da VPC, não de valores fixos.
A Composition de referência tem as 4 subnets hardcoded em 172.16.{1,2,3,4}.0/24
e marca parametrizar como follow-up; herdar isso custaria a única decisão
irreversível da cadeia (o plano de CIDR).

Testes com mock_provider e command = plan: nenhuma chamada à AWS, nenhuma
credencial, e o caso 'acompanha um cidr diferente' prova que a aritmética é
derivada e não coincidência."
```

---

### Task 2: `src/network` — gateways, roteamento e o NAT opcional

**Files:**
- Modify: `aws/terraform/src/network/main.tf` (acrescentar ao final)
- Test: `aws/terraform/src/network/tests/routing.tftest.hcl`

**Interfaces:**
- Consumes: de Task 1 — `aws_vpc.this`, `aws_subnet.public`, `aws_subnet.private`, `var.enable_nat_gateway`, `var.name`, `var.tags`.
- Produces: recursos `aws_internet_gateway.this`, `aws_eip.nat[*]`, `aws_nat_gateway.this[*]`, `aws_route_table.public`, `aws_route_table.private`, `aws_route.public_default`, `aws_route.private_default[*]`, `aws_route_table_association.public[*]`, `aws_route_table_association.private[*]`. Com `enable_nat_gateway = true` o módulo tem **16 recursos**, paridade 1:1 com a camada L1a da Composition.

- [ ] **Step 1: Escrever o teste que falha**

Criar `aws/terraform/src/network/tests/routing.tftest.hcl`:

```hcl
mock_provider "aws" {}

variables {
  name               = "test"
  vpc_cidr           = "10.1.0.0/16"
  availability_zones = ["us-east-1a", "us-east-1b"]
}

run "com_nat_ligado_cria_os_16_recursos_da_l1a" {
  command = plan

  variables {
    enable_nat_gateway = true
  }

  assert {
    condition     = length(aws_eip.nat) == 1
    error_message = "com NAT ligado deveria haver 1 EIP, há ${length(aws_eip.nat)}"
  }

  assert {
    condition     = length(aws_nat_gateway.this) == 1
    error_message = "com NAT ligado deveria haver 1 NAT Gateway, há ${length(aws_nat_gateway.this)}"
  }

  assert {
    condition     = length(aws_route.private_default) == 1
    error_message = "a route table privada deveria ter rota default via NAT"
  }

  assert {
    condition     = aws_route.private_default[0].destination_cidr_block == "0.0.0.0/0"
    error_message = "a rota privada deveria ser 0.0.0.0/0"
  }

  # O NAT tem de nascer numa subnet PÚBLICA — numa privada ele não alcança o IGW.
  assert {
    condition     = aws_nat_gateway.this[0].subnet_id == aws_subnet.public[0].id
    error_message = "o NAT Gateway deveria estar na primeira subnet pública"
  }
}

run "com_nat_desligado_nao_cria_nem_nat_nem_rota_privada" {
  command = plan

  variables {
    enable_nat_gateway = false
  }

  assert {
    condition     = length(aws_nat_gateway.this) == 0
    error_message = "com NAT desligado não deveria haver NAT Gateway"
  }

  assert {
    condition     = length(aws_eip.nat) == 0
    error_message = "com NAT desligado não deveria haver EIP — é o que mantém o custo em zero"
  }

  assert {
    condition     = length(aws_route.private_default) == 0
    error_message = "sem NAT não há rota default privada possível"
  }

  # O IGW e a rota pública existem nos dois casos.
  assert {
    condition     = aws_route.public_default.destination_cidr_block == "0.0.0.0/0"
    error_message = "a rota pública default deveria existir mesmo sem NAT"
  }
}

run "toda_subnet_esta_associada_a_uma_route_table" {
  command = plan

  variables {
    enable_nat_gateway = true
  }

  assert {
    condition     = length(aws_route_table_association.public) == 2
    error_message = "as 2 subnets públicas deveriam estar associadas"
  }

  assert {
    condition     = length(aws_route_table_association.private) == 2
    error_message = "as 2 subnets privadas deveriam estar associadas"
  }
}
```

- [ ] **Step 2: Rodar o teste para confirmar que falha**

```bash
cd aws/terraform/src/network
terraform test -filter=tests/routing.tftest.hcl
```

Esperado: FAIL — `aws_internet_gateway.this`, `aws_nat_gateway.this` etc. não existem.

- [ ] **Step 3: Acrescentar os recursos ao `main.tf`**

```hcl
resource "aws_internet_gateway" "this" {
  vpc_id = aws_vpc.this.id

  tags = merge(var.tags, { Name = "${var.name}-igw" })
}

resource "aws_eip" "nat" {
  count = var.enable_nat_gateway ? 1 : 0

  domain = "vpc"

  tags = merge(var.tags, { Name = "${var.name}-nat-eip" })
}

resource "aws_nat_gateway" "this" {
  count = var.enable_nat_gateway ? 1 : 0

  allocation_id = aws_eip.nat[0].id
  # Subnet PÚBLICA: numa privada o NAT não alcança o IGW e não sai tráfego.
  subnet_id = aws_subnet.public[0].id

  tags = merge(var.tags, { Name = "${var.name}-nat" })

  # A AWS exige o IGW anexado antes de alocar o NAT.
  depends_on = [aws_internet_gateway.this]
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.this.id

  tags = merge(var.tags, { Name = "${var.name}-rt-public" })
}

resource "aws_route" "public_default" {
  route_table_id         = aws_route_table.public.id
  destination_cidr_block = "0.0.0.0/0"
  gateway_id             = aws_internet_gateway.this.id
}

resource "aws_route_table" "private" {
  vpc_id = aws_vpc.this.id

  tags = merge(var.tags, { Name = "${var.name}-rt-private" })
}

resource "aws_route" "private_default" {
  count = var.enable_nat_gateway ? 1 : 0

  route_table_id         = aws_route_table.private.id
  destination_cidr_block = "0.0.0.0/0"
  nat_gateway_id         = aws_nat_gateway.this[0].id
}

resource "aws_route_table_association" "public" {
  count = length(aws_subnet.public)

  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

resource "aws_route_table_association" "private" {
  count = length(aws_subnet.private)

  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private.id
}
```

- [ ] **Step 4: Rodar todos os testes do submódulo**

```bash
cd aws/terraform/src/network
terraform fmt -check -recursive
terraform validate
terraform test
```

Esperado: os 5 `run` de `cidr.tftest.hcl` e os 3 de `routing.tftest.hcl` como `pass`.

- [ ] **Step 5: Commit**

```bash
git add aws/terraform/src/network
git commit -m "feat(terraform): add gateways and routing to src/network

Com enable_nat_gateway = true o módulo tem 16 recursos — paridade 1:1 com a
camada L1a da Composition de referência (VPC -> RouteTableAssociation).

O NAT é opcional porque a VPC hub não tem para onde rotear enquanto não
houver TGW: ligá-lo lá custaria ~US\$32/mês servindo zero tráfego. Teste
cobre os dois caminhos, incluindo a ausência do EIP com o flag desligado."
```

---

### Task 3: `src/state-backend` — bucket S3 endurecido

**Files:**
- Create: `aws/terraform/src/state-backend/versions.tf`
- Create: `aws/terraform/src/state-backend/variables.tf`
- Create: `aws/terraform/src/state-backend/main.tf`
- Create: `aws/terraform/src/state-backend/outputs.tf`
- Test: `aws/terraform/src/state-backend/tests/hardening.tftest.hcl`

**Interfaces:**
- Consumes: nada.
- Produces: módulo em `../src/state-backend` com variáveis `bucket_name` (string) e `tags` (map(string), default {}). Outputs `bucket_name` (string), `bucket_arn` (string). Recursos: `aws_s3_bucket.this`, `aws_s3_bucket_versioning.this`, `aws_s3_bucket_server_side_encryption_configuration.this`, `aws_s3_bucket_public_access_block.this`, `aws_s3_bucket_ownership_controls.this`, `aws_s3_bucket_policy.this`.

- [ ] **Step 1: Escrever o teste que falha**

Criar `aws/terraform/src/state-backend/tests/hardening.tftest.hcl`:

```hcl
mock_provider "aws" {}

variables {
  bucket_name = "test-tfstate-bucket"
}

run "versionamento_ligado" {
  command = plan

  # Versionamento é o que permite recuperar um state corrompido por apply concorrente.
  assert {
    condition     = aws_s3_bucket_versioning.this.versioning_configuration[0].status == "Enabled"
    error_message = "versionamento do bucket de state deveria estar Enabled"
  }
}

run "acesso_publico_bloqueado_nas_quatro_dimensoes" {
  command = plan

  assert {
    condition = alltrue([
      aws_s3_bucket_public_access_block.this.block_public_acls,
      aws_s3_bucket_public_access_block.this.block_public_policy,
      aws_s3_bucket_public_access_block.this.ignore_public_acls,
      aws_s3_bucket_public_access_block.this.restrict_public_buckets,
    ])
    error_message = "as 4 chaves do public access block deveriam ser true"
  }
}

run "criptografia_em_repouso" {
  command = plan

  assert {
    condition     = aws_s3_bucket_server_side_encryption_configuration.this.rule[0].apply_server_side_encryption_by_default[0].sse_algorithm == "AES256"
    error_message = "o bucket deveria ter SSE-S3 (AES256) por default"
  }
}

run "acl_desabilitada" {
  command = plan

  assert {
    condition     = aws_s3_bucket_ownership_controls.this.rule[0].object_ownership == "BucketOwnerEnforced"
    error_message = "object ownership deveria ser BucketOwnerEnforced (ACLs desligadas)"
  }
}

run "nega_transporte_inseguro" {
  command = plan

  # A policy é montada com jsonencode() a partir de var.bucket_name — não de
  # aws_s3_bucket.this.arn — justamente para ser conhecida em tempo de plan e
  # portanto asseverável sob mock_provider.
  assert {
    condition     = jsondecode(aws_s3_bucket_policy.this.policy).Statement[0].Effect == "Deny"
    error_message = "a policy deveria ter um statement Deny"
  }

  assert {
    condition     = jsondecode(aws_s3_bucket_policy.this.policy).Statement[0].Condition.Bool["aws:SecureTransport"] == "false"
    error_message = "o Deny deveria ser condicionado a aws:SecureTransport false"
  }

  assert {
    condition = contains(
      jsondecode(aws_s3_bucket_policy.this.policy).Statement[0].Resource,
      "arn:aws:s3:::test-tfstate-bucket/*"
    )
    error_message = "a policy deveria cobrir os objetos do bucket, não só o bucket"
  }
}
```

- [ ] **Step 2: Rodar o teste para confirmar que falha**

```bash
cd aws/terraform/src/state-backend
terraform init -backend=false
terraform test
```

Esperado: FAIL — nenhum dos recursos existe.

- [ ] **Step 3: Escrever `versions.tf` e `variables.tf`**

`versions.tf`:

```hcl
terraform {
  required_version = ">= 1.15"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}
```

`variables.tf`:

```hcl
variable "bucket_name" {
  description = <<-EOT
    Nome do bucket de state. Globalmente único na AWS — incluir um discriminador de
    Organization ou conta. Valor real fica em terraform.tfvars (gitignored).
  EOT
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$", var.bucket_name))
    error_message = "bucket_name deve seguir as regras de nome de bucket S3 (minúsculas, 3-63 chars)."
  }
}

variable "tags" {
  description = "Tags adicionais."
  type        = map(string)
  default     = {}
}
```

- [ ] **Step 4: Escrever `main.tf`**

```hcl
resource "aws_s3_bucket" "this" {
  bucket = var.bucket_name

  tags = merge(var.tags, { Name = var.bucket_name })
}

# Recupera state corrompido por apply concorrente. Não é opcional num bucket de state.
resource "aws_s3_bucket_versioning" "this" {
  bucket = aws_s3_bucket.this.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "this" {
  bucket = aws_s3_bucket.this.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "this" {
  bucket = aws_s3_bucket.this.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "this" {
  bucket = aws_s3_bucket.this.id

  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_policy" "this" {
  bucket = aws_s3_bucket.this.id

  # ARN montado de var.bucket_name, não de aws_s3_bucket.this.arn: assim a policy é
  # conhecida em tempo de plan e o teste pode asseverar sobre ela sob mock_provider.
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "DenyInsecureTransport"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:*"
        Resource = [
          "arn:aws:s3:::${var.bucket_name}",
          "arn:aws:s3:::${var.bucket_name}/*",
        ]
        Condition = {
          Bool = {
            "aws:SecureTransport" = "false"
          }
        }
      },
    ]
  })

  # A policy tem de ser aplicada DEPOIS do public access block, senão a AWS pode
  # recusá-la por parecer uma policy pública.
  depends_on = [aws_s3_bucket_public_access_block.this]
}
```

- [ ] **Step 5: Escrever `outputs.tf`**

```hcl
output "bucket_name" {
  value = aws_s3_bucket.this.id
}

output "bucket_arn" {
  value = aws_s3_bucket.this.arn
}
```

- [ ] **Step 6: Rodar os testes e confirmar que passam**

```bash
cd aws/terraform/src/state-backend
terraform init -backend=false
terraform fmt -check -recursive
terraform validate
terraform test
```

Esperado: os 5 `run` como `pass`.

- [ ] **Step 7: Commit**

```bash
git add aws/terraform/src/state-backend
git commit -m "feat(terraform): add src/state-backend with hardened S3 bucket

Versionamento, BPA nas 4 dimensões, SSE-S3, BucketOwnerEnforced e deny de
transporte inseguro — as mesmas propriedades já aplicadas ao bucket de
auditoria do CloudTrail, por consistência.

A policy é montada com jsonencode() sobre var.bucket_name em vez do ARN do
recurso, para ser conhecida em tempo de plan e portanto testável sob
mock_provider. depends_on no public access block evita a AWS recusar a
policy por parecer pública."
```

---

### Task 4: raiz `network-foundation` com state local

**Files:**
- Create: `aws/terraform/network-foundation/versions.tf`
- Create: `aws/terraform/network-foundation/variables.tf`
- Create: `aws/terraform/network-foundation/main.tf`
- Create: `aws/terraform/network-foundation/outputs.tf`
- Create: `aws/terraform/network-foundation/terraform.tfvars.example`
- Test: `aws/terraform/network-foundation/tests/composition.tftest.hcl`

**Interfaces:**
- Consumes: `../src/network` (Tasks 1-2) e `../src/state-backend` (Task 3), com as variáveis e outputs declarados ali.
- Produces: raiz aplicável. Outputs `hub_vpc_id`, `hub_vpc_cidr`, `hub_private_subnet_ids`, `hub_control_plane_subnet_ids`, `state_bucket_name`. Módulos endereçáveis em teste: `module.hub_network`, `module.state_backend`.

- [ ] **Step 1: Escrever o teste que falha**

Criar `aws/terraform/network-foundation/tests/composition.tftest.hcl`:

```hcl
mock_provider "aws" {}

variables {
  region             = "us-east-1"
  aws_profile        = "network"
  prefix             = "poc"
  hub_vpc_cidr       = "10.1.0.0/16"
  availability_zones = ["us-east-1a", "us-east-1b"]
  state_bucket_name  = "test-tfstate-bucket"
}

run "o_contrato_de_subnets_do_hub" {
  command = plan

  # Assertion de teste em raiz só alcança outputs de módulo, não os recursos internos
  # dele — a ausência de NAT é coberta em src/network/tests/routing.tftest.hcl.
  assert {
    condition     = length(module.hub_network.private_subnet_ids) == 2
    error_message = "o hub deveria ter 2 subnets privadas"
  }

  assert {
    condition     = length(module.hub_network.control_plane_subnet_ids) == 4
    error_message = "o contrato de control plane são as 4 subnets"
  }
}

run "o_cidr_do_hub_e_o_slash16_n1_do_supernet" {
  command = plan

  assert {
    condition     = module.hub_network.vpc_cidr == "10.1.0.0/16"
    error_message = "o hub deveria usar 10.1.0.0/16 (N=1); N=0 é reservado para a Organization"
  }
}

run "recusa_cidr_fora_do_supernet" {
  command = plan

  variables {
    hub_vpc_cidr = "192.168.0.0/16"
  }

  # O plano de CIDR é 10.0.0.0/12 e é a única decisão irreversível da cadeia.
  expect_failures = [var.hub_vpc_cidr]
}
```

- [ ] **Step 2: Rodar o teste para confirmar que falha**

```bash
cd aws/terraform/network-foundation
terraform init -backend=false
terraform test
```

Esperado: FAIL — não há `main.tf`, `module.hub_network` não existe.

- [ ] **Step 3: Escrever `versions.tf`**

Sem bloco `backend` ainda — o state é local neste passo, e o bucket que vai hospedá-lo ainda não existe.

```hcl
terraform {
  required_version = ">= 1.15"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }

  # backend "s3" é adicionado na Task 5, depois que o bucket existir.
}
```

- [ ] **Step 4: Escrever `variables.tf`**

```hcl
variable "region" {
  description = "Única região aprovada pela SCP DenyOutsideApprovedRegions."
  type        = string
  default     = "us-east-1"
}

variable "aws_profile" {
  description = <<-EOT
    Profile local que assume OrganizationAccountAccessRole na conta network.
    Depende de `aws sso login --profile personal` ativo.
  EOT
  type        = string
  default     = "network"
}

variable "prefix" {
  description = "Prefixo de naming: <prefix>-hub-vpc, <prefix>-hub-igw, ..."
  type        = string
}

variable "hub_vpc_cidr" {
  description = <<-EOT
    CIDR da VPC hub. Um /16 do supernet 10.0.0.0/12; N=0 é reservado para a
    Organization, então o hub é N=1. Ver aws/docs/network/01-cidr-addressing.md.
  EOT
  type        = string

  validation {
    # Terraform não tem builtin de "está contido em". O supernet 10.0.0.0/12 cobre
    # 10.0.0.0–10.15.255.255, então basta checar o 1º e o 2º octeto.
    condition = (
      can(cidrhost(var.hub_vpc_cidr, 0)) &&
      can(regex("^10\\.([0-9]|1[0-5])\\.", var.hub_vpc_cidr))
    )
    error_message = "hub_vpc_cidr deve pertencer ao supernet 10.0.0.0/12 (10.0.x a 10.15.x)."
  }
}

variable "availability_zones" {
  description = "Exatamente 2 AZs da região."
  type        = list(string)
}

variable "state_bucket_name" {
  description = "Nome do bucket de state. Valor real em terraform.tfvars (gitignored)."
  type        = string
}
```

- [ ] **Step 5: Escrever `main.tf`**

```hcl
provider "aws" {
  region  = var.region
  profile = var.aws_profile

  default_tags {
    tags = {
      "managed-by" = "terraform"
      "layer"      = "network-foundation"
    }
  }
}

module "hub_network" {
  source = "../src/network"

  name               = "${var.prefix}-hub"
  vpc_cidr           = var.hub_vpc_cidr
  availability_zones = var.availability_zones

  # Sem TGW, nada roteia pelo hub: os nós do EKS saem pelo NAT da própria VPC spoke.
  # Ligar o NAT aqui custaria ~US$ 32/mês servindo zero tráfego. Quando o TGW entrar
  # (Gap 2), revisitar.
  enable_nat_gateway = false

  tags = { role = "hub" }
}

module "state_backend" {
  source = "../src/state-backend"

  bucket_name = var.state_bucket_name

  tags = { role = "terraform-state" }
}
```

- [ ] **Step 6: Escrever `outputs.tf`**

```hcl
output "hub_vpc_id" {
  value = module.hub_network.vpc_id
}

output "hub_vpc_cidr" {
  value = module.hub_network.vpc_cidr
}

output "hub_private_subnet_ids" {
  value = module.hub_network.private_subnet_ids
}

output "hub_control_plane_subnet_ids" {
  value = module.hub_network.control_plane_subnet_ids
}

output "state_bucket_name" {
  description = "Bucket que hospeda o state a partir da migração da Task 5."
  value       = module.state_backend.bucket_name
}
```

- [ ] **Step 7: Escrever `terraform.tfvars.example`**

Só placeholders — nada de valor real neste arquivo, que é versionado.

```hcl
# Copiar para terraform.tfvars (gitignored) e preencher.
# Valores reais desta conta vivem em CLAUDE.local.md.

prefix             = "poc"
region             = "us-east-1"
aws_profile        = "network"

# /16 do supernet 10.0.0.0/12. N=0 é reservado para a Organization.
hub_vpc_cidr       = "10.1.0.0/16"
availability_zones = ["us-east-1a", "us-east-1b"]

# Globalmente único. Sugestão: tfstate-<organization-id>
state_bucket_name = "<state-bucket-name>"
```

- [ ] **Step 8: Rodar os testes e confirmar que passam**

```bash
cd aws/terraform/network-foundation
terraform init -backend=false
terraform fmt -check -recursive
terraform validate
terraform test
```

Esperado: os 3 `run` como `pass`.

- [ ] **Step 9: Commit**

```bash
git add aws/terraform/network-foundation
git commit -m "feat(terraform): compose the network-foundation root module

Camada 1: VPC hub na conta network + o bucket S3 que passará a hospedar o
state. Nasce com state LOCAL de propósito — o bucket que vai guardá-lo é
criado por este mesmo apply, então a migração é um segundo passo.

O hub nasce com enable_nat_gateway = false e há teste para isso: sem TGW
nada roteia pelo hub, e o NAT custaria ~US\$32/mês servindo zero tráfego.
Mantém o custo da PoC em zero, que é a propriedade que o HANDOFF rastreia.

terraform.tfvars.example só com placeholders; valores reais em
terraform.tfvars (gitignored)."
```

---

### Task 5: apply real, migração do state e runbook

**Requer autorização explícita do Silvio.** É o primeiro passo do plano que muta a AWS.
Custo desta camada: **zero recorrente** — VPC, subnets, IGW, route tables e bucket S3 vazio
não têm cobrança por hora, e o NAT está desligado. O bucket cobra por armazenamento
(centavos) e requisições.

**Files:**
- Modify: `aws/terraform/network-foundation/versions.tf` (acrescentar o bloco `backend "s3"`)
- Create: `aws/terraform/README.md`
- Create: `aws/terraform/network-foundation/terraform.tfvars` (gitignored — não commitar)

**Interfaces:**
- Consumes: a raiz da Task 4 e os outputs `state_bucket_name`, `hub_vpc_id`, `hub_control_plane_subnet_ids`.
- Produces: state remoto em S3 com lock nativo. Os outputs `hub_vpc_id` e `hub_control_plane_subnet_ids` são o que a camada 2 (`control-plane`) lerá — por `data` source, não por `terraform_remote_state`.

- [ ] **Step 1: Preencher o `terraform.tfvars` e confirmar acesso à conta**

```bash
cd aws/terraform/network-foundation
cp terraform.tfvars.example terraform.tfvars
# Editar terraform.tfvars com o nome real do bucket (ver CLAUDE.local.md).

aws sso login --profile personal
AWS_PROFILE=network aws sts get-caller-identity
```

Esperado: o `Account` retornado é a conta `network`. Se falhar, o SSO expirou.

Confirmar que o arquivo não será versionado:

```bash
git check-ignore -v terraform.tfvars
```

Esperado: uma linha apontando para a regra do `.gitignore`. Se não imprimir nada, **parar** — o arquivo entraria no commit.

- [ ] **Step 2: Rodar o plan contra a conta real**

```bash
terraform init
terraform plan -out=foundation.tfplan
```

Esperado: `Plan: 19 to add, 0 to change, 0 to destroy`.

- **13 de rede:** VPC (1) + subnets (4) + IGW (1) + route tables (2) + rota pública (1) +
  associações (4). Sem `aws_nat_gateway`, `aws_eip` nem rota privada — são os 3 que faltam
  para os 16 da camada L1a, e faltam de propósito.
- **6 do bucket:** bucket, versioning, SSE, public access block, ownership controls, policy.

Conferir explicitamente que **não** aparece `aws_nat_gateway` nem `aws_eip` no plano. Se
aparecerem, `enable_nat_gateway` não chegou como `false` — parar e investigar antes do apply.

- [ ] **Step 3: Aplicar**

Rodar manualmente via `! <comando>` — o classifier de auto-mode bloqueia scripts que criam
recursos reais.

```bash
terraform apply foundation.tfplan
```

Esperado: `Apply complete!` com os outputs impressos.

- [ ] **Step 4: Verificar o resultado na AWS**

```bash
terraform output

AWS_PROFILE=network aws ec2 describe-vpcs \
  --filters "Name=tag:Name,Values=*-hub-vpc" \
  --query 'Vpcs[].{Id:VpcId,Cidr:CidrBlock}' \
  --output table

# Confirma o custo zero: nenhum NAT Gateway na conta.
AWS_PROFILE=network aws ec2 describe-nat-gateways \
  --filter "Name=state,Values=available" \
  --query 'NatGateways[].NatGatewayId' \
  --output text
```

Esperado: a VPC com o CIDR do tfvars, e a consulta de NAT Gateway retornando vazio.

- [ ] **Step 5: Acrescentar o bloco de backend ao `versions.tf`**

Substituir o comentário `# backend "s3" é adicionado na Task 5...` por:

```hcl
  backend "s3" {
    # Preenchido via -backend-config no init (o nome do bucket é valor real).
    key          = "network-foundation/terraform.tfstate"
    region       = "us-east-1"
    profile      = "network"
    encrypt      = true
    use_lockfile = true
  }
```

`use_lockfile = true` é o lock nativo do backend S3 — dispensa a tabela DynamoDB do padrão
antigo. O `bucket` fica fora do arquivo porque é valor real; entra por `-backend-config`.

- [ ] **Step 6: Migrar o state para o bucket**

```bash
cp terraform.tfstate terraform.tfstate.pre-migration.bak

terraform init \
  -backend-config="bucket=$(terraform output -raw state_bucket_name)" \
  -migrate-state
```

O Terraform pergunta se deve copiar o state existente para o novo backend — responder `yes`.

Esperado: `Successfully configured the backend "s3"!`.

- [ ] **Step 7: Verificar que o state remoto está íntegro**

```bash
# Deve listar os mesmos recursos de antes da migração.
terraform state list

# E o plan tem de vir limpo — se vier com mudanças, a migração perdeu state.
terraform plan
```

Esperado: `No changes. Your infrastructure matches the configuration.`

Só depois disso, remover o backup e o state local:

```bash
rm terraform.tfstate.pre-migration.bak terraform.tfstate terraform.tfstate.backup
```

- [ ] **Step 8: Escrever o runbook em `aws/terraform/README.md`**

````markdown
# Terraform — bootstrap da plataforma AWS

Substitui o bootstrap por k3d + Crossplane. Desenho em
`docs/superpowers/specs/2026-08-25-terraform-bootstrap-module-design.md`.

## Camadas

| Camada | Conta | State | Entrega |
|---|---|---|---|
| `network-foundation` | `network` | S3 (`network-foundation/terraform.tfstate`) | VPC hub, bucket de state |
| `control-plane` | `cicd` | S3 (`control-plane/terraform.tfstate`) | VPC spoke, EKS, ESO, ArgoCD, Crossplane |

**A VPC spoke nunca pode ser separada do state do cluster.** No teardown, o egress
*pod → subnet privada → NAT → IGW → API do ELB* precisa sobreviver até o último nó sair;
o grafo de dependências do Terraform garante isso somente dentro de um mesmo state. Separar
`rede | cluster` reintroduz o bug do NLB órfão sem o mecanismo que o compensava na
Composition de referência.

## Pré-requisitos

- `aws sso login --profile personal` ativo.
- Profiles locais `network` e `cicd` assumindo `OrganizationAccountAccessRole`.
- A conta `cicd` (OU `Deployments`) **existe** — pré-requisito duro da camada 2. Mover EKS
  entre contas é rebuild, não move.
- `terraform.tfvars` preenchido em cada raiz (gitignored; valores em `CLAUDE.local.md`).

## Ordem de apply

```bash
cd network-foundation
terraform init -backend-config="bucket=<state-bucket-name>"
terraform plan -out=foundation.tfplan
terraform apply foundation.tfplan
```

## Ordem de teardown

**Inverso do apply: `control-plane` antes de `network-foundation`.**

Dentro de uma camada a ordem é de graça — é o grafo de dependências do Terraform. O que
**não** é de graça: XRs que o Crossplane tenha criado dentro do cluster depois do bootstrap.
Eles não estão no state, e destruir o cluster primeiro deixa recurso AWS órfão sem
controlador. Antes de destruir a `control-plane`:

```bash
kubectl get managed          # tem de vir vazio
kubectl get composite        # idem
```

Se não vier vazio, deletar os XRs e esperar a reconciliação terminar **antes** do
`terraform destroy`.

## Testes

Sem credencial, sem chamada à AWS — `mock_provider` + `command = plan`:

```bash
for module in src/network src/state-backend network-foundation; do
  (cd "${module}" && terraform init -backend=false && terraform test)
done
```
````

- [ ] **Step 9: Commit**

```bash
git add aws/terraform/README.md aws/terraform/network-foundation/versions.tf
git status --short   # confirmar que terraform.tfvars e *.tfstate NÃO aparecem
git commit -m "feat(terraform): migrate foundation state to S3, add runbook

State migrado do local para o bucket criado pelo próprio apply, com lock
nativo do backend S3 (use_lockfile) em vez da tabela DynamoDB do padrão
antigo. O nome do bucket entra por -backend-config porque é valor real.

Runbook registra a ordem de apply/teardown e a razão pela qual a VPC spoke
não pode ser separada do state do cluster: o grafo de dependências do
Terraform só cobre o egress do teardown dentro de um mesmo state.

Custo verificado em zero: nenhum NAT Gateway na conta."
```

---

## O que este plano NÃO cobre

A spec descreve duas camadas. Esta é a primeira. A segunda vira plano próprio
(`control-plane`).

**O bloqueio da camada 2 caiu em 2026-08-25:** a OU `Deployments` e a conta `cicd` foram criadas
pelos scripts de `aws/docs/accounts/scripts/`, com SCP baseline herdada e profile local `cicd`
validado. IDs em `CLAUDE.local.md`.

Escopo do plano 2: `src/cluster`, `src/nodegroup`,
`src/pod-identity`, `src/helm/modules/{external-secrets,argo-cd,crossplane}`, a raiz
`control-plane`, o ConfigMap de contrato Terraform→GitOps e o `data` source que lê a VPC hub
desta camada. Custo real: EKS ~US$ 73/mês + NAT ~US$ 32/mês + nós.

O script `follow` determinístico de acompanhamento tem design próprio, ainda não escrito.
