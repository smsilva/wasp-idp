# Provider de SCM connection do GitHub

Valida cada `ScmConnection` com `vendor: github` do namespace `platform-system` contra o GitHub App dela (ADR 0025, #199). Roda **dentro do cluster**, como Deployment `scm-github-provider` em `platform-system`, instalado pelo `platform init --target local`.

É o único leitor dos Secrets de credencial: a Platform API grava a chave pelo `SecretStore` e não tem `get` em `secrets`; a Role deste controller tem só `get` em `secrets`, e `get`/`list`/`watch`/`patch` em `scmconnections`.

## Reconciliação

Para cada connection com `spec.credentialRef` (o App já existe):

1. Lê a chave do Secret e gera o JWT do App (RS256, `iss=appId`, 10 min).
2. `GET /app`: grava o `appSlug` quando falta (caminho `--app-id`). Chave de outro App → `InvalidCredentials`.
3. `GET /app/installations`: procura a instalação cuja `account.login` é a `org`. Não achou → `NotInstalled`, com o link de instalação. Grava o `installationId` quando falta ou quando o gravado não é uma instalação deste App (a rota `installed` da API não tem `state`, então o id é só uma dica e não pode travar a connection). Um id de instalação deste App em outra conta é `NotInstalled`.
4. `repository_selection` precisa ser `all` → senão `NotAllRepositories`.
5. As permissões da instalação precisam cobrir as do manifesto (`REQUIRED`, igual ao `PERMISSIONS` da API, com `actions:write` para o build da #206) → senão `MissingPermissions`, listando o que falta.
6. `POST /app/installations/{id}/access_tokens` funciona → `Ready=True, reason=Verified`, com `permissions`, `repositorySelection` e `lastValidated`.

Erro inesperado (GitHub fora, Secret ilegível) vira `VerificationFailed` com a mensagem.

## Quando revalida

- Quando a anotação `platform.wasp.silvios.me/verify-requested-at` muda (`platform scm connection verify`, a rota `installed`, o create com `--app-id`). A anotação respondida fica em `status.observedVerifyRequest`, e a API mostra `verifying: true` até lá.
- A cada 6 h enquanto `Ready`.
- Enquanto não está `Ready`, com backoff de 30 s dobrando até 10 min. Watch mais uma passada completa a cada 15 s (`--resync-seconds`).

## Depurar

```bash
kubectl --context k3d-platform-local --namespace platform-system logs deploy/scm-github-provider
kubectl --context k3d-platform-local --namespace platform-system get scm
```

## Testes

O GitHub é simulado com `httpx.MockTransport`; a chave dos testes é gerada a cada execução.

```bash
cd platform/providers/scm_github
uv sync
uv run pytest
```
