# Walkthrough

Roteiro para demonstrar a CLI `platform` partindo do zero: sem cluster, sem config e sem a CLI instalada. Rodado de ponta a ponta em 2026-10-10; os passos 8 a 11 foram refeitos com o provider `local_vcluster` (#183) no mesmo dia. O passo 14 (#190) foi rodado no `platform-local` no mesmo dia.

O guia de uso, com cada comando explicado, é a [página principal](index.md). Esta página é a sequência para apresentar ou para conferir que tudo continua funcionando.

## Preparação

Um terminal e um navegador logado na conta Google que vai entrar na plataforma. O provider de ambientes roda dentro do cluster.

| Etapa | Tempo |
|---|---|
| `platform init` do zero | ~4 min |
| Login (device code + Google) | ~1 min, manual |
| Ambiente pronto (vcluster) | ~30 s |
| Roteiro inteiro | ~10 min |

## 0. Partir do zero

!!! warning
    Apaga o control plane local, os ambientes e as credenciais. O usuário do Keycloak é recriado no primeiro login.

```bash
k3d cluster delete platform-local
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

## 8. Criar um ambiente

```bash
time platform environment create greetings-test --profile ephemeral --expires 1h --wait
```

```
provisioning greetings-test (profile: ephemeral) …
  NoProviderForCapability
  Provisioning
✓ greetings-test ready

real    0m32s
```

O pedido começa em `NoProviderForCapability` e o provider `local_vcluster`, que roda dentro do `platform-local`, o assume em seguida. Não há segundo terminal.

## 9. O provider por dentro

```bash
kubectl --context k3d-platform-local --namespace platform-system logs deploy/local-vcluster-provider --tail 3
kubectl --context k3d-platform-local get namespaces | grep env-
```

```
INFO creating vcluster env-greetings-test on port 7100
INFO environment greetings-test ready
env-greetings-test   Active   40s
```

## 10. Usar o ambiente

```bash
platform environment get greetings-test
kubectl --kubeconfig ~/.config/platform/environments/greetings-test.kubeconfig get nodes
kubectl --kubeconfig ~/.config/platform/environments/greetings-test.kubeconfig create deployment web --image nginx:alpine
```

## 11. Segundo ambiente, em paralelo

```bash
platform environment create demo --profile ephemeral --expires 1h --wait
platform environment get demo
platform environment list --output json
```

Cada ambiente ganha a próxima porta livre da faixa `7100`–`7119` (`demo` fica na `7101`).

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

## 13. Catálogo

```bash
platform catalog domain create communication --owner team-alpha
platform catalog domain create messaging --parent communication --owner team-alpha
platform catalog system create greeter --domain messaging --owner team-alpha
platform catalog resource create greeting-db --type database --system greeter --owner team-alpha
platform catalog list
platform catalog system get greeter
platform catalog domain delete messaging
kubectl --context k3d-platform-local --namespace platform-system get domains.catalog.platform.wasp.silvios.me
```

```
system/greeter
  domain       messaging
  owner        team-alpha
  description  —
  dependents   resource/greeting-db
✗ 409: domain 'messaging' has dependents: system/greeter
NAME            PARENT          OWNER
communication                   team-alpha
messaging       communication   team-alpha
```

Funciona com o Backstage parado: o catálogo é da plataforma. Para limpar, na ordem inversa:

```bash
platform catalog resource delete greeting-db
platform catalog system delete greeter
platform catalog domain delete messaging
platform catalog domain delete communication
```

## 14. Importar o catálogo do Backstage

O `idp/catalog/` é a carga inicial do catálogo (ADR 0023). O import mostra o plano, calculado pela Platform API, e só grava depois da confirmação.

```bash
platform catalog import idp/catalog/
```

```
KIND      NAME                  ACTION  DETAIL
Domain    bookstore             create
Domain    communication         create
Domain    platform              create
Domain    messaging             create  parent communication
Domain    notifications         create  parent communication
System    bookinfo              create  domain bookstore
System    greeter               create  domain messaging
System    notifier              create  domain notifications
System    platform              create  domain platform
Resource  development           create  system platform
Resource  greeting-avatars      create  system greeter
Resource  greeting-db           create  system greeter
Resource  greeting-events       create  system greeter
Resource  notification-db       create  system notifier
Resource  notification-jobs     create  system notifier
Resource  notification-reports  create  system notifier
Resource  production            create  system platform
—         —                     skip    not a Backstage entity (idp/catalog/communication/greeter/mkdocs.yml#1)
—         —                     skip    not a Backstage entity (idp/catalog/communication/mkdocs.yml#1)
Group     team-alpha            skip    identity lives in Keycloak (#186)
Group     team-beta             skip    identity lives in Keycloak (#186)
Group     team-platform         skip    identity lives in Keycloak (#186)

17 to create, 0 to update, 0 unchanged, 5 skipped.
Apply? [y/N]: y
✓ 17 created, 0 updated
```

Rodar de novo não grava nada:

```bash
platform catalog import idp/catalog/
```

```
KIND      NAME                  ACTION     DETAIL
Domain    bookstore             unchanged
...

0 to create, 0 to update, 17 unchanged, 5 skipped.
nothing to do
```

Uma referência quebrada aparece no plano com a entidade, o campo e o arquivo, e nada é aplicado:

```bash
printf 'apiVersion: backstage.io/v1alpha1\nkind: System\nmetadata:\n  name: orphan\nspec:\n  owner: team-alpha\n  domain: nowhere\n' > /tmp/orphan.yaml
platform catalog import /tmp/orphan.yaml
```

```
KIND    NAME    ACTION  DETAIL
System  orphan  error   spec.domain: domain 'nowhere' not found (/tmp/orphan.yaml#1)

0 to create, 0 to update, 0 unchanged, 0 skipped, 1 error.
✗ fix the errors above; nothing was applied
```

## 15. Times

Como admin, crie um time e entre nele (ADR 0026). O time chega ao token no próximo login.

```bash
platform team create team-alpha
platform team member add team-alpha voce@example.com
platform team get team-alpha
platform login
platform whoami
```

```
✓ team team-alpha created
✓ voce@example.com added to team-alpha
team-alpha: 1 member(s)
EMAIL             USERNAME
voce@example.com  voce@example.com
voce@example.com (platform-admins, platform-users, team-alpha)
```

Para limpar:

```bash
platform team delete team-alpha
```

## 16. Limpar e sair

```bash
platform environment delete demo
platform environment delete greetings-test
kubectl --context k3d-platform-local get namespaces | grep env- || echo "no environments"
platform logout
platform whoami
```

```
✓ Logged out
✗ not logged in: run 'platform login'
```

O `platform-local` continua no ar para a próxima rodada; para desmontar tudo, volte ao passo 0.

## Sem navegador: `scripts/demo/cli-smoke`

O roteiro acima tem um passo humano, o login. O `scripts/demo/cli-smoke` (#179) roda o fluxo sem ninguém: `init`, login com o usuário de teste (`platform-users`), a recusa `403` ao criar um domínio, um ambiente criado com `--wait` e apagado, login com o admin de teste, `catalog import idp/catalog/` (aplicado e depois `nothing to do`) e `logout`. Ele para na primeira falha, com código diferente de zero.

```bash
scripts/demo/cli-smoke              # do zero, com platform init
scripts/demo/cli-smoke --skip-init  # reaproveita o platform-local que já está no ar
```

Os usuários `platform-smoke` e `platform-smoke-admin` e o client `platform-smoke` existem só no target local. A justificativa do password grant está em `platform/keycloak/README.md`.

## Ideias para tornar o roteiro repetível

- **Script `scripts/demo/cli-walkthrough` (#178):** roda os passos em sequência, pausa antes de cada um (Enter para seguir) e para no login esperando o device code. Serve para apresentar e para conferir antes de um merge.
- **Medir (#180):** guardar o tempo de cada etapa (como na tabela acima) para perceber quando o `init` ou o provider ficam mais lentos.
- **Gravar (#181):** `asciinema rec` durante o roteiro gera um vídeo de terminal leve para o README e para o deck.
- **Evoluir junto com a CLI (#182):** cada comando novo (`release create`, `catalog component create`) entra aqui como um passo, com a saída esperada.
