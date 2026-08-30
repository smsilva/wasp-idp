# Fase 1 — um `values.tfvars` único, sem descoberta

Fecha o critério de aceite da issue #36 **no desenho de hoje**, antes de qualquer extração de módulo:
as raízes continuam onde estão, mas nenhum `up-NN` chama `generate-tfvars` e nenhum valor é
descoberto em runtime. É o walk skeleton da frente — aplicável e verificável na AWS sozinho.

**Pré-requisito:** ler o [`README.md`](README.md) do plano, em especial a tabela "Onde cada valor de
hoje vai parar" — ela é o critério para aceitar ou recusar valor novo no `values.tfvars`.

---

### Task 1: `variables/values.tfvars` como fonte única

**Files:**
- Create: `aws/terraform/variables/values.tfvars.example`
- Create: `aws/terraform/variables/README.md`
- Modify: `.gitignore`
- Delete: `aws/terraform/dns/terraform.tfvars`, `aws/terraform/connectivity/us-east-1/terraform.tfvars`, `aws/terraform/control-plane/terraform.tfvars`
- Delete: `aws/terraform/connectivity/us-east-1/terraform.tfvars.example`, `aws/terraform/control-plane/terraform.tfvars.example`, `aws/terraform/dns/terraform.tfvars.example`

**Interfaces:**
- Produces: o arquivo `aws/terraform/variables/values.tfvars`, carregado por cada raiz através de um
  symlink gitignored `values.auto.tfvars`. Todas as tasks seguintes assumem que qualquer valor de
  identidade vem daí, e que `terraform plan` numa raiz funciona **sem flag e sem passo prévio**.

- [ ] **Step 1: escrever o inventário versionado, com placeholders**

`aws/terraform/variables/values.tfvars.example`:

```hcl
# Inventário dos valores de IDENTIDADE das camadas Terraform — os que identificam esta conta,
# esta Organization e estas pessoas. Copie para values.tfvars (gitignored) e preencha.
#
#   cp values.tfvars.example values.tfvars
#
# O que NÃO entra aqui: região, CIDR, nome do hub, versão do Kubernetes, profiles. Isso é decisão
# de desenho documentada em aws/docs/network/ e vive inline na raiz ou como default de variável —
# ver a tabela "Onde cada valor de hoje vai parar" no plano
# docs/superpowers/plans/2026-08-29-regional-root-hub-and-cell-modules/README.md.
#
# Cada raiz carrega este arquivo por um symlink values.auto.tfvars. Chave que uma raiz não declara
# vira warning "Value for undeclared variable" — é esperado, não erro: o arquivo é único e as
# raízes são várias.

# Domínio raiz sob o qual a camada dns/ delegou a subzona. SEM valor default em nenhuma raiz de
# propósito: a ausência faz o plan falhar por validação explícita, em vez de herdar o domínio de
# outra conta.
base_domain = "exemplo.com"

# IDs de grupo do Identity Center que recebem authorization rule no Client VPN. UUID, NÃO nome: o
# Client VPN casa a rule contra o `memberOf` da assertion, e o Identity Center manda UUID. Nome ali
# produz túnel que sobe e não alcança nada. Resolva uma vez com:
#
#   aws sso-admin list-instances --profile personal --output json
#   aws identitystore list-groups --identity-store-id <id> --profile personal \
#     --query 'Groups[].[DisplayName,GroupId]' --output table
operator_group_ids = ["00000000-0000-0000-0000-000000000000"]

# Contas às quais o TGW é compartilhado via RAM, para que cada uma crie o próprio attachment.
# Uma por célula — hoje só a conta cicd. Resolva com:
#
#   aws organizations list-accounts --profile personal --output json
spoke_account_ids = ["000000000000"]

# Conta que hospeda a VPC hub (a conta network).
network_account_id = "000000000000"

# Contas onde o Crossplane cria recursos, via assume role.
target_account_ids = ["000000000000"]

# BREAK-GLASS — descomente para abrir o endpoint público da API do EKS e declarar quem o alcança.
# Ausente, o endpoint fica fechado e o caminho é o túnel do Client VPN -> TGW -> ENI do endpoint.
# O CIDR é declarado à MÃO: não há descoberta do "/32 desta máquina".
#
# endpoint_public_access = true
# public_access_cidrs    = ["203.0.113.10/32"]
```

- [ ] **Step 2: escrever o `README.md` da pasta**

`aws/terraform/variables/README.md`:

```markdown
# Local values

Um arquivo, `values.tfvars`, gitignored, com os valores de **identidade** das camadas Terraform.
Cada raiz o carrega por um symlink `values.auto.tfvars` — que o Terraform lê sozinho, sem
`-var-file` e sem passo de geração.

```bash
cp values.tfvars.example values.tfvars
$EDITOR values.tfvars
```

Sem ele, `terraform plan` falha em `base_domain` com uma mensagem que diz o que falta. Isso é o
mecanismo, não um efeito colateral: variável sem default é a forma de falhar fechado, e um valor
herdado de outra conta é pior que um erro.

Decisão em [ADR 0014](../../../docs/adr/0014-single-regional-root-composing-hub-and-cell-modules.md);
o formato tfvars substitui o `values.yaml` do [ADR 0013](../../../docs/adr/0013-consolidate-local-values-yaml.md).
```

- [ ] **Step 3: cobrir o arquivo real e os symlinks no `.gitignore`**

Acrescentar ao bloco Terraform de `/home/silvios/git/wasp-idp/.gitignore`, logo depois da linha
`!terraform.tfvars.example`:

```gitignore
# Valores locais de identidade: um arquivo, carregado por cada raiz via symlink values.auto.tfvars.
# O .example É versionado — é o inventário de o que precisa ser preenchido.
aws/terraform/variables/values.tfvars
**/values.auto.tfvars
```

- [ ] **Step 4: criar os symlinks e provar que o Terraform os lê**

```bash
cd /home/silvios/git/wasp-idp/aws/terraform
ln --symbolic ../variables/values.tfvars       dns/values.auto.tfvars
ln --symbolic ../../variables/values.tfvars    connectivity/us-east-1/values.auto.tfvars
ln --symbolic ../variables/values.tfvars       control-plane/values.auto.tfvars
git check-ignore dns/values.auto.tfvars connectivity/us-east-1/values.auto.tfvars control-plane/values.auto.tfvars
```

Esperado: as três linhas ecoadas por `check-ignore` (todas ignoradas). Nenhuma saída ⟹ o padrão do
Step 3 não pegou, corrigir antes de seguir.

- [ ] **Step 5: preencher o `values.tfvars` real a partir do que já existe**

Os valores estão nos `terraform.tfvars` que ainda existem nas três raízes e em `CLAUDE.local.md`.
Copiar à mão, sem script: é uma vez só, e o passo de geração é justamente o que esta fase remove.

```bash
cd /home/silvios/git/wasp-idp/aws/terraform
cp variables/values.tfvars.example variables/values.tfvars
$EDITOR variables/values.tfvars
```

- [ ] **Step 6: provar que o plan resolve sem os `terraform.tfvars` das raízes**

```bash
cd /home/silvios/git/wasp-idp/aws/terraform/dns
mv terraform.tfvars /tmp/dns-terraform.tfvars.backup
terraform plan -no-color -detailed-exitcode
```

Esperado: exit 0 (nada a mudar) ou 2 (mudanças), **nunca** `No value for required variable`. Um erro
aqui significa chave faltando ou com nome errado no `values.tfvars` — corrigir o arquivo, não devolver
o backup.

Repetir em `connectivity/us-east-1` e `control-plane`. Nessas duas o plan exige credencial e as
camadas vizinhas de pé; se o SSO estiver caído, o critério desta task é o `dns/` e a validação das
outras duas fica para a Task 5 (apply real).

- [ ] **Step 7: apagar os tfvars por raiz e os `.example` que eles tinham**

```bash
cd /home/silvios/git/wasp-idp/aws/terraform
rm --force dns/terraform.tfvars connectivity/us-east-1/terraform.tfvars control-plane/terraform.tfvars
git rm dns/terraform.tfvars.example \
       connectivity/us-east-1/terraform.tfvars.example \
       control-plane/terraform.tfvars.example
```

Os três `.example` versionados morrem porque o inventário passou a ser um só. Quem procurar "como
preencho isto" tem de achar **um** lugar, senão a segunda fonte fica desatualizada — que foi o que
aconteceu com o `terraform.tfvars.example` da `control-plane`, cujo comentário ainda manda rodar
`scripts/generate-tfvars --enable-public-endpoint`.

- [ ] **Step 8: commit**

```bash
cd /home/silvios/git/wasp-idp
git add .gitignore aws/terraform/variables/
git commit -m "feat(terraform): consolidar valores de identidade num values.tfvars unico

Um arquivo gitignored, carregado por cada raiz via symlink values.auto.tfvars,
no lugar de tres terraform.tfvars por raiz. Fecha o inventario que a #21 pedia.

Refs #21, #36"
```

---

### Task 2: `control-plane` para de precisar de valor descoberto

**Files:**
- Modify: `aws/terraform/control-plane/variables.tf`
- Modify: `aws/terraform/control-plane/main.tf:58-66` (chamada de `module "network"`)
- Test: `aws/terraform/control-plane/tests/composition.tftest.hcl`, `ingress-alb.tftest.hcl`, `isolation.tftest.hcl`, `spoke-attachment.tftest.hcl`

**Interfaces:**
- Consumes: `values.tfvars` da Task 1, que já traz `network_account_id` e `target_account_ids`.
- Produces: `local.availability_zones` na raiz — lista de duas AZs derivada de
  `data.aws_availability_zones.this.names`, consumida por `module "network"`. As fases 2 e 3 movem
  esse `local` para dentro de `src/cell` sem mudar a forma.

- [ ] **Step 1: escrever o teste que falha — as AZs vêm do data source, não de variável**

Acrescentar a `aws/terraform/control-plane/tests/composition.tftest.hcl`:

```hcl
# As AZs deixaram de ser input: vêm de data.aws_availability_zones, que é o mecanismo que
# substitui o `describe-availability-zones` do generate-tfvars. Dois runs com listas de tamanhos
# e valores diferentes — um só passaria mesmo se a raiz tivesse a lista fixa no código.
run "availability_zones_come_from_the_data_source" {
  command = plan

  override_data {
    target = data.aws_availability_zones.this
    values = {
      names = ["us-east-1a", "us-east-1b", "us-east-1c"]
    }
  }

  assert {
    condition     = toset(module.network.availability_zones) == toset(["us-east-1a", "us-east-1b"])
    error_message = "a raiz deve usar as DUAS primeiras AZs que o data source devolve"
  }
}

run "availability_zones_follow_a_different_region" {
  command = plan

  override_data {
    target = data.aws_availability_zones.this
    values = {
      names = ["us-west-2a", "us-west-2b", "us-west-2c", "us-west-2d"]
    }
  }

  assert {
    condition     = toset(module.network.availability_zones) == toset(["us-west-2a", "us-west-2b"])
    error_message = "a lista tem de vir do data source, nao estar fixa no codigo"
  }
}
```

`module.network` precisa expor `availability_zones` como output para a asserção existir. Se
`src/network/outputs.tf` ainda não o tem, acrescentar:

```hcl
output "availability_zones" {
  description = "AZs em que as subnets deste modulo nasceram. Existe para a raiz assertar de onde a lista veio."
  value       = var.availability_zones
}
```

- [ ] **Step 2: rodar e ver falhar pelo motivo certo**

```bash
cd /home/silvios/git/wasp-idp/aws/terraform/control-plane
terraform test -no-color -filter=tests/composition.tftest.hcl 2>&1 | tail -30
```

Esperado: falha citando `data.aws_availability_zones.this` inexistente (`Reference to undeclared
resource`). Falha por `No value for required variable "availability_zones"` também serve — é o mesmo
buraco visto do outro lado.

- [ ] **Step 3: trocar a variável pelo data source**

Em `aws/terraform/control-plane/variables.tf`, **remover** o bloco `variable "availability_zones"`
inteiro (linhas 39-42) e dar default aos valores estruturais:

```hcl
variable "region" {
  description = "Regiao AWS da celula."
  type        = string
  default     = "us-east-1"
}

variable "aws_profile" {
  description = "Profile local com acesso a conta cicd."
  type        = string
  default     = "cicd"
}

variable "vpc_cidr" {
  description = <<-EOT
    CIDR da VPC spoke. Um /16 dentro do supernet 10.0.0.0/12.

    Tem DEFAULT desde a fase 1: a alocacao esta documentada em
    aws/docs/network/01-cidr-addressing.md, o que a torna decisao de desenho, nao identidade —
    mesmo criterio que ja punha o CIDR do hub inline na network-foundation. Continua sendo a
    unica decisao IRREVERSIVEL da cadeia: mudar aqui recria a VPC inteira.
  EOT
  type        = string
  default     = "10.2.0.0/16"

  validation {
    condition     = can(cidrhost(var.vpc_cidr, 0)) && startswith(var.vpc_cidr, "10.") && can(tonumber(split(".", var.vpc_cidr)[1])) && tonumber(split(".", var.vpc_cidr)[1]) >= 0 && tonumber(split(".", var.vpc_cidr)[1]) <= 15
    error_message = "o CIDR deve ser um /16 dentro do supernet 10.0.0.0/12 (10.0 a 10.15), recebido ${var.vpc_cidr}."
  }
}
```

E corrigir a descrição de `kubernetes_version`, que hoje mente sobre quem a define:

```hcl
variable "kubernetes_version" {
  description = <<-EOT
    Versao do Kubernetes do control plane do EKS.

    Fixada aqui e revisada a olho, nao descoberta: `describe-cluster-versions` devolvia a default
    do EKS na hora, o que fazia a versao do cluster mudar sozinha entre dois applies da mesma
    arvore. Conferir contra a doc do EKS ao subir.
  EOT
  type        = string
  default     = "1.36"
}
```

Em `aws/terraform/control-plane/main.tf`, acrescentar o data source junto dos outros e passar o
`local` ao módulo:

```hcl
# As AZs da regiao, em vez de uma lista escrita no tfvars. Duas: o desenho da celula assume um par
# (o NLB interno fixa um IP privado por AZ, e o nodegroup distribui entre elas).
data "aws_availability_zones" "this" {
  state = "available"
}
```

No bloco `locals` da raiz, acrescentar:

```hcl
  availability_zones = slice(data.aws_availability_zones.this.names, 0, 2)
```

E na chamada de `module "network"` trocar `availability_zones = var.availability_zones` por
`availability_zones = local.availability_zones`.

- [ ] **Step 4: overridar o data source nos OUTROS arquivos de teste da raiz**

Passar a consumir data source num campo que o `src/network` usa para indexar subnets obriga a
overridá-lo em **todo** arquivo de teste da raiz, não só no novo — sob `mock_provider` o valor
sintético não é uma lista de AZs utilizável e o plan morre em raízes que nada tinham a ver com a
mudança. Em cada `run` de `ingress-alb.tftest.hcl`, `isolation.tftest.hcl` e
`spoke-attachment.tftest.hcl`, acrescentar:

```hcl
  override_data {
    target = data.aws_availability_zones.this
    values = {
      names = ["us-east-1a", "us-east-1b"]
    }
  }
```

- [ ] **Step 5: rodar a suíte inteira da raiz**

```bash
cd /home/silvios/git/wasp-idp/aws/terraform/control-plane
terraform test -no-color 2>&1 | tail -20
```

Esperado: `Success!`, com os dois runs novos inclusos. Linha **vazia** na saída significa que o
`init` morreu por credencial, não que não há testes — nesse caso rodar `terraform test` direto,
sem `init`.

- [ ] **Step 6: provar que a mutação é detectada**

Trocar `slice(data.aws_availability_zones.this.names, 0, 2)` por `["us-east-1a", "us-east-1b"]`
(a lista fixa que o teste existe para recusar) e rodar de novo.

Esperado: o run `availability_zones_follow_a_different_region` **falha**. Se passar, a asserção é
vazia — provavelmente `module.network` não expõe o output e a comparação é entre dois desconhecidos.
Antes de concluir "a mutação não foi detectada", conferir com `git diff` que ela foi de fato
aplicada. Desfazer a mutação depois.

- [ ] **Step 7: commit**

```bash
cd /home/silvios/git/wasp-idp
git add aws/terraform/control-plane aws/terraform/src/network
git commit -m "feat(terraform): derivar as AZs de data source e dar default ao que e estrutural

availability_zones sai do tfvars e vem de data.aws_availability_zones; region,
aws_profile, vpc_cidr e kubernetes_version ganham default. Sobra no tfvars so
identidade.

Refs #36"
```

---

### Task 3: `connectivity` para de precisar do arquivo gerado

**Files:**
- Modify: `aws/terraform/connectivity/us-east-1/variables.tf`
- Test: `aws/terraform/connectivity/us-east-1/tests/private-access.tftest.hcl`

**Interfaces:**
- Consumes: `base_domain`, `operator_group_ids`, `spoke_account_ids` do `values.tfvars`.
- Produces: nada novo. A raiz passa a resolver com `values.auto.tfvars` sozinho.

- [ ] **Step 1: conferir o que ainda falta de default**

```bash
cd /home/silvios/git/wasp-idp/aws/terraform/connectivity/us-east-1
grep -n 'variable "' variables.tf
```

`aws_profile`, `subzone_label`, `saml_metadata_path`, `client_cidr_block` e `manage_authorization`
já têm default. Sem default ficam `base_domain`, `operator_group_ids` e `spoke_account_ids` — que é
exatamente o conjunto que o `values.tfvars` entrega, e é assim que deve continuar (fail-closed).

- [ ] **Step 2: tirar do texto das descrições a referência ao script que vai morrer**

Em `variables.tf`, o cabeçalho do arquivo diz que o tfvars é "gerado por `scripts/up-03-connectivity`"
e a descrição de `spoke_account_ids` diz "O `generate-tfvars` descobre". Substituir:

No cabeçalho (linhas 1-8):

```hcl
# O que é inline no main.tf e o que é variável, aqui:
#
# Inline — região, nome do hub, CIDR do supernet: decisões de desenho documentadas em
# ../../../docs/network/, não segredo (mesmo critério de network-foundation/).
#
# Variável — domínio, id do grupo do Identity Center, caminho do metadata SAML: identificam
# a conta e as pessoas de quem roda, e o repo é público. Vêm de `variables/values.tfvars`
# (gitignored), carregado por `values.auto.tfvars` — declarados à mão, nunca descobertos.
```

Na descrição de `spoke_account_ids`, trocar a última frase por:

```hcl
    Sem default: identifica contas desta Organization, e o repo é público. Declarada em
    `variables/values.tfvars`; resolva o nome para id uma vez com
    `aws organizations list-accounts --profile personal --output json`.
```

- [ ] **Step 3: rodar a suíte da raiz**

```bash
cd /home/silvios/git/wasp-idp/aws/terraform/connectivity/us-east-1
terraform test -no-color 2>&1 | tail -20
```

Esperado: `Success!` — esta task não muda comportamento, só texto e a origem dos valores. Uma falha
aqui é regressão de outra task, não desta.

- [ ] **Step 4: commit**

```bash
cd /home/silvios/git/wasp-idp
git add aws/terraform/connectivity/us-east-1/variables.tf
git commit -m "docs(terraform): parar de dizer que o tfvars da 03 e gerado

Refs #36"
```

---

### Task 4: nenhum `up-NN` chama `generate-tfvars`

**Files:**
- Modify: `aws/terraform/scripts/up-03-connectivity`
- Modify: `aws/terraform/scripts/up-04-control-plane`
- Delete: `aws/terraform/connectivity/us-east-1/scripts/generate-tfvars`
- Delete: `aws/terraform/control-plane/scripts/generate-tfvars`
- Modify: `aws/terraform/control-plane/scripts/apply`

**Interfaces:**
- Consumes: as raízes das tasks 2 e 3, que resolvem sem arquivo gerado.
- Produces: `up-03-connectivity` e `up-04-control-plane` sem as opções `--force-tfvars`, `--group` e
  `--label` — que só existiam para alimentar o gerador. A fase 4 substitui os dois por `up-02-region`.

- [ ] **Step 1: substituir a geração por um guard que aponta para o arquivo**

Em `up-03-connectivity` e `up-04-control-plane`, trocar o bloco `if [ ! -f "${root}/terraform.tfvars" ]`
(linhas 114-125 e 89-94 respectivamente) por:

```bash
values_file="${terraform_directory}/variables/values.tfvars"

# Guard, não geração: sem o arquivo o plan falharia em `base_domain` de qualquer jeito. O que este
# bloco compra é a mensagem — o erro do Terraform diz qual variável falta, não onde declará-la.
[ -f "${values_file}" ] \
  || fail "missing ${values_file}. Copy variables/values.tfvars.example to values.tfvars and fill in the identity values — see variables/README.md."
```

E remover das duas `show_usage` as opções `-f`/`--force-tfvars` (e, no `up-03`, `-g`/`--group` e
`-l`/`--label`, que só alimentavam o gerador), mais os `case` correspondentes e as variáveis
`force_tfvars`, `groups` e `label`. Os grupos autorizados passam a viver em `values.tfvars`, que é
onde a mudança do `4.1` acontece.

No `up-03`, trocar também o texto de `show_usage` que promete o roteiro de console:

```
    And on a CONSOLE step: the SAML application in Identity Center. The
    CreateApplication API only creates custom OAuth 2.0 applications, so SAML
    is not Terraform. Save the downloaded metadata as
    connectivity/us-east-1/saml-metadata.xml — the walkthrough is in
    docs/superpowers/plans/2026-08-26-private-access-and-ingress/02-private-access.md,
    section "O passo de console, clique a clique".
```

- [ ] **Step 2: apagar os dois geradores**

```bash
cd /home/silvios/git/wasp-idp
git rm aws/terraform/connectivity/us-east-1/scripts/generate-tfvars \
       aws/terraform/control-plane/scripts/generate-tfvars
```

972 linhas. A metade de descoberta perde a razão de existir; a de validação é redundante com os data
sources (`data.aws_vpc.hub`, `data.aws_lb.hub_ingress`, `data.aws_route53_zone.subzone`), que falham
no plan — decisão 2 do ADR 0014.

- [ ] **Step 3: limpar a referência sobrevivente em `control-plane/scripts/apply`**

```bash
grep -n 'generate-tfvars' aws/terraform/control-plane/scripts/apply
```

Substituir a instrução por um apontamento para `variables/values.tfvars`. Um script que manda rodar
um arquivo apagado é pior que nenhuma instrução.

- [ ] **Step 4: provar que nada mais no repo chama o gerador**

```bash
cd /home/silvios/git/wasp-idp
grep --recursive --line-number 'generate-tfvars' --exclude-dir=.git . \
  | grep --invert-match '^./docs/archived/\|^./docs/superpowers/plans/2026-08-26\|^./docs/superpowers/specs/\|^./docs/adr/0014'
```

Esperado: **nenhuma linha**. Sobrevivem de propósito as ocorrências em `docs/archived/`, nos planos e
specs antigos (registro histórico, imutável) e no ADR 0014 (que narra a remoção). Qualquer hit em
`aws/`, `HANDOFF.md` ou `CLAUDE.md` é trabalho desta task ou da Task 5.

- [ ] **Step 5: rodar os dois scripts em `--help` e sem o values.tfvars**

```bash
cd /home/silvios/git/wasp-idp/aws/terraform
scripts/up-03-connectivity --help
mv variables/values.tfvars /tmp/values.tfvars.backup
scripts/up-04-control-plane --yes ; echo "exit=${?}"
mv /tmp/values.tfvars.backup variables/values.tfvars
```

Esperado: o `--help` sem menção a `--force-tfvars`; o segundo comando saindo **não-zero** com a
mensagem `missing .../variables/values.tfvars`, **antes** de qualquer `terraform init` — o guard tem
de morder antes de tocar a AWS.

- [ ] **Step 6: commit**

```bash
cd /home/silvios/git/wasp-idp
git add aws/terraform/scripts aws/terraform/control-plane/scripts
git commit -m "feat(terraform): remover os dois generate-tfvars

Os up-NN param de gerar tfvars e passam a exigir variables/values.tfvars, que e
mantido a mao. A validacao que os scripts faziam ja falha no plan pelos proprios
data sources.

Closes #36"
```

---

### Task 5: aceite real na AWS e docs verdadeiras

**Files:**
- Modify: `aws/terraform/README.md`
- Modify: `HANDOFF.md`
- Modify: `aws/terraform/CLAUDE.md`

**Interfaces:**
- Consumes: tudo das tasks 1-4.
- Produces: a sequência documentada que a fase 2 vai reescrever de novo — mas que precisa estar
  verdadeira **agora**, porque um `README.md` desatualizado é comando que falha no meio, às vezes com
  recurso já criado atrás.

- [ ] **Step 1: atualizar a sequência de subida no `README.md` da pasta**

O `README.md` descreve hoje 7 passos, com `generate-tfvars --force` entre conectar o túnel e o
`up-04`. Esse passo some. A seção "Manter este arquivo verdadeiro" tem a tabela de o-que-mudou →
onde-atualizar; seguir a própria tabela, e acrescentar uma linha para
`aws/terraform/variables/values.tfvars` como pré-requisito de qualquer camada.

- [ ] **Step 2: atualizar o `HANDOFF.md`**

Duas frases mentem depois desta fase: a de "Subir o ambiente", que lista `generate-tfvars --force`
como passo 5 de 7, e a do "Why", que promete `variables/values.yaml` planejado. Trocar a segunda por
um apontamento ao ADR 0014 e ao `variables/README.md`.

- [ ] **Step 3: registrar a lição em `aws/terraform/CLAUDE.md`**

Na seção "Scripts de subida", acrescentar:

```markdown
- **Valor de identidade é DECLARADO, nunca descoberto.** Os dois `generate-tfvars` consultavam a AWS
  e escreviam um tfvars gitignored; quando uma camada ganhava variável obrigatória nova, o arquivo já
  existente deixava de satisfazer a config e o apply morria **depois** do plan com `No value for
  required variable` — erro que não aponta para o passo de geração. Hoje o valor vem de
  `variables/values.tfvars`, mantido à mão, e o que é produto de outro recurso vem de data source ou
  output de módulo. Ver [ADR 0014](../../docs/adr/0014-single-regional-root-composing-hub-and-cell-modules.md).
```

- [ ] **Step 4: subir a camada 03 de verdade, de árvore limpa**

O aceite da fase é um apply real sem passo de geração. Pré-requisitos: SSO válido nos três profiles
e `saml-metadata.xml` no lugar.

```bash
cd /home/silvios/git/wasp-idp
for p in personal network cicd; do echo "=== ${p} ==="; aws sts get-caller-identity --profile "${p}" --output json; done
ls -la aws/terraform/connectivity/us-east-1/saml-metadata.xml
```

Depois, **pelo usuário** (o classifier de auto-mode bloqueia apply para o agente):

```
! aws/terraform/scripts/up-03-connectivity --yes
```

Esperado: `init` → `plan` → `apply` sem nenhuma linha de descoberta, e o endpoint do Client VPN no
output final. `No value for required variable` aqui significa chave faltando no `values.tfvars` —
o erro certo, no lugar certo, que é o que esta fase entrega.

- [ ] **Step 5: conectar o túnel e provar que a camada serve**

```bash
aws-vpn-client --version                                  # 6.0.1 esperado
aws ec2 export-client-vpn-client-configuration \
  --client-vpn-endpoint-id "$(cd aws/terraform/connectivity/us-east-1 && terraform output -raw client_vpn_endpoint_id)" \
  --profile network --region us-east-1 --output text > /tmp/hub.ovpn
```

E, pelo usuário: `! aws-vpn-client import-profile --profile-name hub --config-path /tmp/hub.ovpn`
seguido de `! aws-vpn-client connect --profile-name hub`, até
`aws-vpn-client get-connection-status --profile-name hub` dizer `Connected`.

- [ ] **Step 6: commit**

```bash
cd /home/silvios/git/wasp-idp
git add aws/terraform/README.md HANDOFF.md aws/terraform/CLAUDE.md
git commit -m "docs: tirar generate-tfvars da sequencia de subida

Refs #36"
```

---

## Aceite da fase 1

- [ ] Nenhum `up-NN` chama `generate-tfvars`; os dois scripts não existem mais.
- [ ] `terraform plan` numa árvore limpa **sem** `variables/values.tfvars` falha em `base_domain`,
      por validação de variável — não por descoberta ausente.
- [ ] `terraform plan` **com** o arquivo resolve sem nenhuma chamada à AWS CLI fora do próprio
      Terraform.
- [ ] A regressão offline segue verde nas raízes tocadas, com `data.aws_availability_zones`
      exercitado sob `mock_provider` por dois runs de valores e tamanhos diferentes.
- [ ] Um apply real da camada 03 entrega o endpoint do Client VPN sem passo de geração anterior, e o
      túnel conecta.
- [ ] `aws/terraform/README.md` e `HANDOFF.md` descrevem a sequência que de fato existe.
