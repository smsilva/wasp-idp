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
platform init --target local                 # k3d platform-local, CRDs, Platform API; idempotente
platform provider run --target local         # outro terminal, foreground
platform environment create greetings-test \
  --profile ephemeral \
  --expires 3d \
  --wait
platform environment list
platform environment delete greetings-test
```

Todos os comandos aceitam `--output json`. O kubeconfig de cada ambiente fica em `~/.config/platform/environments/<nome>.kubeconfig`.

## Fronteira

- `wasp_platform.bootstrap` é a única parte que fala com Docker, k3d e `kubectl`. Só `init` e `provider run` importam esse módulo (`tests/test_boundaries.py` garante).
- `wasp_platform.client` é o cliente HTTP da Platform API, usado por todos os outros comandos.

## Portas do target local

| Uso | Porta |
|---|---|
| Kubernetes API do `platform-local` | `6560` |
| Platform API (`127.0.0.1` apenas) | `9090` |
| Kubernetes API de cada `env-<nome>` | livre, escolhida pelo provider (`127.0.0.1`) |

Os scripts de `scripts/cluster-zero` e `scripts/single-cluster` usam `6550`–`6553` e `9080`–`9083`.

## Testes

```bash
cd cli && uv run pytest
```
