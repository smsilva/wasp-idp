# Forager design

Issue [#263](https://github.com/smsilva/wasp-idp/issues/263), fatia 4 do catálogo, em três sub-issues: [#304](https://github.com/smsilva/wasp-idp/issues/304) (este spec, CRDs e modo `provision`), [#305](https://github.com/smsilva/wasp-idp/issues/305) (modo `compose`) e [#306](https://github.com/smsilva/wasp-idp/issues/306) (modo `bind` e class por override). Decisões em [ADR 0022](../../adr/0022-kube-api-as-platform-source-of-truth.md), [0023](../../adr/0023-platform-catalog-ownership.md), [0031](../../adr/0031-forager-built-on-score-defer-radius-kubevela.md) e [0033](../../adr/0033-workload-spec-and-workload-instance.md).

## Contexto

Uma Workload Spec (o Score de uma `Version`) declara recursos: `db: {type: postgres}`. Até aqui o provider `workload` fechava toda revisão com `resources` como `ResourcesNotSupported`. O Forager é o resolvedor: para cada recurso de uma revisão de deploy, ele escolhe o modo (**provision**, **compose** ou **bind**) pela política em camadas, cria ou reaproveita o `ResourceRequest` e o provisiona. O provider `workload` espera os `ResourceRequest` ficarem prontos e injeta as saídas no Deployment.

## Fluxo

1. A API grava a `WorkloadRevision` de deploy, como antes.
2. O **Forager** vê a revisão aberta, lê `Version.spec.appSpec` e, para cada recurso:
   - resolve a camada e o modo (abaixo);
   - cria o `ResourceRequest` `<env>.<instance>.<resource>`, ou reaproveita o que existe;
   - sem `id` no Score, cria o `Resource` do catálogo `<component>-<resource>`;
   - grava em `status.revision` o número da revisão que resolveu.
3. O provisioner do modo cria o recurso e grava `status.outputs`, `status.secretRef` e a condition `Ready`.
4. O provider **`workload`** só aplica a revisão quando todo recurso tem um `ResourceRequest` com `status.revision` igual ou maior que o da revisão. Enquanto isso, a revisão fica aberta com reason `ResourcesPending`.

Um só processo escreve o `status` do `ResourceRequest` (o Forager), e um só escreve o da revisão (o `workload`).

O Forager só provisiona quando todos os recursos da revisão resolveram. Com um recurso sem provider, os outros ganham o `ResourceRequest`, mas ficam em `Ready=Unknown`, sem criar nada. Uma revisão que vai falhar não sobe um banco que ninguém usa.

Um recurso retirado do Score continua com o seu `ResourceRequest` até o `workload remove` ou até o ambiente ser apagado. Apagá-lo no deploy derrubaria a versão anterior antes de o rollout terminar. A limpeza depois de um deploy `Succeeded` fica para uma fase posterior.

## CRDs

### `ResourceRequest` (`platform.wasp.silvios.me/v1alpha1`)

- **Nome:** `<env>.<instance>.<resource>`. Labels de ambiente, instância e component. ownerReference no `Environment`.
- **`spec`** (gravado pelo Forager na criação):
  - `environment`, `instance`, `component`, `resource`;
  - `type`, `class` e `id` (do Score);
  - `mode` e `provisioner`, ambos imutáveis (CEL `self == oldSelf`).
- **`status`:**
  - `revision`: a última revisão que o Forager resolveu para este pedido;
  - `outputs`: valores não sensíveis (`host`, `port`, `name`, `database`, `username`);
  - `secretRef`: `{name, keys}`, um Secret no namespace `apps` do vcluster;
  - condition `Resolved`: `True`, ou `False` com `NoProviderForCapability` ou `ResourceModeChanged`;
  - condition `Ready`: `Provisioning`, `Ready` ou `Failed`.
- **Finalizer:** `platform.wasp.silvios.me/forager`. No delete, o provisioner desfaz o que criou (provision: StatefulSet, Service e Secret no vcluster; compose: o database). Com o `Environment` sendo apagado, o vcluster vai junto: o provisioner recebe `vcluster=None` e desfaz só o que vive fora dele (o database do `compose`) e o control plane.

### `BindingPolicy` (`platform.wasp.silvios.me/v1alpha1`)

- **`spec.environment`:** vazio é o padrão da plataforma; com valor, é a camada do ambiente.
- **`spec.provisioners`:** lista ordenada de `{type, class?, id?, mode, params?}`.
- **Padrão da plataforma:** a `BindingPolicy` `platform-default` (`postgres` → `provision`), instalada pelo `platform init` com o provider.

## Resolução

Camadas em ordem: as políticas do ambiente, depois as do padrão. Dentro de cada camada, as políticas vão por nome e os itens pela ordem da lista. Vence o primeiro item que casa:

- `type` igual ao do recurso;
- `class` igual à pedida. Item sem `class` casa só pedido sem `class`, e pedido com `class` exige item com a mesma `class`. Uma `class` sem item é `NoProviderForCapability`: a branch que pede `restored` nunca recebe um banco vazio em silêncio.
- `id`, quando o item tem `id`, igual ao do recurso.

A `class` vem do Score (`resources.<n>.class`) e, na #306, de `overrides.resources.<n>.class` na revisão, que tem precedência. Assim a camada de branch do ADR 0031 escolhe uma `class` e nunca uma credencial.

**Troca de modo é recusada.** Quando a resolução muda `mode` ou `provisioner` de um `ResourceRequest` que já existe, o Forager não toca o recurso e grava `Resolved=False`, reason `ResourceModeChanged`, para aquela revisão. O `workload` fecha a revisão com o mesmo reason. Migrar é uma ação explícita: `workload remove`, que apaga os `ResourceRequest` da instância, e um deploy novo.

## Provisioners

O provisioner é código do Forager, um por (`type`, `mode`), com um contrato único:

- **entrada:** o `ResourceRequest`, os `params` do item da política e o vcluster do ambiente;
- **saída:** `outputs`, `secretRef` e o estado (`Provisioning`, `Ready` ou `Failed` com mensagem);
- **delete:** desfazer o que criou.

O Crossplane entra depois como backend de um provisioner (o primeiro tipo AWS: um managed resource de RDS no provision, `Database`/`Role` do `provider-sql` no compose), num ADR que estende o 0032 aos recursos. O Forager e o contrato não mudam.

| Provisioner | Sub-issue | O que faz |
|---|---|---|
| `postgres/provision` | #304 | Cria no namespace `resources` do vcluster, separado dos workloads de `apps`, um StatefulSet `postgres:17-alpine` e um Service. O nome é `<instance>-<resource>-<hash>`, e o hash vem do nome do `ResourceRequest`. A senha gerada vai para um Secret com o mesmo nome em `apps`, que é onde o `secretKeyRef` do workload lê, e também para um Secret do control plane (`resource.<rr>`), de onde o do vcluster é reescrito. Os outputs são `host` `<nome>.resources`, `port` 5432 e `database`/`name`/`username` `app`. Fica `Ready` com o StatefulSet pronto. |
| `postgres/compose` | #305 | Cria na instância `params.instance` (`shared-pg`, no namespace `platform-resources` do `platform-local`, instalada pelo `platform init`) um role e um database com o nome `<instance>-<resource>-<hash>`, só por `sql.Identifier`/`sql.Literal`. O role leva o nome do `ResourceRequest` como comentário, na mesma transação que o cria, e o database é dele só quando esse role é o dono: um role ou database de outro é recusado (`Failed`). `REVOKE ALL ... FROM PUBLIC` deixa só o próprio role conectar. A senha segue o caminho do `provision` (control plane → Secret em `apps`). Os outputs são `host` `shared-pg.resources` (o Service do host que cada vcluster replica, `networking.replicateServices.fromHost`), `port` 5432 e `database`/`name`/`username` com o nome do objeto. Fica `Ready` logo. No delete, `DROP DATABASE ... WITH (FORCE)` e `DROP ROLE`, também com o ambiente sendo apagado, porque a instância sobrevive ao vcluster. |
| `postgres/bind` | #306 | Só devolve valores e copia para o vcluster um Secret existente. |

Nomes que entram em manifest ou SQL (`instance`, `resource`) são validados com `re.fullmatch` antes de qualquer uso (ADR 0031). Sem o hash, nomes diferentes poderiam se encontrar: `a` + `b-db` e `a-b` + `db` dariam `a-b-db`. Além disso, cada objeto leva a anotação `platform.wasp.silvios.me/resource-request`. Um objeto que já existe com outro dono é recusado (`Failed`), nunca tomado, e o delete só apaga o que é do próprio pedido.

**Limitação aceita no `provision` local:** o Postgres não tem volume, como a recipe do spike. Perde os dados se o pod reiniciar, o que é aceitável para ambientes efêmeros. Está registrado em `aws/docs/known-broken.md`.

## Resource derivado

Sem `id`, o Forager cria o `Resource` do catálogo `<component>-<resource>`:

- `type` é o do Score;
- `owner` e `system` vêm do `Component`;
- a anotação `created-by` é `forager`.

A criação é idempotente, e o Forager nunca apaga o `Resource`: ele é a identidade lógica, uma só para todos os ambientes (ADR 0023). Sem o `Component` no catálogo, o Forager não cria o `Resource` e segue com o `ResourceRequest`.

## Provider `workload`

- **Espera:** a revisão fica aberta com `ResourcesPending` até cada recurso ter `ResourceRequest` com `status.revision` igual ou maior que o da revisão e `Ready=True`.
- **Fecha a revisão** em três casos:
  - com `ResourcesNotSupported`, quando algum `ResourceRequest` tem `Resolved=False` com `NoProviderForCapability` (por exemplo, `dns` e `route` do template `python-service`, que ainda não têm provider);
  - com `ResourceModeChanged`, quando é esse o reason de `Resolved=False`;
  - com `ResourcesFailed`, quando algum `ResourceRequest` tem `Ready=False` com `Failed`.
- **Placeholders:** `${resources.<n>.<campo>}` resolve contra `outputs`. Um campo listado em `secretRef.keys` só é aceito como valor inteiro de uma variável e vira `valueFrom.secretKeyRef`; dentro de outra string, em `command` ou em `args`, a revisão fecha com `UnsupportedSpec`.
- **Instância:** `WorkloadInstance.status.resources` recebe nome, tipo, modo e estado de cada recurso.
- **`remove`:** apaga também os `ResourceRequest` da instância. O finalizer do Forager desfaz cada um.

## API e CLI

- **`GET /v1/environments/{env}/workloads/{instance}`** passa a devolver `resources` com `name`, `type`, `mode` e `status`, lidos de `WorkloadInstance.status.resources`.
- **`platform workload get`** mostra uma linha por recurso.
- **Política de ambiente (#305):** `GET`/`PUT /v1/environments/{env}/binding-policy` grava a `BindingPolicy` `env-<env>`, com ownerReference no `Environment`. Escrita só por `platform-admins` (decide onde os dados moram), com journal; leitura por quem usa o ambiente, junto com o padrão. Lista vazia apaga a política. A API recusa `compose` sem `params.instance`. CLI: `platform environment policy set <env> --file` e `policy get <env>`.

## cli-smoke

- Uma `Version` 0.5.0 do podinfo com `db: postgres` e as variáveis `${resources.db.*}`. O deploy termina `Succeeded`, e `workload get` mostra `db postgres provision Ready`.
- A 0.4.0, que é o Score do `python-service` com `dns` e `route`, continua terminando em `ResourcesNotSupported`.
