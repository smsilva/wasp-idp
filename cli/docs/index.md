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

Para testes sem ninguém (`scripts/demo/cli-smoke`), o target local tem dois usuários de teste: `platform login --test-user` (`platform-users`) e `--test-admin` (`platform-admins`). As opções ficam fora do `--help` e recusam outro target; o motivo e o que o `init` cria estão em `platform/keycloak/README.md`.

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
NAME            PROFILE    STATUS  EXPIRES  OWNER             SHARED
greetings-test  ephemeral  ready   59m      voce@example.com  —
```

A lista mostra os seus ambientes e os compartilhados com os seus times (seção 12). `--all` mostra todos, sem kubeconfig; para `platform-admins`, o padrão já é todos.

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

## 11. Catálogo

Domínios, sistemas e recursos que a plataforma guarda. Domínio só `platform-admins` cria; sistema e recurso, qualquer usuário. O `--owner` é um time que já existe (seção 12): `platform team create team-alpha`, ou o import de um `Group`.

```bash
platform catalog domain create communication --owner team-alpha
platform catalog domain create messaging --parent communication --owner team-alpha
platform catalog system create greeter --domain messaging --owner team-alpha
platform catalog resource create greeting-db \
  --type database \
  --system greeter \
  --owner team-alpha
platform catalog list
```

```
KIND      NAME           PARENT         OWNER
Domain    communication  —              team-alpha
Domain    messaging      communication  team-alpha
System    greeter        messaging      team-alpha
Resource  greeting-db    greeter        team-alpha
```

Apagar é na ordem inversa: com dependentes, a API recusa e diz quais são.

```bash
platform catalog domain delete messaging
```

```
✗ 409: domain 'messaging' has dependents: system/greeter
```

O `--type` do recurso é o papel (`database`, `topic`, `queue`, `bucket`), nunca o serviço de nuvem. Componentes e APIs ainda não estão no catálogo da plataforma.

### Importar do Backstage

Quem já tem um catálogo no formato Backstage importa os arquivos de uma vez. A Platform API calcula o plano; nada é gravado antes da confirmação.

```bash
platform catalog import idp/catalog/            # arquivo ou pasta (recursivo: *.yaml, *.yml)
platform catalog import idp/catalog/ --dry-run  # só o plano
platform catalog import idp/catalog/ --yes      # sem perguntar (pipeline)
```

| Ação | Significado |
|---|---|
| `create` | não existe na plataforma |
| `update` | existe e muda; o detalhe mostra `campo: antes → depois` |
| `unchanged` | existe igual |
| `skip` | não é importado: Component e API moram no repo e chegam pelo discovery (#205), User fica no Keycloak; arquivos dentro do conteúdo de um template (`part of template <nome>`); os `steps` de um template do Backstage |
| `forbidden` | sem permissão: domínio só `platform-admins`; sistema e recurso só quem criou |
| `error` | campo faltando ou referência quebrada; o detalhe diz o campo e o arquivo |

Um `Group` vira time (só `platform-admins` criam; membros não são importados) e entra no plano antes das outras entidades. O `spec.owner` de cada entidade escrita precisa ser um time que existe ou um `Group` do mesmo import. Com `forbidden` ou `error` nada é aplicado. O import nunca apaga: o que existe na plataforma e não está nos arquivos fica como está. Um campo ausente no arquivo (a `description`, por exemplo) é removido da entidade. Se o catálogo mudar entre o plano e a confirmação, a API recusa e a CLI mostra o plano novo.

Templates do Backstage (`kind: Template`) também entram pelo `catalog import`, desde que venham `--repo` e `--ref`: o arquivo local não sabe onde está publicado. Sem eles, o template vira `error` e o resto do plano segue.

### Templates

Um template é o golden path de um tipo de component (`service`, `website`, `library`; ADR 0024). O conteúdo fica no Git, e a plataforma guarda repo, caminho e ref. O `platform init` registra `platform/templates/*` no último commit do checkout que existe no GitHub.

```bash
platform catalog template list
platform catalog template get python-service
platform catalog template render python-service --name demo --output ./demo [--param port=9000]
platform catalog template render --from platform/templates/python-service --name demo --output ./demo
```

O `render` roda localmente: busca o conteúdo no ref registrado (ou lê `--from`), renderiza com os delimitadores do Backstage (`${{ values.x }}`, filtro `dump`), copia como estão os arquivos de `copyWithoutRendering` e grava a origem em `catalog-info.yaml` (`platform.wasp.silvios.me/template: <nome>@<ref>`). Os valores padrão são `name`, `owner`, `system` e `description`; o template declara os extras, passados com `--param`.

Só `platform-admins` alteram o registro:

```bash
platform catalog template create my-api --type service --owner team-platform \
  --repo https://github.com/wasp-foundry/templates --path my-api --ref v1.0.0 [--default]
platform catalog template default my-api
platform catalog template import idp/templates/python-service --repo https://github.com/smsilva/wasp-idp --ref main
platform catalog template delete my-api
```

- Um padrão por tipo: `default` desmarca o anterior. Apagar o padrão enquanto houver outros do mesmo tipo é `409`.
- `import` aceita arquivo ou pasta e lê só definições de template: `kind: Template` do Backstage ou `template.yaml` no formato da plataforma. Os `steps` do scaffolder aparecem no plano como `skip`, com o motivo, e reimportar mantém quem é o padrão.
- O `--owner` é um time que já existe, como nas outras entidades do catálogo. O template do Backstage em `idp/templates/python-service` tem `owner: group:default/guests`: importe-o pelo `platform catalog import` junto com o `Group` `guests`, ou crie o time antes.

## 12. Times

Um time é um grupo do Keycloak que a Platform API mantém (ADR 0026). É ele que compartilha ambientes e é dono de entidades do catálogo. Qualquer usuário lista e vê os times; criar, apagar e mudar membros é só para `platform-admins`.

```bash
platform team create team-alpha
platform team member add team-alpha voce@example.com
platform team get team-alpha
```

```
✓ team team-alpha created
✓ voce@example.com added to team-alpha
team-alpha: 1 member(s)
EMAIL             USERNAME
voce@example.com  voce@example.com
```

Um time em uso, dono de entidades do catálogo ou com ambientes compartilhados, não é apagado (`409`). O membro precisa ter entrado na plataforma uma vez, com o e-mail verificado: antes disso, o Keycloak não o conhece e a API responde `404`. O time chega ao token no próximo `platform login`, e o `platform whoami` passa a mostrá-lo junto dos grupos.

### Compartilhar um ambiente

Um ambiente nasce privado. Quem o criou pode compartilhá-lo com os times de que faz parte; com outros times, só `platform-admins`.

```bash
platform environment create review --profile ephemeral --share-with team-alpha --wait
platform environment share greetings-test --team team-alpha
platform environment unshare greetings-test --team team-alpha
```

```
✓ review ready
✓ greetings-test shared with team-alpha
✓ greetings-test no longer shared with team-alpha
```

Os membros do time veem o ambiente no `environment list` e recebem o kubeconfig no `environment get`. Apagar, compartilhar e descompartilhar continuam com o dono e os admins.

Todos recebem o mesmo kubeconfig de administrador do vcluster. Tirar alguém do time, ou descompartilhar, corta o acesso pela API, mas quem já baixou o kubeconfig continua com ele até o ambiente ser recriado. A identidade por pessoa no vcluster é a #233.

## 13. Desmontar tudo

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
| `platform environment create <nome> --profile ephemeral\|shared [--expires 3d] [--share-with <time>]... [--wait]` | pede um ambiente, privado se não compartilhado |
| `platform environment list [--all]` | NAME, PROFILE, STATUS, EXPIRES, OWNER, SHARED; os seus e os dos seus times, ou todos |
| `platform environment share\|unshare <nome> --team <time>` | compartilha ou deixa de compartilhar; só o dono ou `platform-admins` |
| `platform environment get <nome>` | status e mensagem; grava o kubeconfig quando pronto |
| `platform environment delete <nome>` | remove o ambiente e o vcluster; só o dono ou `platform-admins` |
| `platform catalog domain create <nome> --owner <time> [--parent <domínio>]` | cria um domínio ou subdomínio (só `platform-admins`) |
| `platform catalog system create <nome> --domain <domínio> --owner <time>` | cria um sistema |
| `platform catalog resource create <nome> --type <papel> --system <sistema> --owner <time>` | cria um recurso compartilhado |
| `platform catalog list [--kind domain\|system\|resource] [--owner <time>]` | KIND, NAME, PARENT, OWNER |
| `platform catalog <kind> list\|get\|delete` | por kind; `get` mostra os dependentes |
| `platform catalog import <caminho>... [--repo <url> --ref <ref>] [--dry-run] [--yes]` | importa Domain, System, Resource e Template de arquivos Backstage, depois de revisar o plano |
| `platform team list\|get <time>` | times e membros |
| `platform team create\|delete <time>` | cria ou apaga um time (só `platform-admins`) |
| `platform team member add\|remove <time> <email>` | muda membros (só `platform-admins`); vale no próximo `platform login` |
| `platform catalog template list\|get <nome>` | NAME, TYPE, REF, DEFAULT, SOURCE; `get` mostra os parâmetros |
| `platform catalog template create <nome> --type <tipo> --owner <time> --repo <url> --path <pasta> --ref <ref> [--default]` | registra um template (só `platform-admins`) |
| `platform catalog template import <caminho> --repo <url> --ref <ref> [--dry-run] [--yes]` | importa templates do Backstage ou do formato da plataforma |
| `platform catalog template default\|delete <nome>` | muda o padrão do tipo; apaga (só `platform-admins`) |
| `platform catalog template render [<nome>\|--from <pasta>] --name <component> --output <pasta> [--param k=v]` | renderiza localmente |
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
