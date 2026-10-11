# Forager built on Score with layered provisioners; defer Radius and KubeVela

**Status:** Aceito (2026-10-11)

## Contexto

O ADR 0022 definiu os três modos de um recurso declarado no Score: **provision** (recurso dedicado), **compose** (algo dentro de um recurso compartilhado) e **bind** (credenciais de algo que já existe). O ADR 0023 deu ao resolvedor o nome Forager: ele lê o Score, resolve cada recurso contra o catálogo e a política do ambiente, e cria o `ResourceRequest`. A política de binding é em camadas: override da branch > política do ambiente > padrão da plataforma.

O spike da #207 perguntou se `score-k8s`, KubeVela ou Radius já fazem isso. Os três rodaram no `platform-local` com um `app-spec.yaml` do template `python-service` e um recurso `db` do tipo `postgres`, nos três modos. O resultado está na seção 2 de [`docs/superpowers/specs/2026-10-11-adopt-or-build-spike.md`](../superpowers/specs/2026-10-11-adopt-or-build-spike.md). Os fatos que decidem:

- **`score-k8s` (0.20.0):** é o único que aceita Score (com `apiVersion: score.dev/v1b1`) e o único que empilha a precedência: o primeiro provisioner que casa por `type`/`class`/`id`, na ordem lexical dos arquivos, e uma `class` pedida pela branch. Mas é um gerador: sem controller, sem ciclo de vida (nada desfaz o compose), com o state, senhas em claro incluídas, num arquivo local, e com o compose só por um provisioner `cmd://` que age durante a geração.
- **KubeVela (v1.11.0):** cobre os três modos e a precedência (ordem dos `override`s), mas troca o Score pelo OAM, põe a lógica de modo em CUE e em passos de workflow, guarda a senha em claro na `Application` e exige registrar cada vcluster com `vela cluster join`.
- **Radius (v0.61.1):** é o único que desfaz o compose (recipe Terraform com state em Secret), mas exige Bicep, aceita uma recipe por tipo por ambiente (sem camadas), faz o bind exigir a senha no pedido do desenvolvedor, convive com duas gerações de API e, no uninstall, deixou um APIService órfão que travou a remoção de todo namespace do cluster.

## Decisão

**Construir o Forager como controller da plataforma, com o Score como formato de entrada e o modelo de provisioners do `score-k8s`; adiar Radius e KubeVela.**

- **Entrada:** o `app-spec.yaml` é Score, com `apiVersion: score.dev/v1b1`. O template `python-service` hoje usa `platform/v1`, que o schema do Score recusa; ele passa a usar o `apiVersion` do Score, e o resto do arquivo não muda.
- **Provisioners em camadas:** a plataforma mantém uma lista ordenada de provisioners por camada (branch, ambiente, padrão da plataforma). Cada provisioner casa por `type`, `class` opcional e `id` opcional, e o primeiro que casa vence, como no `score-k8s`. A camada de branch escolhe uma `class` (por exemplo, `restored`), nunca uma credencial.
- **Ciclo de vida no controller, não na geração:** o `ResourceRequest` é a unidade de estado. O compose cria e também desfaz (no delete do `ResourceRequest`, por finalizer), como a recipe do Radius. O state e os segredos ficam no cluster de control plane, nunca num arquivo local.
- **Bind:** o provisioner devolve só valores e uma referência a um Secret existente. O desenvolvedor nunca conhece nem passa a credencial do recurso restaurado.
- **Nomes que viram SQL ou comando:** nomes vindos do pedido (component, recurso, ambiente) que entram em SQL ou em linha de comando são validados como identificadores com `re.fullmatch` ou passados pelos parâmetros de identificador do driver, nunca por interpolação de texto.
- **Fachada:** o cliente vê o `ResourceRequest` e as conditions do ADR 0022. Provisioners são detalhe da plataforma.

## Quando revisitar

- **Radius:** quando os tipos `Radius.*` saírem de preview, houver recipes AWS de Postgres e a precedência deixar de ser uma recipe por tipo por ambiente.
- **KubeVela:** se a plataforma decidir trocar o Score pelo OAM como formato da app, o que não está em discussão hoje.
- **`score-k8s`:** se ganhar um modo controller com ciclo de vida, ele vira candidato direto, porque o formato e a precedência já são os mesmos.

## Consequências

- O Forager (fatia 4 do catálogo) é código da plataforma: um controller que lê o Score da versão promovida, aplica as camadas e cria ou reaproveita o `ResourceRequest`.
- Os provisioners de cada modo também são código da plataforma. Para o compose de Postgres, o spike deixou um exemplo em [`score-k8s/compose-postgres`](../superpowers/specs/2026-10-11-adopt-or-build-spike/score-k8s/compose-postgres) e uma recipe Terraform em [`radius/recipes/compose/`](../superpowers/specs/2026-10-11-adopt-or-build-spike/radius/recipes/compose/).
- O gate do Score da #206 valida contra o schema `score.dev/v1b1`, o mesmo que o Forager lê.
- Não há componente de terceiros a operar: o `score-k8s` não roda no cluster, e o Radius (8 pods, ~744 MiB) e o KubeVela (2 pods, ~82 MiB) ficam de fora.
- Nenhuma das três ferramentas traz provisioner AWS de Postgres pronto, então esse trabalho seria da plataforma em qualquer caminho.
