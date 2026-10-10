# platform CLI

Cliente da Platform API. Primeira versão em **Python** (≥ 3.11): no ambiente local, buildar e executar binários novos depende de liberação de segurança, e um pacote Python roda sem isso. A migração para Go vem depois; por isso a CLI é fina, e a lógica mora na API e nos providers.

O pacote se chama `wasp_platform`, não `platform`, porque `platform` colide com o módulo da stdlib. O console script `platform` está em `[project.scripts]` no `pyproject.toml`.

## Instalação

```bash
cd cli
uv sync
uv run platform --help
```

Ou, para ter `platform` no `PATH`: `uv tool install --editable cli/`. A instalação precisa ser editable a partir do checkout: o `init` aplica CRDs, manifests e scripts versionados no repo (ou aponte `PLATFORM_REPO` para o checkout).

## Uso (target local)

```bash
platform init --target local --admin <email> # k3d platform-local, CRDs, Platform API, Keycloak; idempotente
platform login                               # Google via Keycloak; --use-device-code sem navegador
platform whoami
platform provider run --target local         # outro terminal, foreground
platform environment create greetings-test \
  --profile ephemeral \
  --expires 3d \
  --wait
platform environment list
platform environment delete greetings-test
```

Todos os comandos aceitam `--output json`. O kubeconfig de cada ambiente fica em `~/.config/platform/environments/<nome>.kubeconfig`.

## Documentação

Guia passo a passo com exemplos em `docs/index.md` (MkDocs), publicado em https://smsilva.github.io/wasp-idp/cli/ pelo workflow `.github/workflows/pages.yaml` a cada push na `main`. Para ver localmente:

```bash
uvx --with mkdocs-material mkdocs serve --config-file cli/mkdocs.yml
```

## Fronteira

- `wasp_platform.bootstrap` é a única parte que fala com Docker, k3d e `kubectl`. Só `init` e `provider run` importam esse módulo (`tests/test_boundaries.py` garante).
- `wasp_platform.client` é o cliente HTTP da Platform API, usado por todos os outros comandos. Ele manda o access token de `wasp_platform.auth`, que faz o login (PKCE ou device code), guarda os tokens em `~/.config/platform/credentials` (`0600`) e os renova.

## Portas do target local

| Uso | Porta |
|---|---|
| Kubernetes API do `platform-local` | `6560` |
| Platform API (`127.0.0.1` apenas) | `9090` |
| Keycloak (`127.0.0.1` apenas; issuer em `localhost`) | `8180` |
| Kubernetes API de cada `env-<nome>` | livre, escolhida pelo provider (`127.0.0.1`) |

Os scripts de `scripts/cluster-zero` e `scripts/single-cluster` usam `6550`–`6553` e `9080`–`9083`.

## Limitações conhecidas

- O journal é JSON Lines num PVC até o Postgres (#172).
- O provider roda em foreground. Sem ele, os pedidos ficam em `NoProviderForCapability`, e apagar um ambiente com o provider parado deixa o `Environment` preso no finalizer e o cluster `env-*` vivo até o provider subir.

## Alternativas descartadas

- Workflow de Pages separado para o guia: substituiria o site do deck. O guia é publicado pelo mesmo `pages.yaml`, em `/cli/`.
- `kopf`/operator no cluster para o provider `local_k3d`: o provider precisa de Docker no host.

## Testes

```bash
cd cli && uv run pytest
```
