# Fase 4 — apagar o que ficou para trás e deixar as docs verdadeiras

As três raízes antigas continuam no disco depois da fase 3, com states vazios e scripts que apontam
para lugares que não existem mais. Esta fase remove, migra a `us-west-2` e reescreve a sequência que
alguém sem contexto vai copiar.

**Pré-requisito:** fase 3 fechada, com apply e destroy reais provados na `us-east-1`.

**A regra que governa esta fase:** o `aws/terraform/README.md` é a sequência executável, e uma linha
desatualizada ali não é doc velha — é comando que falha no meio, às vezes com recurso já criado atrás.
Duas divergências desse tipo já aconteceram neste repo.

---

### Task 1: apagar as raízes antigas e as keys de state

**Files:**
- Delete: `aws/terraform/network-foundation/` (as duas regiões)
- Delete: `aws/terraform/connectivity/`
- Delete: `aws/terraform/control-plane/`
- Delete: `aws/terraform/scripts/up-01-network-foundation`, `up-03-connectivity`, `up-04-control-plane`
- Move: `aws/terraform/connectivity/us-east-1/saml-metadata.xml.example` → `aws/terraform/variables/`

**Interfaces:**
- Consumes: nada. Só remove.
- Produces: uma árvore em que `grep -r 'control-plane/'` não encontra caminho morto.

- [ ] **Step 1: provar que os states estão vazios antes de apagar qualquer coisa**

```bash
cd /home/silvios/git/wasp-idp/aws/terraform
for m in control-plane connectivity/us-east-1 network-foundation/us-east-1 network-foundation/us-west-2; do
  printf '%-34s ' "${m}"
  (cd "${m}" && terraform state list 2>/dev/null | wc --lines)
done
aws sts get-caller-identity --profile network --output json
```

Esperado: `0` nas três primeiras (a `us-west-2` ainda tem 13, tratada na Task 2). **Uma linha `0` com
o SSO caído não prova nada** — daí o `get-caller-identity` no mesmo passo. Qualquer número diferente
de zero interrompe a task: há recurso vivo, e apagar a raiz o deixaria órfão, fora de qualquer state.

- [ ] **Step 2: só o `.example` do metadata SAML se move (invariante)**

O arquivo real já vive em `variables/` desde a fase 1, Step 4b — **não** há metadata a mover para
dentro de `regions/us-east-1/`, e mover seria desfazer o invariante no último passo do plano. O que
sobrou na `connectivity/` é o `.example` versionado:

```bash
cd /home/silvios/git/wasp-idp/aws/terraform
git mv connectivity/us-east-1/saml-metadata.xml.example variables/saml-metadata.xml.example
rm --force connectivity/us-east-1/saml-metadata.xml      # o symlink que a fase 1 deixou
readlink regions/us-east-1/saml-metadata.xml
git check-ignore variables/saml-metadata.xml
```

Esperado: o `readlink` devolve `../../variables/saml-metadata.xml` — se devolver qualquer caminho com
`regions/` ou `connectivity/`, o symlink está errado e a `us-west-2` da Task 2 vai quebrar. O
`check-ignore` ecoa o caminho: o arquivo identifica a instância do Identity Center e nunca pode ser
versionado; o `.example` é versionado de propósito.

- [ ] **Step 3: apagar as raízes e os scripts órfãos**

```bash
cd /home/silvios/git/wasp-idp
git rm --recursive aws/terraform/connectivity aws/terraform/control-plane aws/terraform/network-foundation
git rm aws/terraform/scripts/up-01-network-foundation \
       aws/terraform/scripts/up-03-connectivity \
       aws/terraform/scripts/up-04-control-plane
rm --recursive --force aws/terraform/connectivity aws/terraform/control-plane aws/terraform/network-foundation
```

O `rm` depois do `git rm` limpa o que era gitignored e por isso sobrevive: `.terraform/`, `logs/`,
`*.tfplan`. A `control-plane/` tem três `.tfplan` de recuperação de sessões antigas — plano salvo não
sobrevive à expiração de credencial e nenhum deles vale nada.

- [ ] **Step 4: apagar as keys antigas no bucket de state**

Só depois do Step 1 ter provado que estão vazias. As keys são as do `versions.tf` de cada raiz
apagada — conferir no `git show HEAD~1` se necessário.

```bash
bucket="tfstate-$(aws organizations describe-organization --profile personal --query Organization.Id --output text)"
aws s3api list-objects-v2 --bucket "${bucket}" --profile network --output json > /tmp/state-objects.json
```

Ler `/tmp/state-objects.json` (nunca pipe direto para `jq` nesta máquina — o wrapper `rtk` quebra o
parsing) e apagar, uma a uma e conferindo o nome antes, as keys de `network-foundation/*`,
`connectivity/*` e `control-plane/*`. O bucket é versionado: o objeto vira uma delete marker, e um
`state pull` de emergência ainda alcança a versão anterior.

- [ ] **Step 5: provar que nada aponta para caminho morto**

```bash
cd /home/silvios/git/wasp-idp
grep --recursive --line-number 'network-foundation\|connectivity/us-east-1\|control-plane/scripts' \
  --exclude-dir=.git --exclude-dir=archived . \
  | grep --invert-match '^./docs/superpowers/plans/\|^./docs/superpowers/specs/\|^./docs/adr/'
```

Esperado: **nenhuma linha** fora de docs históricas. Hits em `aws/`, `HANDOFF.md`, `README.md` ou nos
scripts são trabalho das tasks seguintes. Atenção especial a `scripts/vpn` e `scripts/platform-status`,
que percorrem as raízes por caminho fixo.

- [ ] **Step 6: commit**

```bash
git add --all aws/terraform
git commit -m "chore(terraform): apagar as raizes network-foundation, connectivity e control-plane

Os states estavam vazios e o conteudo vive em src/hub, src/cell e
regions/us-east-1. As keys antigas foram removidas do bucket.

Refs #36"
```

---

### Task 2: `regions/us-west-2/`

**Files:**
- Create: `aws/terraform/regions/us-west-2/{main.tf,variables.tf,outputs.tf,versions.tf,values.auto.tfvars}`

**Interfaces:**
- Consumes: `src/hub` da fase 2 e `src/cell` da fase 3.
- Produces: **a prova do invariante.** Esta task é onde "um hub regional com o seu control plane pode
  ser criado em outra região" deixa de ser intenção e vira fato verificado.

**O aceite é o `plan` da composição inteira, não o apply.** Aplicar só o hub na `us-west-2` é decisão
de custo — mas `terraform plan` com `module.hub` **e** `module.cell` tem de ser verde, porque é ele
que prova que nenhum nome global colide e nenhum caminho de arquivo aponta para a `us-east-1`. Um
`plan` verde só do hub esconde exatamente as cinco roles de IAM da célula, que são o risco maior.

**Se esta task falhar, a correção é na fase 2 ou 3, não aqui.** Um `EntityAlreadyExists`, um
`readlink` apontando para `regions/us-east-1/`, um record do Route 53 disputado — nada disso se
conserta com um `-target` ou um nome escrito à mão na `us-west-2`. Contornar aqui é entregar a
segunda região quebrada para a terceira descobrir.

- [ ] **Step 1: copiar a raiz de `us-east-1` e trocar o que é regional**

```bash
cd /home/silvios/git/wasp-idp/aws/terraform/regions
cp --recursive us-east-1 us-west-2
rm --recursive --force us-west-2/.terraform us-west-2/logs us-west-2/values.auto.tfvars us-west-2/saml-metadata.xml
ln --symbolic ../../variables/values.tfvars us-west-2/values.auto.tfvars
```

Trocar em `us-west-2/main.tf`:

```hcl
locals {
  region        = "us-west-2"
  hub_vpc_cidr  = "10.3.0.0/16"
  cell_vpc_cidr = "10.4.0.0/16"
  # ...
}
```

Conferir os dois `/16` contra `aws/docs/network/01-cidr-addressing.md` **antes** de escrever: CIDR é a
única decisão irreversível da cadeia, o supernet tem teto de 15 `/16` e região multiplica.

E em `us-west-2/versions.tf`, a key própria:

```hcl
key = "regions/us-west-2/terraform.tfstate"
```

Uma raiz por região, com key própria — nunca uma raiz só alternando backend com `init -reconfigure`:
esquecer de trocar mistura as regiões e nada no Terraform pega isso.

- [ ] **Step 2: provar a composição inteira offline e no `plan` (invariante)**

`module "cell"` **fica** no `main.tf` da `us-west-2`, idêntico ao da `us-east-1`. A diferença entre as
duas regiões é operacional (`up-02-region --region us-west-2` sem `--with-cell`), nunca estrutural:
duas raízes que divergem no código deixam de provar qualquer coisa uma sobre a outra.

O `saml-metadata.xml` **não** é obstáculo — a fase 1 o moveu para `variables/`, e uma aplicação do
Identity Center serve as duas regiões (o ACS URL do Client VPN é `http://127.0.0.1:35001` em qualquer
endpoint). O symlink é o mesmo dos outros:

```bash
cd /home/silvios/git/wasp-idp/aws/terraform/regions/us-west-2
ln --symbolic ../../variables/saml-metadata.xml saml-metadata.xml
readlink values.auto.tfvars saml-metadata.xml
```

Esperado: os dois `readlink` apontando para `../../variables/`. **Qualquer `regions/` ou
`connectivity/` na saída é violação do invariante** — pare e conserte na fase de origem.

```bash
cd /home/silvios/git/wasp-idp/aws/terraform/regions/us-west-2
terraform init -no-color
terraform plan -no-color 2>&1 | tail -40
```

Esperado: um plano completo, com os recursos do hub **e** os da célula, e nenhum erro. Os três modos
de falha que este `plan` existe para pegar, e o que cada um significa:

| Erro | Causa | Onde consertar |
|---|---|---|
| `EntityAlreadyExists` em role ou SAML provider | nome global sem região | fase 2 Step 2b (hub) ou fase 3 Task 1 (célula) |
| `no such file or directory` num `file()` | caminho apontando para outra região | fase 1 Step 4b |
| CIDR sobreposto no TGW | `/16` reusado entre regiões | Step 1 desta task, contra a tabela de alocação |

Um `plan` verde aqui **não** significa que a célula será aplicada nesta região — significa que ela
pode ser, que é o invariante.

- [ ] **Step 3: destruir a `network-foundation/us-west-2` e aplicar a raiz nova**

Pelo usuário:

```
! cd aws/terraform/network-foundation/us-west-2 && nohup terraform destroy -no-color -auto-approve > /tmp/destroy-01-west.log 2>&1 < /dev/null & disown
```

Depois, `up-02-region --region us-west-2` (sem `--with-cell`). Aplica o hub inteiro — VPC, TGW e
Client VPN, porque o metadata SAML é compartilhado — e para antes da célula, que é onde o custo está.

**Se a ordem desta task e a da Task 1 se cruzarem**, destruir a `us-west-2` ANTES de apagar a pasta —
apagar a raiz de um state com 13 recursos os deixa órfãos, fora de qualquer state.

- [ ] **Step 4: rodar a suíte e commitar**

```bash
cd /home/silvios/git/wasp-idp/aws/terraform/regions/us-west-2
terraform init -backend=false && terraform test -no-color 2>&1 | tail -20
```

```bash
cd /home/silvios/git/wasp-idp
git add aws/terraform/regions/us-west-2
git commit -m "feat(terraform): regiao us-west-2 como raiz regional

Mesma composicao da us-east-1, so os locals mudam: regiao, os dois /16 e a
key do backend. O plan da composicao inteira (hub + celula) e verde, o que
prova que nenhum nome global colide e nenhum caminho aponta para a outra
regiao. Aplicado so o hub, por custo.

Refs #36"
```

---

### Task 3: scripts renumerados e coerentes

**Files:**
- Rename: `aws/terraform/scripts/up-02-dns` → `up-01-dns`
- Modify: `aws/terraform/scripts/up-all`, `vpn`, `platform-status`
- Modify: `aws/terraform/scripts/up-00-state-backend` (texto)

**Interfaces:**
- Consumes: `up-02-region` e `down-cell` da fase 3.
- Produces: a sequência `00 → 01 → 02` que a Task 4 documenta.

- [ ] **Step 1: renomear e corrigir as referências**

```bash
cd /home/silvios/git/wasp-idp/aws/terraform/scripts
git mv up-02-dns up-01-dns
grep --recursive --line-number 'up-02-dns\|up-01-network-foundation\|up-03-connectivity\|up-04-control-plane' \
  /home/silvios/git/wasp-idp --exclude-dir=.git --exclude-dir=archived
```

Corrigir cada hit fora de docs históricas. A numeração passa a ser: `00` state-backend, `01` dns,
`02` region.

- [ ] **Step 2: `platform-status` e `vpn` contra a nova árvore**

`platform-status` percorre as raízes por caminho fixo e soma o custo/h por nível — a lista de raízes
mudou, e os níveis também: T1 e T2 deixaram de ser camadas e passaram a ser `module.hub` e
`module.cell` dentro do mesmo state. Trocar a varredura de raízes por uma varredura de
`terraform state list` filtrando por prefixo de módulo:

```bash
hub_resources="$( (cd "${root}" && terraform state list) | grep --count '^module\.hub\.' || true)"
cell_resources="$( (cd "${root}" && terraform state list) | grep --count '^module\.cell\.' || true)"
```

`vpn` lê `client_vpn_endpoint_id` de `connectivity/us-east-1` — passa a ler de
`regions/<região>/`, que já repassa o output.

**Nenhum dos sete scripts pode ter região escrita no corpo (invariante).** `vpn` e `platform-status`
recebem `--region` com default `us-east-1`; `up-all` itera `regions/*` em vez de nomear uma. Hoje
`up-all` tem `connectivity/us-east-1/scripts/destroy` numa mensagem de log — é literalmente o padrão
que o invariante proíbe, e some junto com a pasta.

```bash
cd /home/silvios/git/wasp-idp/aws/terraform/scripts
grep --line-number 'us-east-1\|us-west-2' up-00-state-backend up-01-dns up-02-region up-all down-cell vpn platform-status
```

Esperado: hits **só** em valor de default de opção (`region="${region:-us-east-1}"`) e em exemplo de
`show_usage`. Qualquer caminho de diretório com região literal é violação — o script tem de compor
`regions/${region}`.

- [ ] **Step 3: exercitar todos os scripts em `--help`**

```bash
cd /home/silvios/git/wasp-idp/aws/terraform/scripts
for s in up-00-state-backend up-01-dns up-02-region up-all down-cell vpn platform-status; do
  echo "=== ${s} ==="
  ./"${s}" --help 2>&1 | head -20
done
```

Esperado: nenhum erro de arquivo ausente, e nenhuma menção a camada 03/04 ou a `generate-tfvars`.

- [ ] **Step 4: rodar `platform-status` de verdade**

```bash
cd /home/silvios/git/wasp-idp/aws/terraform
scripts/platform-status
```

Esperado: a região aparece com o hub contabilizado e a célula em zero (ou não, se estiver de pé) — e o
custo/h somado bate com a tabela do `README.md`. Divergência aqui é a mordida do "guard que lê
`terraform output` antes de o output existir no state": um `apply` de zero recursos materializa o
output.

- [ ] **Step 5: commit**

```bash
cd /home/silvios/git/wasp-idp
git add aws/terraform/scripts
git commit -m "refactor(terraform): renumerar os scripts para 00 state-backend, 01 dns, 02 region

Refs #36"
```

---

### Task 4: docs verdadeiras e as issues fechadas

**Files:**
- Modify: `aws/terraform/README.md`
- Modify: `HANDOFF.md`
- Modify: `aws/terraform/CLAUDE.md`, `aws/CLAUDE.md`
- Modify: `docs/adr/0013-consolidate-local-values-yaml.md` — **não**, ADR é imutável; ver Step 3

**Interfaces:**
- Consumes: tudo das fases 1-4.
- Produces: o critério final — uma árvore limpa aplica do zero seguindo só o `README.md`.

- [ ] **Step 1: reescrever a sequência no `aws/terraform/README.md`**

De cinco camadas para três, com a tabela de custo por nível reescrita em termos de `module.hub` e
`module.cell` em vez de camadas 03 e 04. Seguir a própria seção "Manter este arquivo verdadeiro" e
acrescentar a ela as linhas novas: `variables/values.tfvars` como pré-requisito de tudo, e
`down-cell` como o teardown noturno.

A ordem de derrubada, que hoje é prosa ("control-plane PRIMEIRO, connectivity só depois"), some: o
grafo a conhece. O que fica no lugar é a explicação do `-target`.

**A tabela de sequência passa a separar os dois eixos explicitamente** — ordem e permanência foram
confundidos uma vez e o resultado foi um nível "T-1" que não existe. `00`/`01`/`02` é ordem; `T0`/
`T1`/`T2` é permanência (custo e ciclo de vida). Não há nível abaixo do T0: a fundação da
Organization é a coisa mais permanente do repositório.

| Ordem | Camada | Permanência | Terraform? |
|---|---|---|---|
| — | Organization, contas, OUs, SCP, Identity Center | T0 | não — `aws/docs/accounts/scripts/` |
| — | *aprovar a região na SCP* | — | não |
| 00 | `state-backend/` | T0 | sim |
| 01 | `dns/` | T0 | sim |
| — | *aplicação SAML no Identity Center* → `variables/saml-metadata.xml` | — | não, é console |
| 02 | `regions/<r>` → `module.hub` | **T1** | sim |
| — | *conectar o túnel do Client VPN* | — | não |
| 02 | `regions/<r>` → `module.cell` | **T2** | sim |
| — | providers e Compositions do Crossplane | T2 | não — GitOps |

Três coisas que essa tabela obriga a escrever, e que hoje não estão em lugar nenhum:

1. **`module.hub` e `module.cell` dividem o `02` e têm permanências diferentes.** É a novidade desta
   frente e é o que o Step 3 da Task 3 tem de fazer o `platform-status` refletir: reportar custo por
   **módulo**, não por raiz, senão T1 e T2 viram uma linha só e "esqueci ligado" volta a ser
   invisível.
2. **A fundação não ganha um `up-00`.** `up-NN` significa "raiz Terraform, idempotente, roda
   sozinha" — e ela não é nenhuma das três: roda uma vez na vida, `create-account` exige e-mail de
   root único e não é re-executável, e o app SAML é console. Renumerar tudo para acomodá-la só
   valeria com um `up-all` que fosse da management account vazia até a célula, e aí a fundação
   precisaria ser idempotente primeiro. Ela entra como bloco próprio acima do `up-*`, apontando para
   a ordem que `aws/docs/accounts/` já estabelece em `00-strategy` … `07-cloudtrail`.
3. **A aplicação SAML é uma para toda a Organization, não uma por região** — o ACS URL do Client VPN
   é `http://127.0.0.1:35001` em qualquer endpoint. É o que permite à `us-west-2` ter Client VPN sem
   um segundo passo de console, e o motivo de o arquivo morar em `variables/`.

**Uma seção "Nova região" verdadeira.** A que existe hoje manda editar `main.tf` e `versions.tf`; com
a raiz regional ela vira o procedimento real e curto — copiar `regions/<r>/`, trocar `local.region`,
os dois `/16` (contra a tabela de alocação) e a `key` do backend, symlinkar `values.auto.tfvars` e
`saml-metadata.xml` para `../../variables/`, `plan`. Escrever ali que **um `plan` verde da composição
inteira é o aceite de uma região nova**, mesmo que só o hub seja aplicado.

- [ ] **Step 2: `HANDOFF.md`**

Trechos que ficam falsos: o comando de conferência do "Estado atual" (lista raízes apagadas), a
sequência de 7 passos de "Subir o ambiente", a ordem obrigatória de derrubada, o "Why" (que promete
`variables/values.yaml`) e a regressão offline (que lista os diretórios um a um). Reescrever a
regressão:

```bash
cd aws/terraform
for m in src/network src/state-backend src/pod-identity src/cluster src/nodegroup src/ingress \
         src/hub src/cell \
         src/helm/modules/aws-load-balancer-controller \
         src/helm/modules/external-secrets src/helm/modules/argo-cd src/helm/modules/crossplane \
         regions/us-east-1 regions/us-west-2 dns; do
  (cd "${m}" && terraform init -backend=false >/dev/null && terraform test -no-color)
done
```

- [ ] **Step 3: o ADR 0013 não se edita**

ADR aceito é imutável — uma decisão revista ganha ADR novo que referencia o anterior. O ADR 0014 já
diz que substitui o `values.yaml` do 0013 pelo `values.tfvars`. Nada a fazer no 0013; se alguém
propuser editá-lo, a resposta está aqui.

Conferir apenas que o índice `docs/adr/README.md` lista o 0014.

- [ ] **Step 4: rodar a regressão offline inteira**

```bash
cd /home/silvios/git/wasp-idp/aws/terraform
nohup bash -c 'for m in src/network src/state-backend src/pod-identity src/cluster src/nodegroup src/ingress src/hub src/cell src/helm/modules/aws-load-balancer-controller src/helm/modules/external-secrets src/helm/modules/argo-cd src/helm/modules/crossplane regions/us-east-1 regions/us-west-2 dns; do echo "=== ${m}"; (cd "${m}" && terraform init -backend=false >/dev/null && terraform test -no-color); done' > /tmp/regression.log 2>&1 < /dev/null & disown
```

Anunciar `/tmp/regression.log` assim que disparar; ~4 min. Esperado: `Success!` em todos, e **nenhuma
linha vazia** — vazio significa `init` morto por credencial, que se lê como "sem testes".

- [ ] **Step 5: o aceite final — árvore limpa, do zero, seguindo só o README**

Em `/tmp`, clonar o repo, copiar o `values.tfvars` e o `saml-metadata.xml` e seguir o `README.md`
sem consultar mais nada. É o único teste que pega instrução faltando.

```bash
git clone /home/silvios/git/wasp-idp /tmp/wasp-idp-clean
cp /home/silvios/git/wasp-idp/aws/terraform/variables/values.tfvars /tmp/wasp-idp-clean/aws/terraform/variables/
cp /home/silvios/git/wasp-idp/aws/terraform/variables/saml-metadata.xml /tmp/wasp-idp-clean/aws/terraform/variables/
cd /tmp/wasp-idp-clean/aws/terraform
```

Os symlinks `values.auto.tfvars` são versionados? **Não** — são gitignored. O `README.md` tem de
mandar criá-los, e este passo é o que descobre se ele manda. Se o `plan` falhar aqui por
`No value for required variable`, a instrução falta: corrigir o `README.md`, não o clone.

- [ ] **Step 6: fechar as issues**

```bash
cd /home/silvios/git/wasp-idp
gh issue close 36 -R smsilva/wasp-idp --comment "Fechada pela reestruturação do ADR 0014: os dois generate-tfvars foram removidos, os valores de identidade vivem em variables/values.tfvars (gitignored) e o acoplamento entre camadas passou a ser referência de módulo em vez de redescoberta. Plano: docs/superpowers/plans/2026-08-29-regional-root-hub-and-cell-modules/"
gh issue close 21 -R smsilva/wasp-idp --comment "Absorvida pela #36: o inventário único é aws/terraform/variables/values.tfvars, em tfvars e não em YAML — o Terraform o lê direto, sem passo de conversão. Ver ADR 0014."
```

Conferir depois que o board #6 reflete o fechamento:

```bash
gh project item-list 6 --owner smsilva --format json > /tmp/board.json
```

- [ ] **Step 7: commit e handoff**

```bash
git add aws/terraform/README.md HANDOFF.md aws/terraform/CLAUDE.md aws/CLAUDE.md
git commit -m "docs: reescrever a sequencia para tres camadas e uma raiz por regiao

Closes #36, closes #21"
```

---

## Aceite da fase 4

- [ ] `network-foundation/`, `connectivity/` e `control-plane/` não existem no disco nem no bucket de
      state, e nenhum arquivo fora de docs históricas as referencia.
- [ ] **(invariante)** `regions/us-west-2/` existe, e `terraform plan` da composição **inteira**
      (`module.hub` + `module.cell`) é verde ali — sem `EntityAlreadyExists`, sem `file()` quebrado,
      sem CIDR sobreposto. Aplicado, só o hub, por custo.
- [ ] **(invariante)** `readlink` de `values.auto.tfvars` e `saml-metadata.xml` nas duas regiões
      aponta para `../../variables/`; nenhuma região referencia o diretório da outra.
- [ ] **(invariante)** `grep -rn 'us-east-1' aws/terraform/src aws/terraform/scripts` só devolve
      default de opção, fixture de teste e exemplo de `show_usage`.
- [ ] **(invariante)** `diff regions/us-east-1/main.tf regions/us-west-2/main.tf` difere **apenas**
      no bloco `locals` (região e os dois CIDR). Divergência estrutural entre as duas raízes é a
      prova se desfazendo.
- [ ] Os sete scripts respondem a `--help` sem mencionar camada 03/04 nem `generate-tfvars`, e
      nenhum tem caminho de diretório com região escrita no corpo.
- [ ] `aws/terraform/README.md` separa os dois eixos (ordem `00`/`01`/`02` × permanência `T0`/`T1`/
      `T2`), traz a fundação da Organization como bloco acima do `up-*`, e tem uma seção "Nova
      região" que é o procedimento real.
- [ ] A regressão offline inteira passa, sem linha vazia.
- [ ] Um clone limpo, com `values.tfvars` e `saml-metadata.xml` copiados, chega ao `plan` seguindo só
      o `README.md`.
- [ ] #36 e #21 fechadas, com o ADR 0014 citado.
