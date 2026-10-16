# Conceptual model design

Issue [#594](https://github.com/smsilva/wasp-idp/issues/594) (vocabulário de resources e modelo conceitual), base da [#595](https://github.com/smsilva/wasp-idp/issues/595) (representações visuais do modelo). **Rascunho em discussão:** nada aqui é decisão até virar ADR.

## Contexto

A aposta da plataforma é que um modelo conceitual forte é o que permite trocar os componentes que implementam cada conceito. Exemplo: a caixa `IaC` do Integration & Delivery plane é um conceito, e a ferramenta por trás dela pode ser Terraform ou Crossplane sem que o desenvolvedor perceba.

O vocabulário atual não ajuda a explicar isso:

- **O Forager mistura níveis.** `BindingPolicy` com os modos `provision`, `compose` e `bind`: "Binding" colide com "bind", "compose" colide com Crossplane Composition e `score-compose`, e a chave do provisioner (`<type>/<mode>`) não tem lugar para a ferramenta.
- **Cada subsistema escolhe sua implementação de um jeito.** Há cinco formas hoje (tabela abaixo), e só `resources` tem uma política explícita.
- **"Provider" é ambíguo.** No repo é o processo (`platform/providers/*`); no Terraform e no Crossplane é o plugin de um vendor (`provider-aws`).

A plataforma fica agnóstica a ferramentas e vendors pelo **contrato** de cada conceito, não pelo nome das camadas: entrada (o `spec` da instância), saída (`status`, outputs, Secret) e ciclo de vida (materializar, observar, liberar). Quem cumpre o contrato pode usar qualquer ferramenta. O vocabulário serve para explicar esse limite.

## Modelo proposto

| Camada | Pergunta | Quem escreve | Kubernetes (analogia) |
|---|---|---|---|
| **Conceito** | o que existe na plataforma? | a plataforma (CRD + contrato) | "volume" |
| **Instância** | qual ocorrência, de quem? | o desenvolvedor (via API) | PersistentVolumeClaim |
| **Class** | como materializar neste contexto? | o operador | StorageClass |
| **Driver** | quem cumpre o contrato? | a plataforma ou um terceiro | CSI driver |
| **Controller** | qual processo executa o Driver? | — (deployable) | o Pod do CSI driver |
| **Tool** | com o quê, por dentro? | — (detalhe do Driver) | a API da cloud |

**Vendor** é atributo, não camada: diz de quem é a coisa materializada (AWS, GitHub) e serve para agrupar e reportar (ADR 0039, capabilities calculadas pelos labels dos Deployments dos providers). Um Driver pode ser específico de um vendor (`aws_rds`) ou genérico por ferramenta (um Driver Crossplane que aplica uma Composition, com o vendor dentro dela); a plataforma não muda em nenhum dos dois casos.

O reconciliation loop da plataforma gira em torno das instâncias dos conceitos: observa a Instância, resolve a Class, chama o Driver para materializar e observar, e escreve o status. Tool e Vendor ficam atrás do Driver.

Exemplo:

```
DatabaseResource → staging.orders.db → env-staging (Class) → CloudDatabase (Driver) → crossplane-database (Controller) → Crossplane (Tool), AWS (Vendor)
```

### Por que Driver, e não Provider

- "Provider" já nomeia o plugin de vendor no Terraform e no Crossplane: na explicação, colide com a camada Tool ("o provider do Crossplane é provider de quê?").
- Driver tem o sentido de sistema operacional: o OS define "impressora", o driver adapta, o hardware é do vendor.
- O ADR 0034 (subsistemas da plataforma) já fala em "driver de um vendor". O que hoje se chama provider (`platform/providers/*`) é o **Controller** que implementa um ou mais Drivers (o `forager` hospeda os drivers de database, dns e route).

## Dois tipos de objeto

A API mistura o que o desenvolvedor pede com o que o operador cadastra, a mesma divisão de PVC × StorageClass, Gateway × GatewayClass e Claim × ProviderConfig no Crossplane:

- **Instância (pedido):** `Environment`, `WorkloadRevision`, `ResourceRequest`, `Build`, `ComponentCreation`.
- **Class ou configuração (cadastro do operador):** `BindingPolicy`, `CloudAccount`, `ScmConnection`, `OCIRegistry`.

É por isso que `CloudAccount`, `ScmConnection` e `OCIRegistry` carregam `spec.vendor`: o vendor mora na configuração. O `OCIRegistry.spec.default` faz o papel do "default StorageClass".

**Teste de agnosticidade:** o `spec` de uma Instância se lê sem saber vendor nem ferramenta? `ResourceRequest`, `WorkloadRevision` e `Build` passam; `Environment` não, porque `spec.cloudAccount` faz o desenvolvedor escolher, indiretamente, onde o ambiente roda.

## O que existe hoje

| Conceito | Instância | Como o Driver é escolhido | Driver → Controller | Tool | Vendor |
|---|---|---|---|---|---|
| Database | `ResourceRequest` | **Class explícita:** `BindingPolicy` em camadas (env → profile → default) | InClusterDatabase, SharedDatabase, ExistingDatabase → `forager` | manifests, SQL, cópia de Secret | local |
| DNS, Route | `ResourceRequest` | a mesma `BindingPolicy` | `dns/provision`, `route/provision` → `forager` | manifests | local |
| Environment | `Environment` | **campo na instância:** com ou sem `spec.cloudAccount` (ADR 0032, um único método de provisionamento por cloud: Crossplane) | LocalVcluster → `local_vcluster`; CloudVcluster → `crossplane_aws` | Helm; Crossplane | local; AWS |
| Build | `Build` | **por referência:** a API resolve a connection da org do repo | GitHubActionsBuild → `scm_github` | GitHub Actions | GitHub |
| Repository | `ComponentCreation` | por referência, como o Build | GitHubRepository → `scm_github` | API do GitHub | GitHub |
| Workload | `WorkloadRevision` | **sem escolha:** um Driver só | VclusterWorkload → `workload` | manifests, Istio | — |
| Cloud account | `CloudAccount` | **vendor na configuração:** `spec.vendor` | AwsAccount → `aws_account` | STS | AWS |
| SCM | `ScmConnection` | `spec.vendor` | GitHubApp → `scm_github` | GitHub App | GitHub |
| Registry | `OCIRegistry` | `spec.vendor`, com `spec.default` | GhcrRegistry → `registry` | OCI Distribution API | GitHub (ghcr) |

Os nomes de Driver nesta tabela são propostas: hoje os Drivers não têm nome próprio, só a chave do provisioner (Forager) ou o controller.

## A Class em cada subsistema

A Class tira do pedido a escolha da infraestrutura: o desenvolvedor pede o conceito, o operador decide como ele se materializa em cada contexto.

- **Database (existe):** `staging` → ExistingDatabase (RDS); profile `ephemeral` → SharedDatabase; default → InClusterDatabase. O mesmo Score roda nos três.
- **Environment (proposta):** o desenvolvedor pede `profile: ephemeral`; a Class do profile decide entre LocalVcluster e CloudVcluster numa conta X. O `cloudAccount` sai do pedido e vira param da Class.
- **Registry (meio caminho):** `default: true` escolhe o registry quando o build não nomeia um. Completo: `ephemeral` publica no ghcr, `shared` no ECR.
- **Build (proposta):** "builds deste time usam GitHub Actions; os da org Y, Tekton". Hoje sai da connection.
- **Workload:** um Driver só; a Class só faria sentido com um segundo (outro runtime além do vcluster).

## Vocabulário de resources

O que muda no Forager com o modelo:

- `mode` deixa de ser camada: `provision`, `compose` e `bind` viram Drivers (InClusterDatabase, SharedDatabase, ExistingDatabase), e a colisão Binding/bind some.
- `BindingPolicy` vira a Class de resources. Nome em aberto: `ResourceClass` segue a analogia com StorageClass; `ResourcePolicy` mantém a ideia de camadas.
- O item da Class escolhe o Driver e seus params; a Tool é declarada pelo Driver, nunca pela Class.
- O Conceito é `Database` genérico com `engine: postgres`, ou `Postgres`? O Score pede hoje `type: postgres`.

## Questões em aberto

1. **Escopo do ADR:** o padrão Instância → Class → Driver vale para todos os subsistemas (ADR geral, com resources como primeira aplicação) ou só para resources por enquanto? Inclinação: todos.
2. **Nome da Class** em geral e em resources (`ResourceClass`, `ResourcePolicy`, `EnvironmentClass`…), e se ela vira um CRD por conceito ou um CRD genérico com `concept:`.
3. **Granularidade do Conceito:** `Database` + engine, ou um Conceito por engine.
4. **Rename de `platform/providers/*` para controllers**, e o que isso muda em `platform status` (ADR 0039: o label `provider` dos Deployments).
5. **`Environment.spec.cloudAccount`:** migra para param da Class (quebra o teste de agnosticidade hoje) ou fica como exceção registrada.
6. **Onde ficam as figuras da #595:** o guia da Platform API, o deck, ou os dois.
