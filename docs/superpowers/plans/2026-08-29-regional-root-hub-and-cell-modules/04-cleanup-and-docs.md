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
- Move: `aws/terraform/connectivity/us-east-1/saml-metadata.xml` → `aws/terraform/regions/us-east-1/`

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

- [ ] **Step 2: mover o metadata SAML para a raiz que sobrevive**

```bash
cd /home/silvios/git/wasp-idp/aws/terraform
rm --force regions/us-east-1/saml-metadata.xml            # o symlink temporario da fase 2
mv connectivity/us-east-1/saml-metadata.xml regions/us-east-1/saml-metadata.xml
git mv connectivity/us-east-1/saml-metadata.xml.example regions/us-east-1/saml-metadata.xml.example
git check-ignore regions/us-east-1/saml-metadata.xml
```

Esperado: `check-ignore` ecoa o caminho. O arquivo identifica a instância do Identity Center e nunca
pode ser versionado; o `.example` é versionado de propósito.

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
- Consumes: `src/hub` da fase 2.
- Produces: a segunda região, hub sozinho — o caso que prova que a raiz regional não obriga a existir
  uma célula.

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

- [ ] **Step 2: `module.cell` fica no código, mas a região não o aplica**

Não remover `module "cell"` do `main.tf` da `us-west-2`: a raiz é a mesma composição, e a diferença
entre as duas regiões é operacional (`up-02-region --region us-west-2` sem `--with-cell`), não
estrutural. Sem `saml-metadata.xml` nesta região, o `module.hub` também não aplica — o que é
consistente: o Client VPN é um por região e a `us-west-2` não tem um.

Escrever isso como comentário no topo do `main.tf` da `us-west-2`, senão a próxima pessoa conclui que
falta arquivo.

- [ ] **Step 3: destruir a `network-foundation/us-west-2` e aplicar a raiz nova**

Pelo usuário:

```
! cd aws/terraform/network-foundation/us-west-2 && nohup terraform destroy -no-color -auto-approve > /tmp/destroy-01-west.log 2>&1 < /dev/null & disown
```

Depois, `up-02-region --region us-west-2` (sem `--with-cell`). A raiz aplica a VPC hub e para — sem
TGW nem Client VPN enquanto não houver `saml-metadata.xml` da região.

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
git commit -m "feat(terraform): regiao us-west-2 como raiz regional, hub sozinho

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
cp /home/silvios/git/wasp-idp/aws/terraform/regions/us-east-1/saml-metadata.xml /tmp/wasp-idp-clean/aws/terraform/regions/us-east-1/
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
- [ ] `regions/us-west-2/` existe e aplica o hub sozinho.
- [ ] Os sete scripts respondem a `--help` sem mencionar camada 03/04 nem `generate-tfvars`.
- [ ] A regressão offline inteira passa, sem linha vazia.
- [ ] Um clone limpo, com `values.tfvars` e `saml-metadata.xml` copiados, chega ao `plan` seguindo só
      o `README.md`.
- [ ] #36 e #21 fechadas, com o ADR 0014 citado.
