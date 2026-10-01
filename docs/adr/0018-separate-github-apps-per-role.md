# Separate GitHub Apps per role in wasp-foundry

**Status:** Aceito (2026-10-01)

## Contexto

Dois atores escrevem na org `wasp-foundry`: o Backstage (cria repos, envia workflows, abre PRs) e o CI de cada aplicação (bump de tag no `gitops`). A chave do CI fica num secret de org, legível por qualquer workflow de qualquer repo da org.

## Decisão

**Dois GitHub Apps.** `wasp-foundry-backstage`: instalado em todos os repos, Administration/Contents/Pull requests/Workflows RW; chave só no arquivo local do Backstage. `wasp-foundry-ci`: instalado **só** no `gitops`, Contents RW; chave no secret de org `FOUNDRY_CI_APP_PRIVATE_KEY`. Tokens de instalação de ~1h, como na [ADR 0012](0012-argocd-github-app-auth.md).

## Consequências

- Um workflow comprometido numa aplicação alcança só o `gitops`, não a criação/remoção de repos da org.
- Continua podendo escrever qualquer caminho do `gitops` — limitação aceita em `aws/docs/known-broken.md`.
- Duas chaves para rotacionar em vez de uma.
