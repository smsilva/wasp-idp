# Build the version index and Promotion; defer Kargo

**Status:** Aceito (2026-10-11)

## Contexto

A #206 desenhou o build por branch com um índice de versões próprio (`versions.catalog.platform.wasp.silvios.me`), e o ADR 0022 previu um CRD `Release` para "ligar uma versão a um ambiente". Antes de construir os dois, o spike da #207 perguntou se o [Kargo](https://kargo.io/) já resolve as duas peças: o Warehouse descobre versões no registry e produz Freight, e a Promotion leva o Freight entre Stages.

O spike rodou o Kargo v1.12.3 no `platform-local` contra uma imagem de teste no GHCR e dois vclusters de `Environment`. O resultado está na seção 1 de [`docs/superpowers/specs/2026-10-11-adopt-or-build-spike.md`](../superpowers/specs/2026-10-11-adopt-or-build-spike.md). Os fatos que decidem:

- **O Warehouse não é um índice de versões.** A cada varredura ele cria Freight só para o artefato mais novo, então versões intermediárias são descobertas mas não viram Freight. Ele não tem onde encaixar o gate do Score, não recusa `VersionConflict`, e o `request-id` de um build só é encontrado listando os Freights e filtrando no cliente, porque as anotações OCI viram metadado, não label.
- **A promoção cobre o conceito, mas o caminho nativo é GitOps.** Nenhum dos 60 passos embutidos aplica manifests num cluster. Sem GitOps, o que funcionou no OSS foi um passo `http` contra a kube API do vcluster, com `insecureSkipTLSVerify` porque o passo não aceita CA própria, e com a credencial do destino guardada no Kargo, ao lado do `StateWriter` em vez de atrás dele.
- **O modelo para ambientes efêmeros é pago.** `Target` e `PromotionRequest` vêm instalados, mas o controller do OSS responde `EnterpriseOnlyFeature`. Um Stage por `Environment` funciona, mas o Freight guarda `status.currentlyIn.<stage>` depois que o Stage é apagado, e esse resto se acumula em ambientes de 3 dias.
- **O nome:** "release" colide com o GitHub Release, que a #206 já separou como "publicar uma versão do código". O deck já descreve a etapa como "an app version _promoted_ across Environments".

## Decisão

**Construir o índice de versões da #206 e um CRD `Promotion` atrás do `StateWriter`; adiar o Kargo. O conceito de implantação passa a se chamar promoção (`promote`/`Promotion`), e o CRD `Release` do ADR 0022 não é criado.**

- **Índice de versões:** fica como a #206 desenhou (CRD `Build`, controller `build_github`, gate do Score, `VersionConflict`, `request-id` pelo `run-name`).
- **Contrato de build, acréscimo:** o workflow `platform-build.yaml` publica a imagem com manifest OCI e as anotações `org.opencontainers.image.source`, `.revision`, `.version` e `me.silvios.wasp.request-id`. Isso exige `docker/setup-buildx-action` antes do `docker/build-push-action` e `outputs: type=image,push=true,oci-mediatypes=true`: sem o buildx, o driver `docker` publica manifest Docker v2 e descarta as anotações sem erro. A plataforma não depende delas hoje; elas deixam a porta aberta para um Warehouse no futuro.
- **Promoção:**
  - A palavra do usuário é `promote` (CLI e API). "release" fica reservado ao GitHub Release.
  - **`Promotion`** é um CRD do grupo `platform.wasp.silvios.me`, um objeto por ato: component, versão do índice e `Environment`, com `spec` imutável e o resultado em conditions. A versão corrente de um component num ambiente é a da última `Promotion` com sucesso, como no Stage do Kargo.
  - Cada `Promotion` tem owner reference para o seu `Environment`: apagar um ambiente efêmero apaga o histórico dele, sem o resto que o Kargo deixa no Freight.
  - A escrita passa pelo `StateWriter` do ADR 0022, e a credencial do destino nunca sai da plataforma.
  - Promoção com aprovação humana continua sendo workflow (ADR 0022). O resultado volta como uma `Promotion`.
- **Formato da CLI e campos do CRD:** ficam para a issue de promoção (tópico 6).

## Quando revisitar o Kargo

Quando a promoção de produção passar a ser GitOps (um `GitCommitWriter`, ADR 0022), com aprovação e verificação entre um conjunto fixo de ambientes. Nesse cenário, o caminho nativo do Kargo (`git-commit` → `argocd-update`) deixa de ser contorno, e Stages fixos não deixam resto. Ambientes efêmeros continuariam com a `Promotion` da plataforma, a menos que `Target`/`PromotionRequest` cheguem ao OSS.

## Consequências

- **Substitui um ponto do ADR 0022:** o CRD `Release` vira `Promotion`, e a frase "o resultado volta como dado: … um `Release`" passa a ser "… uma `Promotion`". O resto do ADR 0022 continua valendo.
- A #206 ganha as anotações OCI e o `setup-buildx-action` no contrato de build. O resto dela não muda.
- O deck (#202) troca "release" por "promote" na etapa de implantação (`journey-release`, `platform release create`, `release status`).
- A plataforma mantém um controller de promoção a mais, em troca de não operar o Kargo (5 pods, ~107 MiB, mais o cert-manager) nem um segundo modelo de RBAC por Project.
- Sem Kargo, verificação automática entre ambientes (análise depois da promoção) e o gate "só promove para `prod` o que passou por `dev`" são da plataforma, quando forem necessários.
