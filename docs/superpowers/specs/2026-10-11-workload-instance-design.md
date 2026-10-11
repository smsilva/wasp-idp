# Workload Spec and Workload Instance — Design

Issue [#262](https://github.com/smsilva/wasp-idp/issues/262). Decisão registrada no [ADR 0033](../../adr/0033-workload-spec-and-workload-instance.md). Relacionadas: [#206](https://github.com/smsilva/wasp-idp/issues/206) (índice de versões), [#263](https://github.com/smsilva/wasp-idp/issues/263) (Forager), [#202](https://github.com/smsilva/wasp-idp/issues/202) (deck), ADR 0022, 0023, 0030.

## Contexto

A #262 nasceu como "promoção": o ADR 0030 trocou o CRD `Release` do ADR 0022 por um CRD `Promotion`, um objeto por ato (component, versão do índice, `Environment`). Ao desenhar a CLI pela jornada do dev, o termo não se sustentou:

- No mercado, "promote" quase sempre significa levar uma versão de um ambiente **para o próximo** (Kargo, Google Cloud Deploy, Heroku Pipelines, Spinnaker, Codefresh). Num ambiente efêmero, ou no primeiro deploy, não há ambiente de origem.
- Quando não há origem, quase todo mundo chama o ato de deploy (Octopus, Humanitec, Qovery, Radius, Waypoint). O Google Cloud Deploy chama de rollout.
- Um objeto por ato registra o que aconteceu, mas não responde "o que está rodando aqui e como está". O Port modela essa pergunta como um blueprint "Running Service" (serviço × ambiente), e é dele que os dados são coletados.

A jornada que guiou o desenho: um component declarado no catálogo, um ambiente de demonstração, o plano do que roda nele (três components do Bookinfo), a ação e o monitoramento.

## Conceitos

| Conceito | O que é | Analogia Helm |
|---|---|---|
| **Workload Spec** | o Score (`app-spec.yaml`) de uma versão, imutável, guardado no índice de versões | Chart numa versão |
| **Workload Instance** | uma Workload Spec viva num `Environment`, mantida pela plataforma, fonte dos dados de runtime | Release |
| **Revisão** | cada ato sobre uma instância (deploy, rollback, remove), imutável, com o resultado | revisão da release |
| **Plano do ambiente** | o conjunto das instâncias de um ambiente, com versão e overrides | helmfile |

"Workload" segue o Score, que se define como *workload specification*. A frase para a documentação da CLI: **a Workload Instance é para a Workload Spec o que uma Helm Release é para um Chart.**

Onde a analogia quebra:

- O Chart traz os templates; o Score declara o que a aplicação precisa, e quem renderiza é a plataforma.
- A Release mora no cluster de destino; a instância mora no control plane, porque a credencial do vcluster não sai da plataforma.
- O status da Release é da instalação; o da instância acompanha a saúde em runtime continuamente.

"Release" continua fora de questão como nome, pela colisão com o GitHub Release (ADR 0030). "Promote" fica reservado para um futuro gate entre ambientes ("leva para `prod` o que está em `dev`"), que criaria uma revisão nova.

## Catálogo × runtime

A Workload Instance **fica fora do catálogo**. O ADR 0023 já separa a identidade lógica (`Resource`) da instância num ambiente (`ResourceRequest`, fora do catálogo); a instância está para o `Component` assim como o `ResourceRequest` está para o `Resource`. A instância muda a cada deploy, nasce e morre com ambientes de 3 dias, e herda dono e acesso do `Component` e do `Environment`.

A Workload Spec **vem do catálogo, mas não é uma entidade**: ela pertence à `Version` (grupo `catalog.platform.wasp.silvios.me`). Não existe kind `Workload` no catálogo.

| Camada | Pergunta | Objetos |
|---|---|---|
| Catálogo | o que existe e de quem é | Domain, System, Component, API, Resource, Version (com a Workload Spec) |
| Entrega | o que foi pedido e como terminou | Build, WorkloadRevision |
| Runtime | o que está rodando agora | Environment, WorkloadInstance, ResourceRequest |

O catálogo mostra as instâncias como um join de leitura (`runningIn` no `catalog component get`), sem guardá-las.

## Mais de uma instância por component

No mesmo ambiente pode haver mais de uma instância do mesmo component. O caso do deck é o **shared sandbox**: o baseline estável e a versão de um PR, com o tráfego dividido por header. Canary e blue-green são outro caso: transitórios, dentro de uma instância, como estratégia de rollout. Só o primeiro molda o modelo agora.

A fase 1 roda uma instância por component, mas nada é chaveado só pelo component:

1. A identidade é (ambiente, nome da instância); o component é um atributo. Na fase 1 o nome da instância é o nome do component, e a API recusa uma segunda instância do mesmo component. É uma validação, não uma premissa do modelo.
2. No vcluster, as recommended labels separam os dois: `app.kubernetes.io/name` é o component e `app.kubernetes.io/instance` é a instância.
3. O seletor do Service inclui `app.kubernetes.io/instance` desde a fase 1. Sem isso, os pods de uma futura `reviews-pr-42` entrariam no balanceamento do Service `reviews` sem ninguém pedir.
4. Um namespace por ambiente (`apps`), não por component: o Score usa nomes curtos (`RATINGS_URL: http://ratings`), que só resolvem no mesmo namespace.
5. O arquivo de plano é chaveado pela instância, com `component` igual à chave por padrão.
6. As revisões pertencem à instância.

| Fase | Entrega |
|---|---|
| 1 | uma instância por component; `--component` identifica a instância |
| 2 | instâncias extras sem tráfego (`--instance`), cada uma com o próprio Service |
| 3 | roteamento por header (sandbox) ou peso (canary); exige mesh ou Gateway API nos vclusters e propagação do header nas chamadas internas (contrato do template) |

## CLI

```bash
platform workload spec validate \
  --file app-spec.yaml

platform workload spec get \
  --component reviews \
  --version 2.1.0-rc.1

platform workload spec get \
  --component reviews \
  --branch feat/v3

platform workload deploy \
  --component reviews \
  --branch feat/v3 \
  --environment demo \
  --replicas 2 \
  --wait

platform workload apply \
  --file demo.yaml \
  --dry-run

platform workload list \
  --environment demo

platform workload get \
  --component reviews \
  --environment demo

platform workload history \
  --component reviews \
  --environment demo

platform workload rollback \
  --component reviews \
  --environment demo \
  --revision 2

platform workload remove \
  --component ratings \
  --environment demo
```

| Comando | Parâmetros | Observações |
|---|---|---|
| `spec validate` | `--file` (padrão `app-spec.yaml`) | o mesmo gate do build: schema, tipos de resource, resources no catálogo |
| `spec get` | `--component`; `--version` ou `--branch` | sem nenhum dos dois, a versão mais recente; `--branch` escolhe a mais recente construída da branch |
| `deploy` | `--component`, `--environment`; `--version` ou `--branch`; `--replicas`, `--wait` | `--branch` é resolvido no pedido e a versão fica fixa na revisão; a instância não segue a branch sozinha |
| `apply` | `--file`; `--dry-run`, `--prune`, `--wait` | o ambiente vem de dentro do arquivo |
| `list` | `--environment` | uma linha por instância: versão, `Ready`, réplicas, revisão, URL |
| `get` | `--component`, `--environment` | detalhe de `reviews@demo` |
| `history` | `--environment`; `--component` | as revisões, com autor e resultado |
| `rollback` | `--component`, `--environment`; `--revision` (padrão: a anterior) | cria uma revisão nova com a versão e os overrides da escolhida |
| `remove` | `--component`, `--environment` | gera uma revisão `remove`; o histórico fica até o ambiente ser apagado |

"Instance" não aparece nos comandos: com `--environment`, `workload` já é uma instância. O nome curto de uma instância é `reviews@demo`. Overrides por ambiente (`--replicas`) vão para a revisão, nunca para a spec.

O arquivo de plano:

```yaml
environment: demo
workloads:
  productpage:
    version: 1.4.0
  reviews:
    version: 2.1.0-rc.1
    replicas: 2
  ratings:
    version: 1.0.2
```

## CRDs

Dois CRDs no grupo `platform.wasp.silvios.me`, namespace `platform-system`. Não há CRD de plano: o plano é a soma das instâncias.

### `WorkloadRevision`

O ato, imutável (CEL `self == oldSelf` no `spec`). Substitui a `Promotion` do ADR 0030.

- **Nome:** `<environment>.<instance>.<n>` (ex.: `demo.reviews.3`), como os Secrets `sh.helm.release.v1.<nome>.v<n>` do Helm.
- **`spec`:** `environment`, `instance`, `component`, `revision`, `action` (`deploy`, `rollback`, `remove`), `version`, `image`, `digest`, `commit`, `overrides.replicas`, `requestedBy`, `requestId`, `rollbackOf`.
- **`status`:** condition `Ready` com reason, `startedAt`, `finishedAt`.
- **Owner reference** para o `Environment`, não para a instância: o histórico sobrevive a um `remove`.

Reasons: `Pending`, `EnvironmentNotReady`, `SpecNotIndexed`, `ResourcesNotSupported` (até a #263), `UnsupportedSpec`, `ApplyFailed`, `RolloutFailed`, `Superseded`, `Succeeded`.

### `WorkloadInstance`

O vivo, escrito só pelo controller.

- **Nome:** `<environment>.<instance>`.
- **`spec`:** `environment`, `instance`, `component`. O desejado é sempre a última revisão.
- **`status`:** `revision`, `version`, `image`, `replicas` (desired/ready), `url`, `resources`, condition `Ready` de runtime com reason `Available`, `Progressing` ou `Degraded`.
- **Owner reference** para o `Environment`.

Os dois levam as labels `platform.wasp.silvios.me/environment`, `/component` e `/instance`.

### Workload Spec na `Version`

O `scm_github` passa a gravar o Score validado em `Version.spec.appSpec` (objeto com `x-kubernetes-preserve-unknown-fields`) ao registrar a versão. A promoção não depende mais do GitHub, e o Forager encontra o Score no mesmo lugar. Uma versão indexada antes disso não tem o campo: a revisão termina com `SpecNotIndexed`.

A validação (`spec_errors` do `scm_github`) vai para um lib compartilhado `platform/libs/score` (pacote `wasp_score`), no molde do `wasp_templates`, usado pelo `scm_github` e pela API.

## Escrita e concorrência

- A API valida, autoriza, grava no journal e escreve **só a `WorkloadRevision`**, via `StateWriter`.
- O número da revisão vem do nome: a API cria `<env>.<instance>.<último+1>`. Dois pedidos simultâneos colidem no nome; o segundo recebe `AlreadyExists` da kube API e a API responde 409. Concorrência otimista, sem lock.
- Vence a mais nova: o controller fecha uma revisão pendente como `Superseded` se houver outra mais nova para a mesma instância.
- `--branch` é resolvido na API (a `Version` mais recente com `spec.branch` igual, pelo `createdAt`). A revisão grava a versão concreta.
- `rollback` copia versão e overrides da revisão de origem para uma revisão nova (`action: rollback`, `rollbackOf: n`).
- `apply` recebe o plano, calcula o diff contra as instâncias (mesmo precedente do `catalog import`, #190) e cria uma revisão por instância que muda. `--dry-run` só devolve o diff; `--prune` gera revisões `remove` para instâncias fora do arquivo.

## Controller

Um provider novo, `platform/providers/workload`, que funciona com qualquer `Environment` `Ready` com `kubeconfigData`, sem depender do `local_vcluster`.

1. Observa as revisões. Para a mais nova de cada instância, lê o `Environment` e a `Version`.
2. Gera, a partir do Score, um Deployment e um Service no namespace `apps` do vcluster: `image: .` vira `image@digest`; labels `app.kubernetes.io/name` e `app.kubernetes.io/instance`; seletor do Service com as duas.
3. Aplica com server-side apply e acompanha o rollout. Fecha a revisão como `Succeeded` ou `Failed` e cria ou atualiza a `WorkloadInstance`.
4. Resync a cada 30 s para atualizar a saúde da instância.
5. Para `remove`: apaga Deployment e Service do vcluster e apaga a instância; as revisões ficam.

Subconjunto do Score aceito na fase 1: `containers` (image, command, args, variables, resources, probes `httpGet`) e `service.ports`. Outro campo termina com `UnsupportedSpec`; `resources` declarados terminam com `ResourcesNotSupported` até a #263.

## API

| Rota | CLI |
|---|---|
| `POST /v1/workload-specs:validate` | `workload spec validate` |
| `GET /v1/catalog/components/{component}/spec?version=\|branch=` | `workload spec get` |
| `POST /v1/environments/{environment}/workloads/{instance}/revisions` | `deploy`; `rollback` com `{"rollbackTo": n}` |
| `DELETE /v1/environments/{environment}/workloads/{instance}` | `remove` |
| `GET /v1/environments/{environment}/workloads` e `/{instance}` | `list`, `get` |
| `GET /v1/environments/{environment}/revisions?instance=` | `history` |
| `POST /v1/environments/{environment}/workloads:apply` | `apply` |
| `GET /v1/catalog/components/{component}` com `runningIn` | `catalog component get` |

- **Escrita** (revisões, remove, apply): `can_use` no `Environment` **e** membro do time dono do component ou `platform-admins`.
- **Leitura:** `can_use` no `Environment`. O `runningIn` do catálogo lista só os ambientes que a pessoa pode usar.
- `users_of` (`teams.py`) não muda: a instância não tem `owner` próprio.

## Divisão em sub-issues

| Sub-issue | Entrega |
|---|---|
| 262.1 Workload Spec | Score na `Version`, lib `wasp_score`, `spec validate`, `spec get` (com `--branch`), docs e passo na cli-smoke |
| 262.2 Workload Instance | CRDs `WorkloadRevision` e `WorkloadInstance`, provider `workload`, `deploy`, `list`, `get`, `history`, `rollback`, `remove`, `runningIn` no catálogo, docs e cli-smoke |
| 262.3 Plano do ambiente | `apply` com `--dry-run`, `--prune` e `--wait` |

Backlog: fase 2 (instâncias extras), fase 3 (roteamento). O deck (#202) troca `release`/`promote` por `workload deploy`/`history`.

## cli-smoke

A cli-smoke não roda um build real. O passo de 262.2 cria, por `kubectl`, uma `Version` com imagem pública por digest e Score sem resources, cria um ambiente com `--wait`, faz `workload deploy --wait`, confere `list`, `history` e `rollback`, e testa as recusas: versão fora do índice, Score com `resources` (`ResourcesNotSupported`) e pessoa fora do time dono.

## Decisões em aberto

- **Retenção de revisões:** sem limite na fase 1 (ambientes efêmeros, owner reference limpa). Um limite por instância entra com o projector no Postgres (ADR 0022), que guarda o histórico longo para as métricas DORA.
- **Imagem privada no GHCR:** fora da fase 1, registrada em `aws/docs/known-broken.md`. A fase 1 promove só imagens que o vcluster consegue puxar.
- **Seguir a branch** (cada build novo da branch gera um deploy): automação sobre o `deploy`, fase posterior.
- **Gate entre ambientes** (`promote`): fora da primeira fatia.
