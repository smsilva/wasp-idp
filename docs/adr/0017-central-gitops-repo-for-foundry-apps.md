# Central GitOps repository for foundry apps

**Status:** Aceito (2026-10-01)

## Contexto

Aplicações criadas pelo template Backstage `python-service` precisam chegar a um cluster. O Backstage não faz deploy; alguém precisa gravar o estado desejado num Git que o ArgoCD lê. As opções eram manifestos dentro do repo de cada aplicação (pasta `deploy/` + ApplicationSet SCM Provider varrendo a org) ou um repositório central `wasp-foundry/gitops`.

## Decisão

**Repositório central `wasp-foundry/gitops`, um diretório `apps/<app>/` por aplicação.** O template grava a aplicação nova por **pull request** (`publish:github:pull-request`) — o merge é o ponto de revisão da plataforma. O CI de cada aplicação faz **commit direto** do bump de tag (`kustomize edit set image`), porque é mecânico e revisá-lo não agrega. O ArgoCD descobre as aplicações por um `ApplicationSet` com gerador Git directory.

## Consequências

- Duas escritas por criação (repo da app + PR no gitops); o scaffolder não faz rollback, então falha no PR deixa repo órfão (limpeza manual).
- O CI de cada aplicação precisa de credencial de escrita num repo que não é o seu — ver [0018](0018-separate-github-apps-per-role.md).
- Pronto para mais de um ambiente (`apps/<app>/overlays/<env>`) sem mudar o modelo.
- O `smsilva/wasp-gitops` (infra das células) não é usado: aplicação e infraestrutura ficam em repositórios separados.
- No repo da aplicação a `main` é protegida — mudança só por PR, com o CI rodando nele — mas **sem aprovação obrigatória** (`requiredApprovingReviewCount: 0`): o default do `publish:github` (1 aprovação + `enforce_admins`) congela o repo numa org de um membro só, que não aprova o próprio PR.
