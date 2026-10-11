# Adopt or Build Spike

Issue [#207](https://github.com/smsilva/wasp-idp/issues/207), com uma sub-issue por parte: Kargo ([#255](https://github.com/smsilva/wasp-idp/issues/255)), resolução de recursos ([#256](https://github.com/smsilva/wasp-idp/issues/256)), Kratix ([#257](https://github.com/smsilva/wasp-idp/issues/257)) e recomendação ([#258](https://github.com/smsilva/wasp-idp/issues/258)).

## Pergunta

Para cada peça ainda em desenho (versões, promoção, resolução de recursos, método de provisionamento): adotar um projeto existente atrás da Platform API ou construir? O critério do [ADR 0022](../../adr/0022-kube-api-as-platform-source-of-truth.md) vale para todas: o cliente (CLI, portal, agente) fala só com a Platform API e nunca vê o formato dos CRDs de terceiros.

As respostas abaixo vêm do que foi executado no `platform-local` (k3d), não só da documentação. O que não rodou está marcado como tal, com o motivo.

## 1. Kargo: versões e promoção

Executado em 2026-10-11 com o Kargo v1.12.3 (chart `oci://ghcr.io/akuity/kargo-charts/kargo`) e o cert-manager v1.21.1 no `platform-local`. Os manifests usados estão em [`2026-10-11-adopt-or-build-spike/kargo/`](2026-10-11-adopt-or-build-spike/kargo/).

### Montagem

- **Imagem de teste:** o repo descartável `smsilva/kargo-spike` publica `ghcr.io/smsilva/kargo-spike` pelo workflow [`publish-workflow.yaml`](2026-10-11-adopt-or-build-spike/kargo/publish-workflow.yaml). Uma tag `vX.Y.Z` gera `X.Y.Z`; um push em outra branch gera `0.2.0-<branch>.<run>`; um `workflow_dispatch` aceita `version` e `request-id`, e o `request-id` vira a anotação OCI `me.silvios.wasp.request-id`. O `greeting-api` não serve porque só publica tags de SHA.
- **Warehouses:** `releases` (SemVer, `constraint: ">=0.0.0"`) e `branch-feat-x` (`constraint: ">=0.0.0-0"` com `allowTagsRegexes` no sufixo da branch).
- **Stages:** `dev` (Freight direto do Warehouse) e `prod` (Freight verificado em `dev`), cada um apontando para um vcluster criado por `platform environment create`.
- **Promoção sem GitOps:** um passo `http` faz `PATCH` (strategic merge) da imagem de um Deployment na API do vcluster, autenticado pelo token de uma ServiceAccount com só `get`/`patch` em Deployments do namespace `app`. O token fica num Secret do Project com o label `kargo.akuity.io/cred-type: generic`, lido por `${{ secret(...).token }}`.

### Respostas

**1. Versões: o Warehouse substitui o índice de versões da #206?** Não.

- **De onde vem a versão:** da tag. Com `SemVer`, `>=0.0.0` ignora pré-releases e `>=0.0.0-0` as inclui; `allowTagsRegexes` isola as de uma branch. As duas seleções funcionaram como esperado.
- **Anotações OCI:** o Freight copia as anotações do manifest para `images[].annotations`, incluindo `org.opencontainers.image.source`/`.revision` e o `request-id`. Elas são só metadado, não critério de seleção.
- **Pegadinha do build:** o GHCR só guarda anotações num manifest OCI. O `docker/build-push-action` sem `docker/setup-buildx-action` usa o driver `docker`, que publica manifest Docker v2 e descarta `annotations` e `oci-mediatypes=true` sem erro. Foram necessárias duas correções no workflow até a anotação aparecer.
- **O Warehouse não é um índice:** a cada varredura ele cria Freight só para o artefato mais novo. `0.1.0` e `0.3.0` foram descobertos (`status.discoveredArtifacts`, até `discoveryLimit`, máximo 100) e nunca viraram Freight. Um Freight antigo pode ser criado à mão: o nome é um hash do conteúdo, então criar de novo é idempotente. Mas aí as anotações não são preenchidas.
- **Achar o build da plataforma:** o `request-id` está em `images[].annotations`, que não é label. Achar o Freight de um pedido exige listar os Freights do Project e filtrar no cliente.
- **Latência:** o polling tem piso de 5 minutos (`MIN_WAREHOUSE_RECONCILIATION_INTERVAL`). Com a anotação `kargo.akuity.io/refresh` (ou um webhook receiver no `ProjectConfig`), o Freight saiu em 6 s.
- **Gate do Score:** não há onde encaixar. O `freightCreationCriteria` é uma expressão sobre os artefatos e não roda validação externa. A #206 exige que uma versão só exista depois do gate e recusa `VersionConflict`; o Warehouse não faz nenhum dos dois.

**2. Promoção: cobre "ligar uma versão a um ambiente"? Exige GitOps?**

- **Cobre:** `dev` recebeu a `0.4.0`, `prod` recebeu o mesmo Freight depois, e o webhook de admissão recusou promover para `prod` um Freight que não passou por `dev` ("Freight is not available to this Stage"). Verificação, histórico por Stage e aprovação vêm prontos.
- **Não exige GitOps, mas é o caminho nativo:** dos 60 passos embutidos, nenhum aplica manifests num cluster. O fluxo documentado é `git-clone` → `kustomize-set-image` → `git-commit`/`git-push` → `argocd-update`. O `custom-steps` (imagem própria, por exemplo com `kubectl`) é exclusivo da Akuity Platform, em alpha. O que funcionou no OSS foi o passo `http` contra a kube API do vcluster, com três tropeços de template: `body` precisa de `quote(...)`, porque o JSON renderizado volta como objeto; `}}` dentro de um literal de mapa fecha o delimitador `${{ }}`; e um `successExpression` sem `failureExpression` deixa o passo em `Running`, repetindo a cada 30 s, sem mostrar a resposta. O passo `http` também não aceita uma CA própria (não há campo para isso), então contra o certificado autoassinado do vcluster o spike precisou de `insecureSkipTLSVerify: true`. Isso aceita qualquer servidor e expõe o token a quem interceptar a conexão: é um atalho de spike, não um modelo para uso real, e é mais um motivo contra esse caminho.
- **`StateWriter` (ADR 0022):** a promoção do Kargo fica *ao lado* do `StateWriter`, não atrás dele. Quem escreve no destino são os passos do Stage, com credenciais guardadas no Kargo. Para manter a Platform API como único escritor, o passo `http` chamaria a própria Platform API, e o Kargo viraria só o orquestrador de Stages. Isso funciona, mas a credencial da Platform API passa a morar no Kargo.

**3. Fachada: dá para expor `build list` e `release create`/`promote` sem o cliente ver CRDs do Kargo?** Dá, com ressalvas.

- **`promote`:** cria um `Promotion` (`spec.stage`, `spec.freight`), e as recusas do webhook de admissão viram erros da API. O estado vem de `Stage.status` e `Freight.status` (`currentlyIn`, `verifiedIn`).
- **`build list`:** não sai bem do Kargo, pela resposta 1. Seria uma junção de `discoveredArtifacts`, que não é Freight, com Freights filtrados por anotação.
- **Dois modelos de autorização:** o Kargo tem RBAC e API próprios por Project (`kargo-api`). Atrás da fachada, a Platform API usaria uma ServiceAccount com acesso a todos os Projects, e o dono/time continuaria decidido pela Platform API, como hoje (ADR 0026).

**4. Ambientes efêmeros: um Stage pode nascer e morrer com um `Environment` de 3 dias?**

- **Stage por ambiente funciona:** criar o Stage `env-kargo-pr1` e promover levou menos de 1 s. Apagar o Stage apaga as Promotions dele.
- **Sobra um resto:** o Freight continua com `status.currentlyIn.env-kargo-pr1` depois que o Stage foi apagado. Em ambientes de 3 dias, esse resto se acumula nos Freights.
- **Target é o modelo certo, mas é pago:** o v1.12 traz `Target` (um destino com `params` livres, lidos nos passos como `target.params.<x>`) e `PromotionRequest`. Um Stage com `spec.targets.selectors` governa as Targets por label, e o modelo prevê Targets descobertas no meio de uma promoção. Os CRDs são instalados no OSS, mas o controller responde **"PromotionRequests are a Kargo Enterprise-only feature"** (`reason: EnterpriseOnlyFeature`), e um Stage com selectors recusa `Promotion` comum. Detalhe adicional: o schema exige `spec.targets`, apesar de o comentário do campo dizer que a ausência pede resolução automática.

**5. Custo operacional no `platform-local`:**

| Componente | Pods | Memória (em uso, depois do teste) | Instalação (`helm --wait`) |
|---|---|---|---|
| cert-manager | 3 | ~72 MiB | 22 s |
| Kargo | 5 (`api`, `controller`, `management-controller`, `webhooks-server`, `external-webhooks-server`) | ~107 MiB | 22 s |

A instalação exige `api.adminAccount.passwordHash` (bcrypt) e `tokenSigningKey`. Para a promoção nativa (GitOps), soma-se o ArgoCD, que o `platform-local` não tem hoje.

Na desinstalação, apague os Projects e espere os namespaces sumirem *antes* do `helm uninstall`. Stages e ServiceAccounts têm o finalizer `kargo.akuity.io/finalizer`, e sem o controller eles prendem o namespace em `Terminating` até o finalizer ser removido à mão.

### Recomendação preliminar

| Peça | Preliminar | Motivo |
|---|---|---|
| Versões (#206) | **Construir** o índice da #206 | O Warehouse cria Freight só do artefato mais novo, não tem gate do Score nem `VersionConflict`, e acha o `request-id` só por varredura. O contrato de build da #206 (`run-name` com `request-id`, label `org.opencontainers.image.version`) continua; vale acrescentar as anotações OCI no manifest (`source`, `revision`, `version`, `request-id`), com `setup-buildx-action`, para não fechar a porta a um Warehouse no futuro. |
| Promoção (tópico 6) | **Adiar** o Kargo, construir um `Release` mínimo atrás do `StateWriter` | No OSS, aplicar sem GitOps é contorno (`http`). O modelo para ambientes efêmeros (Targets) é Enterprise, e um Stage por ambiente deixa resto no Freight. O Kargo volta a valer quando a promoção de produção for por GitOps (`GitCommitWriter`), com aprovação e verificação, para um conjunto fixo de Stages. |
| Nome do conceito | Inclinação para `promote`/`Promotion` | Evita o conflito com o GitHub Release que a #206 aponta e é o vocabulário do Kargo, se ele for adotado depois. Decisão final na #258. |

A consolidação, os ADRs e os comentários nas issues afetadas ficam na #258.

## 2. Resolução de recursos: Radius, KubeVela e `score-k8s`

_Pendente (#256)._

## 3. Kratix: múltiplos métodos de provisionamento

_Pendente (#257)._

## 4. Recomendação

_Pendente (#258)._
