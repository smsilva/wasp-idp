# Platform catalog: organisation entities as CRDs, code entities in the repo, Backstage as reader

**Status:** Aceito (2026-10-10)

## Contexto

O deck apresenta o modelo mental do Backstage como o catálogo da plataforma: Domain e System na visão de negócio; Component, API e Resource na visão de engenharia. Até aqui o catálogo vivia só no Backstage: Domain, System e Resource em arquivos de `idp/catalog/`, Component e API no `catalog-info.yaml` de cada repo (ADR 0020). A Platform API não sabia nada do catálogo.

O ADR 0022 faz da Platform API a fronteira única dos clientes. O catálogo não pode depender do Backstage: se o portal cair, a CLI, a API e os agentes continuam precisando dele.

## Decisão

**Cada entidade do catálogo tem uma casa só, escolhida por onde ela muda; a Platform API é dona das entidades da organização, o repo é dono das entidades de código, e o Backstage lê os dois.**

- **Domain, System e o Resource compartilhado** são CRDs do grupo `catalog.platform.wasp.silvios.me`, criados e apagados pela Platform API (`platform catalog <kind> create`). Não pertencem a nenhum repo.
- **Component e API** ficam no `catalog-info.yaml` (e no `openapi.yaml`) do repo e mudam no mesmo PR que o código. A plataforma os cria pelo golden path (`platform catalog component create --type service`) e depois os descobre.
- **"Catalog" é o espaço de nomes** (grupo de CRDs, `/v1/catalog`, `platform catalog`), não uma entidade que contém as outras.
- **Resource do catálogo é a identidade lógica, descrita pelo papel** ("o banco do greeter"), uma só para todos os ambientes. A instância num ambiente é um `ResourceRequest` (ADR 0022) e não entra no catálogo.
- **O Score liga a app ao catálogo pelo `resources.<nome>.id`.** Sem `id`, o recurso é só da app e o resolvedor deriva o Resource (`<component>-<nome>`). Com `id`, ele aponta para um Resource compartilhado já cadastrado, e um `id` inexistente é recusado no build.
- **O resolvedor do ADR 0022 chama-se Forager**: lê o Score do release, resolve cada recurso contra o catálogo e a `BindingPolicy` do ambiente, e cria ou reaproveita o `ResourceRequest`.
- **O Backstage lê a Platform API** (entity provider) e o discovery da org (ADR 0020). Nenhum dos dois depende do outro para funcionar.
- **Owner é texto livre** (nome do time) até os grupos de time existirem no Keycloak (#186).

## Consequências

- Backstage fora do ar não afeta a CLI, a API nem os agentes. Platform API fora do ar deixa o portal com a última leitura.
- `idp/catalog/` vira carga inicial, importada pelo `platform catalog import` (#190), e deixa de ser location do Backstage quando o entity provider existir.
- O dev pede um tipo (`postgres`) no Score, não escolhe um Resource da plataforma; o banco compartilhado da plataforma aparece no catálogo como Resource de `team-platform`, alvo do modo `compose`.
- A checagem de dependentes antes de apagar não é atômica; um finalizer no pai fecha a brecha quando o volume justificar.
- Os comandos ilustrativos do deck passam de `platform app …` para `platform catalog component …`, e o ciclo de vida usa `--component`.
