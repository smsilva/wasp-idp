# Walkthrough

Roteiro para demonstrar a CLI `platform` partindo do zero: sem cluster, sem config e sem a CLI instalada. Rodado de ponta a ponta em 2026-10-10. Os tempos abaixo vêm dessa execução.

O guia de uso, com cada comando explicado, é a [página principal](index.md). Esta página é a sequência para apresentar ou para conferir que tudo continua funcionando.

## Preparação

Duas janelas de terminal (ou dois painéis do tmux): a de cima para os comandos, a de baixo para o provider. Um navegador logado na conta Google que vai entrar na plataforma.

| Etapa | Tempo |
|---|---|
| `platform init` do zero | ~3 min |
| Login (device code + Google) | ~1 min, manual |
| Ambiente pronto com o provider rodando | ~15 s |
| Roteiro inteiro | ~10 min |

## 0. Partir do zero

!!! warning
    Apaga o control plane local, os ambientes e as credenciais. O usuário do Keycloak é recriado no primeiro login.

```bash
k3d cluster list --no-headers | awk '/^(platform-local|env-)/ {print $1}' | xargs --no-run-if-empty k3d cluster delete
rm -rf ~/.config/platform
uv tool uninstall wasp-platform
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
uv tool install --editable cli/
platform --help
```

## 3. Credenciais do Google

O OAuth client do Google é configurado uma vez (veja `platform/keycloak/README.md`). Mostre só o prefixo:

```bash
export GOOGLE_CLIENT_ID=<id>.apps.googleusercontent.com
export GOOGLE_CLIENT_SECRET=<secret>
echo "${GOOGLE_CLIENT_ID:0:12}… ${GOOGLE_CLIENT_SECRET:0:3}…"
```

## 4. Subir o control plane

```bash
time platform init --target local --admin voce@example.com
cat ~/.config/platform/config.yaml
```

```
creating cluster platform-local …
applying CRDs …
deploying Keycloak …
waiting for Keycloak …
applying the realm platform …
building the Platform API image …
deploying the Platform API …
✓ Platform API at http://127.0.0.1:9090 · config in ~/.config/platform/config.yaml
✓ Keycloak issuer http://localhost:8180/realms/platform

real    2m56s
```

## 5. Sem login, a API recusa

```bash
platform environment list
```

```
✗ not logged in: run 'platform login'
```

## 6. Entrar

```bash
platform login --use-device-code
```

Abra a URL impressa no navegador e passe pelas telas: confirmar o código, entrar com Google, revisar o perfil (só no primeiro login) e autorizar o terminal. O terminal termina em `✓ Logged in as voce@example.com (platform-admins, platform-users)`.

!!! tip
    `platform login` sem flag abre o navegador padrão sozinho. Use o device code quando o navegador padrão estiver em outra conta Google, ou numa apresentação, para mostrar as telas do Keycloak.

## 7. Quem sou eu

```bash
platform whoami
platform whoami --output json
```

O `sub` é o ID imutável do usuário no Keycloak; é ele que vai para a trilha de auditoria.

## 8. Pedido sem provider

```bash
platform environment create greetings-test --profile ephemeral --expires 3d
platform environment list
```

```
NAME            PROFILE    STATUS                   EXPIRES
greetings-test  ephemeral  NoProviderForCapability  2d 23h
```

O pedido foi aceito e gravado como CRD, mas ninguém o atende ainda.

## 9. Subir o provider

No segundo terminal:

```bash
platform provider run --target local
```

```
INFO watching environments in k3d-platform-local/platform-system
INFO creating cluster env-greetings-test
INFO environment greetings-test ready
```

## 10. Usar o ambiente

```bash
platform environment list
kubectl --kubeconfig ~/.config/platform/environments/greetings-test.kubeconfig get nodes
```

## 11. Criar esperando ficar pronto

```bash
time platform environment create demo --profile ephemeral --expires 1h --wait
platform environment list --output json
```

```
provisioning demo (profile: ephemeral) …
  pending
  Provisioning
✓ demo ready

real    0m16s
```

## 12. Trilha de auditoria

```bash
kubectl --context k3d-platform-local --namespace platform-system \
  exec deploy/platform-api -- cat /var/lib/platform/journal.jsonl \
  | jq --compact-output 'select(.action) | {at, actor, action, name}'
```

```json
{"at":"2026-10-10T20:37:30+00:00","actor":"2016b176-… (voce@example.com)","action":"create","name":"greetings-test"}
{"at":"2026-10-10T20:38:45+00:00","actor":"2016b176-… (voce@example.com)","action":"create","name":"demo"}
```

## 13. Limpar e sair

Com o provider ainda rodando (é ele que apaga os clusters `env-*`):

```bash
platform environment delete demo
platform environment delete greetings-test
k3d cluster list
platform logout
platform whoami
```

```
✓ Logged out
✗ not logged in: run 'platform login'
```

Pare o provider com `Ctrl+C`. O `platform-local` continua no ar para a próxima rodada; para desmontar tudo, volte ao passo 0.

## Ideias para tornar o roteiro repetível

- **Script `scripts/demo/cli-walkthrough` (#178):** roda os passos em sequência, pausa antes de cada um (Enter para seguir) e para no login esperando o device code. Serve para apresentar e para conferir antes de um merge.
- **Teste de fumaça sem humano (#179):** o login é o único passo manual. Um usuário local de teste no realm (só no target local, criado pelo `init` com senha aleatória num Secret) e o grant de senha desligado para todos os outros clients permitiriam um `platform login --test-user` e, com ele, rodar o roteiro inteiro em CI.
- **Medir (#180):** guardar o tempo de cada etapa (como na tabela acima) para perceber quando o `init` ou o provider ficam mais lentos.
- **Gravar (#181):** `asciinema rec` durante o roteiro gera um vídeo de terminal leve para o README e para o deck.
- **Evoluir junto com a CLI (#182):** cada comando novo (`release create`, `app create`) entra aqui como um passo, com a saída esperada.
