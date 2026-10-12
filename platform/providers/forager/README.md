# Forager

Resolve os recursos do Score de cada `WorkloadRevision` em `ResourceRequest`s e os provisiona ([ADR 0022](../../../docs/adr/0022-kube-api-as-platform-source-of-truth.md), [0031](../../../docs/adr/0031-forager-built-on-score-defer-radius-kubevela.md), #263). O desenho está em [`docs/superpowers/specs/2026-10-11-forager-design.md`](../../../docs/superpowers/specs/2026-10-11-forager-design.md).

Roda **dentro do cluster**, como Deployment `forager-provider` em `platform-system`, instalado pelo `platform init --target local` junto com a `BindingPolicy` `platform-default` e a instância compartilhada `shared-pg` (`deploy/shared-pg.yaml`, no namespace `platform-resources`, com a senha de admin no Secret `shared-pg-admin`). A política de cada ambiente (`env-<nome>`) vem da API (`PUT /v1/environments/{name}/binding-policy`).

## Reconciliação

- **Resolução:** para a revisão aberta mais nova de cada instância (deploy ou rollback), lê o Score em `Version.spec.appSpec` e resolve cada recurso, com a `class` do override da revisão (`--resource-class`) antes da do Score, pelas `BindingPolicy`s (`policy.py`): primeiro as do ambiente, depois as do padrão; vence o primeiro item que casa `type`, `class` e `id`.
- **`ResourceRequest`:** cria `<environment>.<instance>.<resource>` (finalizer `platform.wasp.silvios.me/forager`, ownerReference no `Environment`) ou reaproveita o que existe, e grava `status.revision` e a condition `Resolved`. Um modo ou uma `class` diferente da já gravada é `ResourceModeChanged`; um tipo sem provisioner é `NoProviderForCapability`.
- **Catálogo:** sem `id`, cria o `Resource` `<component>-<resource>` com o owner e o System do `Component`, e nunca o apaga.
- **Provisionamento:** só quando todos os recursos da revisão resolveram. O provisioner (`postgres.py`) é chamado a cada passada até o `ResourceRequest` ficar `Ready`, e grava `status.outputs` e `status.secretRef`.
- **Delete:** o provisioner desfaz o que criou e o finalizer sai. Com o `Environment` sendo apagado, o provisioner recebe `vcluster=None` e desfaz só o que vive fora dele (o database do `compose`) e a credencial do control plane.
- Watch das revisões com timeout de 5 s enquanto há revisão aberta ou pedido em andamento, e de 30 s no resto do tempo.

## Provisioners

| Provisioner | O que faz |
|---|---|
| `postgres/provision` | StatefulSet `postgres:17-alpine` (sem volume) e Service `<instance>-<resource>-<hash>` no namespace `resources` do vcluster, e o Secret com a senha no namespace `apps`, onde o workload o lê. O hash vem do nome do `ResourceRequest`, e um objeto de outro pedido é recusado, nunca tomado. A senha é gerada uma vez e guardada no Secret `resource.<request>` de `platform-resources`. |
| `postgres/compose` | Role e database `<instance>-<resource>-<hash>` na instância `params.instance` (`shared-pg`), pelo driver (`shared.py`, só `sql.Identifier`/`sql.Literal`). O role leva o nome do `ResourceRequest` como comentário e o database é dele quando o role é o dono: o de outro é recusado. Só o próprio role conecta (`REVOKE ALL ... FROM PUBLIC`). O app chega em `shared-pg.resources`, o Service que o vcluster replica do host. O delete faz `DROP DATABASE ... WITH (FORCE)` e `DROP ROLE`. |
| `postgres/bind` | Os valores (`host`, `port`, `database`, `username`) vêm dos `params` do item da política, e a senha vem do Secret `params.secretRef` de `platform-resources`. Esse Secret precisa da label `platform.wasp.silvios.me/bindable=true` (`store.BindSources`), e só a chave `password` é copiada para `apps`. Nada é criado nem apagado no banco, e o delete apaga só a cópia. |

## Permissões

- **Em `platform-system`:**
  - lê revisões, `BindingPolicy`s, `environments`, `versions` e `components`;
  - cria e corrige os `resourcerequests` e o status deles;
  - cria `resources` do catálogo.
- **Em `platform-resources`:** cria, lê e apaga `secrets` (inclusive lê `shared-pg-admin`, a senha de admin da instância compartilhada). O `bind` só copia os Secrets com a label `bindable`. O Forager nunca lê os Secrets de `platform-system`, onde ficam as credenciais do SCM.
- **No vcluster:** o acesso vem do kubeconfig admin de `Environment.status.kubeconfigData`, pelo mesmo endereço que o provider `workload` usa.

## Testes

```bash
uv sync
uv run pytest
```
