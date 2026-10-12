# OCI registry as a subsystem, chosen per build

**Status:** Aceito (2026-10-12)

## Contexto

O registry era implícito na plataforma. O template `python-service` fixava o destino da imagem (`ghcr.io/${GITHUB_REPOSITORY,,}`), o build conferia só que o resultado tinha uma `image`, e o deploy supunha pull anônimo. O ADR 0034 citava "Registry" apenas como plane do subsistema `build`, sem objeto nem dono.

O registry é onde o build (push) e o deploy (pull) se encontram. O dev precisa ver para onde a imagem foi, o admin precisa cadastrar os registries da plataforma, e um pacote privado precisa de credencial para chegar ao vcluster (#325, agora #368). O design completo está em [`docs/superpowers/specs/2026-10-12-oci-registry-design.md`](../superpowers/specs/2026-10-12-oci-registry-design.md).

## Decisão

**O registry é o subsistema `registry`, e o build escolhe para qual registry faz push.**

- **Nome `OCIRegistry`.** O OCI Distribution Spec guarda imagens, Helm charts, pacotes do Crossplane, assinaturas e SBOMs. O registry não sabe o tipo de artefato: quem diz o que foi publicado é o `Version`. `ContainerRegistry` prenderia ao tipo imagem, e `ArtifactRegistry` é o nome de um produto do Google que sugere formatos não OCI.
- **Subsistema próprio no mapa do ADR 0034:** `registry`, `optional`, `depends_on: identity`. O `build` passa a depender de `registry` (push), e o `workload` também (pull, a partir da #366). Dentro do `build`, o pull do `workload` teria de ler credenciais de outro subsistema. Como `Resource` do catálogo, o registry seria por ambiente e por app, quando é infraestrutura compartilhada.
- **O registry é escolhido no build, não no component.** O component é lógico. O build é o momento físico: roda num CI e produz um artefato num lugar. Sem `--registry`, vale o registry `default` (no máximo um, mantido pela API). Sem default, o build é recusado com `NoDefaultRegistry`. O `Version` grava `spec.registry`.
- **O CI faz o push com a credencial nativa dele.** O dispatch envia o input `image` = `<host>/<namespace>/<component>`, e o resultado do build precisa nomear essa mesma imagem. No vendor `ghcr`, o `GITHUB_TOKEN` do run só escreve no GHCR da org dona do repo, então um `namespace` diferente é recusado antes do dispatch (`RegistryNotWritableByCI`). Um repo com o workflow antigo recebe `WorkflowOutdated`.
- **`--scm-connection` preenche, não liga.** `platform registry add <name> --scm-connection <connection>` cria um registry `ghcr` em `ghcr.io/<org>` a partir de uma connection `github`, lida uma vez, na criação. O `OCIRegistry` não guarda referência à connection: remover a connection não apaga o registry, e o registry não depende de `scm`. A credencial do GitHub App da connection não serve ao registry: o GHCR não aceita token de instalação de App, só PAT classic ou o `GITHUB_TOKEN` de um workflow.
- **Norte do pull:** um `RegistryBinding` liga um registry a um alvo `Environment`, depois `Profile`, com o registry padrão valendo para a plataforma, em camadas como a binding policy (ADR 0038). A credencial de pull é emitida por environment, onde o registry permitir (#366, #367).

## Consequências

- Nesta fatia, só o vendor `ghcr`, com `host: ghcr.io` obrigatório e pull anônimo: os pacotes precisam ser públicos, e um pacote privado termina o deploy em `RolloutFailed` (`ImagePullBackOff`) até a #367/#368.
- Depois desta mudança, todo `build create` exige um registry. `platform init` não cria nenhum: cadastrar o `ghcr-<org>` é o passo do admin no momento 0, depois de `scm connection verify`, que sugere o comando.
- Os repos criados pelo template antes desta mudança precisam do `platform-build.yaml` novo (input `image`).
- O controller `registry` só confere que `https://<host>/v2/` responde (`200`, ou `401` com desafio de token). O status é informativo e não bloqueia o build, porque quem faz o push é o CI.
- Um registry citado por algum `Version` não pode ser removido (`409`): o pull das próximas fatias resolve o registry pelo nome gravado no `Version`.
