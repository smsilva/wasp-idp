# Terraform control-plane layer

> **For agentic workers:** execute uma task por vez, na ordem. Cada task tem um ciclo
> TDD fechado: escreva o teste que falha, confirme o FAIL, implemente, rode o quarteto de
> verificação, faça o commit. Não pule para a próxima antes do commit. Todo comando roda a
> partir da raiz do repositório salvo indicação em contrário. A última task exige
> autorização humana explícita — pare nela.

**Goal:** entregar a camada 2 do Terraform — a célula de plataforma `control-plane` na
conta `cicd`: VPC spoke `10.2.0.0/16`, cluster EKS, node group gerenciado, três Pod
Identities, e os charts External Secrets, ArgoCD e Crossplane core. Ao fim, o Crossplane
roda no EKS autenticando por Pod Identity — a access key de longa duração do
`crossplane-poc` deixa de ser necessária.

**Architecture:** módulos reutilizáveis em `aws/terraform/src/**`, composição fina no root
`aws/terraform/control-plane/`. O root é o único lugar com `backend`, `provider` e valores
concretos. A VPC spoke e o cluster compartilham **um** state — o corte é `hub | spoke+cluster`,
nunca `rede | cluster`. Providers, functions e ProviderConfigs do Crossplane ficam fora do
Terraform, entregues por GitOps a partir do ConfigMap `platform-bootstrap`.

**Tech Stack:** Terraform `>= 1.15`, `hashicorp/aws ~> 6.0`,
`hashicorp/kubernetes >= 3.0.0, < 4.0.0`, `hashicorp/helm >= 3.0.0, < 4.0.0` — as mesmas
faixas de `examples/cluster_argocd_ingress_istio` do repo `azure-kubernetes`, que é a
referência viva desta composição. Testes com o framework nativo (`terraform test`,
`mock_provider`).
Backend S3 com `use_lockfile = true`.

**Spec:** `docs/superpowers/specs/2026-08-25-terraform-bootstrap-module-design.md`

## Global Constraints

- **Nenhum `terraform apply` contra a AWS sem autorização explícita do Silvio.** Só a
  última task aplica, e ela é um gate humano.
- **Nada de account id, e-mail, hosted zone id ou nome de bucket em arquivo versionado.**
  Valores reais só em `terraform.tfvars` (gitignored). O versionado é
  `terraform.tfvars.example` com placeholders `<...>`.
- **`command = plan` em 100% dos `run` de teste**, sempre com `mock_provider "aws" {}`.
  Nenhum teste toca a AWS.
- **Nomes de `run` em pt-BR snake_case**; `error_message` interpola o valor recebido.
- **`src/network` não é alterado.** A camada 2 o consome como está.
- **VPC spoke e cluster no mesmo state.** Não criar um segundo root nem uma segunda chave.
- **Tags em duas camadas:** `default_tags` no provider (`managed-by`, `layer`) e `var.tags`
  repassada aos submódulos (`role`). Todo recurso faz
  `merge(var.tags, { Name = "${var.name}-<sufixo>" })`.
- **O client secret do OIDC do ArgoCD nunca vira variável Terraform** — iria para o state
  em claro. Só via ESO/Secrets Manager.

---

### Task 1: Módulo `src/pod-identity`

O molde reutilizável de Pod Identity: um IAM role com trust para `pods.eks.amazonaws.com`,
sua policy, e a association que amarra role ↔ (cluster, namespace, service account). Três
consumidores na camada: EBS CSI, External Secrets e Crossplane.

**Files:**
- Create: `aws/terraform/src/pod-identity/versions.tf`
- Create: `aws/terraform/src/pod-identity/variables.tf`
- Create: `aws/terraform/src/pod-identity/main.tf`
- Create: `aws/terraform/src/pod-identity/outputs.tf`
- Test: `aws/terraform/src/pod-identity/tests/role.tftest.hcl`

**Interfaces:**
- Consumes: nada — é a base da cadeia.
- Produces: variáveis `name, cluster_name, namespace, service_account_name, policy_json,
  managed_policy_arns, tags`; output `role_arn`; recursos `aws_iam_role.this`,
  `aws_iam_role_policy.this`, `aws_iam_role_policy_attachment.managed`,
  `aws_eks_pod_identity_association.this`.

- [ ] **Step 1: Escrever o teste que falha**

`aws/terraform/src/pod-identity/tests/role.tftest.hcl`:

```hcl
mock_provider "aws" {}

variables {
  name                 = "test-eso"
  cluster_name         = "test-cluster"
  namespace            = "external-secrets"
  service_account_name = "external-secrets"
}

run "trust_exige_assume_role_e_tag_session" {
  command = plan

  assert {
    condition     = strcontains(aws_iam_role.this.assume_role_policy, "sts:AssumeRole")
    error_message = "trust policy sem sts:AssumeRole: ${aws_iam_role.this.assume_role_policy}"
  }

  assert {
    condition     = strcontains(aws_iam_role.this.assume_role_policy, "sts:TagSession")
    error_message = "trust policy sem sts:TagSession — Pod Identity nao funciona sem ela: ${aws_iam_role.this.assume_role_policy}"
  }

  assert {
    condition     = strcontains(aws_iam_role.this.assume_role_policy, "pods.eks.amazonaws.com")
    error_message = "principal do trust deveria ser pods.eks.amazonaws.com: ${aws_iam_role.this.assume_role_policy}"
  }
}

run "association_amarra_namespace_e_service_account" {
  command = plan

  assert {
    condition     = aws_eks_pod_identity_association.this.namespace == "external-secrets"
    error_message = "namespace da association: esperado external-secrets, recebido ${aws_eks_pod_identity_association.this.namespace}"
  }

  assert {
    condition     = aws_eks_pod_identity_association.this.service_account == "external-secrets"
    error_message = "service account da association: esperado external-secrets, recebido ${aws_eks_pod_identity_association.this.service_account}"
  }

  assert {
    condition     = aws_eks_pod_identity_association.this.cluster_name == "test-cluster"
    error_message = "cluster da association: esperado test-cluster, recebido ${aws_eks_pod_identity_association.this.cluster_name}"
  }
}

run "policy_inline_ausente_nao_cria_recurso" {
  command = plan

  assert {
    condition     = length(aws_iam_role_policy.this) == 0
    error_message = "sem policy_json nao deveria existir aws_iam_role_policy, recebido ${length(aws_iam_role_policy.this)}"
  }
}

run "managed_policies_geram_um_attachment_cada" {
  command = plan

  variables {
    managed_policy_arns = [
      "arn:aws:iam::aws:policy/service-role/AmazonEBSCSIDriverPolicy",
      "arn:aws:iam::aws:policy/ReadOnlyAccess",
    ]
  }

  assert {
    condition     = length(aws_iam_role_policy_attachment.managed) == 2
    error_message = "esperados 2 attachments, recebidos ${length(aws_iam_role_policy_attachment.managed)}"
  }
}
```

- [ ] **Step 2: Rodar o teste para confirmar que falha**

```bash
cd aws/terraform/src/pod-identity
terraform init -backend=false
terraform test
```

Esperado: FAIL — o diretório não tem `main.tf`, nenhum dos recursos referenciados existe.

- [ ] **Step 3: `versions.tf`**

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

- [ ] **Step 4: `variables.tf`**

```hcl
variable "name" {
  description = "Nome do role IAM. Deve ser unico na conta."
  type        = string
}

variable "cluster_name" {
  description = "Nome do cluster EKS onde a association vale."
  type        = string
}

variable "namespace" {
  description = "Namespace Kubernetes da service account."
  type        = string
}

variable "service_account_name" {
  description = "Nome da service account que assume o role."
  type        = string
}

variable "policy_json" {
  description = "Policy inline em JSON. Null quando so ha managed policies."
  type        = string
  default     = null
}

variable "managed_policy_arns" {
  description = "ARNs de managed policies a anexar ao role."
  type        = list(string)
  default     = []
}

variable "tags" {
  description = "Tags aplicadas aos recursos do modulo."
  type        = map(string)
  default     = {}
}
```

- [ ] **Step 5: `main.tf`**

```hcl
# Pod Identity exige as DUAS acoes no trust: sts:AssumeRole para assumir o role e
# sts:TagSession para o agente carimbar a sessao com cluster/namespace/service account.
# Faltando TagSession o pod recebe AccessDenied sem mensagem util.
data "aws_iam_policy_document" "trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole", "sts:TagSession"]

    principals {
      type        = "Service"
      identifiers = ["pods.eks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "this" {
  name               = var.name
  assume_role_policy = data.aws_iam_policy_document.trust.json

  tags = merge(var.tags, { Name = var.name })
}

resource "aws_iam_role_policy" "this" {
  count = var.policy_json == null ? 0 : 1

  name   = "${var.name}-inline"
  role   = aws_iam_role.this.id
  policy = var.policy_json
}

resource "aws_iam_role_policy_attachment" "managed" {
  for_each = toset(var.managed_policy_arns)

  role       = aws_iam_role.this.name
  policy_arn = each.value
}

resource "aws_eks_pod_identity_association" "this" {
  cluster_name    = var.cluster_name
  namespace       = var.namespace
  service_account = var.service_account_name
  role_arn        = aws_iam_role.this.arn

  tags = merge(var.tags, { Name = var.name })
}
```

- [ ] **Step 6: `outputs.tf`**

```hcl
output "role_arn" {
  description = "ARN do role assumido pela service account."
  value       = aws_iam_role.this.arn
}

output "role_name" {
  description = "Nome do role, para anexar policies extras fora do modulo."
  value       = aws_iam_role.this.name
}
```

- [ ] **Step 7: Quarteto de verificação**

```bash
cd aws/terraform/src/pod-identity
terraform init -backend=false
terraform fmt -check -recursive
terraform validate
terraform test
```

Esperado: os 4 `run` passam, `fmt` e `validate` silenciosos.

- [ ] **Step 8: Commit**

```bash
git add aws/terraform/src/pod-identity
git commit -m "feat(terraform): add pod-identity module"
```

Corpo em pt-BR explicando que o trust exige `sts:AssumeRole` **e** `sts:TagSession`, e que
o módulo é o molde único para os três consumidores da camada (EBS CSI, ESO, Crossplane).

---

### Task 2: Módulo `src/cluster`

O cluster EKS e os dois roles IAM que ele exige: o role do control plane e o role
compartilhado dos nós. Mais os dois addons de base. `authentication_mode = "API"` — sem
`aws-auth` ConfigMap, acesso por access entries.

**Files:**
- Create: `aws/terraform/src/cluster/versions.tf`
- Create: `aws/terraform/src/cluster/variables.tf`
- Create: `aws/terraform/src/cluster/main.tf`
- Create: `aws/terraform/src/cluster/outputs.tf`
- Test: `aws/terraform/src/cluster/tests/cluster.tftest.hcl`

**Interfaces:**
- Consumes: `subnet_ids` — vem de `module.network.control_plane_subnet_ids` (as 4).
- Produces: outputs `cluster_name`, `cluster_endpoint`, `cluster_ca_data`,
  `cluster_security_group_id`, `node_role_arn`, `oidc_issuer_url`.

- [ ] **Step 1: Escrever o teste que falha**

`aws/terraform/src/cluster/tests/cluster.tftest.hcl`:

```hcl
mock_provider "aws" {}

variables {
  name       = "test-control-plane"
  subnet_ids = ["subnet-aaa", "subnet-bbb", "subnet-ccc", "subnet-ddd"]
}

run "modo_de_autenticacao_e_api_puro" {
  command = plan

  assert {
    condition     = aws_eks_cluster.this.access_config[0].authentication_mode == "API"
    error_message = "authentication_mode deveria ser API (sem aws-auth ConfigMap), recebido ${aws_eks_cluster.this.access_config[0].authentication_mode}"
  }
}

run "cluster_usa_todas_as_subnets_recebidas" {
  command = plan

  assert {
    condition     = length(aws_eks_cluster.this.vpc_config[0].subnet_ids) == 4
    error_message = "o control plane deve ficar nas 4 subnets (imutavel apos a criacao), recebidas ${length(aws_eks_cluster.this.vpc_config[0].subnet_ids)}"
  }
}

run "versao_default_do_kubernetes" {
  command = plan

  assert {
    condition     = aws_eks_cluster.this.version == "1.34"
    error_message = "versao default do kubernetes: esperado 1.34, recebido ${aws_eks_cluster.this.version}"
  }
}

run "menos_de_duas_subnets_e_erro" {
  command = plan

  variables {
    subnet_ids = ["subnet-aaa"]
  }

  expect_failures = [var.subnet_ids]
}

run "addons_de_base_sao_dois_com_overwrite" {
  command = plan

  assert {
    condition     = length(aws_eks_addon.this) == 2
    error_message = "esperados 2 addons de base, recebidos ${length(aws_eks_addon.this)}"
  }

  assert {
    condition     = aws_eks_addon.this["eks-pod-identity-agent"].resolve_conflicts_on_create == "OVERWRITE"
    error_message = "addon deveria resolver conflitos com OVERWRITE, recebido ${aws_eks_addon.this["eks-pod-identity-agent"].resolve_conflicts_on_create}"
  }
}

run "role_dos_nos_tem_as_tres_policies_gerenciadas" {
  command = plan

  assert {
    condition     = length(aws_iam_role_policy_attachment.node) == 3
    error_message = "o role dos nos precisa de WorkerNode + ECR ReadOnly + CNI, recebidos ${length(aws_iam_role_policy_attachment.node)}"
  }
}
```

- [ ] **Step 2: Rodar o teste para confirmar que falha**

```bash
cd aws/terraform/src/cluster
terraform init -backend=false
terraform test
```

Esperado: FAIL — nenhum recurso existe ainda.

- [ ] **Step 3: `versions.tf`** — idêntico ao da Task 1.

- [ ] **Step 4: `variables.tf`**

```hcl
variable "name" {
  description = "Nome do cluster EKS."
  type        = string
}

variable "kubernetes_version" {
  description = "Versao do Kubernetes do control plane."
  type        = string
  default     = "1.34"
}

variable "subnet_ids" {
  description = "Subnets do control plane. Publicas + privadas; imutavel apos a criacao."
  type        = list(string)

  validation {
    condition     = length(var.subnet_ids) >= 2
    error_message = "o EKS exige subnets em pelo menos 2 zonas de disponibilidade, recebidas ${length(var.subnet_ids)}."
  }
}

variable "endpoint_public_access" {
  description = "Expor o endpoint da API na internet."
  type        = bool
  default     = true
}

variable "endpoint_private_access" {
  description = "Expor o endpoint da API dentro da VPC."
  type        = bool
  default     = true
}

variable "public_access_cidrs" {
  description = "CIDRs autorizados no endpoint publico. Vazio significa 0.0.0.0/0."
  type        = list(string)
  default     = []
}

variable "access_entries" {
  description = "Principals IAM com acesso ao cluster, alem do criador. Chave e um rotulo livre."
  type = map(object({
    principal_arn = string
    policy_arn    = string
    access_scope  = optional(string, "cluster")
  }))
  default = {}
}

variable "tags" {
  description = "Tags aplicadas aos recursos do modulo."
  type        = map(string)
  default     = {}
}
```

- [ ] **Step 5: `main.tf`**

```hcl
data "aws_iam_policy_document" "cluster_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["eks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "cluster" {
  name               = "${var.name}-cluster"
  assume_role_policy = data.aws_iam_policy_document.cluster_trust.json

  tags = merge(var.tags, { Name = "${var.name}-cluster" })
}

resource "aws_iam_role_policy_attachment" "cluster" {
  role       = aws_iam_role.cluster.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSClusterPolicy"
}

data "aws_iam_policy_document" "node_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

# Um unico role compartilhado por todos os node groups. Permissoes por workload nao vem
# daqui — vem de Pod Identity, que e o ponto da camada.
resource "aws_iam_role" "node" {
  name               = "${var.name}-node"
  assume_role_policy = data.aws_iam_policy_document.node_trust.json

  tags = merge(var.tags, { Name = "${var.name}-node" })
}

resource "aws_iam_role_policy_attachment" "node" {
  for_each = toset([
    "arn:aws:iam::aws:policy/AmazonEKSWorkerNodePolicy",
    "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly",
    "arn:aws:iam::aws:policy/AmazonEKS_CNI_Policy",
  ])

  role       = aws_iam_role.node.name
  policy_arn = each.value
}

resource "aws_eks_cluster" "this" {
  name     = var.name
  version  = var.kubernetes_version
  role_arn = aws_iam_role.cluster.arn

  access_config {
    authentication_mode                         = "API"
    bootstrap_cluster_creator_admin_permissions = true
  }

  vpc_config {
    subnet_ids              = var.subnet_ids
    endpoint_public_access  = var.endpoint_public_access
    endpoint_private_access = var.endpoint_private_access
    public_access_cidrs     = var.public_access_cidrs
  }

  tags = merge(var.tags, { Name = var.name })

  depends_on = [aws_iam_role_policy_attachment.cluster]
}

resource "aws_eks_access_entry" "this" {
  for_each = var.access_entries

  cluster_name  = aws_eks_cluster.this.name
  principal_arn = each.value.principal_arn

  tags = merge(var.tags, { Name = "${var.name}-${each.key}" })
}

resource "aws_eks_access_policy_association" "this" {
  for_each = var.access_entries

  cluster_name  = aws_eks_cluster.this.name
  principal_arn = each.value.principal_arn
  policy_arn    = each.value.policy_arn

  access_scope {
    type = each.value.access_scope
  }

  depends_on = [aws_eks_access_entry.this]
}

# Sem serviceAccountRoleArn: a identidade do EBS CSI chega por Pod Identity, montada no
# root. Sem addon_version: a AWS escolhe a compativel com a versao do cluster.
resource "aws_eks_addon" "this" {
  for_each = toset(["eks-pod-identity-agent", "aws-ebs-csi-driver"])

  cluster_name                = aws_eks_cluster.this.name
  addon_name                  = each.value
  resolve_conflicts_on_create = "OVERWRITE"
  resolve_conflicts_on_update = "OVERWRITE"

  tags = merge(var.tags, { Name = "${var.name}-${each.value}" })
}
```

- [ ] **Step 6: `outputs.tf`**

```hcl
output "cluster_name" {
  description = "Nome do cluster."
  value       = aws_eks_cluster.this.name
}

output "cluster_endpoint" {
  description = "Endpoint da API do Kubernetes."
  value       = aws_eks_cluster.this.endpoint
}

output "cluster_ca_data" {
  description = "CA do cluster em base64, para configurar os providers kubernetes/helm."
  value       = aws_eks_cluster.this.certificate_authority[0].data
}

output "cluster_security_group_id" {
  description = "Security group gerenciado pelo EKS."
  value       = aws_eks_cluster.this.vpc_config[0].cluster_security_group_id
}

output "node_role_arn" {
  description = "Role compartilhado pelos node groups."
  value       = aws_iam_role.node.arn
}

output "oidc_issuer_url" {
  description = "Issuer OIDC do cluster. Nao usado por Pod Identity; fica para IRSA de terceiros."
  value       = aws_eks_cluster.this.identity[0].oidc[0].issuer
}
```

- [ ] **Step 7: Quarteto de verificação** — mesmos 4 comandos, em `aws/terraform/src/cluster`.

Esperado: os 6 `run` passam.

- [ ] **Step 8: Commit**

```bash
git add aws/terraform/src/cluster
git commit -m "feat(terraform): add eks cluster module"
```

Corpo: `authentication_mode = "API"` elimina o `aws-auth` ConfigMap; addons sem
`service_account_role_arn` porque a identidade vem de Pod Identity; um único role de nó
compartilhado.

---

### Task 3: Módulo `src/nodegroup`

Node groups gerenciados, um por entrada de um mapa. Só nas subnets privadas.

**Files:**
- Create: `aws/terraform/src/nodegroup/versions.tf`
- Create: `aws/terraform/src/nodegroup/variables.tf`
- Create: `aws/terraform/src/nodegroup/main.tf`
- Create: `aws/terraform/src/nodegroup/outputs.tf`
- Test: `aws/terraform/src/nodegroup/tests/nodegroup.tftest.hcl`

**Interfaces:**
- Consumes: `cluster_name` e `node_role_arn` da Task 2; `subnet_ids` das privadas de
  `module.network.private_subnet_ids`.
- Produces: output `node_group_names`.

- [ ] **Step 1: Escrever o teste que falha**

`aws/terraform/src/nodegroup/tests/nodegroup.tftest.hcl`:

```hcl
mock_provider "aws" {}

variables {
  cluster_name  = "test-control-plane"
  node_role_arn = "arn:aws:iam::123456789012:role/test-node"
  subnet_ids    = ["subnet-priv-a", "subnet-priv-b"]
}

run "grupo_default_existe_com_valores_de_referencia" {
  command = plan

  assert {
    condition     = aws_eks_node_group.this["default"].instance_types == tolist(["t3.medium"])
    error_message = "instance type default: esperado t3.medium, recebido ${join(",", aws_eks_node_group.this["default"].instance_types)}"
  }

  assert {
    condition     = aws_eks_node_group.this["default"].capacity_type == "ON_DEMAND"
    error_message = "capacity type default: esperado ON_DEMAND, recebido ${aws_eks_node_group.this["default"].capacity_type}"
  }

  assert {
    condition     = aws_eks_node_group.this["default"].scaling_config[0].desired_size == 2
    error_message = "desired size default: esperado 2, recebido ${aws_eks_node_group.this["default"].scaling_config[0].desired_size}"
  }
}

run "nos_ficam_apenas_em_subnets_privadas" {
  command = plan

  assert {
    condition     = length(aws_eks_node_group.this["default"].subnet_ids) == 2
    error_message = "os nos devem usar so as 2 subnets privadas, recebidas ${length(aws_eks_node_group.this["default"].subnet_ids)}"
  }
}

run "capacity_type_invalido_e_erro" {
  command = plan

  variables {
    node_groups = {
      default = { capacity_type = "RESERVED" }
    }
  }

  expect_failures = [var.node_groups]
}

run "mais_de_um_grupo_gera_mais_de_um_recurso" {
  command = plan

  variables {
    node_groups = {
      default = {}
      spot     = { capacity_type = "SPOT" }
    }
  }

  assert {
    condition     = length(aws_eks_node_group.this) == 2
    error_message = "esperados 2 node groups, recebidos ${length(aws_eks_node_group.this)}"
  }
}
```

- [ ] **Step 2: Rodar o teste para confirmar que falha**

```bash
cd aws/terraform/src/nodegroup
terraform init -backend=false
terraform test
```

Esperado: FAIL — `aws_eks_node_group.this` não existe.

- [ ] **Step 3: `versions.tf`** — idêntico ao da Task 1.

- [ ] **Step 4: `variables.tf`**

```hcl
variable "cluster_name" {
  description = "Cluster EKS que recebe os node groups."
  type        = string
}

variable "node_role_arn" {
  description = "Role IAM compartilhado pelos nos, vindo do modulo cluster."
  type        = string
}

variable "subnet_ids" {
  description = "Subnets dos nos. Apenas privadas."
  type        = list(string)
}

variable "node_groups" {
  description = "Node groups a criar. A chave vira sufixo do nome."
  type = map(object({
    instance_types = optional(list(string), ["t3.medium"])
    capacity_type  = optional(string, "ON_DEMAND")
    desired_size   = optional(number, 2)
    min_size       = optional(number, 2)
    max_size       = optional(number, 4)
    labels         = optional(map(string), {})
  }))
  default = {
    default = {}
  }

  validation {
    condition = alltrue([
      for group in var.node_groups : contains(["ON_DEMAND", "SPOT"], group.capacity_type)
    ])
    error_message = "capacity_type so aceita ON_DEMAND ou SPOT, recebido ${join(",", [for group in var.node_groups : group.capacity_type])}."
  }
}

variable "tags" {
  description = "Tags aplicadas aos recursos do modulo."
  type        = map(string)
  default     = {}
}
```

- [ ] **Step 5: `main.tf`**

```hcl
resource "aws_eks_node_group" "this" {
  for_each = var.node_groups

  cluster_name    = var.cluster_name
  node_group_name = "${var.cluster_name}-${each.key}"
  node_role_arn   = var.node_role_arn
  subnet_ids      = var.subnet_ids
  instance_types  = each.value.instance_types
  capacity_type   = each.value.capacity_type
  labels          = each.value.labels

  scaling_config {
    desired_size = each.value.desired_size
    min_size     = each.value.min_size
    max_size     = each.value.max_size
  }

  # O desired_size vira do autoscaler depois; o Terraform nao deve competir com ele.
  lifecycle {
    ignore_changes = [scaling_config[0].desired_size]
  }

  tags = merge(var.tags, { Name = "${var.cluster_name}-${each.key}" })
}
```

- [ ] **Step 6: `outputs.tf`**

```hcl
output "node_group_names" {
  description = "Nomes dos node groups criados."
  value       = [for group in aws_eks_node_group.this : group.node_group_name]
}
```

- [ ] **Step 7: Quarteto de verificação** — em `aws/terraform/src/nodegroup`.

Esperado: os 4 `run` passam.

- [ ] **Step 8: Commit**

```bash
git add aws/terraform/src/nodegroup
git commit -m "feat(terraform): add eks nodegroup module"
```

Corpo: nós só em subnet privada; `ignore_changes` no `desired_size` para não competir com
autoscaler futuro.

---

### Task 4: Módulo `src/helm/modules/external-secrets`

Primeiro dos três charts. Estabelece o padrão que os outros dois repetem: um
`helm_release` com `wait`, `timeout` 600s e `values` compostos de um bloco base mais o
`extra_values` do chamador.

**Files:**
- Create: `aws/terraform/src/helm/modules/external-secrets/{versions,variables,main,outputs}.tf`
- Test: `aws/terraform/src/helm/modules/external-secrets/tests/release.tftest.hcl`

**Interfaces:**
- Consumes: nada do Terraform — depende do cluster existir, o que o root garante com
  `depends_on`. A identidade AWS vem da Pod Identity criada no root **antes** deste release.
- Produces: outputs `namespace`, `service_account_name`.

- [ ] **Step 1: Escrever o teste que falha**

`tests/release.tftest.hcl`:

```hcl
mock_provider "helm" {}

run "chart_e_versao_fixados" {
  command = plan

  assert {
    condition     = helm_release.this.chart == "external-secrets"
    error_message = "chart: esperado external-secrets, recebido ${helm_release.this.chart}"
  }

  assert {
    condition     = helm_release.this.version == "2.9.0"
    error_message = "versao do chart deve ser fixada em 2.9.0, recebida ${helm_release.this.version}"
  }

  assert {
    condition     = helm_release.this.repository == "https://charts.external-secrets.io"
    error_message = "repositorio: recebido ${helm_release.this.repository}"
  }
}

run "release_espera_ficar_pronto" {
  command = plan

  assert {
    condition     = helm_release.this.wait
    error_message = "wait deve ser true — o ArgoCD e o Crossplane vem depois e dependem do CRD estar registrado"
  }

  assert {
    condition     = helm_release.this.timeout == 600
    error_message = "timeout: esperado 600, recebido ${helm_release.this.timeout}"
  }
}

run "namespace_default" {
  command = plan

  assert {
    condition     = helm_release.this.namespace == "external-secrets"
    error_message = "namespace: esperado external-secrets, recebido ${helm_release.this.namespace}"
  }
}
```

- [ ] **Step 2: Confirmar o FAIL**

```bash
cd aws/terraform/src/helm/modules/external-secrets
terraform init -backend=false
terraform test
```

Esperado: FAIL — `helm_release.this` não existe.

- [ ] **Step 3: `versions.tf`**

```hcl
terraform {
  required_version = ">= 1.15"

  required_providers {
    helm = {
      source  = "hashicorp/helm"
      version = ">= 3.0.0, < 4.0.0"
    }
  }
}
```

- [ ] **Step 4: `variables.tf`**

```hcl
variable "chart_version" {
  description = "Versao do chart external-secrets."
  type        = string
  default     = "2.9.0"
}

variable "namespace" {
  description = "Namespace do External Secrets Operator."
  type        = string
  default     = "external-secrets"
}

variable "service_account_name" {
  description = "Service account do controller. Deve casar com a Pod Identity association."
  type        = string
  default     = "external-secrets"
}

variable "extra_values" {
  description = "YAML adicional mesclado ao values base."
  type        = string
  default     = ""
}
```

- [ ] **Step 5: `main.tf`**

```hcl
resource "helm_release" "this" {
  name             = "external-secrets"
  repository       = "https://charts.external-secrets.io"
  chart            = "external-secrets"
  version          = var.chart_version
  namespace        = var.namespace
  create_namespace = true
  wait             = true
  timeout          = 600

  values = compact([
    yamlencode({
      installCRDs = true
      serviceAccount = {
        create = true
        name   = var.service_account_name
      }
    }),
    var.extra_values,
  ])
}
```

- [ ] **Step 6: `outputs.tf`**

```hcl
output "namespace" {
  description = "Namespace onde o ESO roda."
  value       = var.namespace
}

output "service_account_name" {
  description = "Service account do controller, alvo da Pod Identity association."
  value       = var.service_account_name
}
```

- [ ] **Step 7: Quarteto de verificação.** Esperado: os 3 `run` passam.

- [ ] **Step 8: Commit**

```bash
git add aws/terraform/src/helm
git commit -m "feat(terraform): add external-secrets helm module"
```

Corpo: `wait = true` porque o CRD `ExternalSecret` precisa estar registrado antes do
ArgoCD; a service account é fixada por variável para casar com a Pod Identity association.

---

### Task 5: Módulo `src/helm/modules/argo-cd`

> **Versão:** o repo interno de referência usa o chart `7.7.7`. O atual é `10.4.0`
> (ArgoCD 3.5.1). O plano adota o atual — a referência é de 2024 e atravessa o major
> ArgoCD 2.x → 3.x. As chaves usadas aqui (`configs.cm`, `configs.params`, `server.service`)
> sobreviveram ao major; se o `helm template` reclamar, o schema do chart é a fonte.

Mesmo molde. `ClusterIP` e acesso por `port-forward` — sem ingress, porque o trio DNS está
fora do escopo desta camada. O `admin` local fica habilitado como break-glass. O bloco de
OIDC é gerado só quando `oidc_enabled = true`, e mesmo assim **sem o client secret**: ele
entra por ESO, mesclado no `argocd-secret`.

**Files:**
- Create: `aws/terraform/src/helm/modules/argo-cd/{versions,variables,main,outputs}.tf`
- Test: `aws/terraform/src/helm/modules/argo-cd/tests/release.tftest.hcl`

**Interfaces:**
- Consumes: nada; ordenado depois do ESO pelo root.
- Produces: outputs `namespace`, `server_service_name`, `admin_password_command`.

- [ ] **Step 1: Escrever o teste que falha**

```hcl
mock_provider "helm" {}

run "chart_e_versao_fixados" {
  command = plan

  assert {
    condition     = helm_release.this.version == "10.4.0"
    error_message = "versao do chart argo-cd: esperado 10.4.0, recebido ${helm_release.this.version}"
  }

  assert {
    condition     = helm_release.this.repository == "https://argoproj.github.io/argo-helm"
    error_message = "repositorio: recebido ${helm_release.this.repository}"
  }
}

run "servico_e_cluster_ip_por_padrao" {
  command = plan

  assert {
    condition     = strcontains(helm_release.this.values[0], "ClusterIP")
    error_message = "sem ingress nesta camada, o server deve ser ClusterIP: ${helm_release.this.values[0]}"
  }
}

run "oidc_desligado_nao_emite_configuracao" {
  command = plan

  assert {
    condition     = !strcontains(helm_release.this.values[0], "oidc.config")
    error_message = "com oidc_enabled=false nao deveria haver bloco oidc.config"
  }
}

run "oidc_ligado_referencia_o_secret_por_placeholder" {
  command = plan

  variables {
    oidc_enabled   = true
    oidc_name      = "google"
    oidc_issuer    = "https://accounts.google.com"
    oidc_client_id = "exemplo.apps.googleusercontent.com"
  }

  assert {
    condition     = strcontains(helm_release.this.values[0], "$oidc.google.clientSecret")
    error_message = "o client secret deve ser referenciado por placeholder do argocd-secret, nunca em claro"
  }

  assert {
    condition     = !strcontains(helm_release.this.values[0], "clientSecret: \"")
    error_message = "nenhum client secret literal pode aparecer no values — iria para o state em claro"
  }
}
```

- [ ] **Step 2: Confirmar o FAIL.** Esperado: FAIL — `helm_release.this` não existe.

- [ ] **Step 3: `versions.tf`** — idêntico ao da Task 4.

- [ ] **Step 4: `variables.tf`**

```hcl
variable "chart_version" {
  description = "Versao do chart argo-cd. 10.4.0 entrega o ArgoCD 3.5.1."
  type        = string
  default     = "10.4.0"
}

variable "namespace" {
  description = "Namespace do ArgoCD."
  type        = string
  default     = "argocd"
}

variable "server_url" {
  description = "URL externa do ArgoCD. Com port-forward, localhost."
  type        = string
  default     = "http://localhost:8080"
}

variable "oidc_enabled" {
  description = "Emitir a configuracao de OIDC. Exige o client secret ja no Secrets Manager."
  type        = bool
  default     = false
}

variable "oidc_name" {
  description = "Nome do provedor OIDC. Compoe a chave do placeholder oidc.<nome>.clientSecret."
  type        = string
  default     = "google"
}

variable "oidc_issuer" {
  description = "Issuer OIDC."
  type        = string
  default     = ""
}

variable "oidc_client_id" {
  description = "Client id OIDC. Nao e segredo."
  type        = string
  default     = ""
}

variable "extra_values" {
  description = "YAML adicional mesclado ao values base."
  type        = string
  default     = ""
}
```

- [ ] **Step 5: `main.tf`**

```hcl
locals {
  # O clientSecret NAO aparece aqui. O placeholder $oidc.<nome>.clientSecret e resolvido
  # pelo ArgoCD contra o secret argocd-secret, onde o ESO o mescla com creationPolicy Merge.
  oidc_config = var.oidc_enabled ? {
    "oidc.config" = yamlencode({
      name         = var.oidc_name
      issuer       = var.oidc_issuer
      clientID     = var.oidc_client_id
      clientSecret = "$oidc.${var.oidc_name}.clientSecret"
      requestedScopes = ["openid", "profile", "email"]
    })
  } : {}
}

resource "helm_release" "this" {
  name             = "argo-cd"
  repository       = "https://argoproj.github.io/argo-helm"
  chart            = "argo-cd"
  version          = var.chart_version
  namespace        = var.namespace
  create_namespace = true
  wait             = true
  timeout          = 600

  values = compact([
    yamlencode({
      configs = {
        cm = merge({
          url = var.server_url
        }, local.oidc_config)
        params = {
          "server.insecure" = true
        }
      }
      server = {
        service = {
          type = "ClusterIP"
        }
      }
    }),
    var.extra_values,
  ])
}
```

- [ ] **Step 6: `outputs.tf`**

```hcl
output "namespace" {
  description = "Namespace do ArgoCD."
  value       = var.namespace
}

output "server_service_name" {
  description = "Service do server, alvo do port-forward."
  value       = "argo-cd-argocd-server"
}

output "admin_password_command" {
  description = "Comando que recupera a senha inicial do admin (break-glass)."
  value       = "kubectl -n ${var.namespace} get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' | base64 -d"
}
```

- [ ] **Step 7: Quarteto de verificação.** Esperado: os 4 `run` passam.

- [ ] **Step 8: Commit**

```bash
git add aws/terraform/src/helm/modules/argo-cd
git commit -m "feat(terraform): add argo-cd helm module"
```

Corpo: `ClusterIP` + `port-forward` enquanto o trio DNS está fora do escopo; o client
secret do OIDC nunca entra no values — só o placeholder resolvido contra o `argocd-secret`
que o ESO mescla.

---

### Task 6: Módulo `src/helm/modules/crossplane`

> **Versão:** `2.4.0`, do canal **stable**. O `aws/eks/scripts/install-crossplane` ainda
> tem `2.3.1` como default — atualizar o script fica para uma tarefa separada, para não
> misturar o k3d com esta camada. Não usar o canal `master`
> (`https://charts.crossplane.io/master/`), que publica release candidates.

Crossplane **core** apenas. Providers, functions e ProviderConfigs chegam por GitOps —
são o churn semanal, e o Terraform não é o lugar deles.

**Files:**
- Create: `aws/terraform/src/helm/modules/crossplane/{versions,variables,main,outputs}.tf`
- Test: `aws/terraform/src/helm/modules/crossplane/tests/release.tftest.hcl`

**Interfaces:**
- Consumes: nada; ordenado por último entre os charts.
- Produces: outputs `namespace`, `service_account_name`.

- [ ] **Step 1: Escrever o teste que falha**

```hcl
mock_provider "helm" {}

run "chart_e_versao_fixados" {
  command = plan

  assert {
    condition     = helm_release.this.version == "2.4.0"
    error_message = "versao do chart crossplane: esperado 2.4.0, recebido ${helm_release.this.version}"
  }

  assert {
    condition     = helm_release.this.repository == "https://charts.crossplane.io/stable"
    error_message = "repositorio: recebido ${helm_release.this.repository}"
  }

  assert {
    condition     = helm_release.this.namespace == "crossplane-system"
    error_message = "namespace: esperado crossplane-system, recebido ${helm_release.this.namespace}"
  }
}

run "nenhum_provider_e_instalado_pelo_terraform" {
  command = plan

  assert {
    condition     = !strcontains(helm_release.this.values[0], "provider-aws")
    error_message = "providers do Crossplane chegam por GitOps, nao pelo Terraform: ${helm_release.this.values[0]}"
  }
}
```

- [ ] **Step 2: Confirmar o FAIL.** Esperado: FAIL — `helm_release.this` não existe.

- [ ] **Step 3: `versions.tf`** — idêntico ao da Task 4.

- [ ] **Step 4: `variables.tf`**

```hcl
variable "chart_version" {
  description = "Versao do chart crossplane. Canal stable, nao master (que publica RCs)."
  type        = string
  default     = "2.4.0"
}

variable "namespace" {
  description = "Namespace do Crossplane."
  type        = string
  default     = "crossplane-system"
}

variable "service_account_name" {
  description = "Service account do core. Deve casar com a Pod Identity association."
  type        = string
  default     = "crossplane"
}

variable "extra_values" {
  description = "YAML adicional mesclado ao values base."
  type        = string
  default     = ""
}
```

- [ ] **Step 5: `main.tf`**

```hcl
# Somente o core. Providers, functions e ProviderConfigs sao entregues por GitOps a partir
# do ConfigMap platform-bootstrap.
resource "helm_release" "this" {
  name             = "crossplane"
  repository       = "https://charts.crossplane.io/stable"
  chart            = "crossplane"
  version          = var.chart_version
  namespace        = var.namespace
  create_namespace = true
  wait             = true
  timeout          = 600

  values = compact([
    yamlencode({
      serviceAccount = {
        create = true
        customAnnotations = {}
      }
    }),
    var.extra_values,
  ])
}
```

- [ ] **Step 6: `outputs.tf`**

```hcl
output "namespace" {
  description = "Namespace do Crossplane."
  value       = var.namespace
}

output "service_account_name" {
  description = "Service account do core, alvo da Pod Identity association."
  value       = var.service_account_name
}
```

- [ ] **Step 7: Quarteto de verificação.** Esperado: os 2 `run` passam.

- [ ] **Step 8: Commit**

```bash
git add aws/terraform/src/helm/modules/crossplane
git commit -m "feat(terraform): add crossplane helm module"
```

Corpo: só o core; a fronteira com o GitOps é o ConfigMap `platform-bootstrap`.

---

### Task 7: Root `control-plane/`

A composição. Único lugar com `backend`, `provider` e valores concretos. Nada é aplicado
nesta task — ela termina em `terraform validate` e `terraform test`.

**Files:**
- Create: `aws/terraform/control-plane/{versions,providers,variables,main,outputs}.tf`
- Create: `aws/terraform/control-plane/terraform.tfvars.example`
- Test: `aws/terraform/control-plane/tests/composition.tftest.hcl`

**Interfaces:**
- Consumes: `src/network` (inalterado), `src/cluster`, `src/nodegroup`, `src/pod-identity`
  (×3), os três módulos de Helm; e a VPC hub da camada 1 via `data "aws_vpc"` num provider
  `aws` aliasado para a conta `network`.
- Produces: outputs `cluster_name`, `region`, `argocd_namespace`, `eso_namespace`,
  `crossplane_namespace`, `kubeconfig_command`.

- [ ] **Step 1: Escrever o teste que falha**

`tests/composition.tftest.hcl`:

```hcl
mock_provider "aws" {}
mock_provider "kubernetes" {}
mock_provider "helm" {}

variables {
  name                = "control-plane"
  region              = "us-east-1"
  aws_profile         = "cicd"
  network_profile     = "network"
  hub_vpc_name        = "poc-hub-vpc"
  vpc_cidr            = "10.2.0.0/16"
  availability_zones  = ["us-east-1a", "us-east-1b"]
  target_account_ids  = ["000000000000"]
  network_account_id  = "111111111111"
}

run "spoke_usa_o_segundo_octeto_reservado" {
  command = plan

  assert {
    condition     = module.network.vpc_cidr == "10.2.0.0/16"
    error_message = "a spoke da conta cicd e o N=2 do supernet, recebido ${module.network.vpc_cidr}"
  }
}

run "nat_gateway_ligado_na_spoke" {
  command = plan

  assert {
    condition     = var.enable_nat_gateway
    error_message = "sem TGW nao ha rota pelo hub; os nos precisam de NAT para alcancar a API da AWS e os registries"
  }
}

run "tres_pod_identities_uma_por_consumidor" {
  command = plan

  assert {
    condition     = module.pod_identity_ebs_csi.role_arn != null && module.pod_identity_eso.role_arn != null && module.pod_identity_crossplane.role_arn != null
    error_message = "faltou uma das tres Pod Identities: EBS CSI, External Secrets, Crossplane"
  }
}

run "configmap_de_bootstrap_tem_as_sete_chaves" {
  command = plan

  assert {
    condition     = length(keys(kubernetes_config_map.platform_bootstrap.data)) == 7
    error_message = "o platform-bootstrap e o contrato com o GitOps: esperadas 7 chaves, recebidas ${length(keys(kubernetes_config_map.platform_bootstrap.data))}"
  }

  assert {
    condition     = kubernetes_config_map.platform_bootstrap.metadata[0].namespace == "crossplane-system"
    error_message = "o ConfigMap vive em crossplane-system, recebido ${kubernetes_config_map.platform_bootstrap.metadata[0].namespace}"
  }
}

run "cidr_fora_do_supernet_e_erro" {
  command = plan

  variables {
    vpc_cidr = "192.168.0.0/16"
  }

  expect_failures = [var.vpc_cidr]
}
```

- [ ] **Step 2: Confirmar o FAIL**

```bash
cd aws/terraform/control-plane
terraform init -backend=false
terraform test
```

Esperado: FAIL — o diretório não tem configuração.

- [ ] **Step 3: `versions.tf`**

```hcl
terraform {
  required_version = ">= 1.15"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = ">= 3.0.0, < 4.0.0"
    }
    helm = {
      source  = "hashicorp/helm"
      version = ">= 3.0.0, < 4.0.0"
    }
  }

  # O bucket vive na conta network — dai o profile aqui divergir do profile do provider.
  # bucket vem por -backend-config para nao versionar o nome.
  backend "s3" {
    key          = "control-plane/terraform.tfstate"
    region       = "us-east-1"
    profile      = "network"
    encrypt      = true
    use_lockfile = true
  }
}
```

- [ ] **Step 4: `variables.tf`**

```hcl
variable "name" {
  description = "Nome da celula. Prefixo de todos os recursos."
  type        = string
  default     = "control-plane"
}

variable "region" {
  description = "Regiao AWS da celula."
  type        = string
}

variable "aws_profile" {
  description = "Profile local com acesso a conta cicd."
  type        = string
}

variable "network_profile" {
  description = "Profile local com acesso de leitura a conta network, dona da VPC hub."
  type        = string
  default     = "network"
}

variable "hub_vpc_name" {
  description = "Valor da tag Name da VPC hub criada pela camada 1. O modulo src/network
sufixa -vpc no name do root, que em us-east-1 e poc-hub."
  type        = string
  default     = "poc-hub-vpc"
}

variable "vpc_cidr" {
  description = "CIDR da VPC spoke. Um /16 dentro do supernet 10.0.0.0/12."
  type        = string

  validation {
    condition     = can(cidrhost(var.vpc_cidr, 0)) && cidrsubnet("10.0.0.0/12", 4, 0) != null && startswith(var.vpc_cidr, "10.") && tonumber(split(".", var.vpc_cidr)[1]) >= 0 && tonumber(split(".", var.vpc_cidr)[1]) <= 15
    error_message = "o CIDR deve ser um /16 dentro do supernet 10.0.0.0/12 (10.0 a 10.15), recebido ${var.vpc_cidr}."
  }
}

variable "availability_zones" {
  description = "Duas zonas de disponibilidade da regiao."
  type        = list(string)
}

variable "enable_nat_gateway" {
  description = "NAT na spoke. Sem TGW nao ha egress pelo hub — os nos dependem disto."
  type        = bool
  default     = true
}

variable "kubernetes_version" {
  description = "Versao do Kubernetes."
  type        = string
  default     = "1.34"
}

variable "network_account_id" {
  description = "Conta que hospeda a VPC hub. Publicado no platform-bootstrap."
  type        = string
}

variable "target_account_ids" {
  description = "Contas onde o Crossplane cria recursos, via assume role."
  type        = list(string)
}

variable "access_entries" {
  description = "Principals IAM com acesso ao cluster, alem do criador."
  type = map(object({
    principal_arn = string
    policy_arn    = string
    access_scope  = optional(string, "cluster")
  }))
  default = {}
}
```

- [ ] **Step 5: `providers.tf`**

```hcl
provider "aws" {
  region  = var.region
  profile = var.aws_profile

  default_tags {
    tags = {
      "managed-by" = "terraform"
      "layer"      = "control-plane"
    }
  }
}

# Somente leitura, para descobrir a VPC hub. A camada 2 nao escreve nada na conta network.
provider "aws" {
  alias   = "network"
  region  = var.region
  profile = var.network_profile
}

# Configurar os providers kubernetes e helm a partir de outputs do modulo do cluster e
# aplicar tudo num unico terraform apply funciona: o Terraform so precisa da configuracao
# resolvida na hora de configurar o provider, ja no apply. O que NAO pode e um data source
# desses providers no plan — por isso o platform-bootstrap e um resource, nunca um data.
# Mesmo padrao de examples/cluster_argocd_ingress_istio no repo azure-kubernetes.
provider "kubernetes" {
  host                   = module.cluster.cluster_endpoint
  cluster_ca_certificate = base64decode(module.cluster.cluster_ca_data)

  exec {
    api_version = "client.authentication.k8s.io/v1beta1"
    command     = "aws"
    args        = ["eks", "get-token", "--cluster-name", module.cluster.cluster_name, "--region", var.region, "--profile", var.aws_profile]
  }
}

# No provider helm 3.x o kubernetes deixou de ser bloco e virou atributo — note o `=`.
provider "helm" {
  kubernetes = {
    host                   = module.cluster.cluster_endpoint
    cluster_ca_certificate = base64decode(module.cluster.cluster_ca_data)

    exec = {
      api_version = "client.authentication.k8s.io/v1beta1"
      command     = "aws"
      args        = ["eks", "get-token", "--cluster-name", module.cluster.cluster_name, "--region", var.region, "--profile", var.aws_profile]
    }
  }
}
```

- [ ] **Step 6: `main.tf` — rede, cluster e nós**

```hcl
locals {
  install_external_secrets = true
  install_argocd           = true
  install_crossplane       = true
  install_argocd_oidc      = false # exige o client secret ja no Secrets Manager
  install_app_of_apps      = false # entregue por GitOps, fora do Terraform

  tags = { role = "control-plane" }
}

# A VPC hub e lida pela API da AWS, nao pelo state da camada 1. A camada 2 depende do
# recurso existir, nao do arquivo de state — se a camada 1 mudar de backend ou de chave,
# isto continua valendo. Custo: exige um provider aliasado e credencial de leitura na
# conta network.
data "aws_vpc" "hub" {
  provider = aws.network

  filter {
    name   = "tag:Name"
    values = [var.hub_vpc_name]
  }
}

module "network" {
  source = "../src/network"

  name               = var.name
  vpc_cidr           = var.vpc_cidr
  availability_zones = var.availability_zones
  enable_nat_gateway = var.enable_nat_gateway
  tags               = local.tags
}

module "cluster" {
  source = "../src/cluster"

  name               = var.name
  kubernetes_version = var.kubernetes_version
  subnet_ids         = module.network.control_plane_subnet_ids
  access_entries     = var.access_entries
  tags               = local.tags
}

module "nodegroup" {
  source = "../src/nodegroup"

  cluster_name  = module.cluster.cluster_name
  node_role_arn = module.cluster.node_role_arn
  subnet_ids    = module.network.private_subnet_ids
  tags          = local.tags
}
```

- [ ] **Step 7: `main.tf` — as três Pod Identities (acrescentar ao final)**

```hcl
module "pod_identity_ebs_csi" {
  source = "../src/pod-identity"

  name                 = "${var.name}-ebs-csi"
  cluster_name         = module.cluster.cluster_name
  namespace            = "kube-system"
  service_account_name = "ebs-csi-controller-sa"
  managed_policy_arns  = ["arn:aws:iam::aws:policy/service-role/AmazonEBSCSIDriverPolicy"]
  tags                 = local.tags
}

data "aws_iam_policy_document" "eso" {
  statement {
    effect = "Allow"
    actions = [
      "secretsmanager:GetSecretValue",
      "secretsmanager:DescribeSecret",
    ]
    resources = ["*"]
  }
}

module "pod_identity_eso" {
  source = "../src/pod-identity"

  name                 = "${var.name}-external-secrets"
  cluster_name         = module.cluster.cluster_name
  namespace            = "external-secrets"
  service_account_name = "external-secrets"
  policy_json          = data.aws_iam_policy_document.eso.json
  tags                 = local.tags
}

# Esta e a razao de ser da camada: o Crossplane deixa de depender da access key de longa
# duracao do crossplane-poc e passa a assumir os roles das contas alvo por Pod Identity.
data "aws_iam_policy_document" "crossplane" {
  statement {
    effect    = "Allow"
    actions   = ["sts:AssumeRole", "sts:TagSession"]
    resources = [for account_id in var.target_account_ids : "arn:aws:iam::${account_id}:role/crossplane-*"]
  }
}

module "pod_identity_crossplane" {
  source = "../src/pod-identity"

  name                 = "${var.name}-crossplane"
  cluster_name         = module.cluster.cluster_name
  namespace            = "crossplane-system"
  service_account_name = "crossplane"
  policy_json          = data.aws_iam_policy_document.crossplane.json
  tags                 = local.tags
}
```

- [ ] **Step 8: `main.tf` — charts e o ConfigMap de bootstrap (acrescentar ao final)**

```hcl
# A association de Pod Identity vem ANTES do release: se o pod subir sem ela, falha em
# AccessDenied e fica em CrashLoop ate um restart manual.
module "external_secrets" {
  source = "../src/helm/modules/external-secrets"
  count  = local.install_external_secrets ? 1 : 0

  depends_on = [
    module.nodegroup,
    module.pod_identity_eso,
  ]
}

module "argo_cd" {
  source = "../src/helm/modules/argo-cd"
  count  = local.install_argocd ? 1 : 0

  oidc_enabled = local.install_argocd_oidc

  depends_on = [module.external_secrets]
}

module "crossplane" {
  source = "../src/helm/modules/crossplane"
  count  = local.install_crossplane ? 1 : 0

  depends_on = [
    module.nodegroup,
    module.pod_identity_crossplane,
  ]
}

# Fronteira com o GitOps. Tudo que o app-of-apps precisa saber sobre esta celula esta
# aqui — nenhum manifesto do GitOps carrega id de conta ou de VPC hardcoded.
resource "kubernetes_config_map" "platform_bootstrap" {
  metadata {
    name      = "platform-bootstrap"
    namespace = "crossplane-system"
  }

  data = {
    region             = var.region
    clusterName        = module.cluster.cluster_name
    hubVpcId           = data.aws_vpc.hub.id
    spokeSubnetIds     = join(",", module.network.private_subnet_ids)
    crossplaneRoleArn  = module.pod_identity_crossplane.role_arn
    networkAccountId   = var.network_account_id
    targetAccountIds   = join(",", var.target_account_ids)
  }

  depends_on = [module.crossplane]
}
```

- [ ] **Step 9: `outputs.tf`**

```hcl
output "cluster_name" {
  description = "Nome do cluster da celula."
  value       = module.cluster.cluster_name
}

output "region" {
  description = "Regiao da celula."
  value       = var.region
}

output "argocd_namespace" {
  description = "Namespace do ArgoCD."
  value       = local.install_argocd ? module.argo_cd[0].namespace : null
}

output "eso_namespace" {
  description = "Namespace do External Secrets."
  value       = local.install_external_secrets ? module.external_secrets[0].namespace : null
}

output "crossplane_namespace" {
  description = "Namespace do Crossplane."
  value       = local.install_crossplane ? module.crossplane[0].namespace : null
}

output "kubeconfig_command" {
  description = "Comando que escreve o contexto deste cluster no kubeconfig local."
  value       = "aws eks update-kubeconfig --name ${module.cluster.cluster_name} --region ${var.region} --profile ${var.aws_profile}"
}
```

- [ ] **Step 10: `terraform.tfvars.example`**

```hcl
region             = "us-east-1"
aws_profile        = "<profile-da-conta-cicd>"
network_profile    = "<profile-de-leitura-na-conta-network>"
hub_vpc_name       = "<tag-name-da-vpc-hub>"
vpc_cidr           = "10.2.0.0/16"
availability_zones = ["us-east-1a", "us-east-1b"]
network_account_id = "<id-da-conta-network>"
target_account_ids = ["<id-da-conta-alvo>"]
```

- [ ] **Step 11: Confirmar que o tfvars real está ignorado**

```bash
git check-ignore -v aws/terraform/control-plane/terraform.tfvars
```

Esperado: uma linha apontando a regra do `.gitignore`. **Saída vazia = PARE** e corrija o
`.gitignore` antes de criar o arquivo real.

- [ ] **Step 12: Quarteto de verificação**

```bash
cd aws/terraform/control-plane
terraform init -backend=false
terraform fmt -check -recursive
terraform validate
terraform test
```

Esperado: os 6 `run` passam. Nenhum comando toca a AWS — `-backend=false` e
`mock_provider` garantem isso.

- [ ] **Step 13: Commit**

```bash
git add aws/terraform/control-plane
git commit -m "feat(terraform): compose control-plane layer"
```

Corpo: o corte de state é `hub | spoke+cluster`; a VPC hub é descoberta por `data "aws_vpc"`
num provider aliasado (acoplamento ao recurso, não ao arquivo de state da camada 1); o
`platform-bootstrap` é o contrato com o GitOps.

---

### Task 8: Apply — **requer autorização explícita do Silvio**

> **PARE AQUI.** Esta task cria recursos com custo recorrente real. Um agente não a executa
> por conta própria. O Silvio autoriza, e roda os comandos de apply ele mesmo com `! <comando>`
> — o classifier de auto-mode bloqueia `terraform apply`.

**Custo recorrente estimado: ~US$ 165/mês**

| Item | US$/mês |
|---|---|
| Control plane EKS | ~73 |
| NAT Gateway (1) | ~32 |
| 2 × `t3.medium` ON_DEMAND | ~60 |
| **Total** | **~165** |

> Correção: os handoffs registram ~US$ 105/mês. Aquele número é EKS + NAT **sem os nós**.
> Com o node group default de 2 × `t3.medium`, o recorrente real é ~US$ 165/mês. Reduzir
> para 1 nó, ou usar `SPOT`, corta ~US$ 30–45.

**Files:**
- Create: `aws/terraform/control-plane/terraform.tfvars` (gitignored, valores de `CLAUDE.local.md`)
- Modify: `aws/terraform/README.md` (linha da camada 2: `não escrita` → aplicada)
- Modify: `HANDOFF.local.md`

- [ ] **Step 1: Preflight**

```bash
cd aws/terraform/control-plane
git check-ignore -v terraform.tfvars
aws sts get-caller-identity --profile cicd
aws ec2 describe-availability-zones --region us-east-1 --profile cicd --query 'AvailabilityZones[].ZoneName'
aws ec2 describe-vpcs --region us-east-1 --profile network \
  --filters "Name=tag:Name,Values=poc-hub-vpc" --query 'Vpcs[].VpcId'
```

Esperado: o `check-ignore` retorna uma regra (**vazio = PARE**); a identidade é a conta
`cicd`; a região passa pela SCP `DenyOutsideApprovedRegions`; e o `describe-vpcs` devolve
**exatamente um** id — se devolver zero ou dois, o filtro por tag `Name` é ambíguo e o
`data "aws_vpc"` vai falhar no plan.

- [ ] **Step 2: `init` com o backend real**

```bash
terraform init -backend-config="bucket=<nome-do-bucket>"
```

Esperado: `Successfully configured the backend "s3"`, nenhum state pré-existente na chave
`control-plane/terraform.tfstate`.

- [ ] **Step 3: Apply**

Um único `terraform apply`. Sem `-target` — os providers `kubernetes` e `helm` se
configuram na hora do apply, quando os atributos do cluster já existem.

```bash
terraform apply
```

Antes de digitar `yes`, confira no plano:

| Recurso | Contagem esperada |
|---|---|
| `aws_nat_gateway` | 1 |
| `aws_eip` | 1 |
| `aws_vpc` | 1 |
| `aws_subnet` | 4 |
| `aws_eks_cluster` | 1 |
| `aws_eks_node_group` | 1 |
| `aws_eks_addon` | 2 |
| `aws_eks_pod_identity_association` | 3 |
| `helm_release` | 3 |
| `kubernetes_config_map` | 1 |

Qualquer divergência: **não aplique**, investigue. Esperado ao fim: apply completo em
~20 min (o control plane do EKS sozinho leva ~10, os nós mais ~5, os charts o resto).

- [ ] **Step 4: kubeconfig**

```bash
aws eks update-kubeconfig --name control-plane --region us-east-1 --profile cicd
kubectl get nodes
```

Esperado: 2 nós `Ready`.

> **Quando o `-target` volta a ser necessário.** Não no bootstrap, mas em applies futuros:
> se um `data source` que alimenta os atributos do cluster ficar "known after apply" por
> causa de uma mudança pendente, isso cascateia para os providers `kubernetes`/`helm` e o
> Terraform propõe recriar **todos** os helm releases. O `azure-kubernetes` documenta esse
> caso com o `data.azurerm_resource_group`. Aqui o único data source é
> `data.aws_vpc.hub`, que não alimenta os providers — mas se o plano algum dia propuser
> substituir os três `helm_release` sem motivo, é este o sintoma.

- [ ] **Step 5: Verificação funcional**

```bash
kubectl -n crossplane-system get pods
kubectl -n external-secrets get pods
kubectl -n argocd get pods
kubectl -n crossplane-system get configmap platform-bootstrap -o yaml
kubectl -n crossplane-system exec deploy/crossplane -- env | grep AWS_CONTAINER_CREDENTIALS
```

Esperado: todos os pods `Running`; o ConfigMap tem as 7 chaves preenchidas; a variável
`AWS_CONTAINER_CREDENTIALS_FULL_URI` presente no pod do Crossplane — é a prova de que a
Pod Identity foi injetada e a access key de longa duração não é mais necessária.

- [ ] **Step 6: ArgoCD acessível**

```bash
kubectl -n argocd port-forward svc/argo-cd-argocd-server 8080:80
kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' | base64 -d
```

Esperado: `http://localhost:8080` abre a UI e o login `admin` funciona.

- [ ] **Step 7: Atualizar a documentação**

- `aws/terraform/README.md`: a linha da camada 2 deixa de ser `não escrita`; registrar a
  chave de state, o CIDR e a ordem de teardown (`control-plane` antes de
  `network-foundation`, com `kubectl get managed` e `kubectl get composite` vazios primeiro).
- `HANDOFF.local.md`: remover de *Next Steps* o item `Camada 2 (control-plane, conta cicd,
  CIDR 10.2.0.0/16): escrever o plano` e acrescentar na seção de trabalho concluído o
  estado aplicado — cluster, CIDR, chave de state, custo recorrente real.
- `CLAUDE.local.md`: acrescentar os valores concretos (nome do cluster, ARNs dos três
  roles de Pod Identity).

- [ ] **Step 8: Commit**

```bash
git add aws/terraform/README.md HANDOFF.local.md
git commit -m "docs(terraform): record the applied control-plane layer"
```

---

## O que este plano NÃO cobre

- **Trio DNS** — external-dns, cert-manager e a hosted zone Route53. Decidido em 2026-08-25
  que ficam fora do Terraform. Enquanto `wasp.silvios.me` não for delegado à AWS, não há
  âncora para eles.
- **Ingress para o ArgoCD.** Consequência do item acima: acesso por `port-forward`.
- **OIDC do ArgoCD ligado.** `install_argocd_oidc = false`. Ligar exige o client secret já
  no Secrets Manager e o `ExternalSecret` com `creationPolicy: Merge` no `argocd-secret`.
  O módulo já emite o placeholder correto — falta só o segredo e o manifesto. Atenção: no
  ESO 2.9.0 os manifestos `ExternalSecret` precisam usar `external-secrets.io/v1` — as
  versões `v1beta1` e `v1alpha1` não são mais servidas.
- **App-of-apps.** `install_app_of_apps = false`. É GitOps, entregue a partir do
  `platform-bootstrap`.
- **Providers, functions e ProviderConfigs do Crossplane.** Churn semanal — GitOps.
- **Transit Gateway e peering hub↔spoke.** Sem eles a spoke usa NAT próprio. Ligar depois é
  aditivo; só o CIDR é irreversível.
- **Day-2 do node group e dos addons** (decisão 5 de `decisions.md`, ainda aberta: cluster
  durável × descartável). O plano trata o cluster como recriável.
- **Aposentar a access key do `crossplane-poc`.** O Step 5 prova que a Pod Identity
  funciona; apagar a credencial antiga é uma tarefa separada, depois de migrar os
  ProviderConfigs.
- **Multi-região.** A camada 1 já roda em `us-east-1` e `us-west-2`; a célula de
  control-plane é uma só, em `us-east-1`.