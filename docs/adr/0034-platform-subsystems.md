# Platform subsystems: capabilities with their own boundary, modular monolith in the API, independent controllers

**Status:** Proposto (2026-10-12)

## Contexto

A plataforma cresceu por fatias (#141 a #307): cada capability nova trouxe rotas na Platform API, CRDs e, quase sempre, um controller. O resultado já lembra o OpenStack, em que cada projeto (Keystone, Nova, Neutron, Heat) entrega uma capability, tem sua API e seus drivers, pode ser instalado à parte e depende de outros de forma explícita. Mas essa forma nunca foi declarada, e os limites começam a vazar.

O que existe hoje:

| Subsistema (de fato) | Módulos da API (`platform/api/src/platform_api/`) | CRDs | Controller |
|---|---|---|---|
| identity | `auth`, `teams`, `credentials` | — (Keycloak) | Keycloak |
| catalog | `catalog`, `catalog_import`, `templates`, `components` | `Domain`, `System`, `Resource`, `Template`, `Component` | — (a API escreve) |
| scm | `scm` | `ScmConnection`, `ComponentCreation` | `scm_github` |
| build | `builds`, `workload_specs` | `Build`, `Version` | `scm_github` |
| environment | `environments` | `Environment` | `local_vcluster` |
| cloud-account | `cloud_accounts` | `CloudAccount` | `aws_account` |
| resources | `binding_policies` | `ResourceRequest`, `BindingPolicy` | `forager` |
| workload | `workloads` | `WorkloadRevision`, `WorkloadInstance` | `workload` |

O que não pertence a nenhum deles e todos usam: `state` (o `StateWriter` do ADR 0022), `journal`, `secrets` (o `SecretStore` do ADR 0025), `durations` e a montagem em `app.py`.

Os controllers já se comportam como serviços independentes: cada um é um projeto `uv` e um Deployment próprios, e a dependência entre eles é a leitura de um CRD de outro (o `forager` lê `Version`, `Environment` e `WorkloadRevision`; o `workload` lê `ResourceRequest`). Na API, os limites vazam:

- **A autorização mora em `environments.py`.** `ADMIN_GROUP`, `can_use` e `is_owner_or_admin` são importados de lá por 11 módulos, inclusive os de catálogo, SCM, build, workload e cloud account. A regra de quem pode o quê é de identity, mas mora em environment.
- **Módulos importam detalhes internos uns dos outros**: `components` importa de `catalog`, `scm`, `templates`, `workloads` e `teams`; `builds` e `workloads` importam constantes de `catalog` e `scm`. Nada impede um import novo, e o grafo só cresce.
- **As capabilities são fixas no código** (`CAPABILITIES` em `app.py`): só `cloud-account` é calculada. `build` aparece como `NoProviderForCapability` embora o `scm_github` a entregue desde a #287.
- **`platform init` instala tudo**: não há subsistema opcional, nem como saber o que está instalado (#269).
- **Um controller serve dois subsistemas**: o `scm_github` faz a connection, a criação de component e o build, porque hoje só existe o GitHub.

O deck ("Putting it together") desenha a mesma divisão em planes: Developer Control Plane, Integration & Delivery, Resource, Observability e Security. Os subsistemas acima são a forma concreta desses planes.

## Decisão

**A plataforma é um conjunto de subsistemas, cada um uma capability com limite próprio. A Platform API continua um processo só, organizado como monolito modular. Os controllers continuam deployables independentes.**

### 1. O que é um subsistema

Um subsistema entrega uma capability e declara:

- **nome**, que é também o nome da capability em `GET /v1/capabilities`;
- **nível**: `core` (sempre instalado) ou `optional`;
- **módulos da API** de que é dono, e só ele escreve neles;
- **CRDs** de que é dono, e só ele (API ou controller) escreve neles;
- **controllers ou drivers** que o implementam;
- **dependências** (`depends_on`) de outros subsistemas.

O mapa inicial:

| Subsistema | Nível | `depends_on` | Plane no deck |
|---|---|---|---|
| identity | core | — | Security · Identity |
| catalog | core | identity | Developer · Software Catalog, Golden Paths |
| environment | core | identity | Resource · Compute |
| scm | optional | identity, catalog | Integration · Version Control |
| build | optional | scm, catalog | Integration · CI, Registry |
| cloud-account | optional | identity | Resource |
| resources | optional | environment, build, catalog | Resource · Data, Networking |
| workload | optional | environment, build, resources | Integration · Orchestrator, Delivery |

Ficam previstos, ainda sem código: `observability` (#330, #326) e `usage` (#332, #333).

Um fluxo que atravessa subsistemas pertence a quem o inicia e depende dos outros por interface. Exemplo: `component create` é de catalog. Ele usa o scm para criar o repo, e responde `NotConfigured` se o scm não estiver instalado ou sem connection `ready`.

### 2. Como os subsistemas dependem uns dos outros

- **Entre controllers**: lendo os CRDs do outro, nunca escrevendo neles (já é a prática, e vira regra).
- **Na API**: só pela interface publicada do outro subsistema (um módulo `api` por subsistema, ou funções marcadas como públicas). Constantes, modelos e helpers internos não são importados por outro subsistema.
- **O núcleo comum** (`state`, `journal`, `secrets`, `durations`, a autenticação do token) não é subsistema, e qualquer um o usa.
- **Uma dependência só aponta para o mesmo nível ou para `core`.** Um subsistema `core` não depende de `optional`.
- As regras acima são verificadas por teste (contratos de import, por exemplo `import-linter`), como fitness function (#331). Um import novo que fure o grafo quebra o build.

### 3. A autorização é de identity

`ADMIN_GROUP`, `can_use`, `is_owner_or_admin` e a leitura de `group_paths` passam para um módulo de identity. Cada subsistema decide suas regras de acesso, mas com os predicados de identity. `environments.py` fica só com o que é de ambiente (`can_use` de um ambiente continua lá, como regra do subsistema, usando os predicados).

### 4. A capability é calculada, não declarada

Cada controller publica que está vivo e o que atende, no padrão que o `aws_account` já usa (um ConfigMap atualizado por ele). `GET /v1/capabilities` passa a ser calculado: `Active`, `NotConfigured`, `Degraded`, `Unreachable` ou `NoProviderForCapability` (#269). As rotas de um subsistema `optional` ausente respondem `503` com o código `NoProviderForCapability`, nunca `500`.

### 5. Drivers dentro do subsistema

Um subsistema pode ter mais de um driver, escolhido pelo campo de vendor dos CRDs, que já são neutros (`ScmConnection`, ADR 0025; `CloudAccount`, ADR 0029). O `scm_github` continua hospedando os drivers GitHub de `scm` e `build` até aparecer um segundo vendor de CI. Nesse dia, o build vira um driver próprio. O mesmo vale para `environment` (o `local_vcluster` hoje e, com o ADR 0032 e a #254, um provider em nuvem).

### 6. O que fica como está

- **Um processo para a API.** Separar a API por subsistema traria o custo operacional do OpenStack (um deploy, um banco e um upgrade coordenado por serviço) sem ganho para um time pequeno. A separação física passa a ser possível, não planejada.
- **Um grupo de CRD** (`platform.wasp.silvios.me`), além do `catalog.…`. Trocar o grupo é uma mudança incompatível para todos os CRDs, e o dono de cada CRD já fica no mapa.

## Alternativas consideradas

- **Um serviço por subsistema, com API e banco próprios (modelo OpenStack).** Isolamento e deploy independente de verdade, mas multiplica a operação, os upgrades coordenados e a autenticação entre serviços. Rejeitada agora. Volta a ser considerada se um subsistema precisar escalar ou ser lançado num ritmo diferente dos outros (o candidato mais provável é `usage`, pelo volume de eventos).
- **Manter como está.** O custo é invisível hoje, mas cada fatia nova aumenta o grafo de imports, e a autorização continua num lugar que não é o dela. Rejeitada.
- **Um grupo de CRD por subsistema já** (`environments.platform…`, `workloads.platform…`). Deixa o limite visível no próprio Kubernetes, mas obriga a migrar todos os objetos e todos os controllers ao mesmo tempo. Adiada até haver instalação separada de verdade.

## Consequências

- **Trabalho decorrente**, cada item numa issue:
  1. tirar a autorização de `environments.py` para identity;
  2. contratos de import entre subsistemas como teste (#331);
  3. capabilities calculadas a partir dos controllers e `503 NoProviderForCapability` nas rotas de subsistema ausente (com a #269);
  4. o mapa de subsistemas num arquivo lido pela API e pelo `platform init`, que depois ganha `--with`/`--without` para os opcionais.
- **Toda issue nova diz a qual subsistema pertence.** Uma issue que mexe em dois deixa a dependência explícita.
- **O deck** pode mostrar o estado atual sobre o slide "Putting it together": cada caixa marcada como entregue, em andamento ou ausente, a partir do mapa.
- **Os ADRs 0022 a 0033 continuam valendo.** Este ADR não muda nenhuma decisão de dados ou de fluxo. Ele dá nome aos limites que essas decisões criaram e define as regras para que não vazem.
- Um subsistema novo começa pela linha dele no mapa: nível, dependências e CRDs, antes do código.
