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

Executado em 2026-10-11 no `platform-local` com `score-k8s` 0.20.0, KubeVela v1.11.0 (chart `kubevela/vela-core`) e Radius v0.61.1 (`rad install kubernetes`), uma ferramenta por vez. Os artefatos estão em [`score-k8s/`](2026-10-11-adopt-or-build-spike/score-k8s/), [`kubevela/`](2026-10-11-adopt-or-build-spike/kubevela/) e [`radius/`](2026-10-11-adopt-or-build-spike/radius/).

### Montagem

- **App:** uma cópia do `app-spec.yaml` do template `python-service`, com um recurso `db` do tipo `postgres`. O container é um `psql` que repete `select current_database(), current_user` até conectar; um cenário só conta como executado quando esse `select` respondeu.
- **Base dos cenários** ([`shared/shared-db.yaml`](2026-10-11-adopt-or-build-spike/shared/shared-db.yaml)): uma instância Postgres compartilhada no namespace `shared-db`, alvo do **compose**, e nela um database `orders_restored` com usuário próprio, criado à mão, que faz o papel do restaurado de backup no **bind**.
- **Ambientes:** um namespace por cenário no cluster do `platform-local`. O KubeVela também foi testado contra um vcluster de `Environment`.

### `score-k8s`

- **Entrada:** Score, mas só com `apiVersion: score.dev/v1b1`. O `platform/v1` do template é recusado pelo schema. O resto do arquivo é Score sem mudança, então a plataforma traduziria só o cabeçalho.
- **Modos:**
  - **provision** e **bind** funcionaram como provisioners `template://`. No bind, o provisioner só devolve valores, e a senha vem de um Secret existente que o score-k8s não gerencia (`encodeSecretRef`).
  - **compose** não funcionou como template: o `--namespace` do `generate` sobrescreve o `namespace: shared-db` do Job, que roda longe da instância. Funcionou como provisioner `cmd://` ([`compose-postgres`](2026-10-11-adopt-or-build-spike/score-k8s/compose-postgres)): um script que, na geração, cria role e database via `kubectl exec` e devolve o Secret do app como manifest. Gerar de novo reaproveita o `state` e não duplica nada.
- **Precedência:** vale o primeiro provisioner que casa, na ordem lexical dos arquivos em `.score-k8s/` e por `type`/`class`/`id`. Com `00-branch`, `10-env` e `zz-default`, a ordem branch > ambiente > padrão funcionou. Um provisioner com `class: restored` só entra quando a branch pede (`--override-property resources.db.class=restored`). Ressalva: o `state` fixa o provisioner na primeira geração, e trocar o modo de um ambiente que já existe exige limpar o state.
- **Atrás da Platform API:** não há CRD nem controller; é um gerador. Mas o `state` é um arquivo local com as senhas em claro, que a plataforma teria de guardar com segurança. Também não há reconciliação nem ciclo de vida: nada desfaz o compose (os databases criados nos testes ficaram na instância compartilhada).
- **Custo:** zero no cluster.

### KubeVela

- **Entrada:** só a própria `Application` (OAM). Não há integração com Score; a plataforma traduziria o Score para uma `Application`.
- **Modos:** os três funcionaram, mas o compose ficou desajeitado.
  - O recurso vira um componente com `ComponentDefinition` em CUE (`postgres-dedicated`, `postgres-database`).
  - **compose:** o `topology` força o namespace de tudo, igual ao score-k8s. Funcionou separando o Job num componente implantado por um passo `deploy` próprio com `topology` em `shared-db`, mais um `override` com `selector`, mais um componente de Secret vazio nos outros ambientes.
  - **bind:** um `override` com `selector` tira o componente `db` e aponta o app para o Secret existente.
  - **Segredos:** o CUE é determinístico e não gera senha. Ela entra como propriedade da `Application`, em claro.
- **Precedência:** `override`s aplicados na ordem da lista `policies` do passo `deploy`. No ambiente `branch`, o override de bind aplicado depois do de compose venceu.
- **Atrás da Platform API:** a API geraria uma `Application` por app. Porém:
  - Por padrão o controller aplica com as próprias permissões; isolar exige instalar com `authentication.withUser` (impersonação).
  - **Ambientes em vcluster:** cada vcluster precisa ser registrado com `vela cluster join`, com um endereço que a CLI e o `cluster-gateway` alcancem e um SAN válido. Funcionou com o IP do LoadBalancer e `tls-server-name`. O namespace de destino não é criado sozinho.
  - O `vela cluster detach` é aceito com a `Application` ainda implantada, que segue reportando `running`. Apagá-la depois deixa os objetos órfãos no vcluster, então a ordem tem de ser apagar a `Application` antes do `detach`.
- **Custo:** 2 pods (`vela-core`, `cluster-gateway`), ~82 MiB, 70 s de instalação. Apagar a `Application` removeu tudo o que ela criou, inclusive o Job em `shared-db`, mas não o database que o Job criou.

### Radius

- **Entrada:** Bicep, sobre os tipos `Radius.*` (2025-08-01-preview). Não aceita Score. O Bicep exige um `bicepconfig.json` com a extensão `radius`, e o `rad bicep download` grava o binário em `~/.rad/bin`.
- **Duas gerações de API convivem:** `Applications.*` (2023-10-01-preview) e `Radius.*` (2025-08-01-preview). Vários comandos exigem `--preview` para a geração nova. Sem ele, `rad env delete` falha sem avisar, e `rad app delete` responde "deleted" sobre um `Applications.Core/applications` e não apaga o app real.
- **Modos:** os três funcionaram, com recipes por ambiente via *Recipe Packs*.
  - **provision:** a recipe oficial do pack `kubernetes` (que roda o Postgres num `Deployment`, sem volume).
  - **compose:** uma recipe Terraform própria (provider `cyrilgdn/postgresql`, senha de admin lida de um Secret). O state do Terraform fica num Secret em `radius-system`. É a única das três ferramentas que **desfaz o compose**: apagar o app (com `--preview`) removeu o database.
  - **bind:** uma recipe que só devolve valores. Mas o tipo `postgreSqlDatabases` exige `username` e `password` do *pedido*, e a senha chega ao container pelo Secret do próprio app (a conexão não carrega campos sensíveis). O bind só conectou porque o deploy passou a senha do banco restaurado: **o desenvolvedor precisa conhecer a credencial**. Os tipos novos não têm o `resourceProvisioning: manual` dos antigos.
- **Precedência:** uma recipe por tipo por ambiente. Dois packs com o mesmo tipo no mesmo ambiente são recusados (`Conflict: ... is defined in multiple recipe packs`). Não há empilhamento branch > ambiente > padrão; um override por branch seria outro ambiente.
- **Escopo de nomes:** o nome do recurso é único por *resource group*, não por ambiente. O mesmo app em dois ambientes do mesmo grupo dá conflito, e o padrão vira um grupo por ambiente. Cada ambiente também exige um namespace exclusivo, já existente.
- **Atrás da Platform API:** o Radius tem API e armazenamento próprios (UCP, guardado no CRD genérico `resources.ucp.dev`). A Platform API seria cliente do UCP, não da kube API.
- **Custo:** 8 pods (UCP, dois resource providers, `bicep-de`, controller, dashboard e o Contour, que vem junto), ~744 MiB com carga, sendo ~224–490 MiB só da `dashboard`. A instalação levou 70 s.
- **Desinstalação:** o `rad uninstall kubernetes` deixou o APIService `v1alpha3.api.ucp.dev` apontando para um serviço apagado. Com a descoberta de API falhando, **nenhum namespace do cluster terminava de ser apagado**, inclusive os de `Environment`, até o APIService ser removido à mão.

### Respostas

| Pergunta | `score-k8s` | KubeVela | Radius |
|---|---|---|---|
| 1. Aceita Score? | Sim (só `apiVersion: score.dev/v1b1`) | Não; `Application` (OAM) | Não; Bicep |
| 2. Os três modos por ambiente? | provision e bind por template; compose só por `cmd://` na geração, sem desfazer | Sim, com compose desajeitado (componente e passo à parte) | Sim; compose com Terraform e desfeito no delete; bind exige que o desenvolvedor conheça a senha |
| 2b. Bind a recurso não gerenciado? | Sim, valores mais Secret existente | Sim, override para um Secret existente | Só devolvendo valores; senha vem do pedido |
| 3. Precedência branch > ambiente > padrão? | Sim: ordem dos arquivos mais `class` | Sim: ordem dos `override`s no passo `deploy` | Não: uma recipe por tipo por ambiente |
| 4. Atrás da Platform API sem expor CRDs? | Sim (gerador sem CRDs), mas o state com senhas é um arquivo local | Sim (a API gera a `Application`), com impersonação e registro de cada vcluster | Sim, como cliente do UCP; dois modelos de API e de nomes |
| 5. Maturidade | CNCF Sandbox (spec Score, 2024); 0.x; 23 releases em 12 meses; 49 estrelas | CNCF Incubating (2023); v1.11; 13 releases em 12 meses; ~7,9 mil estrelas | CNCF Sandbox (2024); 0.61; 36 releases em 12 meses; API em preview, duas gerações |
| 5b. AWS real | Nenhum provisioner AWS pronto (cabe por `cmd://`) | Não testado (há addon de Terraform) | No repositório de tipos, só uma recipe AWS (MySQL, Terraform); nenhuma de Postgres |
| Custo no cluster | Nenhum | 2 pods, ~82 MiB | 8 pods, ~744 MiB |

### Recomendação preliminar

| Peça | Preliminar | Motivo |
|---|---|---|
| Resolução de recursos (Forager, fatia 4 do catálogo) | **Construir**, mantendo o Score como formato e copiando o modelo de provisioners do `score-k8s` | Só o score-k8s aceita Score e empilha branch > ambiente > padrão, mas ele é um gerador sem ciclo de vida, com o state (e as senhas) num arquivo local e o compose fora do modelo declarativo. O KubeVela cobre os três modos e a precedência, mas troca o Score pelo OAM e põe a lógica de modo em CUE e em passos de workflow. O Radius é o único que desfaz o compose, mas exige Bicep, não empilha precedência, força a credencial do bind no pedido e é o mais pesado e instável (duas gerações de API, uninstall que trava o cluster). O que vale levar: casar provisioner por `type`/`class`/`id` com camadas ordenadas (score-k8s), compose com ciclo de vida e state fora do app (recipes Terraform do Radius), e o bind como "só valores mais referência a Secret". |

A consolidação e os ADRs ficam na #258.

## 3. Kratix: múltiplos métodos de provisionamento

_Pendente (#257)._

## 4. Recomendação

_Pendente (#258)._
