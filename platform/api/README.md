# Platform API

Fachada sobre os CRDs do grupo `platform.wasp.silvios.me` (ADR 0022). Python + FastAPI, roda no cluster de control plane (`platform-local` no target local) com uma ServiceAccount que só enxerga `environments` no namespace `platform-system`.

## Endpoints

| Método | Caminho | Resposta |
|---|---|---|
| `GET` | `/healthz` | `200` |
| `POST` | `/v1/environments` | `202`, body `{"name", "profile": "ephemeral"\|"shared", "expires": "3d"}` |
| `GET` | `/v1/environments` | `200`, `{"items": [...]}` |
| `GET` | `/v1/environments/{name}` | `200` |
| `DELETE` | `/v1/environments/{name}` | `202` |

Os objetos devolvidos são a visão da API (`name`, `profile`, `status`, `expiresAt`, `kubeconfig`), não o CR cru: clientes não acoplam ao formato dos CRDs.

## Escrita

- Toda escrita passa pela interface `StateWriter` (`state.py`); a implementação é `KubeApplyWriter`, que aplica direto na kube API.
- No create, a API grava `Ready=False, reason=NoProviderForCapability`. O provider substitui a condition quando assume; se ele já tiver tocado o objeto, a API não sobrescreve (concorrência otimista por `resourceVersion`).

## Journal

Nesta fatia, o journal é um arquivo append-only JSON Lines em `/var/lib/platform/journal.jsonl`, num PVC (`platform-api-journal`). Cada pedido aceito gera uma linha com `applied: false` **antes** de ser aplicado e outra com o mesmo `id` e `applied: true` depois. O Postgres substitui o arquivo com a #144.

A expiração de um ambiente é aplicada pelo provider direto no CR e não passa pelo journal.

## Autenticação

Nenhuma nesta fatia: o serviço só é alcançável por `127.0.0.1:9090` no host. O middleware de auth é um no-op marcado `TODO(#144)` (`current_actor` em `app.py`).

## Desenvolvimento

```bash
cd platform/api
uv sync
uv run pytest
```

A imagem é buildada e importada no k3d pelo `platform init --target local`.
