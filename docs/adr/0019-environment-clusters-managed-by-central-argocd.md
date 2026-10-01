# Environment clusters managed by the central ArgoCD

**Status:** Aceito (2026-10-01)

## Contexto

O fluxo da [ADR 0017](0017-central-gitops-repo-for-foundry-apps.md) fazia deploy de cada aplicação num único k3d (`idp-cluster-zero`), sem noção de ambiente. Para ilustrar deploy em mais de um ambiente, cada aplicação precisa existir em `development` e `production`, com promoção explícita entre eles. As opções eram um ArgoCD por cluster, cada um lendo o próprio caminho do `gitops`, ou o ArgoCD do cluster-zero gerenciando os clusters de ambiente.

## Decisão

**O ArgoCD do `idp-cluster-zero` gerencia dois k3d de ambiente, `development` e `production`, na rede Docker compartilhada `k3d-idp`.** Cada cluster de destino é um Secret de cluster com label `env`; o ApplicationSet `foundry-apps` usa o gerador matrix (clusters × diretórios `apps/*`) e gera `<app>-<env>` apontando para `apps/<app>/overlays/<env>`. O cluster-zero não roda aplicações. O CI de cada aplicação faz bump só em `overlays/development`; produção muda por pull request aberto pelo workflow `promote.yaml` do `gitops`.

## Consequências

- Uma tela do ArgoCD mostra todas as aplicações em todos os ambientes; o desenho repete o hub-and-spoke do repo na AWS.
- O ArgoCD tem `cluster-admin` nos clusters de destino (ServiceAccount `argocd-manager`), como faz o `argocd cluster add`.
- Promoção não verifica que a imagem rodou bem em development — qualquer tag de development pode ser promovida.
- Toda aplicação, inclusive as criadas pelo template `python-service`, nasce nos dois ambientes com a tag do primeiro commit.
- O `promote.yaml` abre PR com o `GITHUB_TOKEN`, o que exigiu habilitar "Allow GitHub Actions to create and approve pull requests" na org `wasp-foundry`.
- O host precisa de `fs.inotify.max_user_instances` ≥ 1024: com o padrão (128), cinco nós k3d esgotam o limite e o containerd não sobe.
