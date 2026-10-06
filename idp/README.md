# [Backstage](https://backstage.io)

Visão geral, arquitetura e customizações em [`docs/idp/README.md`](../docs/idp/README.md); comandos, autenticação e gotchas em [`docs/idp/CLAUDE.md`](../docs/idp/CLAUDE.md).

## Rodar localmente com o cluster k3d

Pré-requisito: `idp/github-app-wasp-foundry-backstage-credentials.yaml` presente (ver "GitHub integration" em `docs/idp/CLAUDE.md`) e `yarn install` já executado em `idp/`.

Da raiz do repo:

```sh
scripts/single-cluster/backstage-start              # reaproveita o k3d idp-single se já existir
scripts/single-cluster/backstage-start --recreate   # apaga e recria o idp-single antes
```

O script sobe o k3d `idp-single` (`scripts/single-cluster/up`), exporta as credenciais read-only do plugin Kubernetes (`backstage-reader`) e roda `yarn start` com `app-config.yaml` + `app-config.single-cluster.yaml`. Frontend em http://localhost:3000, backend em `:7007`.

O processo fica em primeiro plano até `Ctrl+C`. Rode-o num terminal próprio (ou numa janela tmux): disparado em background por um agente, ele é encerrado quando o tempo limite da tarefa expira.

## Catálogo extra (local, fora do repo)

Para carregar entidades de outra pasta sem copiá-las para este repo (público), crie um `idp/app-config.<nome>.local.yaml` — `*.local.yaml` é gitignored — e passe-o como config extra:

```sh
scripts/single-cluster/backstage-start --config idp/app-config.<nome>.local.yaml
```

Regras para esse arquivo:

- O merge de config do Backstage **substitui arrays**: repita nele todos os `catalog.locations` de `app-config.yaml` antes dos novos, senão o catálogo base some.
- Use caminho absoluto no `target` das entidades externas. Caminhos relativos são resolvidos a partir de `idp/packages/backend`, não do arquivo de config.
- Restrinja os kinds de cada location com `rules: - allow: [...]`, como nas entradas base.

```yaml
catalog:
  locations:
    # ... cópia das locations de app-config.yaml ...
    - type: file
      target: /caminho/absoluto/para/catalog/system.yaml
      rules:
        - allow: [Domain, System, Component, API, Resource]
```

Arquivo novo na pasta externa exige uma entrada nova aqui. Reinicie o Backstage para recarregar.
