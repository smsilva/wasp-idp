# platform CLI

Sobe um control plane local e cria Environments, cada um como um cluster k3d.

```
platform CLI ──HTTP──▶ Platform API ──▶ CRD Environment ◀──watch── provider local_k3d ──▶ k3d env-<nome>
                       (platform-local)                             (no host)
```

## 1. Pré-requisitos

```bash
docker version --format '{{.Server.Version}}'
k3d version
kubectl version --client
uv --version
```

## 2. Instalar a CLI

```bash
cd wasp-idp/cli
uv sync
uv run platform --help
```

Para ter `platform` no `PATH`:

```bash
uv tool install --editable .
platform --help
```

!!! note
    Os exemplos abaixo usam `platform`. Sem o `uv tool install`, prefixe com `uv run`.

## 3. Subir o control plane

```bash
platform init --target local
```

```
creating cluster platform-local …
applying CRDs …
building the Platform API image …
deploying the Platform API …
✓ Platform API at http://127.0.0.1:9090 · config in ~/.config/platform/config.yaml
```

Rodar de novo é seguro: o cluster é reaproveitado.

```bash
platform init --target local
```

```
cluster platform-local already exists, reusing it
…
```

```bash
cat ~/.config/platform/config.yaml
```

```yaml
target: local
api_url: http://127.0.0.1:9090
context: k3d-platform-local
```

## 4. Criar um ambiente sem provider

```bash
platform environment create greetings-test \
  --profile ephemeral \
  --expires 1h
```

```
provisioning greetings-test (profile: ephemeral) …
greetings-test: NoProviderForCapability
```

O pedido fica registrado e espera um provider.

```bash
platform environment list
```

```
NAME            PROFILE    STATUS                   EXPIRES
greetings-test  ephemeral  NoProviderForCapability  59m
```

## 5. Subir o provider

Em outro terminal, e deixe rodando:

```bash
platform provider run --target local
```

```
INFO watching environments in k3d-platform-local/platform-system
INFO creating cluster env-greetings-test
INFO environment greetings-test ready
```

O ambiente pendente converge sozinho:

```bash
platform environment list
```

```
NAME            PROFILE    STATUS  EXPIRES
greetings-test  ephemeral  ready   59m
```

```bash
k3d cluster list
```

```
NAME                 SERVERS   AGENTS   LOADBALANCER
env-greetings-test   1/1       0/0      true
platform-local       1/1       0/0      true
```

## 6. Usar o cluster do ambiente

```bash
export KUBECONFIG=~/.config/platform/environments/greetings-test.kubeconfig
kubectl get nodes
```

```
NAME                              STATUS   ROLES                  AGE   VERSION
k3d-env-greetings-test-server-0   Ready    control-plane,master   56s   v1.31.5+k3s1
```

## 7. Criar e esperar ficar pronto

Com o provider rodando:

```bash
platform environment create demo \
  --profile ephemeral \
  --expires 3d \
  --wait
```

```
provisioning demo (profile: ephemeral) …
  pending
  Provisioning
✓ demo ready
```

## 8. Saída em JSON

```bash
platform environment create doc-sample \
  --profile ephemeral \
  --expires 3d \
  --output json
```

```json
{
  "name": "doc-sample",
  "profile": "ephemeral",
  "expiresAt": "2026-10-13T17:28:53Z",
  "status": "NoProviderForCapability",
  "message": "no provider has claimed the environment capability yet",
  "kubeconfig": null,
  "createdAt": "2026-10-10T17:28:53Z"
}
```

```bash
platform environment list --output json | jq -r '.[].name'
```

## 9. Apagar

```bash
platform environment delete greetings-test
```

```
✓ greetings-test deleting
```

O provider remove o cluster e o kubeconfig:

```
INFO deleting cluster env-greetings-test
INFO environment greetings-test removed
```

## 10. Expiração

Ambientes com `--expires` são apagados pelo provider quando o prazo vence:

```bash
platform environment create short-lived \
  --profile ephemeral \
  --expires 2m
```

```
INFO environment short-lived expired at 2026-10-10T16:03:16Z, deleting
INFO deleting cluster env-short-lived
INFO environment short-lived removed
```

Formatos de `--expires`: `30m`, `12h`, `3d`, `1w`.

## 11. Por baixo: o CRD

```bash
kubectl --context k3d-platform-local \
  --namespace platform-system \
  get environments
```

```
NAME   PROFILE     READY   REASON         EXPIRES
demo   ephemeral   True    ClusterReady   2026-10-13T17:01:16Z
```

Journal dos pedidos (uma linha antes e outra depois de aplicar):

```bash
kubectl --context k3d-platform-local \
  --namespace platform-system \
  exec deploy/platform-api -- tail -n 2 /var/lib/platform/journal.jsonl
```

```json
{"id":"552d…","actor":"anonymous","action":"create","kind":"Environment","name":"demo","spec":{"profile":"ephemeral","expiresAt":"2026-10-13T17:01:16Z"},"applied":false}
{"id":"552d…","applied":true}
```

## 12. Desmontar tudo

```bash
platform environment list --output json | jq -r '.[].name' \
  | xargs --no-run-if-empty --max-args 1 platform environment delete
k3d cluster delete platform-local
rm ~/.config/platform/config.yaml
```

!!! warning
    Apague os ambientes com o provider rodando: é ele que remove os clusters `env-*`.

## Referência rápida

| Comando | O que faz |
|---|---|
| `platform init --target local` | cria `platform-local`, CRDs e Platform API |
| `platform provider run --target local` | provisiona ambientes como k3d (foreground) |
| `platform environment create <nome> --profile ephemeral\|shared [--expires 3d] [--wait]` | pede um ambiente |
| `platform environment list` | NAME, PROFILE, STATUS, EXPIRES |
| `platform environment delete <nome>` | remove o ambiente e o cluster |
| `--output json` | em todos os comandos |

| Status | Significado |
|---|---|
| `NoProviderForCapability` | nenhum provider assumiu o pedido |
| `Provisioning` | cluster sendo criado |
| `ready` | cluster no ar, kubeconfig gravado |
| `ProvisioningFailed` | erro do provider; veja `message` no JSON |
| `deleting` | remoção em andamento |

| Porta | Uso |
|---|---|
| `6560` | Kubernetes API do `platform-local` |
| `127.0.0.1:9090` | Platform API |
