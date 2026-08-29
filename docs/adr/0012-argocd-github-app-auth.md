# GitHub App for ArgoCD repository authentication

**Status:** Aceito

## Contexto

O ArgoCD de cada célula precisa clonar o repositório privado `wasp-gitops`. Duas opções usuais:
deploy key SSH (chave de vida longa fixada no cluster) ou GitHub App (token de instalação de curta
duração, renovado automaticamente).

## Decisão

**GitHub App, não deploy key SSH.** Token de instalação de ~1h renovado pelo próprio ArgoCD, contra
uma chave de vida longa em disco — escolher SSH recriaria de propósito o problema já catalogado como
Known Broken (credencial de vida longa sem rotação). A App usada tem `Contents: Read-only`, sem
webhook, sem callback.

Validado ponta a ponta num k3d local (mesma versão de chart do ArgoCD da célula) antes de aplicar na
célula real. Detalhes de implementação (formato do secret, `extraObjects`, `AppProject`) em
[`docs/superpowers/specs/2026-08-28-argocd-github-app.md`](../superpowers/specs/2026-08-28-argocd-github-app.md).

## Consequências

- `secret-type: repo-creds` (prefixo da URL do owner), não `repository` — consequência visível:
  `argocd repo list` fica vazio, a credencial só aparece em `argocd repocreds list`.
- `AppProject infra` não pode vir por GitOps (precisa existir antes de qualquer `Application`
  sincronizar) — nasce no Terraform, junto com o ArgoCD.
- A credencial em si (PEM da App) entra em base64 no cofre de secrets, decodificada por `b64dec` no
  template — chave multilinha não sobrevive bem a JSON de secret.
- O teste de autenticação só faz sentido com o repositório **privado**: `wasp-gitops` era público
  até a validação (2026-08-28), o que teria deixado o ArgoCD clonar sem credencial nenhuma e um
  sync verde não provaria nada. Fechado antes de validar, com o risco conferido (as composite
  actions de `actions/` só são referenciadas pelo próprio repo) — consequência para quem depender
  dele de fora: qualquer consumidor anônimo parou de funcionar.
