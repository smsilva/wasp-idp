# platform CLI

Sobe um control plane local e cria Environments, cada um como um cluster Kubernetes virtual (vcluster) dentro dele.

```
platform CLI ──HTTP──▶ Platform API ──▶ CRD Environment ◀──watch── provider local_vcluster ──▶ vcluster env-<nome>
                      └──────────────────────────── platform-local (k3d) ─────────────────────────────┘
```

O provider roda dentro do `platform-local`, instalado pelo `init`: não há processo para manter aberto no host.

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

O login usa o Google através do Keycloak. Exporte as credenciais do OAuth client antes do `init`; o passo a passo do lado do Google está em `platform/keycloak/README.md`. Sem elas, o `init` sobe tudo e avisa que o login com Google fica desligado.

```bash
export GOOGLE_CLIENT_ID=<id>.apps.googleusercontent.com
export GOOGLE_CLIENT_SECRET=<secret>
platform init --target local --admin voce@example.com
```

```
creating cluster platform-local …
applying CRDs …
building the Platform API image …
deploying the Platform API …
deploying Keycloak …
waiting for Keycloak …
applying the realm platform …
✓ Platform API at http://127.0.0.1:9090 · config in ~/.config/platform/config.yaml
✓ Keycloak issuer http://localhost:8180/realms/platform
```

O e-mail do `--admin` entra no grupo `platform-admins` no primeiro login com Google; os demais usuários caem só em `platform-users`. O `init` lembra o `--admin` e as credenciais do Google, então as execuções seguintes não precisam repeti-los.

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
issuer: http://localhost:8180/realms/platform
client_id: platform-cli
```

## 4. Entrar

Todo comando além de `init` fala com a Platform API, que exige um token do Keycloak.

```bash
platform login
```

```
Opening the browser to sign in …
✓ Logged in as voce@example.com (platform-admins, platform-users)
```

O navegador vai direto à tela do Google e termina em "Login complete. You can return to the terminal.". Por trás, a CLI usa Authorization Code com PKCE e recebe o código num listener temporário em `127.0.0.1`.

Sem navegador nesta máquina (SSH, container), use o device code e abra a URL em qualquer outro dispositivo:

```bash
platform login --use-device-code
```

```
Open http://localhost:8180/realms/platform/device?user_code=ABCD-EFGH
and confirm the code ABCD-EFGH
✓ Logged in as voce@example.com (platform-admins, platform-users)
```

```bash
platform whoami
```

```
voce@example.com (platform-admins, platform-users)
```

O `whoami` pergunta à API quem ela vê; não lê o token localmente. Os tokens ficam em `~/.config/platform/credentials` (permissão `0600`), e a CLI renova o access token sozinha quando faltam menos de 60 s para ele expirar. `platform logout` revoga a sessão no Keycloak e apaga o arquivo.

!!! warning
    O Keycloak precisa ser alcançado em `localhost:8180` pelo navegador: é o endereço que o Google aceita como redirect. Em SSH, use `--use-device-code` com um túnel (`ssh -L 8180:localhost:8180`).

## 5. Criar um ambiente

```bash
platform environment create greetings-test \
  --profile ephemeral \
  --expires 1h \
  --wait
```

```
provisioning greetings-test (profile: ephemeral) …
  NoProviderForCapability
  Provisioning
✓ greetings-test ready
```

A API aceita o pedido e grava um `Environment`; o status começa em `NoProviderForCapability`. O provider `local_vcluster`, que roda dentro do `platform-local`, assume o pedido em seguida e instala um vcluster no namespace `env-greetings-test`. Leva cerca de 30 s.

Sem `--wait`, o comando volta logo e o ambiente segue sendo criado:

```bash
platform environment list
```

```
NAME            PROFILE    STATUS  EXPIRES
greetings-test  ephemeral  ready   59m
```

## 6. Usar o cluster do ambiente

O `--wait` grava o kubeconfig. Para um ambiente criado sem ele, `platform environment get` faz o mesmo:

```bash
platform environment get greetings-test
```

```
greetings-test: ready
  vcluster running in namespace env-greetings-test, API on 127.0.0.1:7100
  kubectl --kubeconfig ~/.config/platform/environments/greetings-test.kubeconfig get nodes
```

```bash
export KUBECONFIG=~/.config/platform/environments/greetings-test.kubeconfig
kubectl get nodes
kubectl create deployment web --image nginx:alpine
```

```
NAME                          STATUS   ROLES    AGE   VERSION
k3d-platform-local-server-0   Ready    <none>   17s   v1.36.0
```

O nó que aparece é o do `platform-local`: o vcluster tem API, etcd e controllers próprios, e os pods rodam no cluster de fora, no namespace `env-greetings-test`. Cada ambiente ganha uma porta da faixa `7100`–`7119`, mapeada pelo `init` em `127.0.0.1`.

## 7. Saída em JSON

```bash
platform environment list --output json
```

```json
[
  {
    "name": "greetings-test",
    "profile": "ephemeral",
    "expiresAt": "2026-10-10T21:35:22Z",
    "status": "ready",
    "message": "vcluster running in namespace env-greetings-test, API on 127.0.0.1:7100",
    "port": 7100,
    "createdAt": "2026-10-10T20:35:22Z"
  }
]
```

A lista nunca traz o kubeconfig, que é uma credencial. O `platform environment get` o recebe só para quem criou o ambiente ou para quem está em `platform-admins`; os demais veem o status, sem o acesso.

```bash
platform environment list --output json | jq -r '.[].name'
```

## 8. Apagar

```bash
platform environment delete greetings-test
```

```
✓ greetings-test deleting
```

O provider desinstala o vcluster e remove o namespace `env-greetings-test`.

## 9. Expiração

Ambientes com `--expires` são apagados pelo provider quando o prazo vence (checado a cada 10 s):

```bash
platform environment create short-lived \
  --profile ephemeral \
  --expires 1m
```

```bash
kubectl --context k3d-platform-local --namespace platform-system logs deploy/local-vcluster-provider
```

```
INFO environment short-lived expired at 2026-10-10T21:38:44Z, deleting
INFO deleting vcluster env-short-lived
INFO environment short-lived removed
```

Formatos de `--expires`: `30m`, `12h`, `3d`, `1w`.

## 10. Por baixo: o CRD

```bash
kubectl --context k3d-platform-local \
  --namespace platform-system \
  get environments
```

```
NAME   PROFILE     READY   REASON         EXPIRES
demo   ephemeral   True    ClusterReady   2026-10-13T17:01:16Z
```

Journal dos pedidos (uma linha antes e outra depois de aplicar). O `actor` é o `sub` do token, imutável, seguido do e-mail:

```bash
kubectl --context k3d-platform-local \
  --namespace platform-system \
  exec deploy/platform-api -- tail -n 2 /var/lib/platform/journal.jsonl
```

```json
{"id":"552d…","actor":"fe16e6a6-… (voce@example.com)","action":"create","kind":"Environment","name":"demo","spec":{"profile":"ephemeral","expiresAt":"2026-10-13T17:01:16Z"},"applied":false}
{"id":"552d…","applied":true}
```

## 11. Desmontar tudo

```bash
platform environment list --output json | jq -r '.[].name' \
  | xargs --no-run-if-empty --max-args 1 platform environment delete
k3d cluster delete platform-local
rm ~/.config/platform/config.yaml
```

Apagar o `platform-local` leva junto os vclusters, que vivem dentro dele.

## Referência rápida

| Comando | O que faz |
|---|---|
| `platform init --target local [--admin <email>]` | cria `platform-local`, CRDs, Keycloak, Platform API e o provider `local_vcluster` |
| `platform login [--use-device-code]` | entra com a conta Google |
| `platform whoami` | e-mail e grupos, vistos pela API |
| `platform logout` | revoga a sessão e apaga as credenciais |
| `platform environment create <nome> --profile ephemeral\|shared [--expires 3d] [--wait]` | pede um ambiente |
| `platform environment list` | NAME, PROFILE, STATUS, EXPIRES |
| `platform environment get <nome>` | status e mensagem; grava o kubeconfig quando pronto |
| `platform environment delete <nome>` | remove o ambiente e o vcluster; só o dono ou `platform-admins` |
| `--output json` | em todos os comandos |

| Status | Significado |
|---|---|
| `NoProviderForCapability` | nenhum provider assumiu o pedido |
| `Provisioning` | vcluster sendo criado |
| `ready` | vcluster no ar; `get` ou `--wait` gravam o kubeconfig |
| `ProvisioningFailed` | erro do provider; veja `message` no JSON |
| `deleting` | remoção em andamento |

| Porta | Uso |
|---|---|
| `6560` | Kubernetes API do `platform-local` |
| `127.0.0.1:9090` | Platform API |
| `localhost:8180` | Keycloak (issuer `http://localhost:8180/realms/platform`) |
| `127.0.0.1:7100`–`7119` | API de cada ambiente (vcluster), uma porta por ambiente |
