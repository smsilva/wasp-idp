# Workflow GitHub Actions para provisionar uma região — Plano de Implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Um `workflow_dispatch` no GitHub Actions provisiona hub + célula de uma região inteira (`up-02-region --with-cell`) usando credenciais OIDC GitHub→AWS, sem tocar em Terraform ou nos scripts existentes — mais um workflow separado de recuperação manual de lock, e um mapa de bootstrap do zero.

**Architecture:** Duas roles IAM (uma em `cicd`, uma em `network`) nascem de uma raiz Terraform T0 nova (`aws/terraform/ci/`): a role da `cicd` confia no provider OIDC do GitHub, a role da `network` confia só na role da `cicd` (`sts:AssumeRole` encadeado). O workflow escreve `~/.aws/config` em runtime com os dois profiles (`web_identity_token_file` + `source_profile`), grava o metadata SAML de um secret, descobre o IP de saída do runner e chama `up-02-region --with-cell --public-cidr <ip>/32 --yes` seguido de `--close-public-access --yes` num `if: always()`.

**Tech Stack:** Terraform >= 1.15, provider `aws` ~> 6.0, `terraform test` com `mock_provider`, GitHub Actions (`workflow_dispatch`, OIDC `id-token: write`), bash (scripts existentes, verbatim).

**Spec:** `docs/superpowers/specs/2026-08-31-github-actions-provisioning-workflow-design.md`

## Global Constraints

- `required_version = ">= 1.15"`, provider `aws` `"~> 6.0"` — mesmo floor de toda raiz existente.
- Comentários em Terraform em pt-BR (padrão do repo); scripts bash, YAML de workflow e mensagens de commit em inglês (regra de idioma do usuário para scripts/CI).
- `aws_iam_openid_connect_provider` **sem** `thumbprint_list` — decisão explícita da spec, não esquecimento.
- Trust policies via `jsonencode` de um `local`, nunca `data.aws_iam_policy_document` — sob `mock_provider` o data source devolve valor sintético e a asserção do teste perde sentido (padrão já estabelecido em `src/pod-identity/main.tf`).
- `terraform test` cobre as condições de trust com asserção de conteúdo exato (não só presença de substring genérica) — mutação consciente: pelo menos uma asserção que falharia se a condição fosse enfraquecida.
- Nenhuma mudança em `regions/*`, `src/*` ou `scripts/*` — o workflow chama `up-02-region` verbatim.
- `up-02-region` e `recover-lock` sempre recebem `--state-bucket`/`STATE_BUCKET` explícito — `discover_state_bucket` (default) chama `aws organizations describe-organization` com profile `personal`, que a role de CI não tem.
- `PowerUserAccess` + inline de IAM é o fallback aceito para as duas roles nesta PoC (decisão explícita da spec, registrada como tal — não é ausência de revisão).

---

### Task 1: `variables/values.tfvars` sai do `.gitignore` e entra versionado

**Files:**
- Modify: `.gitignore:27` (raiz do repo)
- Modify: `aws/terraform/variables/values.tfvars` (já existe no disco, gitignored — passa a ser rastreado)

**Interfaces:**
- Produces: `variables/values.tfvars` como arquivo versionado, lido por todo `up-02-region` via symlink `values.auto.tfvars` (nenhuma mudança nesse mecanismo).

- [ ] **Step 1: Remover a linha do `.gitignore`**

Editar `.gitignore` removendo a linha `aws/terraform/variables/values.tfvars` (e o comentário acima que só faz sentido enquanto o arquivo é gitignored — reescrever o comentário para refletir que a partir de agora ele é versionado por decisão de PoC efêmera):

```diff
- # Valores locais de identidade: um arquivo, carregado por cada raiz via symlink values.auto.tfvars.
- # O .example É versionado — é o inventário de o que precisa ser preenchido.
- aws/terraform/variables/values.tfvars
+ # variables/values.tfvars É versionado (decisão de 2026-08-31): as contas AWS desta PoC são
+ # efêmeras e de teste, e versionar elimina toda a maquinaria de materializar o arquivo em CI.
+ # Reverter para gitignored quando as contas deixarem de ser descartáveis.
```

- [ ] **Step 2: Verificar que o arquivo existente não vaza segredo real**

```bash
cat aws/terraform/variables/values.tfvars
```

Confirmar que só há account IDs, um subscription ID do Azure, um domínio e um group ID — nenhuma credencial, chave ou token. (Já verificado nesta sessão; repetir aqui é o gate antes do commit.)

- [ ] **Step 3: Adicionar e commitar**

```bash
git add .gitignore aws/terraform/variables/values.tfvars
git commit -m "chore(terraform): version variables/values.tfvars (ephemeral PoC accounts)"
```

---

### Task 2: Raiz `aws/terraform/ci/` — esqueleto e providers

**Files:**
- Create: `aws/terraform/ci/versions.tf`
- Create: `aws/terraform/ci/variables.tf`
- Create: `aws/terraform/ci/terraform.tfvars.example`
- Modify: `.gitignore` (nenhuma mudança nova necessária — `terraform.tfvars`/`!terraform.tfvars.example` já cobre qualquer raiz nova)

**Interfaces:**
- Produces: variáveis `region`, `cicd_profile`, `network_profile`, `github_org`, `github_repo`, `role_name` — consumidas pelo Task 3.

- [ ] **Step 1: Criar `versions.tf`**

```hcl
terraform {
  required_version = ">= 1.15"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }

  # O bucket de state fica na conta network, como toda raiz regional — o acesso ao
  # bucket passa pelo profile network, nunca pelo cicd.
  backend "s3" {
    key          = "ci/terraform.tfstate"
    region       = "us-east-1"
    profile      = "network"
    encrypt      = true
    use_lockfile = true
  }
}
```

- [ ] **Step 2: Criar `variables.tf`**

```hcl
variable "region" {
  description = "Regiao onde os providers desta raiz operam. IAM e OIDC provider sao globais, mas o provider AWS exige um valor."
  type        = string
  default     = "us-east-1"
}

variable "cicd_profile" {
  description = "Profile local com acesso a conta cicd. Quem aplica esta raiz — um admin humano, uma vez."
  type        = string
  default     = "cicd"
}

variable "network_profile" {
  description = "Profile local com acesso a conta network."
  type        = string
  default     = "network"
}

variable "github_org" {
  description = "Organizacao/usuario do GitHub dono do repositorio que dispara o workflow."
  type        = string
  default     = "smsilva"
}

variable "github_repo" {
  description = "Nome do repositorio no GitHub."
  type        = string
  default     = "wasp-idp"
}

variable "role_name" {
  description = "Nome das duas roles (uma por conta) assumidas pelo workflow do GitHub Actions."
  type        = string
  default     = "github-actions-provision"
}
```

- [ ] **Step 3: Criar `terraform.tfvars.example`**

```hcl
# Copie para terraform.tfvars (gitignored) e ajuste se os defaults de variables.tf nao servirem.
# Na maioria dos casos nenhum valor aqui precisa mudar — os defaults ja apontam para este repo.

# region        = "us-east-1"
# cicd_profile  = "cicd"
# network_profile = "network"
# github_org    = "smsilva"
# github_repo   = "wasp-idp"
# role_name     = "github-actions-provision"
```

- [ ] **Step 4: Confirmar que `terraform.tfvars` real (se algum dia precisar de override) fica fora do git**

```bash
cd aws/terraform/ci
git check-ignore -v terraform.tfvars || echo "cobrir com a regra existente do .gitignore raiz"
```

Esperado: a regra `terraform.tfvars` / `!terraform.tfvars.example` do `.gitignore` já cobre — não precisa de linha nova.

- [ ] **Step 5: Commit**

```bash
git add aws/terraform/ci/versions.tf aws/terraform/ci/variables.tf aws/terraform/ci/terraform.tfvars.example
git commit -m "feat(terraform): scaffold ci/ root (versions, variables)"
```

---

### Task 3: Role `cicd` — OIDC provider + trust + teste de mutação

**Files:**
- Create: `aws/terraform/ci/main.tf` (parcial — providers + OIDC provider + role `cicd` + trust)
- Create: `aws/terraform/ci/tests/roles.tftest.hcl` (parcial — testes da role `cicd`)

**Interfaces:**
- Consumes: `var.region`, `var.cicd_profile`, `var.network_profile`, `var.github_org`, `var.github_repo`, `var.role_name` (Task 2).
- Produces: `aws_iam_openid_connect_provider.github`, `aws_iam_role.cicd` — consumidos por Task 4 (trust da role `network` referencia `aws_iam_role.cicd.arn`) e Task 5 (policies anexadas a `aws_iam_role.cicd`).

- [ ] **Step 1: Escrever o teste (falha esperada — nada existe ainda)**

`aws/terraform/ci/tests/roles.tftest.hcl`:

```hcl
mock_provider "aws" {}

run "cicd_trust_exige_oidc_do_github_com_aud_e_sub_corretos" {
  command = plan

  assert {
    condition     = strcontains(aws_iam_role.cicd.assume_role_policy, "sts:AssumeRoleWithWebIdentity")
    error_message = "trust da role cicd deveria usar AssumeRoleWithWebIdentity: ${aws_iam_role.cicd.assume_role_policy}"
  }

  assert {
    condition     = strcontains(aws_iam_role.cicd.assume_role_policy, "\"token.actions.githubusercontent.com:aud\":\"sts.amazonaws.com\"")
    error_message = "trust da role cicd sem a condicao StringEquals de aud: ${aws_iam_role.cicd.assume_role_policy}"
  }

  assert {
    condition     = strcontains(aws_iam_role.cicd.assume_role_policy, "\"token.actions.githubusercontent.com:sub\":\"repo:smsilva/wasp-idp:ref:refs/heads/*\"")
    error_message = "trust da role cicd sem a condicao StringLike de sub esperada: ${aws_iam_role.cicd.assume_role_policy}"
  }
}

run "oidc_provider_sem_thumbprint_fixo" {
  command = plan

  assert {
    condition     = length(aws_iam_openid_connect_provider.github.thumbprint_list) == 0
    error_message = "thumbprint_list deveria ficar vazio/omitido de proposito — ver ci/README.md"
  }

  assert {
    condition     = aws_iam_openid_connect_provider.github.url == "https://token.actions.githubusercontent.com"
    error_message = "url do provider OIDC incorreta: ${aws_iam_openid_connect_provider.github.url}"
  }

  assert {
    condition     = contains(aws_iam_openid_connect_provider.github.client_id_list, "sts.amazonaws.com")
    error_message = "client_id_list deveria conter sts.amazonaws.com: ${jsonencode(aws_iam_openid_connect_provider.github.client_id_list)}"
  }
}
```

- [ ] **Step 2: Rodar o teste e confirmar que falha**

```bash
cd aws/terraform/ci
terraform init -backend=false
terraform test
```

Esperado: FALHA — `aws_iam_role.cicd` e `aws_iam_openid_connect_provider.github` não existem.

- [ ] **Step 3: Escrever `main.tf` (providers + OIDC provider + role cicd)**

```hcl
provider "aws" {
  region  = var.region
  profile = var.cicd_profile

  default_tags {
    tags = {
      "managed-by" = "terraform"
      "layer"      = "ci"
    }
  }
}

provider "aws" {
  alias   = "network"
  region  = var.region
  profile = var.network_profile

  default_tags {
    tags = {
      "managed-by" = "terraform"
      "layer"      = "ci"
    }
  }
}

locals {
  # jsonencode em vez de data.aws_iam_policy_document: sob mock_provider o data source
  # devolve valor sintetico e a asercao do teste sobre aud/sub perderia o sentido — mesmo
  # motivo documentado em src/pod-identity/main.tf.
  cicd_trust_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Action    = "sts:AssumeRoleWithWebIdentity"
      Principal = { Federated = aws_iam_openid_connect_provider.github.arn }
      Condition = {
        StringEquals = {
          "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
        }
        StringLike = {
          "token.actions.githubusercontent.com:sub" = "repo:${var.github_org}/${var.github_repo}:ref:refs/heads/*"
        }
      }
    }]
  })
}

# thumbprint_list omitido de proposito: a AWS valida o endpoint JWKS pela propria
# biblioteca de CAs raiz confiaveis, e a doc do provider e explicita que, para o GitHub,
# qualquer thumbprint configurado "e retido na configuracao mas nao usado para
# verificacao". Fixar aqui e a armadilha classica de CI que quebra na rotacao do
# certificado, por zero seguranca a mais — ver ci/README.md.
resource "aws_iam_openid_connect_provider" "github" {
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
}

resource "aws_iam_role" "cicd" {
  name               = var.role_name
  assume_role_policy = local.cicd_trust_policy
}
```

- [ ] **Step 4: Rodar o teste e confirmar que passa**

```bash
terraform test
```

Esperado: `oidc_provider_sem_thumbprint_fixo` e as duas asserções de `cicd_trust_exige_oidc_do_github_com_aud_e_sub_corretos` — PASS.

- [ ] **Step 5: Commit**

```bash
cd /home/silvios/git/wasp-idp
git add aws/terraform/ci/main.tf aws/terraform/ci/tests/roles.tftest.hcl
git commit -m "feat(terraform): ci/ OIDC provider and cicd role trust, with mutation-conscious tests"
```

---

### Task 4: Role `network` — confia só na `cicd`, nunca direto no GitHub

**Files:**
- Modify: `aws/terraform/ci/main.tf` (acrescenta trust + resource da role `network`)
- Modify: `aws/terraform/ci/tests/roles.tftest.hcl` (acrescenta o teste de mutação da role `network`)

**Interfaces:**
- Consumes: `aws_iam_role.cicd.arn` (Task 3).
- Produces: `aws_iam_role.network` — consumido por Task 5 (policies).

- [ ] **Step 1: Escrever o teste (falha esperada)**

Acrescentar a `roles.tftest.hcl`:

```hcl
run "network_trust_confia_so_na_role_cicd_nunca_direto_no_github" {
  command = plan

  assert {
    condition     = strcontains(aws_iam_role.network.assume_role_policy, "\"Action\":\"sts:AssumeRole\"")
    error_message = "trust da role network deveria ser sts:AssumeRole simples: ${aws_iam_role.network.assume_role_policy}"
  }

  # Mutacao consciente: esta asercao FALHARIA se alguem, por engano, desse trust direto
  # do OIDC do GitHub tambem a network — o desenho exige que so a cicd confie no GitHub.
  assert {
    condition     = !strcontains(aws_iam_role.network.assume_role_policy, "token.actions.githubusercontent.com")
    error_message = "trust da role network NAO deveria citar o OIDC do GitHub: ${aws_iam_role.network.assume_role_policy}"
  }

  assert {
    condition     = !strcontains(aws_iam_role.network.assume_role_policy, "AssumeRoleWithWebIdentity")
    error_message = "trust da role network NAO deveria usar AssumeRoleWithWebIdentity: ${aws_iam_role.network.assume_role_policy}"
  }
}
```

- [ ] **Step 2: Rodar o teste e confirmar que falha**

```bash
cd aws/terraform/ci
terraform test
```

Esperado: FALHA — `aws_iam_role.network` não existe.

- [ ] **Step 3: Acrescentar a `main.tf`**

```hcl
locals {
  network_trust_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Action    = "sts:AssumeRole"
      Principal = { AWS = aws_iam_role.cicd.arn }
    }]
  })
}

resource "aws_iam_role" "network" {
  provider           = aws.network
  name               = var.role_name
  assume_role_policy = local.network_trust_policy
}
```

- [ ] **Step 4: Rodar o teste e confirmar que passa**

```bash
terraform test
```

Esperado: todas as asserções de `network_trust_confia_so_na_role_cicd_nunca_direto_no_github` — PASS.

- [ ] **Step 5: Commit**

```bash
cd /home/silvios/git/wasp-idp
git add aws/terraform/ci/main.tf aws/terraform/ci/tests/roles.tftest.hcl
git commit -m "feat(terraform): ci/ network role trusts only the cicd role"
```

---

### Task 5: Permissões — `PowerUserAccess` + inline (fallback declarado)

**Files:**
- Modify: `aws/terraform/ci/main.tf` (policies anexadas às duas roles)
- Modify: `aws/terraform/ci/tests/roles.tftest.hcl` (teste do encadeamento `sts:AssumeRole`)

**Interfaces:**
- Consumes: `aws_iam_role.cicd`, `aws_iam_role.network` (Tasks 3-4).
- Produces: permissões finais das duas roles — nenhum consumidor Terraform downstream (fim da cadeia de recursos desta raiz).

- [ ] **Step 1: Escrever o teste (falha esperada)**

Acrescentar a `roles.tftest.hcl`:

```hcl
run "cicd_pode_assumir_a_role_network" {
  command = plan

  assert {
    condition     = strcontains(aws_iam_role_policy.cicd_assume_network.policy, aws_iam_role.network.name)
    error_message = "policy inline da cicd deveria referenciar o nome da role network: ${aws_iam_role_policy.cicd_assume_network.policy}"
  }
}
```

- [ ] **Step 2: Rodar o teste e confirmar que falha**

```bash
cd aws/terraform/ci
terraform test
```

Esperado: FALHA — `aws_iam_role_policy.cicd_assume_network` não existe.

- [ ] **Step 3: Acrescentar a `main.tf`**

```hcl
# PowerUserAccess + inline de IAM: fallback aceito para as duas roles nesta PoC —
# decisao explicita da spec aprovada em 2026-08-31. Derivar o escopo fino por modulo
# (VPC/EKS/ELB/Route53/Secrets Manager de um lado, VPC/TGW/Client VPN/ACM/RAM/Route53
# do outro) fica registrado como trabalho futuro, nao esquecimento — ver ci/README.md.
resource "aws_iam_role_policy_attachment" "cicd_power_user" {
  role       = aws_iam_role.cicd.name
  policy_arn = "arn:aws:iam::aws:policy/PowerUserAccess"
}

resource "aws_iam_role_policy_attachment" "network_power_user" {
  provider   = aws.network
  role       = aws_iam_role.network.name
  policy_arn = "arn:aws:iam::aws:policy/PowerUserAccess"
}

# PowerUserAccess exclui gestao de IAM por desenho da AWS — os dois modulos criam
# roles (cluster, node group, pod identities, SAML provider do Client VPN), entao as
# duas roles precisam de um inline cobrindo isso, alem do sts:AssumeRole encadeado.
resource "aws_iam_role_policy" "cicd_iam_and_assume" {
  name = "${var.role_name}-iam-and-assume"
  role = aws_iam_role.cicd.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "IamForClusterAndPodIdentity"
        Effect = "Allow"
        Action = [
          "iam:CreateRole",
          "iam:DeleteRole",
          "iam:GetRole",
          "iam:TagRole",
          "iam:UntagRole",
          "iam:PutRolePolicy",
          "iam:DeleteRolePolicy",
          "iam:GetRolePolicy",
          "iam:AttachRolePolicy",
          "iam:DetachRolePolicy",
          "iam:PassRole",
          "iam:CreateServiceLinkedRole",
        ]
        Resource = "*"
      },
    ]
  })
}

resource "aws_iam_role_policy" "cicd_assume_network" {
  name = "${var.role_name}-assume-network"
  role = aws_iam_role.cicd.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid      = "AssumeNetworkRole"
      Effect   = "Allow"
      Action   = "sts:AssumeRole"
      Resource = aws_iam_role.network.arn
    }]
  })
}

resource "aws_iam_role_policy" "network_iam_saml" {
  provider = aws.network
  name     = "${var.role_name}-iam-saml"
  role     = aws_iam_role.network.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid    = "SamlProviderForClientVpn"
      Effect = "Allow"
      Action = [
        "iam:CreateSAMLProvider",
        "iam:DeleteSAMLProvider",
        "iam:GetSAMLProvider",
        "iam:UpdateSAMLProvider",
        "iam:TagSAMLProvider",
        "iam:ListSAMLProviders",
      ]
      Resource = "*"
    }]
  })
}
```

- [ ] **Step 4: Rodar o teste completo e confirmar que passa**

```bash
terraform test
terraform validate
terraform fmt -check
```

Esperado: todos os `run` blocks — PASS; `validate` e `fmt -check` sem erro.

- [ ] **Step 5: Commit**

```bash
cd /home/silvios/git/wasp-idp
git add aws/terraform/ci/main.tf aws/terraform/ci/tests/roles.tftest.hcl
git commit -m "feat(terraform): ci/ role permissions (PowerUserAccess + scoped IAM/assume inline)"
```

---

### Task 6: `ci/README.md` + link a partir de `aws/terraform/README.md`

**Files:**
- Create: `aws/terraform/ci/README.md`
- Modify: `aws/terraform/README.md`

**Interfaces:**
- Nenhuma interface de código — documentação.

- [ ] **Step 1: Escrever `ci/README.md`**

```markdown
# ci/ — trust OIDC GitHub → AWS

Raiz T0, aplicada uma vez por um admin humano com os profiles `cicd`/`network` — mesma
disciplina de `state-backend/`. Cria o que o workflow `.github/workflows/provision-region.yml`
usa para autenticar: um `aws_iam_openid_connect_provider` do GitHub Actions na conta `cicd`,
mais uma role por conta.

## Passo a passo

1. `terraform init -backend-config="bucket=$(aws organizations describe-organization --profile personal --query Organization.Id --output text | sed 's/^/tfstate-/')"`
2. `terraform plan` — revisar antes de aplicar; é IAM em duas contas.
3. `terraform apply`
4. Ler as duas ARNs de saída e configurar no repositório GitHub (Settings → Secrets and variables → Actions → Variables):

   | Variable | Valor |
   |---|---|
   | `CICD_ROLE_ARN` | `terraform output -raw cicd_role_arn` |
   | `NETWORK_ROLE_ARN` | `terraform output -raw network_role_arn` |
   | `STATE_BUCKET` | `tfstate-<organization-id>` (mesmo valor do passo 1, sem o `terraform.tfstate` da key) |

5. Configurar o secret `SAML_METADATA_XML` (Settings → Secrets and variables → Actions → Secrets) com o conteúdo de `variables/saml-metadata.xml` — ver `aws/terraform/README.md` para de onde esse arquivo vem.

## Por que trust só na `cicd`, e a `network` confia só na `cicd`

Ver `docs/superpowers/specs/2026-08-31-github-actions-provisioning-workflow-design.md`, seção
"Trust: OIDC só na cicd, network confia na cicd". Resumo: um único provider OIDC evita duplicar
URL/`client_id_list`/condições em duas contas, e espelha a cadeia que já existe operacionalmente
(`personal` → `network`/`cicd`).

## Por que `thumbprint_list` fica vazio

A AWS valida o endpoint JWKS pela própria biblioteca de CAs raiz confiáveis; para o GitHub, um
thumbprint configurado *"is retained in the configuration but not used for verification"* — ver
[OIDC provider thumbprint list (IAM)](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_providers_create_oidc_verify-thumbprint.html).
Fixar um aqui só cria uma armadilha de rotação de certificado, por zero segurança a mais.

## Permissões: `PowerUserAccess` + inline (fallback declarado, não descuido)

As duas roles usam `PowerUserAccess` mais um inline escopado para IAM (que `PowerUserAccess`
exclui por desenho da AWS) e para o `sts:AssumeRole` encadeado. Derivar o escopo fino por módulo
— o que `module.hub` e `module.cell` de fato criam — é trabalho futuro; ver a issue de
"least-privilege das roles de CI" (aberta junto com este workflow).

## Limitação: role chaining trava a sessão em 1h

A role `network` encadeia de `cicd` (`source_profile`). A doc da IAM é explícita: *"When you use
role chaining, the session duration is limited to one hour, regardless of the maximum session
duration setting configured for individual roles"* — nenhum `max_session_duration` levanta esse
teto. O `apply` da célula leva 20-30 min; a margem existe, mas é fina. Ver issue dedicada.
```

- [ ] **Step 2: Adicionar link em `aws/terraform/README.md`**

Adicionar uma linha na tabela de "Ordem e permanência" existente (a que lista `00`/`01`/`02`), uma nova linha entre a fundação da Organization e `up-00-state-backend`, e uma seção curta ao final referenciando `ci/`:

```markdown
| — | `ci/` — trust OIDC GitHub → AWS | T0 | sim |
```

E uma seção nova, próxima da seção de sequência de provisionamento:

```markdown
## Provisionar via GitHub Actions

O workflow `.github/workflows/provision-region.yml` roda `up-02-region --with-cell` em CI,
autenticado por OIDC. O trust GitHub→AWS nasce da raiz `aws/terraform/ci/` — ver
`ci/README.md` para o passo a passo de bootstrap e `aws/terraform/bootstrap-checklist.md`
para a sequência completa do zero.
```

- [ ] **Step 3: Commit**

```bash
git add aws/terraform/ci/README.md aws/terraform/README.md
git commit -m "docs(terraform): ci/ README and link from aws/terraform/README.md"
```

---

### Task 7: `.github/workflows/provision-region.yml`

**Files:**
- Create: `.github/workflows/provision-region.yml`

**Interfaces:**
- Consumes: repository variables `CICD_ROLE_ARN`, `NETWORK_ROLE_ARN`, `STATE_BUCKET`; repository secret `SAML_METADATA_XML` (todos configurados no Task 6, passo 1, itens 4-5).

- [ ] **Step 1: Escrever o workflow**

```yaml
name: Provision region

on:
  workflow_dispatch:
    inputs:
      region:
        description: "Region root under aws/terraform/regions/ (e.g. us-east-1)"
        required: true
        default: "us-east-1"

permissions:
  id-token: write
  contents: read

jobs:
  provision:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Configure OIDC credentials
        env:
          ACTIONS_ID_TOKEN_REQUEST_URL: ${{ env.ACTIONS_ID_TOKEN_REQUEST_URL }}
          ACTIONS_ID_TOKEN_REQUEST_TOKEN: ${{ env.ACTIONS_ID_TOKEN_REQUEST_TOKEN }}
        run: |
          curl --silent --show-error --location \
            --header "Authorization: Bearer ${ACTIONS_ID_TOKEN_REQUEST_TOKEN}" \
            "${ACTIONS_ID_TOKEN_REQUEST_URL}&audience=sts.amazonaws.com" \
            | jq -r '.value' > /tmp/gha-oidc-token

          mkdir -p ~/.aws
          cat > ~/.aws/config <<EOF
          [profile cicd]
          role_arn = ${{ vars.CICD_ROLE_ARN }}
          web_identity_token_file = /tmp/gha-oidc-token

          [profile network]
          role_arn = ${{ vars.NETWORK_ROLE_ARN }}
          source_profile = cicd
          EOF

      - name: Write SAML metadata from secret
        run: printf '%s' "${{ secrets.SAML_METADATA_XML }}" > aws/terraform/variables/saml-metadata.xml

      - name: Discover runner egress IPv4
        id: egress-ip
        run: |
          ip="$(curl --silent --show-error https://checkip.amazonaws.com | tr -d '[:space:]')"
          if [[ ! "${ip}" =~ ^[0-9]{1,3}(\.[0-9]{1,3}){3}$ ]]; then
            echo "runner egress IP is not IPv4: '${ip}' — refusing to build a malformed CIDR" >&2
            exit 1
          fi
          echo "ip=${ip}" >> "${GITHUB_OUTPUT}"

      - name: Setup Terraform
        uses: hashicorp/setup-terraform@v3
        with:
          terraform_version: "1.15.0"

      - name: Provision hub + cell
        working-directory: aws/terraform
        env:
          STATE_BUCKET: ${{ vars.STATE_BUCKET }}
        run: |
          ./scripts/up-02-region \
            --region "${{ inputs.region }}" \
            --with-cell \
            --public-cidr "${{ steps.egress-ip.outputs.ip }}/32" \
            --state-bucket "${STATE_BUCKET}" \
            --yes

      - name: Close public endpoint
        if: always()
        working-directory: aws/terraform
        env:
          STATE_BUCKET: ${{ vars.STATE_BUCKET }}
        run: |
          ./scripts/up-02-region \
            --region "${{ inputs.region }}" \
            --with-cell \
            --close-public-access \
            --state-bucket "${STATE_BUCKET}" \
            --yes
```

- [ ] **Step 2: Validar a sintaxe YAML**

```bash
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/provision-region.yml'))" && echo OK
```

Esperado: `OK`.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/provision-region.yml
git commit -m "feat(ci): provision-region workflow (OIDC, up-02-region --with-cell)"
```

---

### Task 8: `.github/workflows/recover-lock.yml`

**Files:**
- Create: `.github/workflows/recover-lock.yml`

**Interfaces:**
- Consumes: mesmas variáveis/secret do Task 7.

- [ ] **Step 1: Escrever o workflow**

```yaml
name: Recover Terraform lock

on:
  workflow_dispatch:
    inputs:
      region:
        description: "Region root under aws/terraform/regions/ whose lock is stuck (no default — pick deliberately)"
        required: true
      lock_id:
        description: "Lock ID from the 'Error acquiring the state lock' message (no default — pick deliberately)"
        required: true

permissions:
  id-token: write
  contents: read

jobs:
  recover:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Configure OIDC credentials
        env:
          ACTIONS_ID_TOKEN_REQUEST_URL: ${{ env.ACTIONS_ID_TOKEN_REQUEST_URL }}
          ACTIONS_ID_TOKEN_REQUEST_TOKEN: ${{ env.ACTIONS_ID_TOKEN_REQUEST_TOKEN }}
        run: |
          curl --silent --show-error --location \
            --header "Authorization: Bearer ${ACTIONS_ID_TOKEN_REQUEST_TOKEN}" \
            "${ACTIONS_ID_TOKEN_REQUEST_URL}&audience=sts.amazonaws.com" \
            | jq -r '.value' > /tmp/gha-oidc-token

          mkdir -p ~/.aws
          cat > ~/.aws/config <<EOF
          [profile cicd]
          role_arn = ${{ vars.CICD_ROLE_ARN }}
          web_identity_token_file = /tmp/gha-oidc-token

          [profile network]
          role_arn = ${{ vars.NETWORK_ROLE_ARN }}
          source_profile = cicd
          EOF

      - name: Write SAML metadata from secret
        run: printf '%s' "${{ secrets.SAML_METADATA_XML }}" > aws/terraform/variables/saml-metadata.xml

      - name: Setup Terraform
        uses: hashicorp/setup-terraform@v3
        with:
          terraform_version: "1.15.0"

      - name: force-unlock and plan for human review
        working-directory: aws/terraform/regions/${{ inputs.region }}
        env:
          STATE_BUCKET: ${{ vars.STATE_BUCKET }}
        run: |
          ln --symbolic --force ../../variables/values.tfvars values.auto.tfvars
          terraform init -reconfigure -backend-config="bucket=${STATE_BUCKET}" -input=false
          terraform force-unlock -force "${{ inputs.lock_id }}"

          echo "::notice::force-unlock done. Reviewing the plan below is mandatory before re-running provision-region — a plan proposing to CREATE a resource that should already exist means the recovery is 'terraform import', not force-unlock (see aws/terraform/CLAUDE.md)."
          terraform plan -no-color -input=false
```

**Por que o job não decide sozinho** (documentar aqui, não só na spec): detectar "recurso duplicado" só a partir do texto do `plan` não é confiável — um `plan` com criações pode ser drift real e legítimo. O job faz o `force-unlock` e imprime o `plan` no log das Actions; a leitura e a decisão (prosseguir vs. `import`) ficam com quem lê, deliberadamente — é a mesma barreira humana que motivou este workflow ter gatilho próprio em vez de recuperação automática dentro de `provision-region.yml`.

- [ ] **Step 2: Validar a sintaxe YAML**

```bash
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/recover-lock.yml'))" && echo OK
```

Esperado: `OK`.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/recover-lock.yml
git commit -m "feat(ci): manual recover-lock workflow (mandatory region + lock_id inputs)"
```

---

### Task 9: `aws/terraform/bootstrap-checklist.md`

**Files:**
- Create: `aws/terraform/bootstrap-checklist.md`

**Interfaces:**
- Nenhuma — documentação.

- [ ] **Step 1: Escrever o checklist**

```markdown
# Checklist de bootstrap — do zero ao primeiro `workflow_dispatch`

Sequência completa, uma vez por Organization. Cada item diz **quem executa** e **onde** o
detalhe vive — sem duplicar conteúdo.

- [ ] **1. Organization, contas, OUs, Identity Center** — admin humano, console + scripts.
      Detalhe: `aws/docs/accounts/`.
- [ ] **2. Aprovar a região na SCP** — admin humano, console.
      Detalhe: `aws/docs/accounts/` (política de regiões habilitadas).
- [ ] **3. `up-00-state-backend`** — admin humano, `terraform apply` local com profile `network`.
      Detalhe: `aws/terraform/README.md`, seção "Ordem e permanência".
- [ ] **4. `up-01-dns`** — admin humano, `terraform apply` local.
      Detalhe: `aws/terraform/README.md`.
- [ ] **5. Aplicação SAML no Identity Center** — admin humano, console (não é Terraform:
      `CreateApplication` só cria OAuth 2.0 customizado). Salvar o metadata baixado em
      `variables/saml-metadata.xml`.
      Detalhe: `aws/terraform/README.md`, seção "Os dois eixos".
- [ ] **6. `terraform apply` da raiz `ci/`** (OIDC provider + as duas roles) — admin humano,
      local, profiles `cicd`/`network`.
      Detalhe: `aws/terraform/ci/README.md`.
- [ ] **7. Configurar variáveis e secret no repositório GitHub** — admin humano, console do
      GitHub (Settings → Secrets and variables → Actions): `CICD_ROLE_ARN`, `NETWORK_ROLE_ARN`,
      `STATE_BUCKET` (variables) e `SAML_METADATA_XML` (secret).
      Detalhe: `aws/terraform/ci/README.md`, passo 4-5.
- [ ] **8. Primeiro `workflow_dispatch` de `provision-region.yml`** — CI, gatilho manual.
      Detalhe: `.github/workflows/provision-region.yml`.

O valor deste checklist é ordenação e completude, não profundidade — o atrito real desta frente
foi descobrir, uma peça de cada vez, que faltava `values.tfvars`, faltava o metadata SAML,
faltava o symlink. Um item pulado custa um `apply` que morre no meio, longe da causa.
```

- [ ] **Step 2: Commit**

```bash
git add aws/terraform/bootstrap-checklist.md
git commit -m "docs(terraform): bootstrap checklist, zero to first workflow_dispatch"
```

---

### Task 10: Abrir as 5 issues das limitações documentadas

**Files:** nenhum (ação via `gh issue create`, não arquivo).

**Interfaces:** nenhuma.

- [ ] **Step 1: Confirmar o board/labels do repositório**

```bash
gh issue list --repo smsilva/wasp-idp --limit 1
gh label list --repo smsilva/wasp-idp
```

- [ ] **Step 2: Abrir as 5 issues**

```bash
gh issue create --repo smsilva/wasp-idp \
  --title "ci: role chaining trava a sessão do provisionamento em 1h" \
  --body "A role \`network\` (raiz \`aws/terraform/ci/\`) encadeia de \`cicd\` via \`source_profile\`. A doc da IAM é explícita: \"When you use role chaining, the session duration is limited to one hour, regardless of the maximum session duration setting configured for individual roles\" — nenhum \`max_session_duration\` levanta esse teto. O \`apply\` de \`module.cell\` leva 20-30 min: a margem existe, mas é fina, e o modo de falha (renovação expirando no meio de um apply) é confuso e longe da causa.

Mitigação se apertar: dar trust OIDC direto à role \`network\` em vez de encadear de \`cicd\` — abandona o espelhamento da cadeia operacional atual (\`personal\` → \`network\`/\`cicd\`), por isso não foi feito na primeira versão do workflow.

Referência: docs/superpowers/specs/2026-08-31-github-actions-provisioning-workflow-design.md, seção Limitações."

gh issue create --repo smsilva/wasp-idp \
  --title "ci: sub do trust OIDC aceita qualquer branch (refs/heads/*)" \
  --body "A role \`cicd\` (raiz \`aws/terraform/ci/\`) confia em \`repo:smsilva/wasp-idp:ref:refs/heads/*\` — qualquer branch deste repositório pode disparar o workflow e assumir a role, deliberadamente, para permitir validar o workflow antes do merge em \`main\`.

Apertar para \`refs/heads/main\` depois que \`provision-region.yml\` estiver validado em uso real — mudar \`aws/terraform/ci/main.tf\`, o \`local.cicd_trust_policy\`, e o teste correspondente em \`aws/terraform/ci/tests/roles.tftest.hcl\`.

Referência: docs/superpowers/specs/2026-08-31-github-actions-provisioning-workflow-design.md, seção Limitações."

gh issue create --repo smsilva/wasp-idp \
  --title "ci: endpoint público do EKS fica aberto se o job morrer antes do passo de fechamento" \
  --body "\`.github/workflows/provision-region.yml\` abre o endpoint público do EKS com \`--public-cidr <ip-do-runner>/32\` e fecha com \`--close-public-access\` num passo \`if: always()\`. Se o runner for encerrado à força (timeout do job, cancelamento manual, falha de infraestrutura do GitHub) antes de esse passo rodar, o endpoint fica aberto restrito ao IP do runner — que já não existe mais, mas o CIDR permanece na configuração do cluster até o próximo apply.

Sem sweep agendado — decisão explícita já registrada na spec do obstáculo 2 (acesso privado do runner, PR #46). Se isso se mostrar um problema recorrente, considerar um workflow agendado que force \`--close-public-access\` periodicamente.

Referência: docs/superpowers/specs/2026-08-31-github-actions-provisioning-workflow-design.md, seção Limitações."

gh issue create --repo smsilva/wasp-idp \
  --title "ci: variables/values.tfvars versionado — reverter quando as contas deixarem de ser efêmeras" \
  --body "\`aws/terraform/variables/values.tfvars\` saiu do \`.gitignore\` em 2026-08-31 porque as contas AWS desta PoC são efêmeras e de teste — versionar elimina a maquinaria de materializar o arquivo em CI. Quando as contas passarem a ser de uso real/duradouro, reverter: voltar o arquivo para gitignored e reintroduzir alguma forma de materialização em CI (ex.: um secret por chave, ou um secret único com o \`.tfvars\` inteiro).

Referência: docs/superpowers/specs/2026-08-31-github-actions-provisioning-workflow-design.md, seção Limitações."

gh issue create --repo smsilva/wasp-idp \
  --title "ci: rotação do certificado do Identity Center exige atualizar o secret SAML_METADATA_XML à mão" \
  --body "O metadata SAML do Identity Center vive no secret do GitHub \`SAML_METADATA_XML\`, escrito em \`variables/saml-metadata.xml\` no início de cada job. Quando o certificado da aplicação SAML rotacionar (o Identity Center rotaciona periodicamente), o secret precisa ser atualizado à mão, baixando o metadata novo no console. Sem esse passo, o primeiro sintoma é falha de validação do Client VPN — longe da causa raiz.

Sem automação prevista: \`CreateApplication\`/rotação de certificado SAML não são operações de API do Identity Center. O item aqui é só o lembrete operacional — nenhuma mudança de código pendente, a menos que se decida por um alerta de expiração.

Referência: docs/superpowers/specs/2026-08-31-github-actions-provisioning-workflow-design.md, seção Limitações."
```

- [ ] **Step 3: Adicionar as 5 issues ao Project v2 (board #6) e ao backlog**

```bash
for n in $(gh issue list --repo smsilva/wasp-idp --search "ci: role chaining OR ci: sub do trust OR ci: endpoint público OR ci: variables/values.tfvars OR ci: rotação do certificado" --json number --jq '.[].number'); do
  gh issue edit "${n}" --repo smsilva/wasp-idp --add-label "backlog" 2>/dev/null || true
done
```

Se o repositório usa GitHub Projects v2 em vez de labels para backlog (como o restante desta sessão indicou — board #6), adicionar via `gh project item-add` com o número do projeto e a URL de cada issue, seguindo o mesmo padrão já usado nesta sessão para mover #37/#41.

---

## Self-Review

**1. Cobertura da spec:** OIDC provider sem thumbprint (Task 3) · trust `cicd`↔GitHub e `network`↔`cicd` com testes de mutação (Tasks 3-4) · permissões PowerUserAccess+inline declarado como fallback (Task 5) · raiz `ci/` T0 com `terraform test` (Tasks 2-5) · `ci/README.md` referenciado do README principal (Task 6) · `values.tfvars` versionado (Task 1) · SAML em secret do GitHub (Tasks 7-8) · `provision-region.yml` nos 7 passos da spec (Task 7) · `recover-lock.yml` com inputs obrigatórios sem default (Task 8) · `bootstrap-checklist.md` com os 8 itens (Task 9) · as 5 issues de limitações (Task 10). Nenhuma lacuna identificada.

**2. Placeholders:** nenhum "TBD"/"implementar depois" — todo passo de código tem o conteúdo real (HCL, YAML, bash) que será commitado.

**3. Consistência de tipos/nomes:** `var.role_name` (Task 2) usado identicamente em `aws_iam_role.cicd.name`/`aws_iam_role.network.name` (Tasks 3-4); `aws_iam_role.cicd.arn`/`aws_iam_role.network.arn` (Tasks 3-4) referenciados nos outputs implícitos consumidos por `ci/README.md` (Task 6, `terraform output -raw cicd_role_arn`) — **atenção:** nenhuma task acima declara blocos `output`. Corrigido abaixo.

### Correção pós-autorrevisão: outputs da raiz `ci/`

Adicionar a **Task 5, Step 3** (mesmo commit), ao final de `main.tf`:

```hcl
output "cicd_role_arn" {
  description = "ARN da role assumida via OIDC do GitHub. Configurar como variable CICD_ROLE_ARN no repositorio GitHub."
  value       = aws_iam_role.cicd.arn
}

output "network_role_arn" {
  description = "ARN da role assumida por encadeamento a partir da cicd. Configurar como variable NETWORK_ROLE_ARN no repositorio GitHub."
  value       = aws_iam_role.network.arn
}
```

E, na Task 5 Step 4, acrescentar `terraform output` à lista de comandos de verificação (sem asserção de teste — outputs não são testáveis por `mock_provider` de forma útil aqui, já que o valor é só um repasse de atributo já coberto pelos testes de trust).

---

## Execution Handoff

Plano completo e salvo em `docs/superpowers/plans/2026-08-31-github-actions-provisioning-workflow.md`. Duas opções de execução:

**1. Subagent-Driven (recomendado)** — um subagente por task, revisão entre tasks, iteração rápida.

**2. Inline Execution** — execução em lote nesta sessão via `executing-plans`, com checkpoints.

Qual abordagem?
