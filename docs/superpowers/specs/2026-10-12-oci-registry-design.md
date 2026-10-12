# OCI Registry — Design

Issue [#364](https://github.com/smsilva/wasp-idp/issues/364), fatias [#365](https://github.com/smsilva/wasp-idp/issues/365) a [#369](https://github.com/smsilva/wasp-idp/issues/369). A decisão vai para o ADR 0037, na fatia 1. Conversa de design de 2026-10-12.

## Problema

O registry é implícito na plataforma:

- **O template fixa o destino da imagem.** O `platform-build.yaml` do `python-service` calcula `image=ghcr.io/${GITHUB_REPOSITORY,,}` e faz login no `ghcr.io` com o `GITHUB_TOKEN` do run.
- **O build confere pouco.** O `check_result` (`platform/providers/scm_github/src/scm_github_provider/build.py`) confere só que `image` existe e que o `digest` é `sha256:<hex>`.
- **O deploy supõe pull anônimo.** O `Version` guarda `image` e `digest`, e o provider `workload` renderiza `image@digest` sem `imagePullSecret`. O reference exige uma imagem "pullable by the vcluster without credentials".
- **Não há dono.** O ADR 0034 cita "Registry" só como plane do subsistema `build`, sem objeto.

O registry é onde o build (push) e o deploy (pull) se encontram, e por isso faz parte da jornada do dev. Hoje ele não aparece nela, não há como usar outro registry além do GHCR da org do repo, e um pacote privado não tem como chegar ao vcluster (#325).

## Objetivos

1. **Visibilidade:** o dev vê para onde a imagem foi (`build create`, `build list`, `build get`), e o admin cadastra os registries da plataforma.
2. **Neutralidade de vendor:** o build recebe o destino da plataforma, e o template não fixa o GHCR.
3. **Pull de vários registries por environment**, com um registry padrão da plataforma assumido quando nada é dito.
4. **Credenciais de pull emitidas pela plataforma, uma por environment**, onde o registry permitir.

Fora do escopo: governança de imagens (recusar imagens de registries não cadastrados), retenção (#362) e aprovações (#363).

## Decisões

### Nome: `OCIRegistry`

O OCI Distribution Spec não é só de imagens. O mesmo registry guarda Helm charts (`oci://`, como o `/helm` do ACR), pacotes do Crossplane (`xpkg`), assinaturas e SBOMs. "Container registry" é nome de produto: GHCR, ACR e ECR guardam artefatos OCI. O CRD é `OCIRegistry` (como o `OCIRepository` do Flux), a CLI é `platform registry`, e a doc diz "OCI registry: images, Helm charts, Crossplane packages". O registry não sabe o tipo de artefato: quem diz o que foi publicado é o `Version`.

Alternativas: `ContainerRegistry`, que prende ao tipo imagem, e `ArtifactRegistry`, que é o nome do produto do Google e sugere formatos que não são OCI (npm, maven).

### Subsistema próprio: `registry`

Ele entra no mapa do ADR 0034 como `optional`, com `depends_on: identity`. O `build` passa a depender de `registry` (push), e o `workload` também (pull).

- **Alternativa: o registry dentro do `build`.** Rejeitada: o pull é do `workload`/`environment`, que teria de ler credenciais de dentro do `build` (regra 2 do ADR 0034), e imagens que não vêm de build ficariam sem dono.
- **Alternativa: o registry como `Resource` do catálogo/Forager.** Rejeitada: um `Resource` é por ambiente e por app (ADR 0023/0031), e o registry é infraestrutura da plataforma, compartilhada entre ambientes e builds.

### O registry é escolhido no build, não no component

O component é lógico ("o `hello-api`"). Amarrá-lo a um registry mistura essa ideia com um serviço real. O build é o momento físico: roda num CI e produz um artefato num lugar. As versões de um mesmo component podem ficar em registries diferentes, e o deploy lê o registry do `Version`.

## Modelo

```yaml
apiVersion: platform.wasp.silvios.me/v1alpha1
kind: OCIRegistry
metadata:
  name: ghcr-wasp-foundry
  namespace: platform-system
spec:
  vendor: ghcr             # ghcr | harbor | ecr | acr | gar | generic
  host: ghcr.io
  namespace: wasp-foundry  # org (GHCR), project (Harbor), repository prefix (ECR)
  default: true            # at most one: what build create uses without --registry
  pull:
    mode: anonymous        # anonymous | issued | static
status:
  conditions: [Ready]      # Verified | Unreachable | CredentialRejected
```

```yaml
apiVersion: platform.wasp.silvios.me/v1alpha1
kind: RegistryBinding
metadata:
  name: harbor-lab.demo
  namespace: platform-system
spec:
  registry: harbor-lab
  target: {kind: Environment, name: demo}   # Platform for the default; Profile later
```

O `Version` ganha `spec.registry: <nome>`. A `image` continua sendo o endereço completo (`ghcr.io/wasp-foundry/hello-api`), com o `digest`.

## Push

`build create --component hello-api --branch feat/greetings [--registry <nome>]`. Sem `--registry`, vale o registry `default`. Se não houver default, o build é recusado com `NoDefaultRegistry`.

- **O dispatch ganha o input `image`** = `<host>/<namespace>/<component>`, e o workflow faz push ali:

  ```json
  {"ref": "feat/greetings", "inputs": {"request-id": "b-7f3c2a", "version": "", "image": "ghcr.io/wasp-foundry/hello-api"}}
  ```

- **O resultado é conferido:** o `check_result` exige que o `image` do `platform-build.json` seja o pedido. Se não for, o build termina com `ContractViolation`.
- **O `Version` grava o registry**, e a saída o mostra:

  ```
  ✓ image hello-api:0.1.0-greetings.86a7c08 pushed to ghcr-wasp-foundry (ghcr.io/wasp-foundry/hello-api)
  ```

  `build list` ganha a coluna `REGISTRY`, e `build get` ganha a linha `registry`.
- **Repos com o workflow antigo:** o GitHub recusa o dispatch com `422 Unexpected inputs`, e a plataforma responde `WorkflowOutdated`, com a mensagem de atualizar o `platform-build.yaml` a partir do template. O input é sempre enviado, para que o contrato tenha uma forma só.

O CI continua sem credencial da plataforma. Cada vendor autentica o push com a credencial nativa do CI:

| Vendor | Push | Fatia |
|---|---|---|
| `ghcr` | `GITHUB_TOKEN` do run, que só escreve na org dona do repo: um `namespace` diferente é recusado antes do dispatch (`RegistryNotWritableByCI`) | 1 |
| `harbor` / `generic` | robot de push gravado pela plataforma como secret do Actions no repo (permissão `secrets: write` no App) | 3 |
| `ecr` / `acr` / `gar` | OIDC do GitHub Actions para uma identidade da CloudAccount (#254) | 5 |

## Pull

### Bindings

Um environment baixa do registry padrão (binding `Platform`) e dos registries ligados a ele. O binding pode ser criado dos dois lados, e os dois comandos escrevem o mesmo objeto:

```bash
platform environment create demo --registry harbor-lab --registry ghcr-acme

platform environment registry add demo --registry harbor-lab --registry ghcr-acme

platform registry enable harbor-lab --environment demo --environment smoke-env
```

Mais `environment registry remove` e `registry disable`. Apagar um environment apaga os bindings dele.

O deploy confere o binding antes de gravar a revisão:

```
✗ version 0.2.0 of hello-api is in harbor-lab, which environment smoke-env does not pull from (RegistryNotEnabled)
  enable it with: platform environment registry add smoke-env --registry harbor-lab
              or: platform registry enable harbor-lab --environment smoke-env
```

Imagens declaradas direto no Score (por exemplo `postgres:17-alpine`), e não vindas de um build, continuam com pull anônimo de host público.

**Norte:** o alvo do binding ganha `Profile` (depois da #329), e a lista de um environment passa a ser resolvida em camadas: environment → profile → plataforma, como a binding policy do Forager.

### Credenciais

O alvo é **uma credencial por environment, emitida pela plataforma**. Se um ambiente for comprometido, revoga-se só a dele (o mesmo raciocínio das ServiceAccounts por pessoa do ADR 0028).

| `pull.mode` | O que a plataforma faz | Onde |
|---|---|---|
| `anonymous` | nada: não há segredo | GHCR público, Docker Hub público |
| `issued` | emite uma credencial por binding, renova antes de expirar e revoga no unbind, no delete do environment ou em `registry credential revoke` | Harbor (robot por API, com expiração), ACR (token com scope map), ECR/GAR (identidade por ambiente, #254); GHCR depende do spike da #368 |
| `static` | distribui uma credencial que o admin cadastrou | registries sem API de emissão |

- **O que fica no `SecretStore`:** só a credencial que *emite* (o robot de sistema do Harbor, por exemplo). Ela é write-only na API e só o controller `registry` a lê (regra da `ScmConnection`, ADR 0025).
- **Acesso, derivado do modo:** `anonymous` e `issued` são `open` (o dono do environment habilita). `static` é `restricted` (só `platform-admins` habilitam, e quem não é admin recebe a recusa sem sugestão de comando; o pedido de aprovação é a #363).
- **Entrega no vcluster, sem passar pelo `workload`:**
  1. O `local_vcluster` instala o vcluster com um mapeamento `sync.fromHost.secrets` de `env-<name>-registries/*` para `apps/*`. É o mesmo padrão do `replicateServices.fromHost` que já usa. Que o chart `0.37.2` aceita esse mapeamento é o spike da #367.
  2. O controller `registry` escreve o `Secret` `kubernetes.io/dockerconfigjson` `registry-<nome>` nesse namespace, um por binding com credencial.
  3. O provider `workload` só acrescenta `imagePullSecrets` ao Deployment. Ele nunca lê o segredo.
- **Environments antigos** não têm o mapeamento: um deploy com credencial neles termina com `RegistryNotSynced`.
- **Falha de pull:** `ErrImagePull`/`ImagePullBackOff` encerra a revisão logo com `ImagePullFailed`, nomeando o registry.

Alternativa rejeitada: o provider `workload` copiar o `Secret` a cada deploy. Ele já alcança o vcluster, mas passaria a ler credenciais de outro subsistema.

## Superfície

| Rota | Quem |
|---|---|
| `GET /v1/registries`, `GET /v1/registries/{name}` | qualquer autenticado |
| `POST /v1/registries`, `DELETE /v1/registries/{name}`, `PUT /v1/registries/{name}/default` | `platform-admins` |
| `PUT /v1/registries/{name}/credential` (write-only, redigida no journal) | `platform-admins` |
| `POST`/`DELETE /v1/registries/{name}/environments` `{environments: [...]}` | admin, ou o dono do environment num registry `open` |
| `GET`/`POST`/`DELETE /v1/environments/{name}/registries` `{registries: [...]}` | idem |
| `POST /v1/builds` aceita `registry` | o dono do component, como hoje |

```
platform registry add|list|get|remove <name>
platform registry set-default <name>
platform registry credential set|revoke <name> [--environment <env>]
platform registry enable|disable <name> --environment <env>...
platform environment registry list|add|remove <env> [--registry <name>...]
platform environment create <env> [--registry <name>...]
platform build create ... [--registry <name>]
```

## Fatias

| # | Issue | Entrega | Jornada local |
|---|---|---|---|
| 1 | #365 | ADR 0037, `OCIRegistry` (`ghcr`, `anonymous`, `default`), controller `registry` mínimo, `build create --registry`, input `image`, `Version.spec.registry`, `REGISTRY` | sim, antes da #360 |
| 2 | #366 | `RegistryBinding`, os comandos dos dois lados, `RegistryNotEnabled` | não |
| 3 | #367 | credenciais `issued` e `static`, `Secret` via `sync.fromHost`, `ImagePullFailed`; Harbor primeiro | não |
| 4 | #368 | GHCR privado (absorve a #325) | não |
| 5 | #369 | ECR, ACR e GAR pela CloudAccount (#254) | não |

## Exemplo no contexto do repo

```bash
platform registry add ghcr-wasp-foundry \
  --vendor ghcr \
  --host ghcr.io \
  --namespace wasp-foundry \
  --default

platform build create \
  --component hello-api \
  --branch feat/greetings \
  --wait

platform build list \
  --component hello-api
```

```
✓ registry ghcr-wasp-foundry added (default)
building from feat/greetings @ 86a7c08 …
✓ app-spec.yaml valid · db (postgres), dns, route
✓ image hello-api:0.1.0-greetings.86a7c08 pushed to ghcr-wasp-foundry (ghcr.io/wasp-foundry/hello-api)
VERSION                  BRANCH          REGISTRY           CREATED
0.1.0-greetings.86a7c08  feat/greetings  ghcr-wasp-foundry  2026-10-12T14:02:11Z
```

```
$ platform build create --component hello-api --branch feat/greetings --registry ghcr-smsilva
✗ registry ghcr-smsilva (ghcr.io/smsilva) is not writable by the CI of wasp-foundry/hello-api: GITHUB_TOKEN pushes only to ghcr.io/wasp-foundry (RegistryNotWritableByCI)

$ platform build create --component greeting-api --branch main
✗ greeting-api: WorkflowOutdated: .github/workflows/platform-build.yaml has no input 'image' (GitHub: Unexpected inputs provided): update it from the template python-service
```
