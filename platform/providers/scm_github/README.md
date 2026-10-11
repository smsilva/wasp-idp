# Provider de SCM connection do GitHub

Valida cada `ScmConnection` com `vendor: github` do namespace `platform-system` contra o GitHub App dela (ADR 0025, #199) e executa cada `ComponentCreation` (`platform catalog component create`, #279) e cada `Build` (`platform build create`, #206). Roda **dentro do cluster**, como Deployment `scm-github-provider` em `platform-system`, instalado pelo `platform init --target local`.

É o único leitor dos Secrets de credencial: a Platform API grava a chave pelo `SecretStore` e não tem `get` em `secrets`; a Role deste controller tem só `get` em `secrets`, e `get`/`list`/`watch`/`patch` em `scmconnections`. Por isso a criação de repos e os builds rodam aqui, em outros dois watches do mesmo processo, e não em controllers à parte.

## Reconciliação

Para cada connection com `spec.credentialRef` (o App já existe):

1. Lê a chave do Secret e gera o JWT do App (RS256, `iss=appId`, 10 min).
2. `GET /app`: grava o `appSlug` quando falta (caminho `--app-id`). Chave de outro App → `InvalidCredentials`.
3. `GET /app/installations`: procura a instalação cuja `account.login` é a `org`. Não achou → `NotInstalled`, com o link de instalação. Grava o `installationId` quando falta ou quando o gravado não é uma instalação deste App (a rota `installed` da API não tem `state`, então o id é só uma dica e não pode travar a connection). Um id de instalação deste App em outra conta é `NotInstalled`.
4. `repository_selection` precisa ser `all` → senão `NotAllRepositories`.
5. As permissões da instalação precisam cobrir as do manifesto (`REQUIRED`, igual ao `PERMISSIONS` da API, com `actions:write` para o build da #206) → senão `MissingPermissions`, listando o que falta.
6. `POST /app/installations/{id}/access_tokens` funciona → `Ready=True, reason=Verified`, com `permissions`, `repositorySelection` e `lastValidated`.

Erro inesperado (GitHub fora, Secret ilegível) vira `VerificationFailed` com a mensagem.

## Criação de component

Cada `ComponentCreation` passa por um passo idempotente por condition, retomável depois de um restart:

1. `Validated`: a connection ainda está `Ready`, com `installationId` e chave → senão `ConnectionNotFound`/`ConnectionNotReady`.
2. `Rendered`: busca o template no `source.ref` copiado para o CR (`git`, na imagem), renderiza com `wasp_templates` num `emptyDir` (`/work/<uid>`), anota `platform.wasp.silvios.me/template` e `github.com/project-slug` no `catalog-info.yaml` e troca o `docs/prd.md` pelo `spec.prd`. Grava `status.files` e `status.appSpec`. Depois de um restart, renderiza de novo: o ref é fixo.
3. `RepoCreated`: `POST /orgs/{org}/repos` com `auto_init: true` e grava `status.repo` (com o `nodeId`) na hora. Repo existente cujo `node_id` não é o do status → `RepoAlreadyExists`, sem tocar no repo.
4. `Pushed`: Git Data API (blobs → tree → commit sem parent → `refs/heads/main` com `force`). O `auto_init` existe porque a Git Data API recusa repo vazio (`409`); o commit sem parent substitui o do README, e o repo fica com um commit só. Se a `main` já aponta para um commit com o trailer `Platform-Component-Creation: <nome>`, o passo está feito.
5. `Protected`: `PUT /repos/{repo}/branches/main/protection` com PR obrigatório, `required_approving_review_count: 0` e `enforce_admins: false` (a org pode ter um só membro, ADR 0017). Um `403` que não é rate limit (repo privado numa org GitHub Free) → `Protected=False, reason=ProtectionUnavailable`: é aviso, o `Ready` não espera por ele.
6. `Registered`: cria ou atualiza o `Component` do grupo `catalog.platform.wasp.silvios.me` com os dados do `catalog-info.yaml` renderizado, `lifecycle: experimental` e `source` (`repo`, `template`, `origin: created`). Um índice com esse nome para outro repo → `ComponentExists`.

Uma falha vira `reason` no primeiro passo pendente e no `Ready`; o status só é gravado quando muda.

- **Transitória:** `RateLimited` (`403`/`429` com `retry-after` ou `x-ratelimit-remaining: 0`), `GitHubUnavailable` (5xx, ou GitHub inalcançável) e `StepFailed` (cluster, erro inesperado), além dos reasons da connection. Repete com backoff de 30 s dobrando até 10 min, em memória como o das connections; um rate limit espera pelo menos até o `retry-after`/`x-ratelimit-reset`.
- **Definitiva:** `GitHubRejected` (qualquer outro 4xx, com a mensagem do GitHub), `RepoAlreadyExists`, `RepoGone` e `ComponentExists`. A criação para.

Uma criação `Ready`, ou parada num reason definitivo, é removida 24 h depois (`lastTransitionTime` do `Ready`); o índice `Component` fica.

## Build

Cada `Build` (#206, ADR 0030) segue o contrato `platform-build` (`cli/docs/reference/builds.md`). O token da instalação é reaproveitado por 50 min, e o status só é gravado quando muda.

1. `Dispatched`: `GET …/actions/workflows/platform-build.yaml` (`404` → `WorkflowNotFound`), `GET …/branches/{branch}` (`404` → `BranchNotFound`), e `POST …/dispatches` com `request-id` e `version`. Antes do dispatch procura o run pelo `run-name`: um restart entre o dispatch e o status gravado não dispara de novo. `422` no dispatch → `ContractViolation`. O status é gravado na hora.
2. `Running`: acha o run em `GET …/actions/runs?event=workflow_dispatch&branch=…` pelo `display_title` `platform-build <requestId>` e grava `runUrl` e `run.headSha`. Enquanto o run não termina, `Ready=False, reason=Building`, e o resync (15 s) olha de novo. Sem run 10 min depois do dispatch → `ContractViolation`. Run sem sucesso → `BuildFailed`.
3. `Succeeded`: baixa o zip do artefato `platform-build` (no máximo 1 MiB; o `httpx` tira o `Authorization` no redirect para o blob storage) e confere o `platform-build.json` → `status.result`, ou `ContractViolation`.
4. `SpecValidated`: lê o `app-spec.yaml` no `commit` (`GET …/contents/app-spec.yaml?ref=`) e valida o schema do Score vendorizado (`schemas/score-v1b1.json`, de `score-spec/spec@f29aafc`), os tipos de recurso (`--resource-types`, padrão `postgres,dns,route`) e cada `resources.<nome>.id` contra os `Resource` do catálogo → `status.errors` e `InvalidSpec`.
5. `Ready`: cria o `Version` `<component>.<version>` em `catalog.platform.wasp.silvios.me`. Já existe com outro `commit` → `VersionConflict`, sem sobrescrever; com o mesmo `commit`, é a mesma versão.

Os reasons transitórios e o backoff são os da criação de component. Definitivos: `WorkflowNotFound`, `BranchNotFound`, `BuildFailed`, `ContractViolation`, `InvalidSpec`, `VersionConflict` e `GitHubRejected`. Um build `Ready`, ou parado num reason definitivo, é removido 24 h depois; a versão fica no índice.

## Quando revalida

- Quando a anotação `platform.wasp.silvios.me/verify-requested-at` muda (`platform scm connection verify`, a rota `installed`, o create com `--app-id`). A anotação respondida fica em `status.observedVerifyRequest`, e a API mostra `verifying: true` até lá.
- A cada 6 h enquanto `Ready`.
- Enquanto não está `Ready`, com backoff de 30 s dobrando até 10 min. Watch mais uma passada completa a cada 15 s (`--resync-seconds`).

## Depurar

```bash
kubectl --context k3d-platform-local --namespace platform-system logs deploy/scm-github-provider
kubectl --context k3d-platform-local --namespace platform-system get scm
kubectl --context k3d-platform-local --namespace platform-system get componentcreations
```

## Testes

O GitHub é simulado com `httpx.MockTransport`; a chave dos testes é gerada a cada execução.

```bash
cd platform/providers/scm_github
uv sync
uv run pytest
```
