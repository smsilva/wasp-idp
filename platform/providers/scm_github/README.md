# Provider de SCM connection do GitHub

Valida cada `ScmConnection` com `vendor: github` do namespace `platform-system` contra o GitHub App dela (ADR 0025, #199) e executa cada `ComponentCreation` (`platform catalog component create`, #279). Roda **dentro do cluster**, como Deployment `scm-github-provider` em `platform-system`, instalado pelo `platform init --target local`.

É o único leitor dos Secrets de credencial: a Platform API grava a chave pelo `SecretStore` e não tem `get` em `secrets`; a Role deste controller tem só `get` em `secrets`, e `get`/`list`/`watch`/`patch` em `scmconnections`. Por isso a criação de repos roda aqui, num segundo watch do mesmo processo, e não num controller à parte.

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
5. `Registered`: cria ou atualiza o `Component` do grupo `catalog.platform.wasp.silvios.me` com os dados do `catalog-info.yaml` renderizado, `lifecycle: experimental` e `source` (`repo`, `template`, `origin: created`). Um índice com esse nome para outro repo → `ComponentExists`.

Falha de GitHub ou do cluster vira `GitHubError`/`StepFailed` no primeiro passo pendente e repete no resync (15 s); o status só é gravado quando muda. Backoff, a proteção da `main` e a remoção após 24 h são a #280.

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
