# Acceptance and Docs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Provar o critério de sucesso do spec ponta a ponta, registrar as decisões (ADRs 0019, 0020) e limitações (known-broken), atualizar a documentação e abrir o PR da #105.

**Architecture:** Nenhum código novo. Execução guiada contra a org real, os três clusters e o Backstage local; correções que surgirem voltam ao plano de origem com commit próprio.

**Tech Stack:** Backstage, GitHub, GHCR, ArgoCD, k3d.

**Spec:** `docs/superpowers/specs/2026-10-01-bookinfo-catalog-multi-cluster-design.md` — "Testes › Aceitação ponta a ponta", "Riscos a validar primeiro" (2 e 3), "Limitações aceitas", "ADRs a escrever na implementação".

## Global Constraints

- ADRs: `0019`, `0020` (último existente: `0018-separate-github-apps-per-role.md`). Formato Nygard dos existentes: `# Título em inglês`, `**Status:** Aceito (AAAA-MM-DD)`, `## Contexto`, `## Decisão`, `## Consequências`, corpo em pt-BR.
- `HANDOFF.md` é visão geral (regra do `CLAUDE.md`): uma linha em "Frentes" e uma em "Completed Work"; progresso fica no `HANDOFF.local.md`.
- Nenhum PII em arquivo versionado.
- Pré-requisito: planos 00–04 concluídos; Backstage rodando com os `eval` do `backstage-reader` para `development` e `production`.

## Review Focus

- Backstage reiniciado durante a aceitação: o item 6 cobre — o catalog volta pelo provider.
- App nova pelo template registrada duas vezes (provider + `catalog:register`): conferir no item 5 que a entidade é uma só e que o log não acusa erro além do conflito de location esperado.

---

### Task 1: Aceitação ponta a ponta

**Files:** nenhum.

- [ ] **Step 1: Catalog (item 1)** — na UI (`http://localhost:3000`, login guest) e pela API:

```bash
token="$(curl --silent localhost:7007/api/auth/guest/refresh | python3 -c 'import sys,json;print(json.load(sys.stdin)["backstageIdentity"]["token"])')"
curl --silent --header "Authorization: Bearer ${token}" localhost:7007/api/catalog/entities/by-name/component/default/reviews \
  | python3 -c 'import sys,json;print(sorted(r["type"]+" "+r["targetRef"] for r in json.load(sys.stdin)["relations"]))'
```

Expected: `apiProvidedBy`/`providesApi api:default/reviews-api`, `consumesApi api:default/ratings-api`, `dependsOn resource:default/development` e `resource:default/production`, `partOf system:default/bookinfo`, `ownedBy group:default/team-beta`. Na UI: `/catalog/default/domain/bookstore` → System `bookinfo` → aba de Components (4) e APIs (3); `/catalog/default/api/details-api` → aba **Definition** renderiza a OpenAPI; grafo de relações do `reviews` mostra provides/consumes e os dois Resources. Registrar com print (`skill print`/`peek`) se a UI divergir da API.

- [ ] **Step 2: Aba Kubernetes (item 2)**

```bash
entity="$(curl --silent --header "Authorization: Bearer ${token}" localhost:7007/api/catalog/entities/by-name/component/default/reviews)"
curl --silent --header "Authorization: Bearer ${token}" --header 'Content-Type: application/json' \
  --data "{\"entity\": ${entity}}" localhost:7007/api/kubernetes/services/reviews \
  | python3 -c '
import sys, json
for item in json.load(sys.stdin)["items"]:
    pods = [r for r in item["resources"] if r["type"] == "pods"][0]["resources"]
    print(item["cluster"]["name"], item["errors"], sorted(p["metadata"]["name"].rsplit("-", 2)[0] for p in pods))'
```

Expected: `development [] ['reviews-v1', 'reviews-v2', 'reviews-v3']` e `production [] [...]`. Na UI, aba Kubernetes do `reviews` com os dois clusters.

- [ ] **Step 3: Página de produto (item 3)** — repetir o plano 04, Task 5, Step 5. Expected: idem.

- [ ] **Step 4: Promoção do `details` (item 4)**

```bash
work_dir="$(mktemp --directory)"
git clone git@github.com:wasp-foundry/details.git "${work_dir}"
git -C "${work_dir}" switch --create publisher-b
sed --in-place "s/'publisher' => 'PublisherA'/'publisher' => 'PublisherB'/" "${work_dir}/details.rb"
git -C "${work_dir}" commit --all --message "feat: publisher B"
git -C "${work_dir}" push --set-upstream origin publisher-b
gh pr create --repo wasp-foundry/details --head publisher-b --base main --title "feat: publisher B" --body "Acceptance test of the promotion flow."
```

Esperar o `build` do PR verde; `gh pr merge publisher-b --repo wasp-foundry/details --squash --delete-branch`; esperar o run da `main` (build + bump). Então:

```bash
for port in 9081 9082; do printf '%s ' "${port}"; curl --silent "http://localhost:${port}/productpage" | grep --only-matching 'Publisher[AB]' | head -1; done
```

Expected (depois do refresh da `details-development`): `9081 PublisherB`, `9082 PublisherA`. Promover:

```bash
gh workflow run promote.yaml --repo wasp-foundry/gitops -f app=details
```

Merge do PR aberto; refresh da `details-production`; repetir o `curl`. Expected: `9082 PublisherB`. Remover `work_dir`.

- [ ] **Step 5: `hello-alpha` e app nova pelo template (item 5)**

```bash
for environment in development production; do kubectl --context "k3d-${environment}" --namespace hello-alpha get deployment hello-alpha --output jsonpath='{.status.readyReplicas}{"\n"}'; done
```

Expected: `1` e `1`. Criar `hello-beta` (owner `team-beta`) pelo template, via `/create` na UI ou API do scaffolder (`templateRef: template:default/python-service`), fazer merge do PR do `gitops` e esperar as Applications `hello-beta-development`/`-production` `Healthy`. Conferir que existe uma única entidade `component:default/hello-beta`. Manter `hello-beta` como segundo exemplo vivo.

- [ ] **Step 6: Restart do backend (item 6)** — parar o Backstage pelos PIDs de `:3000`/`:7007`, subir de novo com os `eval`, e em até 2 min:

```bash
curl --silent --header "Authorization: Bearer ${token}" 'localhost:7007/api/catalog/entities?filter=kind=component' \
  | python3 -c 'import sys,json;print(sorted(e["metadata"]["name"] for e in json.load(sys.stdin)))'
```

(Gerar `token` de novo.) Expected: inclui `details`, `hello-alpha`, `hello-beta`, `productpage`, `ratings`, `reviews` sem nenhum registro manual.

- [ ] **Step 7: Memória (risco 3)**

```bash
docker stats --no-stream --format '{{.Name}} {{.MemUsage}}' | grep k3d- | sort
free --human
```

Registrar o total. Se a máquina estiver sem folga (swap em uso crescente, pods `OOMKilled`), aplicar o fallback do spec: overlay de `production` do `reviews` removendo v2 e v3 (`patches` com `$patch: delete` para `reviews-v2` e `reviews-v3`) — commit no `gitops` e ledger.

- [ ] **Step 8: Registrar riscos 2 e 3 no spec** — em "Riscos a validar primeiro", itens 2 e 3: `— **resultado (AAAA-MM-DD):** <duração do build do reviews no runner>` e `<memória total dos nós k3d; fallback aplicado ou não>`.

```bash
git add docs/superpowers/specs/2026-10-01-bookinfo-catalog-multi-cluster-design.md
git commit --message "docs(#105): resultado dos riscos de build e memória"
```

### Task 2: ADRs

**Files:**
- Create: `docs/adr/0019-environment-clusters-managed-by-central-argocd.md`
- Create: `docs/adr/0020-catalog-discovery-from-github-org.md`
- Modify: `docs/adr/README.md` (tabela — duas linhas no fim)

- [ ] **Step 1: `0019-environment-clusters-managed-by-central-argocd.md`**

```markdown
# Environment clusters managed by the central ArgoCD

**Status:** Aceito (AAAA-MM-DD)

## Contexto

O fluxo da [ADR 0017](0017-central-gitops-repo-for-foundry-apps.md) fazia deploy de cada aplicação num único k3d (`idp-cluster-zero`), sem noção de ambiente. Para ilustrar deploy em mais de um ambiente, cada aplicação precisa existir em `development` e `production`, com promoção explícita entre eles. As opções eram um ArgoCD por cluster, cada um lendo o próprio caminho do `gitops`, ou o ArgoCD do cluster-zero gerenciando os clusters de ambiente.

## Decisão

**O ArgoCD do `idp-cluster-zero` gerencia dois k3d de ambiente, `development` e `production`, na rede Docker compartilhada `k3d-idp`.** Cada cluster de destino é um Secret de cluster com label `env`; o ApplicationSet `foundry-apps` usa o gerador matrix (clusters × diretórios `apps/*`) e gera `<app>-<env>` apontando para `apps/<app>/overlays/<env>`. O cluster-zero não roda aplicações. O CI de cada aplicação faz bump só em `overlays/development`; produção muda por pull request aberto pelo workflow `promote.yaml` do `gitops`.

## Consequências

- Uma tela do ArgoCD mostra todas as aplicações em todos os ambientes; o desenho repete o hub-and-spoke do repo na AWS.
- O ArgoCD tem `cluster-admin` nos clusters de destino (ServiceAccount `argocd-manager`), como faz o `argocd cluster add`.
- Promoção não verifica que a imagem rodou bem em development — qualquer tag de development pode ser promovida.
- Toda aplicação, inclusive as criadas pelo template `python-service`, nasce nos dois ambientes com a tag do primeiro commit.
```

- [ ] **Step 2: `0020-catalog-discovery-from-github-org.md`**

```markdown
# Catalog discovery from the wasp-foundry GitHub org

**Status:** Aceito (AAAA-MM-DD)

## Contexto

O Backstage local usa SQLite em memória: tudo registrado por `catalog:register` ou pela UI some quando o backend reinicia. Registrar cada repo como location fixa no `app-config.yaml` resolveria a persistência, mas exigiria um commit no `wasp-idp` para cada aplicação nova da org.

## Decisão

**O catalog descobre os repos da org `wasp-foundry` pelo entity provider do GitHub** (`@backstage/plugin-catalog-backend-module-github`, `catalog.providers.github.waspFoundry`): lê `/catalog-info.yaml` da `main` de cada repo a cada 5 minutos, autenticado pelo App `wasp-foundry-backstage`. Entidades da plataforma que não pertencem a um repo (Domain, System, Resources dos clusters, times) ficam em `idp/catalog/` como locations de arquivo.

## Consequências

- Reiniciar o backend não perde aplicações: o primeiro ciclo do provider (15 s após o start) reconstrói o catalog.
- Aplicação nova aparece sem passo extra; o `catalog:register` do template continua só para o registro imediato.
- A descrição de cada serviço vive no próprio repo (`catalog-info.yaml`, `openapi.yaml`) e muda no mesmo PR que o código.
- Um repo da org com `catalog-info.yaml` inválido gera erro de processamento visível só no log do backend.
```

- [ ] **Step 3: `docs/adr/README.md`** — acrescentar à tabela:

```markdown
| [0019](0019-environment-clusters-managed-by-central-argocd.md) | Clusters `development` e `production` gerenciados pelo ArgoCD do cluster-zero: matrix generator, overlays por ambiente, promoção por PR |
| [0020](0020-catalog-discovery-from-github-org.md) | Catalog descobre os repos da org `wasp-foundry` pelo entity provider do GitHub |
```

- [ ] **Step 4: Commit**

```bash
git add docs/adr/
git commit --message "docs(#105): ADRs 0019 e 0020"
```

### Task 3: Known broken, docs e HANDOFF

**Files:**
- Modify: `aws/docs/known-broken.md` (lista numerada em "## Em aberto ou intencional")
- Modify: `docs/idp/CLAUDE.md`
- Modify: `docs/idp/README.md` (bloco "Monorepo structure" não muda; acrescentar seção curta de clusters se não existir)
- Modify: `HANDOFF.md`

- [ ] **Step 1: known-broken** — acrescentar ao fim da lista, com o próximo número:

```markdown
N. **Clusters de ambiente do IDP local (#105): ArgoCD com `cluster-admin` e promoção sem verificação** — *intentional*. O ServiceAccount `argocd-manager` tem `cluster-admin` em `development` e `production`; `promote.yaml` promove qualquer tag de development sem conferir que ela rodou bem lá; cada cluster tem uma porta de host só (`9081`/`9082`), reservada ao `productpage` — as demais apps são acessadas por `port-forward`. Ver [ADR 0019](../../docs/adr/0019-environment-clusters-managed-by-central-argocd.md).
```

Se o plano 00 caiu no fallback `insecure: true`, acrescentar à mesma entrada: "O Secret de cluster usa `insecure: true` porque o certificado do k3s não cobre o nome do container na rede `k3d-idp`."

- [ ] **Step 2: `docs/idp/CLAUDE.md`** — conferir que a tabela `## Scripts` já tem `register-clusters`, `cluster-create` e `backstage-reader` atualizados (plano 01) e acrescentar:

```markdown
| `scripts/foundry/seed-bookinfo` | Imports the Istio Bookinfo services into `wasp-foundry` (one repo per service + one gitops PR) — idempotent; `--dry-run` builds everything locally |
| `scripts/foundry/test-bookinfo-assets` | Validates the seed assets offline: catalog entities, OpenAPI, gitops overlays, CI |
```

E, na seção de operação, o fluxo de promoção: `gh workflow run promote.yaml --repo wasp-foundry/gitops -f app=<app>` + merge do PR.

- [ ] **Step 3: `HANDOFF.md`** — na tabela "Frentes", a linha da #105 passa a `Entregue em AAAA-MM-DD`; na seção "Estado atual", parágrafo **IDP**, acrescentar: "Exemplo de catalog completo: Domain `bookstore` / System `bookinfo` (4 serviços do Bookinfo, repos próprios na org). Deploy em dois ambientes (`development`, `production`) gerenciados pelo ArgoCD do cluster-zero — ADR 0019." No topo de "Completed Work":

```markdown
- **AAAA-MM-DD — #105, Bookinfo no catalog com deploy em development e production.** Quatro serviços do Istio Bookinfo em repos próprios da `wasp-foundry`, Domain/System/APIs/Resources no catalog com descoberta automática da org, ArgoCD do cluster-zero gerenciando dois clusters de ambiente com promoção por PR. Spec e planos em `docs/superpowers/{specs,plans}/2026-10-01-bookinfo-catalog-multi-cluster*`.
```

- [ ] **Step 4: Commit**

```bash
git add aws/docs/known-broken.md docs/idp/CLAUDE.md docs/idp/README.md HANDOFF.md
git commit --message "docs(#105): known-broken, docs do idp e HANDOFF"
```

### Task 4: PR da #105

- [ ] **Step 1: Descrição** em `/tmp/feat-105-bookinfo-catalog-multi-cluster-pr.txt` (markdown, caminhos relativos ao repo): objetivo, diagrama da seção "Arquitetura" do spec, mudanças por área (clusters, ApplicationSet/gitops, template, catalog/Backstage, seed), resultados dos três riscos, checklist da aceitação do Task 1 com os resultados, links das ADRs 0019/0020, `Closes #105`, terminando com `🤖 Generated with [Claude Code](https://claude.com/claude-code)`.

- [ ] **Step 2: Push e PR**

```bash
git push
gh pr create --base main --title "feat(#105): Bookinfo no catalog com deploy em development e production" --body-file /tmp/feat-105-bookinfo-catalog-multi-cluster-pr.txt
```

Se `gh pr create` falhar, mostrar `https://github.com/smsilva/wasp-idp/compare/feat/105-bookinfo-catalog-multi-cluster?expand=1`.

- [ ] **Step 3: Após o merge (usuário)** — #105 para `Done`:

```bash
gh project item-edit 6 --owner smsilva --url https://github.com/smsilva/wasp-idp/issues/105 --field Status --value Done
```
