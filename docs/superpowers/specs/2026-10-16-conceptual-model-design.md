# Conceptual model design

**Status:** rascunho em discussão, nada aqui é decisão. Issues: [#594](https://github.com/smsilva/wasp-idp/issues/594) (vocabulário e modelo conceitual, futuro ADR) e [#595](https://github.com/smsilva/wasp-idp/issues/595) (representações visuais do modelo), ambas em `Backlog` e marcadas "not ready". Branch: `feat/594-conceptual-model-spec`.

## Como usar este documento

Este documento é o resultado de uma conversa de design (2026-10-16) e foi escrito para que uma sessão nova, sem nenhum contexto, continue de onde ela parou.

**Antes de tudo (agente):** ao receber este documento numa sessão nova, a primeira coisa a fazer, antes de qualquer resumo, é perguntar: "Você está com mais alguém para quem precisamos introduzir o tema?". Se sim, seguir a [Sessão ao vivo](#sessão-ao-vivo-trazer-um-colega-para-pensar-junto). Se não, seguir os passos abaixo.

**Para retomar numa sessão nova (agente ou pessoa):**

1. Ler o [Resumo](#resumo) e o [Glossário](#glossário). Eles bastam para entender o resto.
2. Ler o [Exemplo de ponta a ponta](#exemplo-de-ponta-a-ponta): é a espinha do modelo, e cada seção posterior detalha um pedaço dele.
3. Ir para [Questões em aberto](#questões-em-aberto) e [Próximos passos](#próximos-passos): o trabalho seguinte é a análise ponto a ponto dessas questões.
4. Os fatos sobre o código de hoje estão em [O que existe hoje](#o-que-existe-hoje), com caminhos de arquivo. Não é preciso redescobri-los, só conferir se mudaram.

**Para apresentar ao time:** seguir o [Guia para apresentar ao time](#guia-para-apresentar-ao-time), que introduz os conceitos em sessões curtas, um bloco por vez.

**Vocabulário em inglês:** os termos do modelo (Concept, Instance, Class, Driver, Controller, Tool, Vendor), as personas (User, Admin, Maintainer) e os termos técnicos do Kubernetes e das ferramentas (Persistent Volume, PersistentVolumeClaim, StorageClass, CSI driver, Pod) ficam sempre em inglês, mesmo em texto e conversa em pt-BR: "a Instance grava o Driver escolhido", nunca "a Instância grava o Driver escolhido"; "Persistent Volumes", nunca "volumes persistentes". Isso vale para este documento, para ADRs, issues, comentários e para quem conduz a conversa (pessoa ou agente). "Instância da plataforma", no sentido de uma instalação da plataforma, não é termo do modelo e fica em português.

**Convenções:** os nomes propostos (`EnvironmentClass`, `ResourceClass`, `driver.yaml`, `platform driver`, `platform class`, `kind: Platform`…) são propostas para discussão. Os exemplos de YAML e de CLI mostram a experiência desejada, não comandos que existem hoje, exceto onde o texto diz "hoje".

## Resumo

**A aposta:** um modelo conceitual forte é o que permite trocar os componentes que implementam cada Concept. A caixa `IaC` do Integration & Delivery plane é um Concept; a ferramenta por trás dela pode ser Terraform ou Crossplane sem que o User perceba.

**O modelo** separa seis camadas: **Concept → Instance → Class → Driver → Tool**, com **Vendor** como atributo. É o mesmo padrão do Kubernetes com volumes: PersistentVolumeClaim (Instance) → StorageClass (Class) → CSI driver (Driver) → API do storage (Tool).

**A divisão entre camadas do sistema:** a Platform API conhece Concepts e Instances e trata a Class como dado opaco. A resolução da Class, os Drivers e as Tools ficam na camada Kubernetes (CRDs e controllers). Assim o modelo não recria na API a abstração que o Kubernetes já oferece.

**As regras que saíram da conversa:**

- Toda Instance grava qual Driver a atende (`status.resolution`) antes de qualquer Driver agir.
- A Tool é código do Driver; nunca aparece no pedido nem na Class.
- Drivers de Concepts diferentes se encontram por um **contrato de runtime** (`provides`/`consumes`), não por acoplamento direto: um único `kubernetes-workload` atende vcluster, EKS e AKS.
- O método de acesso a um ambiente (token de ServiceAccount, STS do EKS, Entra ID do AKS) é responsabilidade do Driver de environment; o User pede uma credencial por um caminho único.
- A experiência é consistente para três personas (User, Admin, Maintainer): os mesmos verbos na CLI, o mesmo formato declarativo, as mesmas relações de permissão.
- A mudança é incremental, e a CLI é o contrato estável: o que muda por baixo muda fatia a fatia.

## Contexto

### A aposta

A plataforma (Platform API, CLI `platform`, MCP) cresceu por fatias, uma capability por vez (ADR 0034, subsistemas da plataforma). Cada capability tem uma implementação concreta: vcluster para ambientes, GitHub para SCM e build, Postgres em cluster para bancos. Para que a plataforma sirva a organizações diferentes (AWS, Azure, GCP, GitHub, Bitbucket, Crossplane, Terraform), a implementação tem que ser trocável sem mudar o que o User pede. Isso só funciona se o Concept for estável e bem definido, e se a forma de explicá-lo for clara.

### Os problemas de vocabulário que dispararam a conversa

- **O Forager mistura níveis.** A `BindingPolicy` escolhe entre os modos `provision`, `compose` e `bind`. "Binding" colide com "bind"; "compose" colide com Crossplane Composition e `score-compose`; e a chave do provisioner (`<type>/<mode>`, em `platform/providers/forager/src/forager_provider/reconciler.py`) não tem lugar para a ferramenta, então "Postgres por Crossplane" e "Postgres por Terraform" não podem coexistir.
- **A `BindingPolicy` nomeia uma estratégia** (bind) quando decide todas.
- **"Provider" é ambíguo.** No repo é o processo (`platform/providers/*`); no Terraform e no Crossplane é o plugin de um vendor (`provider-aws`).
- **Cada subsistema escolhe sua implementação de um jeito diferente** (ver [O que existe hoje](#o-que-existe-hoje)).

### A preocupação com duplicar o Kubernetes

A Platform API usa o Kubernetes como motor: ela grava CRs, e controllers os reconciliam (ADR 0022, a kube API como fonte da verdade). O risco do modelo é recriar na API uma camada de abstração que o Kubernetes já tem. A resposta adotada: **a API fica com os Concepts e as abstrações se resolvem na camada Kubernetes**, usando os idiomas dela (CRD, CR, *Class, controller). O modelo é uma forma de explicar e padronizar esse uso, não uma camada nova.

## Glossário

| Camada | Pergunta que responde | Quem escreve | Analogia no Kubernetes | Exemplo |
|---|---|---|---|---|
| **Concept** | o que existe na plataforma? | a plataforma (CRD + contrato) | "volume" | Environment, Workload, Database |
| **Instance** | qual ocorrência, de quem? | o User, via API | PersistentVolumeClaim | Environment `demo`, Workload `orders` em `demo` |
| **Class** | como materializar neste contexto? | o Admin | StorageClass | "ambientes efêmeros usam vcluster" |
| **Driver** | quem cumpre o contrato do Concept? | a plataforma ou terceiros | CSI driver | `vcluster`, `aws-eks`, `kubernetes-workload` |
| **Controller** | qual processo executa o Driver? | — (deployable) | o Pod do CSI driver | hoje `platform/providers/*` |
| **Tool** | com o quê o Driver trabalha, por dentro? | — (detalhe do Driver) | a API do storage | Helm, Crossplane, Terraform, STS |
| **Vendor** (atributo) | de quem é a coisa materializada? | — | AWS, NetApp | AWS, Azure, GitHub |

Termos auxiliares:

- **Contrato de um Concept:** entrada (o `spec` da Instance), saída (`status`, outputs, Secrets) e ciclo de vida (materializar, observar, liberar). A agnosticidade da plataforma vem do contrato, não dos nomes.
- **Resolução:** o ato de escolher o Driver de uma Instance, gravado em `status.resolution`.
- **Runtime:** o tipo de lugar que um ambiente entrega (`kubernetes`, `container-apps`, `cloud-run`). É o contrato entre Drivers de environment e Drivers de workload e resources.
- **Pacote de Driver:** o controller, o manifesto `driver.yaml` e os manifests da Tool.
- **Personas:** **User** (pede Instances: qualquer papel que usa a plataforma, seja desenvolvimento, segurança, SRE, DevOps, negócio ou um agente), **Admin** (instala e configura uma instância da plataforma e cadastra as Classes) e **Maintainer** (opera e diagnostica os Drivers). No Kubernetes, o par é o mesmo: o user do cluster escreve o PVC, o admin do cluster escreve a StorageClass. Maintainer, e não Operator, para não colidir com o operator do Kubernetes.

**Por que Driver, e não Provider:** "Provider" já nomeia o plugin de vendor no Terraform e no Crossplane, o que colide com a camada Tool na explicação ("o provider do Crossplane é provider de quê?"). Driver tem o sentido de sistema operacional: o OS define "impressora", o driver adapta, o hardware é do vendor. O ADR 0034 já fala em "driver de um vendor". O que hoje se chama provider (`platform/providers/*`) é o **Controller** que implementa um ou mais Drivers.

### O paralelo com PVC, lado a lado

O mesmo pedido nos dois mundos: um volume para um Pod no Kubernetes, e o Postgres `db` do componente `orders` num ambiente efêmero da plataforma.

| Camada | Kubernetes | Plataforma hoje | Plataforma no modelo |
|---|---|---|---|
| Concept | volume | `type: postgres` no Score | Database |
| Instance | PersistentVolumeClaim `data` | `ResourceRequest` `demo.orders.db` (o Forager cria a partir do Score) | igual |
| Class | StorageClass `fast` | `BindingPolicy` `profile-ephemeral` | `ResourceClass` `database-ephemeral` |
| Driver | `ebs.csi.aws.com` | `postgres/compose` | `shared-database` |
| Controller | Pod `ebs-csi-controller` | `forager` | `forager` |
| Tool | API do EBS | SQL no Postgres compartilhado `shared-pg` | igual |
| Vendor | AWS | local | local |
| Onde a escolha fica gravada | annotation `volume.kubernetes.io/storage-provisioner` no PVC | `spec.provisioner` do `ResourceRequest` | `status.resolution` |
| O que é materializado | PersistentVolume + volume EBS | database e role no `shared-pg` + Secret | igual |

Lado a lado, o que o Admin cadastra e o que o User pede:

```yaml
# Kubernetes                               # Plataforma (no modelo)
kind: StorageClass                         kind: ResourceClass
metadata:                                  metadata:
  name: fast                                 name: database-ephemeral
provisioner: ebs.csi.aws.com               spec:
parameters:                                  concept: database
  type: gp3                                  scope:
                                               profile: ephemeral
                                             driver: shared-database
                                             params:
                                               instance: shared-pg
---                                        ---
kind: PersistentVolumeClaim                # score.yaml do orders
metadata:                                  resources:
  name: data                                 db:
spec:                                          type: postgres
  storageClassName: fast
  resources:
    requests:
      storage: 10Gi
```

E a Instance depois da escolha:

```yaml
# Kubernetes                               # Plataforma (no modelo)
kind: PersistentVolumeClaim                kind: ResourceRequest
metadata:                                  metadata:
  name: data                                 name: demo.orders.db
  annotations:                             spec:
    volume.kubernetes.io/storage-provisioner:  environment: demo
      ebs.csi.aws.com                        component: orders
spec:                                        resource: db
  storageClassName: fast                     type: postgres
  volumeName: pvc-3f1c…                    status:
status:                                      resolution:
  phase: Bound                                 class: database-ephemeral
                                               driver: shared-database
                                             conditions:
                                               - {type: Ready, status: "True"}
```

**Onde o paralelo não é exato:**

- **Quem nomeia a Class.** O PVC pode nomear a StorageClass (`storageClassName`) ou cair na default. O User da plataforma nunca nomeia a Class: ela é escolhida pelo escopo, em camadas (ambiente → profile → default). É como se cada namespace tivesse a própria default StorageClass.
- **Quem cria a Instance.** O PVC é escrito pelo user do cluster. O `ResourceRequest` é derivado do Score pelo Forager, um por recurso de cada `WorkloadRevision`; o User escreve só o Score.
- **Não há PersistentVolume.** O Kubernetes tem um objeto para a coisa materializada (o PV). A plataforma não tem: o que o Driver criou aparece no `status` da Instance e nos Secrets que ela publica.

## Princípios

1. **A API conhece Concepts e Instances; a Class é dado opaco para ela.** A API autoriza quem escreve uma Class e a guarda no journal, mas não interpreta o conteúdo. Resolução e escolha de Driver acontecem em controllers.
2. **Um escritor por objeto** (ADR 0034). A API escreve o `spec` das Instances; o resolvedor escreve `status.resolution`; o Driver escreve o resto do `status`.
3. **A resolução fica gravada na Instance** (`status.resolution`) antes de qualquer Driver agir, venha ela de uma Class (Environment, Database) ou de uma regra fixa (Workload pelo runtime do ambiente). Cada Driver só atende Instances com o próprio nome, como um CSI driver só atende os PVCs anotados com ele.
4. **A Tool é código do Driver.** Não aparece no pedido, na Class nem no manifesto `Platform`. O Driver a declara no próprio `driver.yaml`.
5. **Vendor é atributo**, usado para agrupar e reportar. Vai no nome do Driver só quando a coisa materializada é do vendor (`aws-eks`), não quando o Concept é genérico.
6. **Drivers se encontram por contrato de runtime** (`provides`/`consumes`), nunca por acoplamento direto. Um pacote pode trazer vários Drivers juntos, mas o contrato continua separado.
7. **O método de acesso a um ambiente é do Driver de environment.** O consumidor (User ou Driver) pede uma credencial de curta duração por um caminho único, e a plataforma delega ao Driver do ambiente.
8. **Cada consumidor recebe uma credencial com escopo próprio**, nunca a credencial admin do ambiente.
9. **Segredo nunca vai em pedido nem em manifesto**, só referência (como o `externalId` da `CloudAccount`, ADR 0029).
10. **A experiência é dedutível:** os mesmos verbos para todo Concept na CLI, o mesmo formato declarativo para todo `kind`, as mesmas relações de permissão para todo tipo.
11. **Todo comando imperativo tem contraparte declarativa**, e os dois convergem para o mesmo estado.
12. **A CLI é o contrato estável da migração.** CRDs, nomes de Class e Tools mudam por baixo, fatia a fatia, sem mudar a experiência.

## Exemplo de ponta a ponta

**Cenário:** uma instância da plataforma com ambientes efêmeros em vcluster e ambientes de produção em EKS. O componente `orders` tem um Postgres no Score e vai para os dois tipos de ambiente.

### Ato 0 — Admin: instalar a plataforma

A instância da plataforma declara só quais Drivers estão ligados:

```yaml
apiVersion: platform.wasp.silvios.me/v1
kind: Platform
metadata:
  name: wasp
spec:
  version: 0.9.0
  drivers:
    environment: [vcluster, aws-eks]
    workload: [kubernetes-workload]
    resources: [in-cluster-database, existing-database]
```

Cada Driver traz um manifesto no próprio pacote:

```yaml
# platform/providers/vcluster/driver.yaml
name: vcluster
subsystem: environment
tool: helm
requires:
  - chart: vcluster
provides:
  runtime: kubernetes
  access: serviceAccountToken
---
# platform/providers/aws_eks/driver.yaml
name: aws-eks
subsystem: environment
tool: crossplane
vendor: aws
requires:
  - crossplane >= 2.3
  - xpkg.upbound.io/upbound/provider-aws-eks
dependsOn:
  - cloud-account/aws-account
provides:
  runtime: kubernetes
  access: aws-iam
---
# platform/providers/kubernetes_workload/driver.yaml
name: kubernetes-workload
subsystem: workload
tool: manifests
consumes:
  runtime: kubernetes
```

O instalador (hoje `platform init`, no futuro um operator) lê os manifestos e:

- instala cada Tool uma vez só, mesmo que vários Drivers a peçam (o Crossplane sobe uma vez; cada Driver acrescenta os providers do Crossplane de que precisa);
- instala as dependências (`aws-eks` traz o Driver `aws-account` de `cloud-account`);
- avisa quando um runtime oferecido não tem quem o consuma.

```bash
platform status
# environment  vcluster             Ready
# environment  aws-eks              Ready   (crossplane ✓, provider-aws-eks ✓, aws-account ✓)
# workload     kubernetes-workload  Ready   (consome kubernetes ← vcluster, aws-eks)
# resources    in-cluster-database  Ready
# resources    existing-database    Ready
```

### Ato 1 — Admin: configurar contas e Classes

```yaml
apiVersion: platform.wasp.silvios.me/v1
kind: CloudAccount
metadata:
  name: aws-prod
spec:
  vendor: aws
  roleArn: arn:aws:iam::123456789012:role/wasp-platform
---
apiVersion: platform.wasp.silvios.me/v1
kind: EnvironmentClass
metadata:
  name: ephemeral
spec:
  profile: ephemeral
  driver: vcluster
  params:
    ttl: 72h
---
apiVersion: platform.wasp.silvios.me/v1
kind: EnvironmentClass
metadata:
  name: production
spec:
  profile: production
  driver: aws-eks
  params:
    cloudAccount: aws-prod
    region: sa-east-1
---
apiVersion: platform.wasp.silvios.me/v1
kind: ResourceClass
metadata:
  name: database-ephemeral
spec:
  concept: database
  scope:
    profile: ephemeral
  driver: in-cluster-database
---
apiVersion: platform.wasp.silvios.me/v1
kind: ResourceClass
metadata:
  name: database-production
spec:
  concept: database
  scope:
    profile: production
  driver: existing-database
  params:
    host: orders.abc.sa-east-1.rds.amazonaws.com
    secretRef: rds-orders
```

```bash
platform apply --file platform-config/     # requer a permissão can_configure
```

O `cloudAccount` vai na Class, não no pedido do User nem no `Platform`. O `Platform` diz "esta plataforma sabe criar EKS"; a Class diz "produção cria EKS na conta `aws-prod`". Uma Class que aponta para um Driver incompatível com o runtime do escopo é recusada (`in-cluster-database` só existe onde o runtime é `kubernetes`).

### Ato 2 — User: pedir os ambientes

```bash
platform environment create demo --profile ephemeral
platform environment create prod --profile production    # requer can_create no projeto
```

A API grava só o Concept:

```yaml
apiVersion: platform.wasp.silvios.me/v1alpha1
kind: Environment
metadata:
  name: demo
spec:
  profile: ephemeral
```

O resolvedor lê a `EnvironmentClass` e grava a escolha. O Driver escolhido materializa o ambiente e publica o contrato de runtime:

```yaml
# Environment demo                         # Environment prod
status:                                    status:
  resolution:                                resolution:
    class: ephemeral                           class: production
    driver: vcluster                           driver: aws-eks
  runtime: kubernetes                        runtime: kubernetes
  access:                                    access:
    endpoint: https://vcluster.env-demo        endpoint: https://ABC.gr7.sa-east-1.eks.amazonaws.com
    method: serviceAccountToken                method: aws-iam
  conditions:                                conditions:
    - {type: Ready, status: "True"}            - {type: Ready, status: "True"}
```

### Ato 3 — User: deploy

```bash
platform workload deploy --component orders --environment demo --version 1.4.0
platform workload deploy --component orders --environment prod --version 1.4.0
```

A API grava um `WorkloadRevision` por deploy (o estado desejado, sem Driver):

```yaml
apiVersion: platform.wasp.silvios.me/v1alpha1
kind: WorkloadRevision
metadata:
  name: demo.orders.7
spec:
  environment: demo
  instance: orders
  component: orders
  version: 1.4.0
  revision: 7
```

Depois, para cada revisão:

1. **Resolução do workload, sem Class:** o runtime do ambiente é `kubernetes`, então `status.resolution.driver: kubernetes-workload`.
2. **Resolução do `db` do Score pela `ResourceClass`:** em `demo`, `in-cluster-database` (um Postgres dentro do vcluster); em `prod`, `existing-database` (copia a senha do RDS, sem criar nada).
3. **Acesso:** o `kubernetes-workload` e o `in-cluster-database` pedem uma credencial para `demo`. A plataforma delega ao Driver `vcluster`, que emite um token de ServiceAccount com escopo restrito. Em `prod`, delega ao `aws-eks`, que gera o token STS com a própria identidade (EKS Pod Identity).
4. **Materialização:** o `kubernetes-workload` aplica Deployment, Service, ConfigMap e Secret, **com o mesmo código** nos dois ambientes, e grava o estado observado no `WorkloadInstance` (ADR 0033).

A plataforma **não** cria um CR intermediário como "WorkloadKubernetes". O Driver traduz o Concept em objetos nativos do runtime. Se um Driver precisar de um CR intermediário (um kind do Crossplane, por exemplo), ele é detalhe interno daquele Driver e a API nunca o vê.

### Ato 4 — User: observar e acessar

```bash
platform workload get orders --environment prod
# orders  1.4.0  Ready  driver: kubernetes-workload
#   db    Ready  driver: existing-database (class database-production)

platform environment get prod   # kubeconfig com exec: platform environment credential prod
kubectl get pods                # o exec passa pelo mesmo caminho: a plataforma delega ao aws-eks
```

A pessoa nunca instala `aws` nem `kubelogin`: o método de acesso vive no Driver.

### Ato 5 — Maintainer

```bash
platform driver list
platform driver verify aws-eks
# crossplane provider: Healthy · pod identity: ok · sts: ok · 1 environment
platform driver logs kubernetes-workload --since 1h
platform driver metrics aws-eks
platform auth who-can operate driver aws-eks
```

A interação é a mesma para qualquer Driver, seja qual for a Tool.

### Ato 6 — Tudo como declarativo

```
platform-config/   Platform, CloudAccount, Classes     → Admin
envs/demo/         Environment + Workloads             → User
envs/prod/         Environment + Workloads
```

```bash
platform diff --file envs/prod/
platform apply --file envs/prod/ --prune
```

Um repositório com esses diretórios e um CI que roda `platform apply --prune` é GitOps sem nenhum controller novo.

### O mesmo exemplo em outros runtimes

Trocar EKS por Cloud Run em produção muda só a Class e os Drivers instalados: o pedido do User e o Score continuam os mesmos.

```yaml
apiVersion: platform.wasp.silvios.me/v1
kind: EnvironmentClass
metadata:
  name: serverless
spec:
  profile: serverless
  driver: gcp-cloud-run
  params:
    cloudAccount: gcp-sandbox
    region: southamerica-east1
```

O `gcp-cloud-run` oferece `runtime: cloud-run`; o workload resolve para `cloud-run-workload`; o `db` precisa de uma `ResourceClass` com um Driver compatível com esse runtime (`gcp-cloud-sql`), porque `in-cluster-database` só existe onde há Kubernetes.

## O que existe hoje

### Concepts, Instances e como o Driver é escolhido

| Concept | Instance | Como o Driver é escolhido hoje | Driver (nome proposto) → Controller de hoje | Tool | Vendor |
|---|---|---|---|---|---|
| Database | `ResourceRequest` | **Class explícita:** `BindingPolicy` em camadas (ambiente → profile → default) | InClusterDatabase, SharedDatabase, ExistingDatabase → `forager` | manifests, SQL, cópia de Secret | local |
| DNS, Route | `ResourceRequest` | a mesma `BindingPolicy` | `dns/provision`, `route/provision` → `forager` | manifests | local |
| Environment | `Environment` | **campo na Instance:** com ou sem `spec.cloudAccount` | LocalVcluster → `local_vcluster`; CloudVcluster → `crossplane_aws` | Helm; Crossplane | local; AWS |
| Build | `Build` | **por referência:** a API resolve a `ScmConnection` da org do repo | GitHubActionsBuild → `scm_github` | GitHub Actions | GitHub |
| Repository | `ComponentCreation` | por referência, como o Build | GitHubRepository → `scm_github` | API do GitHub | GitHub |
| Workload | `WorkloadRevision` | **sem escolha:** um Driver só | VclusterWorkload → `workload` | manifests, Istio | — |
| Cloud account | `CloudAccount` | **vendor na configuração:** `spec.vendor` | AwsAccount → `aws_account` | STS | AWS |
| SCM | `ScmConnection` | `spec.vendor` | GitHubApp → `scm_github` | GitHub App | GitHub |
| Registry | `OCIRegistry` | `spec.vendor` (só `ghcr`), com `spec.default` | GhcrRegistry → `registry` | OCI Distribution API | GitHub |

São cinco formas de escolher o Driver: Class explícita, campo na Instance, referência, vendor na configuração e nenhuma escolha. Só `resources` tem a forma completa.

### Dois tipos de objeto

A API mistura o que o User pede com o que o Admin cadastra. É a mesma divisão de PVC × StorageClass, Gateway × GatewayClass, e Claim × ProviderConfig no Crossplane:

- **Instances (pedidos):** `Environment`, `WorkloadRevision`, `ResourceRequest`, `Build`, `ComponentCreation`.
- **Classes e configuração (cadastros):** `BindingPolicy`, `CloudAccount`, `ScmConnection`, `OCIRegistry`.

É por isso que `CloudAccount`, `ScmConnection` e `OCIRegistry` carregam `spec.vendor`: o vendor mora na configuração. O `OCIRegistry.spec.default` faz o papel do "default StorageClass".

**Teste de agnosticidade:** o `spec` de uma Instance se lê sem saber vendor nem Tool? `ResourceRequest`, `WorkloadRevision` e `Build` passam. `Environment` não passa: `spec.cloudAccount` (imutável, `platform/crds/environment.yaml`) faz o User escolher, indiretamente, onde o ambiente roda.

### Contratos que já existem sem nome

- **Contrato de runtime:** o `local_vcluster` publica `Environment.status.kubeconfigData`, e dois consumidores o usam: o provider `workload` (Deployments) e o Forager (o Postgres dentro do vcluster), ambos pelo endereço `https://vcluster.env-{name}`. O dado é o certificado **admin** do vcluster, que viola o princípio 8.
- **Pacote de Driver:** `platform/providers/crossplane_aws/deploy/` já traz a Tool junto com o controller (`crossplane.yaml`, o chart do Crossplane; `provider-aws-ec2.yaml`). Mas quem liga isso é uma flag global, `platform init --with-crossplane` (`cli/src/wasp_platform/bootstrap/settings.py`), e não o Driver.
- **Credencial da Tool vinda da configuração:** o `crossplane_aws` gera um `ProviderConfig` por `CloudAccount` (ADR 0029); nem a plataforma nem o Crossplane têm credencial própria da nuvem.
- **Manifesto do Driver:** os labels `provider`, `capabilities` e `vendor` dos Deployments (ADR 0039) são uma versão incompleta do `driver.yaml`.
- **Credencial por `exec`:** o kubeconfig pessoal é um `exec` de `platform environment credential` (ADR 0028), que é o caminho único de credencial do princípio 7, ainda só para pessoas.

### Vazamentos da API para a camada Kubernetes

1. **A API resolve um Driver:** `connection_of` em `platform/api/src/platform_api/builds.py` escolhe a `ScmConnection` da org do repo e a grava no `Build`. Isso é resolução de Class e deveria estar num controller.
2. **A API conhece os params de um Driver:** `BIND_PARAMS` em `platform/api/src/platform_api/binding_policies.py` valida `host`, `database` e `username` do `bind`. Um Driver novo obrigaria a mexer na API. A validação deveria estar no schema do CRD (CEL) ou ser declarada pelo Driver.
3. **A API conhece o enum de modos** (`provision`, `compose`, `bind`), pelo mesmo motivo.

### Inconsistências da CLI

| Ação | Hoje |
|---|---|
| criar | `create` em `environment`, `team`, `build`; `add` em `cloud account`, `registry`, `scm connection` |
| apagar | `delete` em `environment`, `team`, `catalog`; `remove` em `cloud account`, `registry`, `scm connection`, `workload` |
| marcar como padrão | `scm connection default`, `catalog template default`, `registry set-default` |
| checar a conexão com a Tool | `verify` em `cloud account` e `scm connection`; não existe em `registry` nem em `environment` |
| configurar Class | escondido em `platform environment policy set` e `platform environment profile policy set` |

### Formatos declarativos de hoje

Há três, cada um com o seu formato:

| Comando | Formato |
|---|---|
| `platform workload apply --file plan.yaml --prune` | YAML próprio, sem `kind` (`environment:` + `workloads:`), descrito em `platform/docs/reference/workloads.md` |
| `platform environment policy set --file policy.yaml` | lista `provisioners` solta |
| `platform catalog import` | documentos do Backstage |

O `workload apply` já tem o comportamento desejado (diff contra o estado atual, `--dry-run`, `--prune`, `unchanged` quando nada muda); falta o formato comum.

### Autorização

Hoje: `can_use` e `is_owner_or_admin` em `platform/api/src/platform_api/environments.py`, importados por vários módulos. O ADR 0042 (Proposto: projetos e OpenFGA como ponto de decisão de autorização) define um ponto de entrada `authorize(principal, relation, object)` e relações por tipo (`can_view`, `can_use`, `can_delete`, `can_share`) que já se aproximam da padronização do princípio 10.

## Experiência por persona

### User

Gramática `platform <concept> <verbo> <nome>`, com verbos fixos (`create`, `list`, `get`, `delete`) e ações próprias do Concept (`share`, `deploy`). Quem aprendeu um Concept deduz o próximo. O User nunca vê Class, Driver nem Tool, a não ser como informação no `get`.

```bash
platform environment create demo --profile ephemeral
platform workload deploy --component orders --environment demo
platform workload get orders --environment demo
```

### Admin

Class e Driver como substantivos de primeiro nível, iguais para todo Concept. Duas instâncias da plataforma diferem só no manifesto `Platform` e nas Classes.

```bash
platform status
platform driver list
platform class list
platform class get database --environment staging   # qual Driver resolve aqui, e por qual camada
platform class set database --profile ephemeral --driver shared-database --param instance=shared-pg
```

### Maintainer

A mesma interação com qualquer Driver: `verify` (conversa com a Tool), `logs`, `metrics`, `get`.

```bash
platform driver get github-actions-build
platform driver verify github-actions-build
platform driver logs cloud-database --since 1h
platform driver metrics cloud-database
```

### Permissões dedutíveis

Se todo Concept tem os mesmos verbos, todo tipo no modelo de autorização tem as mesmas relações:

| Verbo da CLI | Relação |
|---|---|
| `get`, `list` | `can_view` |
| `create` | `can_create` (no projeto) |
| `delete` | `can_delete` |
| `share` | `can_share` |
| `deploy`, `credential` | `can_use` |
| `class set`, `apply` de Class | `can_configure` |
| `driver verify`, `logs`, `metrics` | `can_operate` |

As camadas do modelo se alinham às personas: Instance → User; Class → Admin; Driver → Maintainer. Um Concept novo herda o conjunto de relações. Na CLI, no estilo de `kubectl auth can-i`:

```bash
platform auth can-i delete environment demo
platform auth can-i configure class database
platform auth who-can use environment demo
```

### Imperativo e declarativo

Todo comando imperativo é um gerador do mesmo objeto que o declarativo aplica (como `kubectl create ... --dry-run=client -o yaml`):

```bash
platform environment create demo --profile ephemeral --share team-a --dry-run --output yaml
platform environment get demo --output yaml     # round-trip no mesmo formato
platform apply --file demo.yaml
platform diff --file demo.yaml
```

Cuidados:

- **O manifesto é o modelo público da API, não o CRD.** `kind: Workload` vira `WorkloadRevision`s por dentro. Nada de `kubectl apply` nos CRDs: pularia autorização, journal e validação.
- **Imperativo e declarativo convergem:** um `apply` depois de um `create` com os mesmos valores dá `unchanged`.
- **Segredo só por referência.**

## Driver como pacote

Um Driver é um pacote com três partes: o controller, o manifesto `driver.yaml` e os manifests da Tool. A plataforma conhece só o manifesto.

| Campo do `driver.yaml` | Para quê |
|---|---|
| `name`, `subsystem` | identidade; o que aparece em `platform driver list` e no `Platform` |
| `tool` | informativo, para o Maintainer |
| `vendor` | atributo, para agrupar (ADR 0039) |
| `requires` | Tools e versões que o instalador garante |
| `dependsOn` | Drivers de outros subsistemas que precisam estar ligados |
| `provides` | o contrato que o Driver entrega (runtime e método de acesso, para Drivers de environment) |
| `consumes` | o contrato que o Driver precisa (runtime, para Drivers de workload e resources) |

**Instalação das Tools:**

- **Tool compartilhada:** instalada uma vez; cada Driver acrescenta o que é dele.
- **Tool que já existe no cluster** (um Crossplane de outro time): o Driver só verifica e reporta `ToolMissing` se faltar. A única escolha legítima no nível da plataforma é **quem gerencia a Tool** (`managed` ou `external`), nunca **qual Tool**.
- **Tool externa à plataforma** (Terraform Cloud, Spacelift, Atlantis): o Driver precisa de uma credencial para falar com ela, que vira um objeto de configuração com referência ao segredo, no padrão da `ScmConnection`. Não é campo do `Platform`.
- **Tool no mesmo cluster** (Crossplane): o Driver só cria kinds da Tool; a credencial da nuvem vem da `CloudAccount`, como o `crossplane_aws` já faz.

**Contrato e pacote são coisas diferentes:** o contrato é sempre separado (`provides`/`consumes`), mas um pacote pode trazer vários Drivers. Um pacote `azure-container-apps` pode instalar o Driver de environment e o de workload juntos, porque os dois são do mesmo vendor.

## Contrato de runtime e acesso

**Por que o Driver de environment não traz o de workload:** vcluster, AKS e EKS são construídos de formas totalmente diferentes, mas entregam a mesma coisa: uma API Kubernetes e uma forma de entrar nela. Quem faz deploy só precisa disso, como o ArgoCD faz deploy em qualquer cluster a partir de um kubeconfig, e como no Cluster API o provider de infra cria o cluster e publica o kubeconfig num Secret.

| | Driver de environment traz o de workload | Contrato separado por runtime |
|---|---|---|
| vcluster, AKS, EKS | três cópias da lógica de deploy | um `kubernetes-workload` para os três |
| Novo tipo de cluster (GKE) | mais uma cópia | só o Driver de environment |
| Container Apps | junto faz sentido | dois Drivers, que podem vir no mesmo pacote |
| Forager (`in-cluster-database`) | também precisaria da credencial de cada Driver | consome o mesmo acesso |

**A variação de autenticação é grande, mas converge:**

| Runtime | Pessoa (client) | Máquina (controller) |
|---|---|---|
| vcluster | certificado ou token de ServiceAccount | token de ServiceAccount (TokenRequest) |
| EKS | `aws eks get-token` (token STS pré-assinado) + access entries | EKS Pod Identity ou IRSA → STS → o mesmo token |
| AKS | `kubelogin` (Entra ID) | workload identity federada → token do Entra |
| GKE | `gke-gcloud-auth-plugin` | Workload Identity → token do Google |

Todas terminam num token de curta duração para a kube API, que o kubeconfig obtém por um plugin `exec` (`ExecCredential`). Por isso o contrato publica o **método** (`access.method`), nunca uma credencial fixa, e qualquer consumidor pede o token pelo mesmo caminho:

```
consumidor (pessoa ou Driver) → "credential para o environment X" → a plataforma delega ao Driver de X → token + validade
```

O `kubelogin` e o `aws eks get-token` ficam encapsulados nos Drivers de environment, e os Drivers de workload ficam agnósticos de vendor. Runtimes que não são Kubernetes (Container Apps, Cloud Run) publicam outro `runtime` e outro método (o id do ambiente da nuvem mais a identidade da `CloudAccount`).

**Escopo:** cada consumidor recebe uma credencial própria. O `kubernetes-workload` com acesso aos namespaces de apps; o Forager, ao namespace `resources`. É o princípio dos kubeconfigs pessoais do ADR 0028, aplicado aos Drivers.

## Vocabulário de resources

O que muda no Forager (`platform/providers/forager/`) com o modelo:

| Hoje | No modelo |
|---|---|
| `BindingPolicy` | `ResourceClass` (ou `ResourcePolicy`; ver questões) |
| `mode: provision` | Driver `in-cluster-database` |
| `mode: compose` (com `params.instance: shared-pg`) | Driver `shared-database` |
| `mode: bind` | Driver `existing-database` |
| `ResourceRequest.spec.provisioner` (`postgres/provision`) | `status.resolution.driver` |
| camadas ambiente → profile → default (`policy.py`) | iguais, mais o runtime como escopo |
| `NoProviderForCapability` no deploy | recusa já no `class set` quando o Driver é incompatível com o runtime |

As regras de match de `policy.py` (`type`, `class`, `id`) e o comportamento do Forager (provisionar só quando todos os recursos da revisão resolveram) não mudam. Os modos deixam de ser uma camada própria, e a colisão Binding/bind desaparece.

## Alternativas em aberto

- **Environment lógico × Runtime como recurso.** Separar o Environment (nome, dono, compartilhamento, profile, o que é deployado) do Runtime, que viraria um recurso do ambiente resolvido por Class como qualquer database (modelo do Humanitec). Ganho: tudo vira Class → Driver, e o Environment fica 100% agnóstico. Custo: um nível a mais para explicar; e hoje o vcluster do `local_vcluster` é o próprio Environment.
- **Crossplane como camada Kubernetes inteira, ou só como Tool.** O Crossplane já implementa esse modelo dentro do Kubernetes (XRD = Concept, Claim = Instance, Composition = Class/Driver, Function/Provider = Tool). Os Drivers de infra poderiam ser Compositions. Ele não cobre Build, SCM nem Workload, que continuam com controller próprio, então a tendência é um híbrido. Fatos já decididos: o ADR 0031 adiou Radius e KubeVela; o ADR 0032 adotou o Crossplane como único método de provisionamento por cloud e adiou o Kratix.
- **Class por Concept (`EnvironmentClass`, `ResourceClass`) ou Class genérica** (`kind: Class` com `spec.concept`).
- **Como o consumidor obtém a credencial:** (a) o Driver de environment grava um Secret por consumidor e o rotaciona; (b) o consumidor pede à plataforma, que delega ao Driver, o mesmo caminho do `platform environment credential`.

## Caminho incremental

Cada fatia começa pelos exemplos de CLI (o walkthrough escrito antes do código, como já exige a regra da #182 de atualizar `platform/docs/walkthrough/`), entra no `cli-smoke` ou no `cli-e2e` e não quebra a fatia anterior.

1. **Só leitura, sem quebrar nada:** `platform driver list` e `get`, montados a partir dos labels do ADR 0039 e de um primeiro `driver.yaml`. É o walking skeleton: as três personas enxergam o modelo sem mudança de comportamento.
2. **Consistência de verbos:** `create`, `delete` e `default` em todos os comandos, com os nomes antigos como aliases e aviso de deprecação.
3. **Permissões por verbo:** relações uniformes no modelo do ADR 0042 antes de ele ser aceito; `can_configure` e `can_operate`; `platform auth can-i` e `who-can`.
4. **`verify`, `logs` e `metrics` uniformes por Driver**, generalizando o `verify` que já existe em dois lugares.
5. **Declarativo:** `--dry-run --output yaml` nos `create`, e `get --output yaml` no mesmo formato; depois `platform apply`/`diff` genéricos por `kind`, começando por `Environment`; o `workload apply` migra para `kind: Workload`, aceitando o formato antigo durante a transição.
6. **Class de resources:** `platform class` sobre a `BindingPolicy` atual; o rename do CRD e dos modos vem depois, por trás do comando.
7. **Correção dos vazamentos da API:** a escolha da connection do build e os params do `bind`.
8. **`status.resolution` em todas as Instances**, começando por `ResourceRequest` (onde já existe como `spec.provisioner`) e `WorkloadRevision`.
9. **Contrato de runtime e credencial por consumidor:** `status.runtime` e `status.access` no `Environment`; o caminho único de credencial; o fim do uso do certificado admin pelos Drivers.
10. **`EnvironmentClass`:** o `cloudAccount` sai do pedido e vira param da Class.
11. **`driver.yaml` completo e `kind: Platform` no `platform init`:** o `--with-crossplane` some, porque ligar um Driver que pede Crossplane já implica Crossplane.

## Ideias futuras

**Operator para instalar a plataforma.** O `kind: Platform` vira o CR de um operator que instala CRDs, a API e os controllers dos Drivers ligados, e faz os upgrades. O `platform init` deixa de instalar e passa só a gravar o CR; o `platform status` passa a ler o status do `Platform`. A separação de responsabilidades fica:

| Peça | Responsável por | Nunca toca em |
|---|---|---|
| Operator | o ciclo de vida da plataforma | Instances |
| Platform API | Concepts, Instances, autorização, journal | a instalação de si mesma |
| Controllers (Drivers) | materializar e observar Instances | a instalação de outros controllers |

Cuidados: o operator precisa ser instalado por algo de fora (Helm ou OLM); falta decidir se ele instala ou só referencia Keycloak e OpenFGA; ele precisa de RBAC amplo, restrito à instalação; e o upgrade de CRDs com Instances vivas (versões e conversão) é o ponto mais caro.

## Questões em aberto

1. **Escopo do ADR:** o padrão Instance → Class → Driver vale para todos os subsistemas (ADR geral, com resources como primeira aplicação) ou só para resources por enquanto? Inclinação: todos.
2. **Nomes:** Class por Concept ou genérica; `ResourceClass` ou `ResourcePolicy`; nomes dos Drivers (`in-cluster-database`, `shared-database`, `existing-database`…).
3. **Granularidade do Concept:** `Database` com `engine: postgres`, ou um Concept por engine. O Score pede hoje `type: postgres`.
4. **Environment lógico × Runtime como recurso** (ver [Alternativas em aberto](#alternativas-em-aberto)).
5. **Crossplane como camada inteira ou só como Tool** (ver [Alternativas em aberto](#alternativas-em-aberto)).
6. **Caminho da credencial:** Secret rotacionado por consumidor ou pedido delegado ao Driver.
7. **Rename de `platform/providers/*`** para controllers, e o que muda em `platform status` e no label `provider` do ADR 0039.
8. **`Environment.spec.cloudAccount`:** migra para param da `EnvironmentClass` ou fica como exceção registrada. Envolve o ADR 0032.
9. **Vazamentos da API:** entram como consequências do ADR ou viram issues próprias antes dele.
10. **Class por projeto:** um admin de projeto (ADR 0042) pode ter Classes próprias para os ambientes do projeto, ou Class é só da plataforma?
11. **`managed` × `external` por Tool:** onde se declara, no `Platform` ou na configuração do Driver.
12. **Onde ficam as figuras da #595:** o guia da Platform API, o deck, ou os dois.

## Próximos passos

1. **Revisão deste documento** pelo autor da conversa.
2. **Análise ponto a ponto das [Questões em aberto](#questões-em-aberto)**, uma por vez. Cada questão decidida vira texto definitivo aqui e, quando for decisão de arquitetura, um ADR (Nygard, um por decisão, em `docs/adr/`).
3. **Reescrita das issues:** a #594 vira o ADR do modelo (ou um ADR geral e issues por subsistema), e a #595 passa a desenhar o modelo de seis camadas e o exemplo de ponta a ponta. Até lá, as duas ficam em `Backlog` com o aviso "not ready".
4. **Issues do caminho incremental**, a partir da fatia 1 (`platform driver list`, só leitura), uma por entrega, com labels de subsistema (ADR 0034) e `platform-cli`.
5. **Apresentação ao time** em paralelo, seguindo o guia abaixo, para que as questões em aberto recebam mais olhares.

## Guia para apresentar ao time

O modelo tem muitos conceitos, e apresentá-los todos de uma vez confunde. O guia divide a apresentação em seis sessões curtas (30 a 45 minutos), cada uma com um objetivo, o material deste documento que ela usa, o que **não** mostrar ainda e uma pergunta para fechar. Cada sessão só começa quando a anterior está clara para todos.

**Regras gerais:**

- Começar sempre pelo exemplo concreto, nunca pelo glossário: primeiro o Postgres do `orders`, depois o nome das camadas.
- Usar a analogia PVC/StorageClass/CSI driver com quem conhece Kubernetes e a analogia de sistema operacional (impressora, driver, fabricante) com quem não conhece.
- Uma camada nova por sessão, no máximo duas.
- Terminar cada sessão com a pergunta proposta e registrar as respostas como comentário na #594: elas alimentam as questões em aberto.
- Deixar claro desde o início que é um rascunho: o objetivo é ouvir, não convencer.

### Sessão 1 — A aposta e o problema

- **Objetivo:** entender por que vale a pena investir num modelo conceitual.
- **Material:** [Resumo](#resumo) (só o parágrafo "A aposta"); [Contexto](#contexto) (a aposta e os problemas de vocabulário).
- **Mostrar:** o Forager com `BindingPolicy` e os modos `provision`/`compose`/`bind`, e a confusão entre "Binding" e "bind"; e a tabela de [Inconsistências da CLI](#inconsistências-da-cli).
- **Não mostrar ainda:** Class, Driver, Tool, runtime.
- **Pergunta para fechar:** "Onde vocês já sentiram essa inconsistência usando ou explicando a plataforma?"

### Sessão 2 — Concept, Instance e Class

- **Objetivo:** separar o que se pede do como se materializa.
- **Material:** [Glossário](#glossário) (só as três primeiras linhas); [O paralelo com PVC, lado a lado](#o-paralelo-com-pvc-lado-a-lado), sem as linhas Driver, Controller, Tool e Vendor; [Dois tipos de objeto](#dois-tipos-de-objeto); o Ato 1 e o Ato 2 do [Exemplo de ponta a ponta](#exemplo-de-ponta-a-ponta), só com Database.
- **Mostrar:** o mesmo Score do `orders` resolvendo em três Postgres diferentes conforme o ambiente (no cluster, compartilhado, RDS existente); e a analogia PVC × StorageClass.
- **Não mostrar ainda:** Tool, Vendor, runtime, credenciais.
- **Pergunta para fechar:** "Que outros Concepts da plataforma deveriam ter uma Class?"

### Sessão 3 — Driver, Tool e Vendor

- **Objetivo:** entender onde fica a troca de ferramenta, e por que "Driver" e não "Provider".
- **Material:** o restante do [Glossário](#glossário) e o parágrafo "Por que Driver, e não Provider"; [Princípios](#princípios) 3, 4 e 5; a tabela de [Concepts, Instances e como o Driver é escolhido](#concepts-instances-e-como-o-driver-é-escolhido).
- **Mostrar:** o `crossplane_aws` de hoje (o controller cria kinds do Crossplane, que materializa na AWS); e as cinco formas diferentes de escolher o Driver que a plataforma tem hoje.
- **Não mostrar ainda:** contrato de runtime, credenciais, `driver.yaml`.
- **Pergunta para fechar:** "Qual a próxima ferramenta ou vendor que vocês esperam ter que suportar?"

### Sessão 4 — A Platform API e a camada Kubernetes

- **Objetivo:** entender que o modelo não duplica o Kubernetes.
- **Material:** [A preocupação com duplicar o Kubernetes](#a-preocupação-com-duplicar-o-kubernetes); [Princípios](#princípios) 1, 2 e 3; [Vazamentos da API para a camada Kubernetes](#vazamentos-da-api-para-a-camada-kubernetes).
- **Mostrar:** o Ato 3 do exemplo (a API grava o `WorkloadRevision` sem Driver; a resolução e os Drivers agem nos controllers); e a alternativa do Crossplane como camada inteira.
- **Não mostrar ainda:** credenciais, operator.
- **Pergunta para fechar:** "Que lógica da API de hoje vocês acham que deveria estar num controller?"

### Sessão 5 — Runtimes, contratos e acesso

- **Objetivo:** entender como Drivers de Concepts diferentes se encontram, e por que o acesso é do Driver de environment.
- **Material:** [Contrato de runtime e acesso](#contrato-de-runtime-e-acesso); [Driver como pacote](#driver-como-pacote); o Ato 0 e o trecho "O mesmo exemplo em outros runtimes".
- **Mostrar:** o mesmo `orders` em vcluster, EKS e Cloud Run; a tabela de autenticação por runtime.
- **Não mostrar ainda:** operator.
- **Pergunta para fechar:** "Que runtimes vocês veem no horizonte, e com que forma de autenticação?"

### Sessão 6 — Experiência, migração e próximos passos

- **Objetivo:** juntar tudo do ponto de vista de quem usa, e decidir por onde começar.
- **Material:** [Experiência por persona](#experiência-por-persona); o [Exemplo de ponta a ponta](#exemplo-de-ponta-a-ponta) completo, agora de uma vez; [Caminho incremental](#caminho-incremental); [Ideias futuras](#ideias-futuras); [Questões em aberto](#questões-em-aberto).
- **Mostrar:** os Atos 4, 5 e 6 (observar, manter, declarar); as permissões dedutíveis a partir dos verbos.
- **Pergunta para fechar:** "Quais questões em aberto cada um quer assumir, e qual fatia do caminho incremental começamos?"

### Sessão ao vivo: trazer um colega para pensar junto

O autor e mais uma pessoa ou um grupo, juntos numa chamada, com a tela compartilhada mostrando uma sessão nova do Claude Code. Quem chega vem sem nenhum contexto e vai colaborar no modelo. O objetivo é entender o modelo bem o bastante para questioná-lo, não recebê-lo pronto. O agente conduz, o autor complementa, e quem chegou é quem precisa entender.

**Como a sessão começa:** o autor abre uma sessão limpa e manda o path deste documento (`@docs/superpowers/specs/2026-10-16-conceptual-model-design.md`), talvez já dizendo que está com mais alguém. O agente lê o documento inteiro e, antes de qualquer resumo, pergunta: "Você está com mais alguém para quem precisamos introduzir o tema?". Se a resposta for sim, o agente segue o roteiro abaixo. Se for não, segue [Para retomar numa sessão nova](#como-usar-este-documento).

**Regras para o agente:**

- **Ir direto ao ponto:** depois da resposta, a primeira mensagem é exatamente a do passo 1 do roteiro: o objetivo em uma frase e a pergunta. Sem dizer que o modelo é um rascunho nem como a conversa vai funcionar: o autor já fez esse enquadramento.
- **Sem nomes:** a saudação e as mensagens seguintes se dirigem a quem chegou como colaborador, sem vocativo nem nome de ninguém, mesmo que o autor os informe. Usar "vocês" quando for um grupo e "você" quando for uma pessoa.
- **O público é de programadores muito experientes:** ir direto ao ponto, sem didatismo, sem explicar o óbvio.
- **Menos texto, mais exemplos:** mostrar um YAML, um comando ou uma tabela curta em vez de um parágrafo; a prosa só liga os exemplos.
- **Listas em linhas, no terminal:** quando a mensagem no terminal enumera itens (tools, camadas, recursos, opções), cada item vai numa linha própria, como lista em markdown, nunca separado por vírgulas no meio da frase. Isso facilita a leitura na janela do agente.
- **Uma cor por camada, como no deck:** o terminal não renderiza cor arbitrária, então cada camada do modelo leva sempre o mesmo quadrado colorido antes do nome, do mesmo jeito que o deck dá uma cor a cada conceito do catálogo (`concept-colors` em `docs/presentation/idp.yaml`). Legenda: 🟪 **Concept**, 🟦 **Instance**, 🟩 **Class**, 🟨 **Driver**, 🟫 **Controller**, 🟧 **Tool**, ⬜ **Vendor**. A cor vale também para o equivalente no Kubernetes (🟦 PVC, 🟩 StorageClass, 🟨 CSI driver), e é isso que torna o paralelo visível. Cor e **negrito** valem desde a primeira mensagem: os termos do Kubernetes já entram com o quadrado da camada equivalente (🟦 **PersistentVolumeClaim**, 🟩 **StorageClass**, 🟨 **CSI driver**) e as tools com 🟧, para que o olho se acostume com a cor antes de o nome da camada aparecer. O nome das camadas e a legenda só aparecem quando a primeira camada é nomeada (passo 3 do roteiro). Todo termo-chave vai em **negrito**, em toda mensagem.
- **Diagramas no browser:** o Visual Companion do skill `superpowers:brainstorming` (`skills/brainstorming/visual-companion.md` do plugin) abre uma aba do browser que o agente atualiza a cada passo. O documento já vale como aprovação do autor: o agente sobe o servidor logo depois do "sim" (`scripts/start-server.sh --project-dir <repo> --open`), sem oferecer antes. No browser vão os diagramas, os YAMLs lado a lado e a tabela de camadas, com as cores reais por camada, na mesma família `oklch` do slide `concept-colors` do deck (`docs/presentation/idp.html`): Concept `oklch(0.78 0.05 290)`, Instance `oklch(0.90 0.09 210)`, Class `oklch(0.84 0.11 170)`, Driver `oklch(0.86 0.06 105)`, Controller `oklch(0.74 0.12 260)`, Tool `oklch(0.80 0.08 35)`, Vendor `oklch(0.70 0.02 250)`. No terminal ficam a prosa curta e a pergunta de transição. Cada passo que muda o que está na tela termina com "Na aba do browser: …" em uma linha. Quando o passo não tem nada visual, o browser mostra a tela anterior até o próximo diagrama.
- **Exemplos com syntax highlight:** todo YAML, comando ou saída de CLI renderizado no browser leva realce de sintaxe (chaves, valores, comentários e `kind` em cores distintas), para facilitar a leitura. O realce é inline no HTML, sem depender de biblioteca externa, e não usa as cores das camadas, que ficam reservadas ao modelo.
- **Destacar as linhas que importam:** em cada YAML, as linhas que o passo explica (a annotation `storage-provisioner`, o `provisioner`, o `status.resolution`) ganham um fundo destacado e uma barra na margem esquerda, para que o olho vá direto a elas. O resto do YAML fica como contexto, com realce normal. No máximo duas ou três linhas destacadas por YAML.
- **Contraste em toda caixa:** todo bloco de conteúdo (código, lista, caixa de diagrama) usa o mesmo fundo escuro dos YAMLs, com texto claro, em vez de herdar as cores do template do Visual Companion, que deixaram texto escuro sobre fundo escuro. Não reutilizar nomes de classe CSS do template (`main`, `side`, `option`, `card`…): eles herdam estilos inesperados. Depois de cada tela nova, tirar um print (skill `print`) e conferir a legibilidade antes de falar dela.
- **Comandos na convenção dos scripts bash do autor** (skill `bash-scripts`): opções sempre na forma longa (`--namespace`, nunca `-n`; `--output`, nunca `-o`), variáveis entre aspas e chaves (`"${name}"`), e um comando com mais de uma opção quebrado com `\`, uma opção por linha e 2 espaços de indentação. Vale para o terminal e para o browser.

  ```bash
  helm install aws-ebs-csi-driver aws-ebs-csi-driver/aws-ebs-csi-driver \
    --namespace kube-system
  ```
- **Caber em meia tela:** na chamada, o browser ocupa metade de um monitor 1920×1080 (cerca de 960×870 px úteis), ao lado do terminal. Dois YAMLs lado a lado ficam com cerca de 50 caracteres por linha (fonte de 13 px): comentários vão em linha própria, nunca no fim da linha, e nada pede barra de rolagem horizontal. Uma tela não passa de cerca de 25 linhas de código.
- **Siglas por extenso na primeira menção:** a primeira vez que uma sigla aparece na conversa, o significado vem entre parênteses: CSI (Container Storage Interface), PVC (PersistentVolumeClaim), EBS (Elastic Block Store), EKS (Elastic Kubernetes Service), CRD (Custom Resource Definition). Depois, só a sigla.
- **pt-BR**, com os termos do modelo e os termos técnicos em inglês (Persistent Volume, nunca "volume persistente").
- **Nunca "desenvolvedor"** para quem usa a plataforma ou o cluster: segurança, SRE, DevOps e negócio também usam. Na plataforma, User; no Kubernetes, o user do cluster (quem escreve o PVC) e o admin do cluster (quem escreve a StorageClass).
- **Mensagens curtas:** no máximo três ou quatro linhas de prosa além do exemplo, sem cenário hipotético longo.
- **Um passo por vez, curto:** cada mensagem cabe numa tela, explica um passo e termina numa pergunta de transição que deixa a pessoa escolher como seguir ("Seguimos para …?"), esperando a resposta antes do passo seguinte. Nada de despejar seções do documento.
- **Explicar, não testar:** o agente explica; não faz perguntas de conteúdo nem pede que a pessoa repita o passo com as próprias palavras. Quem quiser aprofundar ou questionar pergunta. Se a pessoa travar, voltar ao exemplo concreto, nunca ao glossário.
- **Divergência é resultado:** quando a pessoa propuser outra coisa, anotar e, no fim, oferecer registrar como comentário na #594, em vez de defender o texto.
- **FAQ vivo:** antes de responder a uma pergunta fora do roteiro, consultar o [FAQ das sessões ao vivo](#faq-das-sessões-ao-vivo). Se ela já estiver lá, partir da resposta registrada (e da tela, se houver). Se for nova, responder e, depois de ver como a resposta foi recebida, avaliar se ela funcionou (clara, curta, com o exemplo certo). Se funcionou, propor ao autor guardá-la no FAQ, com o passo do roteiro em que surgiu. Se não funcionou, anotar o que mudar antes de guardar.
- **Não mostrar o que ainda não foi introduzido:** nenhum termo do modelo aparece antes do passo que o introduz.

**Roteiro:**

1. **Objetivo em uma frase e nivelamento sobre CSI.** A primeira mensagem é só o bloco abaixo, com o negrito, as cores e as quebras de linha exatamente assim ("você sabe" quando for uma pessoa):

   > Oi! Queremos discutir alguns conceitos-chave para a **Platform API** ser agnóstica a 🟧 **tools**, com inspiração nas specs do Kubernetes:
   >
   > - Crossplane
   > - Terraform
   > - Pulumi
   > - Helm
   > - Argo CD
   > - GitHub Actions
   >
   > Para nivelar: o que vocês já sabem da spec **CSI** (Container Storage Interface)?
   >
   > - 🟦 **PersistentVolumeClaim**
   > - 🟩 **StorageClass**
   > - 🟨 **CSI driver**

   Nada sobre como a plataforma funciona ainda. Se a pessoa pedir uma recapitulação, responder com o PVC e a StorageClass em YAML (os do [paralelo](#o-paralelo-com-pvc-lado-a-lado)) e uma linha de comentário em cada, sem lista de definições. Senão, completar a partir do que a pessoa sabe: o Pod quer um volume; o PersistentVolumeClaim é o pedido ("10Gi, leitura e escrita"), sem dizer onde nem como; a StorageClass, escrita pelo admin do cluster, diz como materializar (`provisioner: ebs.csi.aws.com`, `parameters: {type: gp3}`); a StorageClass default atende o PVC que não nomeia uma. Nos dois casos, terminar com a pergunta de transição: "Seguimos para o que acontece quando o PVC é criado?".
2. **O CSI driver em detalhe.** O controller do driver observa os PVCs cuja StorageClass aponta para ele (e só esses); chama a API do storage (AWS EBS); cria o volume; o PersistentVolume registra o volume criado e o PVC fica `Bound`. A escolha fica gravada no próprio PVC (annotation `volume.kubernetes.io/storage-provisioner`). O Kubernetes não sabe nada de EBS: quem sabe é o driver. Trocar EBS por NetApp muda a StorageClass e o driver instalado, e o PVC continua igual: o user do cluster não precisa saber nada do storage para pedir um volume.
3. **Dar nome às camadas, ainda no Kubernetes:** volume (Concept), PVC (Instance), StorageClass (Class), CSI driver (Driver), o Pod do driver (Controller), a API do EBS (Tool), AWS (Vendor). Só a primeira coluna da tabela de [O paralelo com PVC, lado a lado](#o-paralelo-com-pvc-lado-a-lado).
4. **A plataforma em uma frase:** a Platform API recebe pedidos (ambiente, deploy, banco) e controllers os materializam no Kubernetes. Mostrar o Postgres `db` do `orders`: o Score pede `type: postgres`, e conforme o ambiente vira um Postgres no cluster, um database num Postgres compartilhado ou um RDS existente: o mesmo padrão do PVC.
5. **O paralelo lado a lado:** a tabela e os YAMLs de [O paralelo com PVC, lado a lado](#o-paralelo-com-pvc-lado-a-lado), com a coluna "hoje", e os pontos em que o paralelo não é exato.
6. **O problema:** os nomes de hoje (`BindingPolicy`, os modos `provision`/`compose`/`bind`, "provider" com dois sentidos) e as cinco formas de escolher o Driver ([Concepts, Instances e como o Driver é escolhido](#concepts-instances-e-como-o-driver-é-escolhido)). Em seguida, a proposta: Class e `status.resolution` para todo Concept.
7. **A aposta:** um modelo forte permite trocar a Tool (Terraform, Crossplane) sem que o User perceba, como o PVC não muda quando o storage muda. Aqui entra o [Resumo](#resumo).
8. **Fechar:** perguntar o que fez sentido e o que não fez, e combinar o próximo encontro. Daí em diante a sequência é a do guia (Sessão 3 em diante), uma por encontro; as [Questões em aberto](#questões-em-aberto) entram só no fim, uma por vez.

### FAQ das sessões ao vivo

Perguntas que já surgiram nas sessões ao vivo, com a resposta que funcionou. Cada entrada traz o passo do roteiro em que a pergunta apareceu, a resposta curta e o que mostrar no browser. Uma entrada só entra aqui depois de avaliada (ver a regra "FAQ vivo" acima).

**O CSI driver é instalado como qualquer coisa no Kubernetes?** (passo 2, sessão de 2026-10-16)

Sim: é um pacote comum (Helm chart ou add-on do EKS), e o core do Kubernetes não traz nenhum driver de storage. O pacote sobe um Deployment `ebs-csi-controller` (o plugin que fala com a API do EBS, mais sidecars genéricos da spec, como o `csi-provisioner`, que observa os PVCs e chama `CreateVolume`; roda com identidade própria via IRSA ou Pod Identity), um DaemonSet `ebs-csi-node` (formata e monta no nó) e o objeto `CSIDriver`, que registra o nome `ebs.csi.aws.com`. A StorageClass aponta para esse nome em `provisioner`. Os sidecars são iguais em todo CSI driver; o que muda por vendor é só o plugin. **No browser:** os comandos de instalação, o que o pacote sobe e o `CSIDriver` ao lado da StorageClass, com o nome em comum destacado. **Ponte para o modelo:** é o mesmo "Pacote de Driver" de [Driver como pacote](#driver-como-pacote) (controller, manifesto e Tool), mas só mencionar depois do passo 3.

### Entrada de uma pessoa nova no meio do caminho

Quem chega depois das sessões segue a mesma ordem, sozinho, lendo as seções indicadas em cada sessão, e depois conversa 30 minutos com alguém que já participou, usando as perguntas de fechamento como roteiro. Um agente (Claude Code) também pode conduzir essa introdução: basta pedir para ele seguir este guia, uma sessão por vez, e esperar a pessoa confirmar que entendeu antes de passar à seguinte.

## Referências

**ADRs** (`docs/adr/`):

- 0022: a kube API como fonte da verdade da plataforma.
- 0023: dono do catálogo da plataforma.
- 0025: conexões de SCM.
- 0026: times no Keycloak.
- 0028: kubeconfig pessoal por `exec`.
- 0029: cloud accounts.
- 0031: o Forager construído sobre o Score, adiando Radius e KubeVela.
- 0032: um único método de provisionamento por cloud (Crossplane), adiando o Kratix.
- 0033: Workload Spec e Workload Instance.
- 0034: subsistemas da plataforma.
- 0038: camada de profile na binding policy.
- 0039: capabilities calculadas a partir dos Deployments dos providers.
- 0042 (Proposto): projetos e OpenFGA como ponto de decisão de autorização.

**Código:**

- Forager: `platform/providers/forager/` (`policy.py`, `reconciler.py`, `postgres.py`, `routing.py`, `README.md`).
- Seeds de policy: `platform/providers/forager/deploy/forager-provider.yaml`, `profile-policies.yaml`.
- Policy na API: `platform/api/src/platform_api/binding_policies.py`.
- Build e connection: `platform/api/src/platform_api/builds.py`.
- Autorização de hoje: `platform/api/src/platform_api/environments.py`.
- Environment em cloud: `platform/providers/crossplane_aws/` (inclui `deploy/crossplane.yaml`).
- Instalação: `cli/src/wasp_platform/bootstrap/local.py`, `settings.py`.
- CLI: `cli/src/wasp_platform/commands/`.
- CRDs: `platform/crds/`.
- Diagrama de planes do deck: `docs/presentation/diagrams/landscape/build.py`.

**Issues:**

- #594: vocabulário e modelo conceitual (futuro ADR).
- #595: representações visuais do modelo.
- #540: padronizar o estilo visual do guia da Platform API.
- #182: todo comando novo atualiza o walkthrough.
