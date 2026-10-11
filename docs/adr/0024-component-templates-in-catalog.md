# Component templates: catalog entity, content in Git, one default per type, Backstage import

**Status:** Aceito (2026-10-11)

## Contexto

`platform catalog component create` (fatia 2 do catálogo) precisa de templates para gerar o repo. O spec do catálogo (`docs/superpowers/specs/2026-10-10-platform-catalog-design.md`, decisão 6) já fixou que `--type` escolhe o golden path padrão e que `--template` serve para fugir dele. A plataforma não tem modelo de template.

O único template existente é do scaffolder do Backstage, em `idp/templates/python-service/`: `template.yaml` (`v1beta3`) com `parameters` e `steps` (`fetch:template`, `publish:github`, `publish:github:pull-request` no `wasp-foundry/gitops`), conteúdo em `content/` e `gitops/` com a sintaxe Nunjucks `${{ values.x }}` (inclusive o filtro `| dump`), e `.github/workflows/*` copiados sem template (`copyWithoutTemplating`).

O ADR 0022 faz da Platform API a fronteira única dos clientes, e o ADR 0023 põe as entidades da organização em CRDs do grupo `catalog.platform.wasp.silvios.me`. O template precisa caber nesse modelo sem depender do Backstage.

## Decisão

**`Template` é uma entidade do catálogo que aponta para conteúdo versionado no Git; a plataforma executa os passos, o template só traz conteúdo.**

- **CRD `templates.catalog.platform.wasp.silvios.me`**, namespaced como Domain, System e Resource. O `spec` tem:
  - `type`: `service | website | library`;
  - `default`: no máximo um template padrão por tipo;
  - `source.repo`, `source.path` e `source.ref` (tag ou commit; branch só para templates em desenvolvimento);
  - `parameters`: JSON Schema dos parâmetros extras;
  - `description` e `owner`.
- **Só `platform-admins` criam, alteram e removem templates.** Listar é para todos.
- **O tipo escolhe o template padrão; `--template` é opcional.** `--type service` usa o padrão de `service`; `--template <nome>` escolhe outro e já implica o tipo. Trocar o golden path de todos é trocar o padrão, sem mudar o comando de ninguém.
- **Passos fixos da plataforma:** criar o repo pela scm connection (#198), fazer o push do conteúdo renderizado e deixar o discovery achar o `catalog-info.yaml`. Os `steps` de um template do Backstage não são executados; o import os reporta como ignorados.
- **Parâmetros padrão vêm da plataforma:** `name`, `owner`, `system` e `description`. O template declara só os extras, preenchidos com `--param chave=valor`.
- **Motor de renderização: Jinja2 com os delimitadores do Backstage** (`${{` … `}}`) e um filtro `dump` (JSON), para os templates do Backstage renderizarem sem reescrita. Arquivos marcados como cópia literal (o `copyWithoutTemplating` do Backstage) não passam pelo motor.
- **O component registra a origem:** o repo gerado recebe a anotação `platform.wasp.silvios.me/template: <nome>@<ref>` no `catalog-info.yaml`.
- **O import do Backstage tem dois caminhos com a mesma lógica:** `platform catalog import` (#190) passa a entender `kind: Template`, e `platform catalog template import` é um atalho que aceita um arquivo ou uma pasta.
- **Seeds:** o `platform init` registra os templates de fábrica a partir de `platform/templates/` neste repo, que é público e não exige credencial para leitura. Templates em repos privados usam a credencial da scm connection.

## Consequências

- Mudar um template é um PR no repo do template mais um bump do `ref` no registro. Repos já criados não mudam sozinhos; a anotação de origem habilita, no futuro, atualizar um repo para a versão nova do template (como o `copier` faz), fora do escopo agora.
- O `catalog-info.yaml` dentro do conteúdo de um template não é um Component real: o import (#190) e o discovery (#205) precisam ignorá-lo.
- O scaffolder do Backstage e a plataforma convivem até a fatia 2 do catálogo migrar o golden path. `idp/templates/python-service` vira o primeiro import.
- O passo de GitOps (o PR no `wasp-foundry/gitops`) sai do template e passa a ser responsabilidade do release, quando ele existir.
- Templates em repos privados dependem da scm connection (#198); até ela existir, só a fonte pública (`platform/templates/`) funciona.
- A implementação (CRD, rotas, `platform catalog template`, import) é a #201.
