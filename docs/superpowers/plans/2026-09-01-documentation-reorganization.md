# Documentation Reorganization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the repo a real navigation path (entry point, per-folder index, one-topic-per-doc
rule) without moving any existing content physically, closing [#64](https://github.com/smsilva/wasp-idp/issues/64)'s structure-proposal + execution deliverables.

**Architecture:** Minimal consolidation (spec Approach A). Both existing trunks (`aws/docs/`,
`docs/`) stay physically where they are. Every `CLAUDE.md` that today doubles as a folder index
gets a `README.md` sibling holding only the navigational content; `CLAUDE.md` keeps only
imperative rules. The root `README.md` becomes the repo's single entry point. A new
`scripts/bin/check-doc-links` script verifies no relative doc link breaks along the way.

**Tech Stack:** Markdown, bash (for the link-check script, following this repo's `bash-scripts`
skill conventions: no extension, long-form flags, `set -e` only if sequential, 2-space indent).

**Spec:** `docs/superpowers/specs/2026-09-01-documentation-reorganization-design.md`

## Global Constraints

- No `git mv` of existing reference content — only new files (`README.md` siblings) and content
  moved *within* a file pair (`CLAUDE.md` ↔ `README.md`), never a folder relocation.
- `README.md` = navigation (what's here, what it's for, when to read it). `CLAUDE.md` = imperative
  rules for the agent (conventions, maintenance rules, pitfalls). Never duplicate the same content
  in both.
- Known PII leaks (issue #23) are out of scope — do not touch `aws/docs/bootstrap/00-crossplane-iam-user.md:91` or `accounts/03-provisioning.md` content beyond what a link-path change requires.
- `scripts/bin/check-doc-links` is a reusable script, not a CI gate, in this iteration.
- Every commit in this plan is scoped to one task; do not batch multiple tasks into one commit.

---

### Task 1: `check-doc-links` script

**Files:**
- Create: `scripts/bin/check-doc-links`
- Test: manual run against the repo (no automated test framework for bash scripts in this repo)

**Interfaces:**
- Consumes: nothing (reads the git working tree directly)
- Produces: exit code 0 with no output when all relative doc links resolve; exit code 1 and one
  line per broken link (`<file>:<line>: broken link to <target>`) otherwise. Later tasks run
  `scripts/bin/check-doc-links` after each edit.

- [ ] **Step 1: Write the script**

```bash
#!/usr/bin/env bash
set -e

# Finds markdown-style relative links [text](path) in every versioned file
# (not just *.md — descriptions in YAML/XRD and --help text also cite doc
# paths) and reports any target that does not resolve on disk.

root_dir="$(git rev-parse --show-toplevel)"
cd "${root_dir}"

broken=0

while IFS=: read -r file line rest; do
  link="${rest#\]\(}"
  link="${link%\)}"

  # Skip external links and anchor-only links.
  case "${link}" in
    http://*|https://*|mailto:*|\#*)
      continue
      ;;
  esac

  # Strip a trailing #anchor before resolving the file path.
  target_path="${link%%#*}"
  [ -z "${target_path}" ] && continue

  resolved="$(dirname "${file}")/${target_path}"

  if [ ! -e "${resolved}" ]; then
    echo "${file}:${line}: broken link to ${link}"
    broken=1
  fi
done < <(git ls-files | xargs grep -noE '\]\([^()]+\)')

exit "${broken}"
```

- [ ] **Step 2: Make it executable**

Run: `chmod +x scripts/bin/check-doc-links`

- [ ] **Step 3: Run it against the current repo state to confirm it's clean**

Run: `scripts/bin/check-doc-links`
Expected: exit code 0, no output (the repo has no known broken links today outside the PII items
tracked in #23, which are not link breaks).

Run: `echo $?`
Expected: `0`

- [ ] **Step 4: Verify detection with a deliberately broken link**

Run:
```bash
printf '[bad link](does/not/exist.md)\n' >> HANDOFF.md
scripts/bin/check-doc-links; echo "exit=$?"
git checkout HANDOFF.md
```
Expected: one line reporting `HANDOFF.md:<N>: broken link to does/not/exist.md`, `exit=1`. The
`git checkout` at the end discards the test line — confirm with `git status` that `HANDOFF.md` is
clean again before continuing.

- [ ] **Step 5: Commit**

```bash
git add scripts/bin/check-doc-links
git commit -m "$(cat <<'EOF'
feat(#64): add check-doc-links script

Scans every versioned file (not just *.md) for relative doc links
that don't resolve, per the aws/docs/CLAUDE.md rule that a *.md-only
grep already missed 13 broken references once.
EOF
)"
```

---

### Task 2: `aws/docs/CLAUDE.md` → extract `README.md`

**Files:**
- Modify: `aws/docs/CLAUDE.md` (remove the `## Domínios` section)
- Create: `aws/docs/README.md`

**Interfaces:**
- Consumes: `scripts/bin/check-doc-links` (Task 1)
- Produces: `aws/docs/README.md` as the pattern every later domain-split task follows.

- [ ] **Step 1: Create `aws/docs/README.md`**

Move the `## Domínios` section (the table linking to each domain folder) out of
`aws/docs/CLAUDE.md` verbatim, with this header:

```markdown
# `aws/docs/` — Reference Architecture: Hub-and-Spoke on AWS

Índice de leitura. Convenções de escrita e regras de manutenção ficam em
[`CLAUDE.md`](CLAUDE.md); isto aqui é só "o que existe e onde".

## Domínios

<table moved verbatim from CLAUDE.md>
```

Update every link inside the moved table from `<domain>/CLAUDE.md` to `<domain>/README.md` — the
domain-split tasks (Task 3–10) create those `README.md` files, so after this task the links point
one commit ahead of themselves; that's fixed by the time Task 10 lands, and `check-doc-links` run
now will correctly flag them as broken until then (expected — re-run after Task 10, not now).

- [ ] **Step 2: Remove the moved section from `CLAUDE.md`**

Delete the `## Domínios` heading and its table/note block from `aws/docs/CLAUDE.md`. Leave
`## Objetivo`, `## Princípios`, `## Vocabulário`, `## Como esta documentação é organizada` (and its
subsections), `## Relação com o resto do repo`, `## Fontes externas de referência`, and
`## Explorações paralelas` in place — those are conventions/rules/pointers, not a topic index.

- [ ] **Step 3: Commit**

```bash
git add aws/docs/CLAUDE.md aws/docs/README.md
git commit -m "$(cat <<'EOF'
docs(#64): split aws/docs/README.md index out of CLAUDE.md

README.md becomes the navigable domain index; CLAUDE.md keeps only
conventions and maintenance rules. Domain links updated to point at
each domain's README.md once tasks 3-10 create them.
EOF
)"
```

---

### Task 3: `aws/docs/bootstrap/CLAUDE.md` → extract `README.md`

**Files:**
- Modify: `aws/docs/bootstrap/CLAUDE.md`
- Create: `aws/docs/bootstrap/README.md`

**Interfaces:**
- Consumes: same recipe as Task 2
- Produces: `aws/docs/bootstrap/README.md`, referenced by `aws/docs/README.md`'s `## Domínios` table (Task 2)

- [ ] **Step 1: Create `aws/docs/bootstrap/README.md`**

Move `## O que este domínio entrega` and `## Tópicos` out of `aws/docs/bootstrap/CLAUDE.md`
verbatim, with header:

```markdown
# `bootstrap/` — Domain: Manual Bootstrap of the `network` Account

Índice de leitura. Convenções e regras ficam em [`CLAUDE.md`](CLAUDE.md).
```

- [ ] **Step 2: Remove the moved sections from `CLAUDE.md`**

Delete `## O que este domínio entrega` and `## Tópicos` from `aws/docs/bootstrap/CLAUDE.md`. Keep
`## Sequência de construção`, `## Por que isto não é uma Composition Crossplane`, and
`## Relação com o resto do repo` — those are explanatory/rule content, not a file index.

- [ ] **Step 3: Commit**

```bash
git add aws/docs/bootstrap/CLAUDE.md aws/docs/bootstrap/README.md
git commit -m "docs(#64): split aws/docs/bootstrap/README.md index out of CLAUDE.md"
```

---

### Task 4: `aws/docs/network/CLAUDE.md` → extract `README.md`

**Files:**
- Modify: `aws/docs/network/CLAUDE.md`
- Create: `aws/docs/network/README.md`

**Interfaces:**
- Consumes: same recipe as Task 2
- Produces: `aws/docs/network/README.md`

- [ ] **Step 1: Create `aws/docs/network/README.md`**

Move `## O que este domínio entrega` and `## Tópicos` verbatim, header:

```markdown
# `network/` — Domain: Hub-and-Spoke Network

Índice de leitura. Convenções e regras ficam em [`CLAUDE.md`](CLAUDE.md).
```

- [ ] **Step 2: Remove the moved sections from `CLAUDE.md`**

Keep `## Sequência de construção`, `## Estado atual vs. alvo (resumo)`,
`## Armadilha: route table de tenant só isola se o attachment for por tenant`, and
`## Duas coisas que o TGW não faz` in `CLAUDE.md` — gotchas and state, not an index.

- [ ] **Step 3: Commit**

```bash
git add aws/docs/network/CLAUDE.md aws/docs/network/README.md
git commit -m "docs(#64): split aws/docs/network/README.md index out of CLAUDE.md"
```

---

### Task 5: `aws/docs/accounts/CLAUDE.md` → extract `README.md`

**Files:**
- Modify: `aws/docs/accounts/CLAUDE.md`
- Create: `aws/docs/accounts/README.md`

**Interfaces:**
- Consumes: same recipe as Task 2
- Produces: `aws/docs/accounts/README.md`

- [ ] **Step 1: Create `aws/docs/accounts/README.md`**

Move `## O que este domínio entrega` and `## Tópicos` verbatim, header:

```markdown
# `accounts/` — Domain: Accounts and Organizations

Índice de leitura. Convenções e regras ficam em [`CLAUDE.md`](CLAUDE.md).
```

- [ ] **Step 2: Remove the moved sections from `CLAUDE.md`**

Keep `## Sequência de construção`, `## Scripts`, `## Gotchas de API já descobertos`,
`## Decisões em aberto`, `## Estado atual vs. alvo (resumo)`, and the `Gap conhecido` subsection —
none of those are the file index.

- [ ] **Step 3: Commit**

```bash
git add aws/docs/accounts/CLAUDE.md aws/docs/accounts/README.md
git commit -m "docs(#64): split aws/docs/accounts/README.md index out of CLAUDE.md"
```

---

### Task 6: `aws/docs/security/CLAUDE.md` → extract `README.md`

**Files:**
- Modify: `aws/docs/security/CLAUDE.md`
- Create: `aws/docs/security/README.md`

**Interfaces:**
- Consumes: same recipe as Task 2
- Produces: `aws/docs/security/README.md`

- [ ] **Step 1: Create `aws/docs/security/README.md`**

Move `## O que este domínio entrega` and `## Tópicos` verbatim, header:

```markdown
# `security/` — Domain: Security & IAM

Índice de leitura. Convenções e regras ficam em [`CLAUDE.md`](CLAUDE.md).
```

- [ ] **Step 2: Remove the moved sections from `CLAUDE.md`**

Keep `## Sequência de construção`, `## Estado atual vs. alvo (resumo)`, and
`## Relação com o resto do repo`.

- [ ] **Step 3: Commit**

```bash
git add aws/docs/security/CLAUDE.md aws/docs/security/README.md
git commit -m "docs(#64): split aws/docs/security/README.md index out of CLAUDE.md"
```

---

### Task 7: `aws/docs/dns/CLAUDE.md` → extract `README.md`

**Files:**
- Modify: `aws/docs/dns/CLAUDE.md`
- Create: `aws/docs/dns/README.md`

**Interfaces:**
- Consumes: same recipe as Task 2
- Produces: `aws/docs/dns/README.md`

- [ ] **Step 1: Create `aws/docs/dns/README.md`**

Move `## O que este domínio entrega` and `## Tópicos` verbatim, header:

```markdown
# `dns/` — Domain: DNS

Índice de leitura. Convenções e regras ficam em [`CLAUDE.md`](CLAUDE.md).
```

- [ ] **Step 2: Remove the moved sections from `CLAUDE.md`**

Keep `## Sequência de construção`, `## Estado atual vs. alvo (resumo)`,
`## Delegação verificada na prática (2026-08-26)`, `## Relação com o resto do repo`, and
`## TLS no edge: o ALB só lê ACM`.

- [ ] **Step 3: Commit**

```bash
git add aws/docs/dns/CLAUDE.md aws/docs/dns/README.md
git commit -m "docs(#64): split aws/docs/dns/README.md index out of CLAUDE.md"
```

---

### Task 8: `aws/docs/compute/CLAUDE.md` → extract `README.md`

**Files:**
- Modify: `aws/docs/compute/CLAUDE.md`
- Create: `aws/docs/compute/README.md`

**Interfaces:**
- Consumes: same recipe as Task 2
- Produces: `aws/docs/compute/README.md`

- [ ] **Step 1: Create `aws/docs/compute/README.md`**

Move `## O que este domínio entrega` and `## Tópicos` verbatim, header:

```markdown
# `compute/` — Domain: Compute — EKS as a Spoke

Índice de leitura. Convenções e regras ficam em [`CLAUDE.md`](CLAUDE.md).
```

- [ ] **Step 2: Remove the moved sections from `CLAUDE.md`**

Keep `## Sequência de construção`, `## Estado atual vs. alvo (resumo)`, and
`## Relação com o resto do repo`.

- [ ] **Step 3: Commit**

```bash
git add aws/docs/compute/CLAUDE.md aws/docs/compute/README.md
git commit -m "docs(#64): split aws/docs/compute/README.md index out of CLAUDE.md"
```

---

### Task 9: `aws/docs/observability/CLAUDE.md` → extract `README.md`

**Files:**
- Modify: `aws/docs/observability/CLAUDE.md`
- Create: `aws/docs/observability/README.md`

**Interfaces:**
- Consumes: same recipe as Task 2
- Produces: `aws/docs/observability/README.md`

- [ ] **Step 1: Create `aws/docs/observability/README.md`**

Move `## O que este domínio entrega` and `## Tópicos` verbatim, header:

```markdown
# `observability/` — Domain: Observability

Índice de leitura. Convenções e regras ficam em [`CLAUDE.md`](CLAUDE.md).
```

- [ ] **Step 2: Remove the moved sections from `CLAUDE.md`**

Keep `## Sequência de construção`, `## Onde a observabilidade centralizada mora (slots canônicos)`,
`## Estado atual vs. alvo (resumo)`, and `## Relação com o resto do repo`.

- [ ] **Step 3: Commit**

```bash
git add aws/docs/observability/CLAUDE.md aws/docs/observability/README.md
git commit -m "docs(#64): split aws/docs/observability/README.md index out of CLAUDE.md"
```

---

### Task 10: `aws/docs/tenancy/CLAUDE.md` → extract `README.md`

**Files:**
- Modify: `aws/docs/tenancy/CLAUDE.md`
- Create: `aws/docs/tenancy/README.md`

**Interfaces:**
- Consumes: same recipe as Task 2
- Produces: `aws/docs/tenancy/README.md`

- [ ] **Step 1: Create `aws/docs/tenancy/README.md`**

Move `## O que este domínio entrega` and `## Tópicos` verbatim, header:

```markdown
# `tenancy/` — Domain: Tenancy & SaaS

Índice de leitura. Convenções e regras ficam em [`CLAUDE.md`](CLAUDE.md).
```

- [ ] **Step 2: Remove the moved sections from `CLAUDE.md`**

Keep `## Sequência de decisão (não é sequência de provisionamento)`,
`## Relação com o resto do repo`, `## Estado atual vs. alvo (resumo)`, `## Decisões em aberto`, and
`## Fontes`.

- [ ] **Step 3: Fix the `## Domínios` links in `aws/docs/README.md`**

All 8 domains are now split. Update every `<domain>/CLAUDE.md` link in `aws/docs/README.md`'s
`## Domínios` table (left dangling since Task 2) to point at `<domain>/README.md`.

- [ ] **Step 4: Run the link checker**

Run: `scripts/bin/check-doc-links`
Expected: exit code 0 — the domain links fixed in Step 3 now resolve.

- [ ] **Step 5: Commit**

```bash
git add aws/docs/tenancy/CLAUDE.md aws/docs/tenancy/README.md aws/docs/README.md
git commit -m "$(cat <<'EOF'
docs(#64): split aws/docs/tenancy/README.md index out of CLAUDE.md

Also repoints aws/docs/README.md's domain table at each domain's new
README.md now that all 8 domains are split.
EOF
)"
```

---

### Task 11: `docs/idp/CLAUDE.md` → extract `README.md`

**Files:**
- Modify: `docs/idp/CLAUDE.md`
- Create: `docs/idp/README.md`

**Interfaces:**
- Consumes: `scripts/bin/check-doc-links` (Task 1)
- Produces: `docs/idp/README.md`, the target the root `README.md` rewrite (Task 14) links to as
  the Backstage entry point.

- [ ] **Step 1: Read `docs/idp/CLAUDE.md` in full**

Run: `cat docs/idp/CLAUDE.md` — this file mixes project overview, dev commands, and architecture
notes; unlike the `aws/docs/` domains it has no single `## Tópicos`-style section, so the split
needs a fresh read rather than the mechanical recipe used in Tasks 3–10.

- [ ] **Step 2: Create `docs/idp/README.md`**

Move `## Project Overview`, `## Architecture` (with its subsections), and `## UI Customisations`
(with its subsections) into `docs/idp/README.md`, header:

```markdown
# Backstage IDP

Índice de leitura e visão geral do app Backstage. Comandos de dev/build/test, regras de
autenticação e convenções ficam em [`CLAUDE.md`](CLAUDE.md).
```

- [ ] **Step 3: Remove the moved sections from `CLAUDE.md`**

Keep `## Branches`, `## Commands` (with subsections), `## Authentication`, `## Scripts`,
`## Architecture decisions (recorded)`, `## Security TODOs (PoC hardening, deferred)`, and
`## Targets` in `CLAUDE.md` — these are operational/imperative, not overview content.

- [ ] **Step 4: Run the link checker**

Run: `scripts/bin/check-doc-links`
Expected: exit code 0.

- [ ] **Step 5: Commit**

```bash
git add docs/idp/CLAUDE.md docs/idp/README.md
git commit -m "docs(#64): split docs/idp/README.md overview out of CLAUDE.md"
```

---

### Task 12: `aws/terraform/README.md` — move the maintenance rule into `CLAUDE.md`

**Files:**
- Modify: `aws/terraform/README.md` (remove `## Manter este arquivo verdadeiro`)
- Modify: `aws/terraform/CLAUDE.md` (add the moved section)

**Interfaces:**
- Consumes: `scripts/bin/check-doc-links` (Task 1)
- Produces: nothing new consumed by later tasks — this is the one reverse-direction split named in
  the spec (README currently holds both index and a rule; CLAUDE.md currently holds only rules).

- [ ] **Step 1: Read the `## Manter este arquivo verdadeiro` section**

Run: `sed -n '/^## Manter este arquivo verdadeiro/,/^## /p' aws/terraform/README.md`

- [ ] **Step 2: Move it into `aws/terraform/CLAUDE.md`**

Append the section verbatim to the end of `aws/terraform/CLAUDE.md`, unchanged in content — only
its location moves.

- [ ] **Step 3: Remove it from `aws/terraform/README.md`**

Delete `## Manter este arquivo verdadeiro` and its content from `aws/terraform/README.md`. Every
other section in that file (Raízes, Sequência de provisionamento, Submódulos, etc.) is navigational
and stays.

- [ ] **Step 4: Run the link checker**

Run: `scripts/bin/check-doc-links`
Expected: exit code 0.

- [ ] **Step 5: Commit**

```bash
git add aws/terraform/README.md aws/terraform/CLAUDE.md
git commit -m "$(cat <<'EOF'
docs(#64): move aws/terraform maintenance rule from README to CLAUDE.md

README.md was mixing navigation with an agent rule; CLAUDE.md is
where imperative rules live per the reorg spec's role split.
EOF
)"
```

---

### Task 13: `docs/superpowers/README.md` — mark the tree as process memory

**Files:**
- Create: `docs/superpowers/README.md`

**Interfaces:**
- Consumes: nothing
- Produces: `docs/superpowers/README.md`, referenced by the root `README.md` rewrite (Task 14) as
  an explicit "not in the main index" pointer, and by `aws/docs/CLAUDE.md`'s
  "Relação com o resto do repo" section if that section references specs/plans (verify while
  editing; add the pointer there too if it doesn't already exist).

- [ ] **Step 1: Create the file**

```markdown
# `docs/superpowers/`

Memória de processo — como uma decisão foi tomada (`specs/`) e como um plano de implementação foi
executado (`plans/`) — não documentação de referência sobre como o sistema funciona hoje. Por isso
esta árvore não aparece no índice de leitura principal do repo nem em `aws/docs/CLAUDE.md`.

Para saber como o sistema funciona hoje: `aws/docs/` (arquitetura de referência) ou
`docs/adr/` (decisões que ainda valem). Para saber por que uma decisão passada foi tomada, ou como
uma entrega específica foi planejada: procure aqui pela data no nome da pasta.

Nada aqui é apagado; um plano ou spec superado por uma decisão nova não é editado — a decisão nova
ganha seu próprio documento (ADR, ou spec/plan com data mais recente).
```

- [ ] **Step 2: Commit**

```bash
git add docs/superpowers/README.md
git commit -m "docs(#64): mark docs/superpowers/ as process memory, out of the main index"
```

---

### Task 14: Root `README.md` — rewrite as the repo's entry point

**Files:**
- Modify: `README.md` (root)

**Interfaces:**
- Consumes: `docs/idp/README.md` (Task 11), `aws/docs/README.md` (Task 2/10),
  `aws/terraform/README.md` (Task 12), `docs/adr/README.md`, `docs/archived/README.md`,
  `docs/superpowers/README.md` (Task 13) — all must exist before this task runs.
- Produces: the repo's single entry point; no later task in this plan depends on it, but it is the
  deliverable that closes the concrete symptom from the issue (`ci/` missing from the terraform
  Raízes table happened because nothing pointed a reader toward that table in the first place).

- [ ] **Step 1: Read the current root `README.md` in full**

Run: `cat README.md` — today it is entirely about Backstage (Stack, Quick start, Structure, UI
customisations).

- [ ] **Step 2: Confirm the Backstage content already exists in `docs/idp/README.md` / `docs/idp/CLAUDE.md`**

Compare against the sections moved in Task 11. If the root `README.md` has content not already
captured in `docs/idp/{README,CLAUDE}.md` (e.g. a Quick start command sequence), copy the missing
parts into `docs/idp/README.md` before proceeding — nothing gets lost in the rewrite.

- [ ] **Step 3: Rewrite `README.md`**

```markdown
# wasp-idp

Plataforma AWS multi-tenant (hub-and-spoke, EKS) com um IDP (Backstage) por cima. Ponto de entrada
único do repo — cada linha abaixo é uma porta para um tronco de documentação.

## Por onde começar

| Se você quer... | Vá para |
|---|---|
| Entender a arquitetura de referência AWS (hub-and-spoke, domínios) | [`aws/docs/README.md`](aws/docs/README.md) |
| Provisionar a plataforma (Terraform, sequência, raízes) | [`aws/terraform/README.md`](aws/terraform/README.md) |
| Usar ou desenvolver o Backstage (IDP) | [`docs/idp/README.md`](docs/idp/README.md) |
| Ver decisões de arquitetura já tomadas (ADRs) | [`docs/adr/README.md`](docs/adr/README.md) |
| Ver o histórico do que já foi entregue | [`docs/archived/README.md`](docs/archived/README.md) |
| Entender por que uma decisão passada foi tomada, ou reler um plano antigo | [`docs/superpowers/README.md`](docs/superpowers/README.md) |
| Retomar de onde a última sessão parou | [`HANDOFF.md`](HANDOFF.md) |

## Convenções deste repo

- `CLAUDE.md` de cada pasta = regras para quem edita ali. `README.md` de cada pasta = índice do
  que existe. Nunca duplicar o mesmo conteúdo nos dois.
- Um documento cobre um assunto; quando uma seção se aprofunda demais num subtema, ela vira um
  arquivo próprio, referenciado de onde fazia sentido.
- Antes de renomear qualquer arquivo `.md`, rodar `scripts/bin/check-doc-links`.
```

- [ ] **Step 4: Run the link checker**

Run: `scripts/bin/check-doc-links`
Expected: exit code 0.

- [ ] **Step 5: Commit**

```bash
git add README.md docs/idp/README.md
git commit -m "$(cat <<'EOF'
docs(#64): rewrite root README.md as the repo's entry point

Was entirely about Backstage and never mentioned AWS — the root
cause the issue names for #52's duplicate README (aws/terraform/ci/
missing from the Raízes table had no path leading a reader there).
EOF
)"
```

---

### Task 15: Full-repo verification, ADR, and maintenance-rule lines

**Files:**
- Modify: `aws/docs/CLAUDE.md` (add "Manter este arquivo verdadeiro" line, if the table exists — check first)
- Modify: `docs/archived/README.md` (add the corresponding line)
- Create: `docs/adr/0016-documentation-navigation-structure.md` (next available ADR number — verify
  by running `ls docs/adr/` first, since another ADR may have landed since this plan was written)
- Modify: `docs/adr/README.md` (add the new ADR to the index table)

**Interfaces:**
- Consumes: every file created/modified in Tasks 1–14
- Produces: nothing consumed further — this is the plan's closing task

- [ ] **Step 1: Run the link checker across the whole repo**

Run: `scripts/bin/check-doc-links`
Expected: exit code 0. If anything is reported, fix the specific broken link (do not silence the
script) and re-run before continuing.

- [ ] **Step 2: Confirm the next ADR number**

Run: `ls docs/adr/ | sort | tail -3`
Use the next sequential number after the highest existing one.

- [ ] **Step 3: Write the ADR**

```markdown
# <NNNN>. Estrutura de navegação da documentação

Data: 2026-09-01

## Status

Aceito

## Contexto

251 arquivos `.md` versionados fora de `idp/`, crescidos por acreção, sem estrutura que permita
achar o que se precisa sem contexto prévio — ver #64 para os números completos e o sintoma que
motivou a issue (duplicação de `aws/terraform/ci/README.md` no #52 porque `ci/` não constava da
tabela de Raízes).

## Decisão

Consolidação mínima: os dois troncos físicos existentes (`aws/docs/`, `docs/`) permanecem onde
estão — nenhum `git mv` de conteúdo de referência. Em vez disso:

- Todo `CLAUDE.md` que fazia papel duplo de índice de pasta + regras é dividido: `README.md` vira o
  índice navegável, `CLAUDE.md` fica só com regras imperativas para o agente.
- `README.md` da raiz do repo vira o portão de entrada único, apontando para todos os troncos.
- `docs/superpowers/{specs,plans}/` sai do índice de leitura principal — é memória de processo, não
  referência — sem mover fisicamente.
- Documento cobre um assunto; quando uma seção aprofunda demais um subtema, vira arquivo próprio
  referenciado de onde fazia sentido. Sem limite de linhas fixo.
- `scripts/bin/check-doc-links` verifica link relativo quebrado em todo arquivo versionado (não só
  `*.md`); reutilizável, não é gate de CI nesta iteração.

Detalhamento completo:
[`docs/superpowers/specs/2026-09-01-documentation-reorganization-design.md`](../superpowers/specs/2026-09-01-documentation-reorganization-design.md).

## Consequências

- Ganho: qualquer pasta com `CLAUDE.md`+`README.md` tem papel claro; um agente sabe que regra vive
  num arquivo e índice no outro, sem ler os dois para descobrir qual é qual.
- Custo: duas árvores de documentação continuam existindo (`aws/docs/` e `docs/`) em vez de uma só
  — trade-off aceito para manter o risco de link quebrado baixo nesta passada.
- Vazamento de PII conhecido (#23) não foi corrigido por esta decisão — continua rastreado
  separadamente.
- A issue do site MkDocs (próxima) herda uma estrutura decidida, não a bagunça anterior.
```

- [ ] **Step 4: Add the ADR to the index**

Add a row to the table in `docs/adr/README.md`, following the existing format
(`| [NNNN](NNNN-slug.md) | Título |`).

- [ ] **Step 5: Add the maintenance-rule lines**

In every file this plan touched that already has a "Manter este arquivo verdadeiro" (or
equivalent) table — check `aws/docs/CLAUDE.md`, `docs/archived/README.md`, and the new root
`README.md` — add a row/line noting the new `README.md`/`CLAUDE.md` pair it should keep in sync
with. Skip any file that has no such table already; do not invent the convention where it doesn't
exist yet.

- [ ] **Step 6: Final link check**

Run: `scripts/bin/check-doc-links`
Expected: exit code 0.

- [ ] **Step 7: Commit**

```bash
git add docs/adr/ aws/docs/CLAUDE.md docs/archived/README.md README.md
git commit -m "$(cat <<'EOF'
docs(#64): record documentation-structure ADR, close reorg execution

Closes the structure-proposal and execution deliverables from #64:
navigation entry point, CLAUDE.md/README.md role split, and this
decision recorded as an immutable ADR.
EOF
)"
```
