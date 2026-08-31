# GitHub Actions Runner Private Access Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** dar a `up-02-region` duas flags novas (`--public-cidr`, `--close-public-access`) que
permitem a um runner de CI (ou qualquer chamador) abrir e fechar o endpoint público da API do EKS
restrito a um único CIDR, por execução — sem infraestrutura de rede nova.

**Architecture:** o mecanismo (`endpoint_public_access`/`public_access_cidrs`) já existe em
`src/cluster`/`src/cell`, mas `regions/<região>/` nunca o repassa — é um wiring gap desde a
consolidação da ADR 0014. A Task 1 conserta o repasse (as duas variáveis viajam
`regions/<região>` → `module.cell` → `module.cluster`, e `src/cell` reexporta os dois outputs de
`module.cluster` para o teste do root conseguir provar isso). A Task 2 estende `scripts/lib` e
`up-02-region` para injetar `-var` só nesses dois casos, sem passthrough genérico.

**Tech Stack:** Terraform ≥ 1.15, provider `aws` ~> 6.x; `terraform test` com `mock_provider` para
regressão offline; bash para os scripts `up-*`.

**Spec:**
`docs/superpowers/specs/2026-08-31-github-actions-runner-private-access-design.md` — a decisão, as
abordagens rejeitadas e as limitações aceitas. Ler antes de executar.

## Global Constraints

- `--public-cidr` e `--close-public-access` são mutuamente exclusivas — o script recusa as duas
  juntas.
- As duas só têm efeito com `--with-cell` — só `module.cell` consome essas variáveis. O script
  recusa qualquer uma das duas sem `--with-cell`.
- `--close-public-access` nunca manda `public_access_cidrs` explícito (nem vazio) — o módulo já
  omite o atributo quando `endpoint_public_access = false`; mandar lista vazia é a pegadinha de
  perpetual diff já documentada em `aws/terraform/CLAUDE.md`.
- Nenhuma das duas flags escreve em `variables/values.tfvars` — o override é só `-var` na chamada
  de `terraform plan`, nunca no arquivo compartilhado (regra "declarado, não descoberto",
  `aws/terraform/CLAUDE.md`).
- Comentários e mensagens de `--help` dos scripts em inglês (convenção já usada nos scripts
  existentes); comentários de código Terraform em pt-BR (convenção do repo).

---

### Task 1: Consertar o repasse de `regions/<região>` para `module.cell`

**Files:**
- Modify: `aws/terraform/regions/us-east-1/variables.tf`
- Modify: `aws/terraform/regions/us-east-1/main.tf:106-135`
- Modify: `aws/terraform/regions/us-west-2/variables.tf`
- Modify: `aws/terraform/regions/us-west-2/main.tf:106-135`
- Modify: `aws/terraform/src/cell/outputs.tf`
- Modify: `aws/terraform/regions/us-east-1/tests/composition.tftest.hcl`
- Modify: `aws/terraform/regions/us-west-2/tests/composition.tftest.hcl`

**Interfaces:**
- Consumes: `module.cell.endpoint_public_access` (bool), `module.cell.public_access_cidrs`
  (list(string)) — hoje inexistentes, esta task os cria.
- Produces: `var.endpoint_public_access`/`var.public_access_cidrs` em cada raiz `regions/<região>`,
  repassadas até `module.cluster` (dentro de `module.cell`), e reexportadas de volta como
  `module.cell.endpoint_public_access`/`module.cell.public_access_cidrs`. A Task 2 injeta valores
  nessas duas variáveis via `-var`.

- [ ] **Step 1: Escrever o teste que prova a lacuna (falha antes do fix)**

Em `aws/terraform/regions/us-east-1/tests/composition.tftest.hcl`, acrescentar ao final do
arquivo:

```hcl
# Achado na sessao 2026-08-31: regions/<regiao> nunca repassava estas duas variaveis para
# module.cell — o break-glass documentado no README.md ficava sem efeito desde a consolidacao
# da ADR 0014 (editar values.tfvars so produzia warning de variavel nao declarada aqui).
run "endpoint_publico_nasce_fechado" {
  command = plan

  override_data {
    target = data.aws_availability_zones.network
    values = { names = ["us-east-1a", "us-east-1b"] }
  }

  override_data {
    target = data.aws_availability_zones.cell
    values = { names = ["us-east-1a", "us-east-1b"] }
  }

  assert {
    condition     = module.cell.endpoint_public_access == false
    error_message = "o default tem de ser fechado, recebido ${module.cell.endpoint_public_access}"
  }
}

run "endpoint_publico_repassa_o_cidr_ate_o_cluster" {
  command = plan

  variables {
    endpoint_public_access = true
    public_access_cidrs    = ["203.0.113.10/32"]
  }

  override_data {
    target = data.aws_availability_zones.network
    values = { names = ["us-east-1a", "us-east-1b"] }
  }

  override_data {
    target = data.aws_availability_zones.cell
    values = { names = ["us-east-1a", "us-east-1b"] }
  }

  assert {
    condition     = module.cell.endpoint_public_access == true
    error_message = "o flag do root deveria chegar a module.cell, recebido ${module.cell.endpoint_public_access}"
  }

  assert {
    condition     = module.cell.public_access_cidrs == toset(["203.0.113.10/32"])
    error_message = "o CIDR do root deveria chegar a module.cell, recebido ${jsonencode(module.cell.public_access_cidrs)}"
  }
}
```

- [ ] **Step 2: Rodar o teste e confirmar que falha pela razão certa**

```bash
cd /home/silvios/git/wasp-idp/aws/terraform/regions/us-east-1
terraform test -no-color -filter=tests/composition.tftest.hcl
```

Esperado: `Error: Unsupported attribute` ou `Error: Reference to undeclared resource` nas duas
novas asserções — `module.cell.endpoint_public_access` não existe ainda. Se o erro for outro
(ex.: variável `endpoint_public_access` não declarada na raiz), tudo bem também — confirma que a
raiz não tem a variável, o mesmo sintoma do bug. O importante é NÃO passar.

- [ ] **Step 3: Declarar as duas variáveis em `regions/us-east-1/variables.tf`**

Acrescentar ao final do arquivo:

```hcl
variable "endpoint_public_access" {
  description = <<-EOT
    Expor o endpoint da API do EKS na internet, restrito a public_access_cidrs. DEFAULT false —
    repassado direto a module.cell, que documenta o resto (src/cell/variables.tf).
  EOT
  type        = bool
  default     = false
}

variable "public_access_cidrs" {
  description = "CIDRs autorizados quando endpoint_public_access = true. Ver src/cell/variables.tf."
  type        = list(string)
  default     = []
}
```

- [ ] **Step 4: Repassar as duas em `regions/us-east-1/main.tf`**

Em `main.tf`, dentro do bloco `module "cell" { ... }`, a linha `target_account_ids =
var.target_account_ids` (linha 125) é seguida por uma linha em branco e o comentário `# O hub, por
referencia`. Inserir as duas novas linhas logo após `target_account_ids`:

```hcl
  target_account_ids = var.target_account_ids

  endpoint_public_access = var.endpoint_public_access
  public_access_cidrs    = var.public_access_cidrs

  # O hub, por referencia. Cada linha aqui e um data source que morreu do outro lado.
```

(Substitui o texto atual — a linha em branco e o comentário `# O hub, por referencia...` já
existem; só as duas linhas novas entram entre `target_account_ids` e a linha em branco.)

- [ ] **Step 5: Repetir os Steps 3 e 4 em `regions/us-west-2`**

`regions/us-west-2/variables.tf` e `regions/us-west-2/main.tf` são idênticos aos de
`us-east-1` (só `locals` de `main.tf` e a `key` de `versions.tf` divergem — invariante já
documentado no `README.md`). Aplicar as mesmas duas edições, byte a byte:

```bash
diff /home/silvios/git/wasp-idp/aws/terraform/regions/us-east-1/variables.tf \
     /home/silvios/git/wasp-idp/aws/terraform/regions/us-west-2/variables.tf
```

Esperado antes desta task: nenhuma diferença. Editar `us-west-2/variables.tf` com o texto idêntico
do Step 3, e `us-west-2/main.tf` com a mesma inserção do Step 4 (mesmas linhas, mesmo lugar —
`us-west-2/main.tf` também tem `target_account_ids = var.target_account_ids` seguido do mesmo
comentário `# O hub, por referencia`).

- [ ] **Step 6: Reexportar os dois outputs em `src/cell/outputs.tf`**

Ao final do arquivo, acrescentar:

```hcl
# Reexportados para regions/<regiao> conseguir testar o repasse de endpoint_public_access/
# public_access_cidrs sem precisar alcancar module.cluster de dois niveis acima (fronteira de
# modulo nao e transparente — mesmo motivo de cluster_endpoint/cluster_ca_data acima).
output "endpoint_public_access" {
  description = "Se o endpoint da API do EKS esta exposto na internet."
  value       = module.cluster.endpoint_public_access
}

output "public_access_cidrs" {
  description = "CIDRs autorizados no endpoint publico, quando aberto."
  value       = module.cluster.public_access_cidrs
}
```

- [ ] **Step 7: Copiar o teste do Step 1 para `regions/us-west-2/tests/composition.tftest.hcl`**

Mesmo conteúdo dos dois `run` blocks do Step 1, adaptado só na região do
`aws_availability_zones` — `us-west-2a`/`us-west-2b` em vez de `us-east-1a`/`us-east-1b` (mesma
convenção que o resto do arquivo já usa, confirmável com `diff` entre os dois arquivos de teste
antes desta task).

- [ ] **Step 8: Rodar os testes das duas regiões e confirmar que passam**

```bash
cd /home/silvios/git/wasp-idp/aws/terraform
for r in regions/us-east-1 regions/us-west-2; do
  echo "=== ${r}"
  (cd "${r}" && terraform init -backend=false -no-color >/dev/null && terraform test -no-color)
done
```

Esperado: `Success!` nas duas raízes, incluindo os dois `run` novos em cada uma.

- [ ] **Step 9: Rodar a regressão offline completa (garantir que nada mais quebrou)**

```bash
cd /home/silvios/git/wasp-idp/aws/terraform
for m in src/network src/state-backend src/pod-identity src/cluster src/nodegroup src/ingress \
         src/hub src/cell \
         src/helm/modules/aws-load-balancer-controller \
         src/helm/modules/external-secrets src/helm/modules/argo-cd src/helm/modules/crossplane \
         regions/us-east-1 regions/us-west-2 dns; do
  echo "=== ${m}"
  (cd "${m}" && terraform init -backend=false -no-color >/dev/null && terraform test -no-color)
done
```

Esperado: `Success!` em todos, sem linha vazia (linha vazia = `init` morto por SSO caído, não "sem
testes" — ver `aws/terraform/CLAUDE.md`).

- [ ] **Step 10: Commit**

```bash
cd /home/silvios/git/wasp-idp
git add aws/terraform/regions/us-east-1/variables.tf aws/terraform/regions/us-east-1/main.tf \
        aws/terraform/regions/us-west-2/variables.tf aws/terraform/regions/us-west-2/main.tf \
        aws/terraform/src/cell/outputs.tf \
        aws/terraform/regions/us-east-1/tests/composition.tftest.hcl \
        aws/terraform/regions/us-west-2/tests/composition.tftest.hcl
git commit -m "$(cat <<'EOF'
fix(terraform): repassar endpoint_public_access/public_access_cidrs a module.cell

regions/<regiao>/main.tf nunca declarava nem repassava essas duas
variaveis para module.cell - o break-glass documentado no README.md
(editar variables/values.tfvars) ficava sem efeito desde a
consolidacao da ADR 0014, silenciosamente (so um warning de variavel
nao declarada). src/cell reexporta os dois outputs de module.cluster
para o teste do root conseguir provar o repasse.

Refs #41
EOF
)"
```

---

### Task 2: Flags `--public-cidr`/`--close-public-access` em `up-02-region`

**Files:**
- Modify: `aws/terraform/scripts/lib:101-104` (assinatura de `terraform_plan_and_apply`)
- Modify: `aws/terraform/scripts/lib:116` (chamada de `terraform plan` dentro da função)
- Modify: `aws/terraform/scripts/up-02-region`
- Modify: `aws/terraform/README.md`

**Interfaces:**
- Consumes: `var.endpoint_public_access`/`var.public_access_cidrs` da Task 1.
- Produces: `up-02-region --public-cidr <cidr>` e `up-02-region --close-public-access`, chamáveis
  por um workflow de CI (fora do escopo deste plano) ou por um operador humano na mesma sessão de
  CLI que já usa `--with-cell`.

- [ ] **Step 1: Estender `terraform_plan_and_apply` para aceitar `-var` extra**

Em `aws/terraform/scripts/lib`, a função hoje (linhas 101-104):

```bash
terraform_plan_and_apply() {
  local root="${1?}"
  local label="${2?}"
  local assume_yes="${3:-false}"
```

Trocar para:

```bash
terraform_plan_and_apply() {
  local root="${1?}"
  local label="${2?}"
  local assume_yes="${3:-false}"
  shift 3
  local extra_plan_args=("$@")
```

E a chamada de `terraform plan` (linha 116, hoje):

```bash
  (cd "${root}" && terraform plan -no-color -input=false -out="${plan_file}") 2>&1 | tee "${plan_log}"
```

Trocar para:

```bash
  (cd "${root}" && terraform plan -no-color -input=false -out="${plan_file}" "${extra_plan_args[@]}") 2>&1 | tee "${plan_log}"
```

Os `-var` só entram no `plan` — o `apply` usa o arquivo de plano salvo (`terraform apply
"${plan_file}"`, linha 157), que já embute os valores resolvidos e não aceita `-var` de novo.
`shift 3` nunca falha aqui: a função sempre recebe pelo menos 3 argumentos (os `?` nos três
primeiros `local` já garantem isso). Chamadas existentes com exatamente 3 argumentos (como a de
`up-01-dns`) continuam funcionando sem mudança: `extra_plan_args` fica vazio.

- [ ] **Step 2: Verificar que `up-01-dns` continua funcionando (retrocompatibilidade)**

```bash
cd /home/silvios/git/wasp-idp/aws/terraform/scripts
bash -n lib && echo "syntax ok"
bash -n up-01-dns && echo "syntax ok"
```

Esperado: `syntax ok` nas duas. (A verificação funcional completa de `up-01-dns` já foi feita na
fase 4 — este step só garante que a mudança em `lib` não quebrou a sintaxe que ele consome.)

- [ ] **Step 3: Acrescentar as duas variáveis de flag em `up-02-region`**

Depois de `with_cell="false"` (linha 65), acrescentar:

```bash
public_cidr=""
close_public_access="false"
```

- [ ] **Step 4: Acrescentar os dois `case` novos no parsing de opções**

Depois do bloco `--with-cell )` (linhas 83-85):

```bash
    --with-cell )
      with_cell="true"
      ;;

    --public-cidr )
      shift
      public_cidr="${1}"
      ;;

    --close-public-access )
      close_public_access="true"
      ;;

    --state-bucket )
```

(a linha `--state-bucket )` já existe logo depois — só as duas novas entram entre `--with-cell`
e `--state-bucket`.)

- [ ] **Step 5: Guards de uso — mutuamente exclusivas, e exigem `--with-cell`**

Depois de `set -e` (linha 106), antes de `require_tools` (linha 108):

```bash
set -e

if [ -n "${public_cidr}" ] && [ "${close_public_access}" == "true" ]; then
  fail "--public-cidr and --close-public-access are mutually exclusive."
fi

if { [ -n "${public_cidr}" ] || [ "${close_public_access}" == "true" ]; } && [ "${with_cell}" != "true" ]; then
  fail "--public-cidr/--close-public-access only affect module.cell — pass --with-cell too."
fi

require_tools aws jq terraform
```

- [ ] **Step 6: Montar o `-var` extra e passar para `terraform_plan_and_apply`**

Antes do `if [ "${with_cell}" == "true" ]; then` (linha 135), acrescentar:

```bash
cell_network_args=()
if [ -n "${public_cidr}" ]; then
  cell_network_args=(-var "endpoint_public_access=true" -var "public_access_cidrs=[\"${public_cidr}\"]")
elif [ "${close_public_access}" == "true" ]; then
  cell_network_args=(-var "endpoint_public_access=false")
fi
```

E trocar a chamada (linha 136):

```bash
  terraform_plan_and_apply "${root}" "region-${region}" "${assume_yes}"
```

por:

```bash
  terraform_plan_and_apply "${root}" "region-${region}" "${assume_yes}" "${cell_network_args[@]}"
```

- [ ] **Step 7: Atualizar `--help`**

No bloco de opções (linhas 44-51), acrescentar as duas novas depois de `--with-cell`:

```
      -h,  --help           Show this help
      -y,  --yes            Do not ask before applying
      -r,  --region         Region root under regions/ (default: us-east-1)
           --with-cell      Also apply module.cell (~US\$ 165/month; needs
                             the Client VPN tunnel connected)
           --public-cidr    Open the EKS API's public endpoint restricted to
                             this CIDR, for module.cell only (needs
                             --with-cell). Mutually exclusive with
                             --close-public-access.
           --close-public-access
                             Close the EKS API's public endpoint (needs
                             --with-cell). Mutually exclusive with
                             --public-cidr.
           --state-bucket   Bucket name (default: tfstate-<organization-id>)
           --org-profile    Profile that reads Organizations and Identity
                             Center (default: personal)
```

E um exemplo novo depois dos existentes (linhas 53-57):

```
    Examples:

      ${this_script_name}

      ${this_script_name} --yes --with-cell

      ${this_script_name} --yes --with-cell --public-cidr 203.0.113.10/32
```

- [ ] **Step 8: Verificar sintaxe e `--help`**

```bash
cd /home/silvios/git/wasp-idp/aws/terraform/scripts
bash -n up-02-region && echo "syntax ok"
./up-02-region --help 2>&1 | grep -A2 'public-cidr\|close-public-access'
```

Esperado: sintaxe ok, e as duas flags aparecem documentadas na saída.

- [ ] **Step 9: Verificar os dois guards sem tocar a AWS**

```bash
cd /home/silvios/git/wasp-idp/aws/terraform/scripts
./up-02-region --public-cidr 203.0.113.10/32 --close-public-access 2>&1 | tail -3
echo "exit=$?"
./up-02-region --public-cidr 203.0.113.10/32 2>&1 | tail -3
echo "exit=$?"
```

Esperado: a primeira chamada falha com `ERROR: --public-cidr and --close-public-access are
mutually exclusive.`; a segunda falha com `ERROR: --public-cidr/--close-public-access only affect
module.cell — pass --with-cell too.`. As duas saem antes de `require_tools`/qualquer chamada AWS —
conferir que nenhuma delas imprime nada de `aws`/`terraform`.

- [ ] **Step 10: Verificar o `-var` chegando ao plan de verdade (sem aplicar)**

Requer SSO ativo. Roda um `plan` manual passando os mesmos `-var` que o script montaria, contra
`regions/us-east-1` (sem tocar `up-02-region` em si, para não arriscar um apply real por engano —
mesma lição já registrada em `HANDOFF.md` desta sessão):

```bash
cd /home/silvios/git/wasp-idp/aws/terraform/regions/us-east-1
terraform plan -no-color -input=false \
  -var 'endpoint_public_access=true' -var 'public_access_cidrs=["203.0.113.10/32"]' \
  2>&1 | grep -A3 'endpoint_public_access\|public_access_cidrs'
```

Esperado: o plan mostra a mudança de `endpoint_public_access` para `true` e `public_access_cidrs`
para `["203.0.113.10/32"]` no `module.cell.module.cluster.aws_eks_cluster.this` (ou "No changes"
se o cluster real já estiver com esse valor — não deve estar, dado que o hub está com zero
recursos nesta sessão, então este `plan` mostra o cluster inteiro sendo criado, e a asserção é
sobre os valores DENTRO desse plano de criação).

- [ ] **Step 11: Documentar as flags no `README.md`**

Na seção "Sequência de provisionamento", depois do parágrafo que explica `--with-cell` (logo após
a tabela de custo/sequência, antes de "Desbloqueio de emergência"), acrescentar:

```markdown
**Para CI (ou qualquer chamador não-interativo) sem túnel do Client VPN:** `--public-cidr <cidr>`
abre o endpoint público da API do EKS restrito a esse CIDR só para o apply da célula, e
`--close-public-access` fecha de novo — nenhuma infraestrutura de rede nova, é o mesmo
break-glass abaixo, só que setado por flag em vez de editar `variables/values.tfvars`. As duas só
valem com `--with-cell`, e são mutuamente exclusivas. Ver
`docs/superpowers/specs/2026-08-31-github-actions-runner-private-access-design.md` para o desenho
completo e as limitações aceitas (sem sweep de fechamento agendado; break-glass manual e de CI
compartilham o mesmo atributo — não usar os dois ao mesmo tempo).
```

- [ ] **Step 12: Commit**

```bash
cd /home/silvios/git/wasp-idp
git add aws/terraform/scripts/lib aws/terraform/scripts/up-02-region aws/terraform/README.md
git commit -m "$(cat <<'EOF'
feat(terraform): flags --public-cidr/--close-public-access em up-02-region

Permite abrir o endpoint publico da API do EKS restrito a um CIDR so
para o apply da celula (sem tunel do Client VPN), e fechar de novo -
mecanismo pensado para CI (issue #41), mas utilizavel por qualquer
chamador nao-interativo. Reaproveita o break-glass ja existente
(endpoint_public_access/public_access_cidrs, consertado na task
anterior), sem infraestrutura de rede nova. Mutuamente exclusivas,
exigem --with-cell, nunca escrevem em variables/values.tfvars.

Ver docs/superpowers/specs/2026-08-31-github-actions-runner-private-access-design.md
para o desenho completo.

Refs #41
EOF
)"
git push
```

---

## Aceite do plano

- [ ] Os testes offline de `regions/us-east-1` e `regions/us-west-2` provam o repasse
  (`endpoint_public_access`/`public_access_cidrs` chegando a `module.cell`), com mutação (o teste
  falhava antes do fix, passa depois).
- [ ] `up-02-region --help` documenta as duas flags novas.
- [ ] As duas flags recusam uso sem `--with-cell` e recusam uso combinado entre si.
- [ ] Um `-var` equivalente ao que as flags montam, aplicado manualmente contra
  `regions/us-east-1`, muda `endpoint_public_access`/`public_access_cidrs` no plano do cluster.
- [ ] Regressão offline completa (todos os módulos) continua verde depois das duas tasks.
- [ ] `variables/values.tfvars` nunca é escrito por nenhuma das duas flags — conferir com
  `git status`/`git diff` no arquivo (fora do repo, gitignored) depois dos testes.
