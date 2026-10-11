# Adopt or Build Spike

Issue [#207](https://github.com/smsilva/wasp-idp/issues/207), com uma sub-issue por parte: Kargo ([#255](https://github.com/smsilva/wasp-idp/issues/255)), resolução de recursos ([#256](https://github.com/smsilva/wasp-idp/issues/256)), Kratix ([#257](https://github.com/smsilva/wasp-idp/issues/257)) e recomendação ([#258](https://github.com/smsilva/wasp-idp/issues/258)).

## Pergunta

Para cada peça ainda em desenho (versões, promoção, resolução de recursos, método de provisionamento): adotar um projeto existente atrás da Platform API ou construir? O critério do [ADR 0022](../../adr/0022-kube-api-as-platform-source-of-truth.md) vale para todas: o cliente (CLI, portal, agente) fala só com a Platform API e nunca vê o formato dos CRDs de terceiros.

As respostas abaixo vêm do que foi executado no `platform-local` (k3d), não só da documentação. O que não rodou está marcado como tal, com o motivo.

## 1. Kargo: versões e promoção

Executado em 2026-10-11 com o Kargo v1.12.3 (chart `oci://ghcr.io/akuity/kargo-charts/kargo`) e o cert-manager v1.21.1 no `platform-local`. Os manifests usados estão em [`2026-10-11-adopt-or-build-spike/kargo/`](2026-10-11-adopt-or-build-spike/kargo/).

### Montagem

- **Imagem de teste:** o repo de teste `smsilva/kargo-spike` publica `ghcr.io/smsilva/kargo-spike` pelo workflow [`publish-workflow.yaml`](2026-10-11-adopt-or-build-spike/kargo/publish-workflow.yaml). Uma tag `vX.Y.Z` gera `X.Y.Z`; um push em outra branch gera `0.2.0-<branch>.<run>`; um `workflow_dispatch` aceita `version` e `request-id`, e o `request-id` vira a anotação OCI `me.silvios.wasp.request-id`. O `greeting-api` não serve porque só publica tags de SHA.
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
| Resolução de recursos (Forager, fatia 4 do catálogo) | **Construir**, mantendo o Score como formato e copiando o modelo de provisioners do `score-k8s` | Só o score-k8s aceita Score e empilha branch > ambiente > padrão, mas ele é um gerador sem ciclo de vida, com o state (e as senhas) num arquivo local e o compose fora do modelo declarativo. O KubeVela cobre os três modos e a precedência, mas troca o Score pelo OAM e põe a lógica de modo em CUE e em passos de workflow. O Radius é o único que desfaz o compose, mas exige Bicep, não empilha precedência, força a credencial do bind no pedido e é o mais pesado e instável (duas gerações de API, uninstall que trava o cluster). O que vale levar: casar provisioner por `type`/`class`/`id` com camadas ordenadas (score-k8s), compose com ciclo de vida e state fora do app (recipes Terraform do Radius), e o bind como "só valores mais referência a Secret". Atenção: o compose monta SQL com nomes vindos do pedido (workload, recurso, ambiente); valide-os como identificadores (`re.fullmatch`, como a API já faz com nomes) ou use os parâmetros de identificador do driver, nunca interpolação de texto. Os artefatos deste spike receberam essa validação depois da execução. |

A consolidação e os ADRs ficam na #258.

## 3. Kratix: múltiplos métodos de provisionamento

Pergunta da [#254](https://github.com/smsilva/wasp-idp/issues/254): o `Environment` numa `CloudAccount` pode ter mais de um método de provisionamento (Crossplane por padrão, OpenTofu como alternativa), como nas Promises do Kratix?

Executado em 2026-10-11 com o `install-all-in-one.yaml` e o `config-all-in-one.yaml` da release `latest` do Kratix (imagem `kratix-platform@sha256:41d133d4…`): o Kratix, um S3 (SeaweedFS) como state store e o Flux. O cert-manager já estava no cluster. Os artefatos estão em [`kratix/`](2026-10-11-adopt-or-build-spike/kratix/). Não houve chamada à AWS: o Crossplane e o tofu-controller não foram instalados, e o teste para no que o Kratix entrega a cada destino.

### Montagem

- **Promise `cloud-environment`** ([`02-promise.yaml`](2026-10-11-adopt-or-build-spike/kratix/02-promise.yaml)): a API é um CRD nosso, `CloudEnvironment` (`spec.cloudAccount`, `spec.method` com `crossplane` como padrão ou `opentofu`, `spec.region`).
- **Pipeline:** um passo que, conforme `spec.method`, escreve:
  - **crossplane:** um `ProviderConfig` com `assumeRoleChain`/`externalID` e uma `VPC`;
  - **opentofu:** um `Terraform` do tofu-controller com backend `kubernetes`.
  
  O passo também grava `destination-selectors.yaml` com o método e devolve `method`/`cloudAccount` no status.
- **Destinos:** dois `Destination`s no mesmo bucket, um por método (`provisioning-method: crossplane|opentofu`), sem consumidor no cluster.

### Respostas

**1. A Promise fica atrás da Platform API sem o cliente ver os CRDs do Kratix?**

Sim, e de um jeito melhor que as outras ferramentas: a API da Promise é um CRD *nosso*, então o `Environment` poderia ser ele.

- **O que o Kratix escreve no status do nosso CRD:** as conditions `ConfigureWorkflowCompleted`, `Reconciled` e `WorksSucceeded`, mais `status.kratix` (pipelines e jobs), `status.healthStatus` e os campos que o pipeline devolve.
- **Contrato com o ADR 0022:** as conditions do `Environment` (`Ready` e reasons) teriam de conviver com as do Kratix. Elas dizem que o pipeline rodou e os manifests foram entregues, não que a infraestrutura está pronta.

**2. Onde mora a escolha do método, e como ela casa com `Environment` e `CloudAccount`?**

- **No teste:** no pedido (`spec.method`). O pipeline traduz o método em seletor de destino; `env-a` (padrão) foi para `aws-crossplane` e `env-b` (`opentofu`) para `aws-opentofu`.
- **Alternativas:** a escolha caberia também na Promise (`destinationSelectors` fixos) ou nos labels do `Destination` (um por conta e método). A `CloudAccount` viraria um ou mais `Destination`s.
- **A escolha é pegajosa:** trocar `spec.method` de `env-a` para `opentofu` **não move o pedido**. A `WorkPlacement` fica no destino antigo, marcada `Misplaced`, e a saída nova (`terraform.yaml`) foi escrita *no destino do Crossplane*, no lugar do `crossplane.yaml`. Com Flux e `prune`, isso apagaria a VPC do Crossplane e entregaria um `Terraform` onde não há tofu-controller. O método tem de ser imutável depois de criado o `Environment`, ou a troca tem de ser uma migração explícita.

**3. Drift e estado em cada método:**

| | Crossplane | OpenTofu (tofu-controller) |
|---|---|---|
| Quem detecta e corrige | O próprio Crossplane, continuamente (o managed resource reconcilia) | O tofu-controller roda `plan` a cada `interval`; com `approvePlan: auto` também aplica (corrige), sem ele só reporta |
| Onde fica o state | Na kube API do cluster de destino (o managed resource) | Num backend; no teste, `kubernetes` (um Secret no cluster de destino), sem segredo na `CloudAccount` |
| Credencial | `ProviderConfig` com `assumeRoleChain` e `externalID` | `role_arn`/`external_id` como variáveis do módulo (`assume_role` no provider AWS) |
| Executado? | Só a geração e a entrega do manifest | Só a geração e a entrega do manifest |

- **O Kratix não detecta drift na nuvem.** Ele reexecuta os pipelines a cada 10 h por padrão (`DefaultReconciliationInterval`, mínimo de 1 minuto, ajustável por Promise), o que só regenera os manifests.
- **O caminho de volta existe:** um agente no destino grava um `HealthRecord`. Simulei um `unhealthy` com `reason: Drifted` ([`04-health-record.yaml`](2026-10-11-adopt-or-build-spike/kratix/04-health-record.yaml)), e o Kratix o levou para `status.healthStatus` do pedido. Quem detecta é outra peça: o Crossplane, o tofu-controller ou um agente próprio. A Syntasso publica um chart `k8s-health-agent`, não testado aqui.

**4. Kratix contra um seletor de métodos mantido pela plataforma:**

- **O Kratix traz:**
  - pipelines em containers por Promise;
  - entrega por state store (Git ou bucket) e GitOps no destino;
  - escalonamento por `Destination`;
  - o canal de saúde (`HealthRecord`);
  - um `DryRun` em preview.
- **O Kratix custa:**
  - três peças a operar (Kratix, state store, Flux ou ArgoCD em cada destino);
  - as conditions dele misturadas às nossas;
  - a semântica de `Misplaced`;
  - uma distribuição sem versão (resposta 5).
- **O seletor próprio custa pouco:** a plataforma já tem o padrão de providers por capacidade (`local_vcluster`, `aws_account`), e a #254 já prevê a seleção de provider por campo (sem conta → `local_vcluster`, com conta → nuvem). Um segundo método é um segundo provider. Cada um escreve direto o que o seu motor consome (managed resources do Crossplane, ou o `Terraform` do tofu-controller) e traduz o estado dele nas conditions do `Environment`.

**5. Maturidade e custo operacional:**

- **Governança:** Apache-2.0, mantido pela Syntasso (que vende o SKE por cima), fora da CNCF; ~780 estrelas.
- **Distribuição:** no GitHub, só uma release rolante `latest` (os manifests mudam no mesmo endereço). A última tag semver é a v0.125.0, de 2024. O chart Helm está em `v0.0.1`. Fixar versão exige guardar o manifest e o digest da imagem.
- **Custo:** 6 pods (Kratix, SeaweedFS e 4 controllers do Flux), ~113 MiB vazio e ~207 MiB com os pedidos; 21 s de instalação. A desinstalação, com pedidos e Promise apagados antes, foi limpa.

### Recomendação preliminar

| Peça | Preliminar | Motivo |
|---|---|---|
| Método de provisionamento (#254) | **Construir, com um método só (Crossplane), e adiar o Kratix** | A Promise como fachada é boa (o CRD é nosso), mas o resto do Kratix (state store, GitOps no destino, conditions próprias) é infraestrutura a mais para um único método, e a escolha de método ficou pegajosa de um jeito perigoso. Se um segundo método for necessário, ele entra como outro provider selecionado por campo, imutável depois de criado o `Environment`, com o OpenTofu pelo tofu-controller e o drift virando condition (`Drifted`), no mesmo papel do `HealthRecord`. |

A consolidação e os ADRs ficam na #258; o resultado vai como comentário na #254.

## 4. Recomendação

Nenhuma peça é adotada. Em todas, o que as ferramentas fazem bem cabe num modelo que a plataforma já tem (CRD próprio, controller, `StateWriter`), e o que elas exigem a mais (GitOps, outro formato de entrada, outra API, infraestrutura de entrega) custa mais do que a parte que economizam. O que vale é copiar os modelos que funcionaram, e cada ADR diz quando a ferramenta volta a ser candidata.

| Peça | Decisão | Motivo | ADR | O que muda nas issues |
|---|---|---|---|---|
| Versões | **Construir** o índice da #206 | O Warehouse cria Freight só do artefato mais novo, não tem gate do Score nem `VersionConflict`, e acha o `request-id` só por varredura. | [0030](../../adr/0030-build-version-index-and-promotion-defer-kargo.md) | **#206:** o desenho continua. O contrato de build ganha manifest OCI com anotações (`source`, `revision`, `version`, `request-id`), o que exige `setup-buildx-action`. O template passa a `apiVersion: score.dev/v1b1`, porque o gate valida o schema do Score e o `platform/v1` é recusado. |
| Promoção | **Construir** uma `Promotion` atrás do `StateWriter`; **adiar** o Kargo | No OSS, aplicar sem GitOps é contorno (`http` com TLS desligado e credencial no Kargo), e o modelo para ambientes efêmeros (`Target`) é Enterprise. | [0030](../../adr/0030-build-version-index-and-promotion-defer-kargo.md) | **#262 (nova, tópico 6):** CRD `Promotion` por ato, com owner reference para o `Environment`. O CRD `Release` do ADR 0022 não é criado. |
| Nome do conceito | **`promote`/`Promotion`** | "release" colide com o GitHub Release, que a #206 já separou. O deck já fala em versão "promoted across Environments". | [0030](../../adr/0030-build-version-index-and-promotion-defer-kargo.md) | **#202:** a etapa `journey-release` e os comandos `platform release create`/`release status` passam a ser promoção. |
| Resolução de recursos | **Construir** o Forager sobre o Score, com provisioners em camadas no modelo do `score-k8s`; **adiar** Radius e KubeVela | Só o `score-k8s` aceita Score e empilha branch > ambiente > padrão, mas é um gerador sem ciclo de vida e com state local. KubeVela troca o Score pelo OAM; Radius exige Bicep, não empilha e põe a credencial do bind no pedido. | [0031](../../adr/0031-forager-built-on-score-defer-radius-kubevela.md) | **#263 (nova, fatia 4 do catálogo):** controller com `ResourceRequest` como unidade de estado, compose desfeito por finalizer, bind como valores mais referência a Secret. |
| Método de provisionamento | **Construir** com um método só (Crossplane), como provider da plataforma; **adiar** o Kratix | A Promise como fachada é boa, mas o resto (state store, GitOps no destino, conditions próprias) é infraestrutura a mais para um método, e trocar o método move a saída para o destino errado. | [0032](../../adr/0032-single-provisioning-method-defer-kratix.md) | **#254:** só o provider de Crossplane, sem `spec.method`. Um segundo método seria outro provider, com campo imutável e drift como condition `Drifted`. |

### O que fica de cada ferramenta

- **Kargo:** a promoção como ato com histórico, e a versão corrente de um ambiente como a última promoção com sucesso.
- **`score-k8s`:** o casamento de provisioner por `type`/`class`/`id` em camadas ordenadas.
- **Radius:** o compose com ciclo de vida, desfeito quando o pedido é apagado.
- **KubeVela:** nada específico; o modelo de `override` por ordem é o mesmo das camadas do `score-k8s`.
- **Kratix:** a API como CRD nosso, e a saúde voltando do destino como dado (`HealthRecord`), no papel da condition `Drifted`.

### Limpeza

O repo de teste `smsilva/kargo-spike` e o pacote `ghcr.io/smsilva/kargo-spike` continuam publicados, como referência executável do contrato de build (anotações OCI com buildx) e das recipes Terraform do Radius. O `platform-local` já voltou ao estado inicial ao fim de cada parte.
