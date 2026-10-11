# Catalog

Domínios, sistemas e recursos que a plataforma guarda. Domínio só `platform-admins` cria; sistema e recurso, qualquer usuário. O `--owner` é um time que já existe ([times](12-teams.md)): `platform team create team-alpha`, ou o import de um `Group`.

```bash
platform catalog domain create communication --owner team-alpha
platform catalog domain create messaging --parent communication --owner team-alpha
platform catalog system create greeter --domain messaging --owner team-alpha
platform catalog resource create greeting-db \
  --type database \
  --system greeter \
  --owner team-alpha
platform catalog list
```

```
KIND      NAME           PARENT         OWNER
Domain    communication  —              team-alpha
Domain    messaging      communication  team-alpha
System    greeter        messaging      team-alpha
Resource  greeting-db    greeter        team-alpha
```

Apagar é na ordem inversa: com dependentes, a API recusa e diz quais são.

```bash
platform catalog domain delete messaging
```

```
✗ 409: domain 'messaging' has dependents: system/greeter
```

O `--type` do recurso é o papel (`database`, `topic`, `queue`, `bucket`), nunca o serviço de nuvem. Componentes e APIs ainda não estão no catálogo da plataforma.

## Importar do Backstage

Quem já tem um catálogo no formato Backstage importa os arquivos de uma vez. A Platform API calcula o plano; nada é gravado antes da confirmação.

```bash
platform catalog import idp/catalog/            # arquivo ou pasta (recursivo: *.yaml, *.yml)
platform catalog import idp/catalog/ --dry-run  # só o plano
platform catalog import idp/catalog/ --yes      # sem perguntar (pipeline)
```

| Ação | Significado |
|---|---|
| `create` | não existe na plataforma |
| `update` | existe e muda; o detalhe mostra `campo: antes → depois` |
| `unchanged` | existe igual |
| `skip` | não é importado: Component e API moram no repo e chegam pelo discovery (#205), User fica no Keycloak; arquivos dentro do conteúdo de um template (`part of template <nome>`); os `steps` de um template do Backstage |
| `forbidden` | sem permissão: domínio só `platform-admins`; sistema e recurso só quem criou |
| `error` | campo faltando ou referência quebrada; o detalhe diz o campo e o arquivo |

Um `Group` vira time (só `platform-admins` criam; membros não são importados) e entra no plano antes das outras entidades. O `spec.owner` de cada entidade escrita precisa ser um time que existe ou um `Group` do mesmo import. Com `forbidden` ou `error` nada é aplicado. O import nunca apaga: o que existe na plataforma e não está nos arquivos fica como está. Um campo ausente no arquivo (a `description`, por exemplo) é removido da entidade. Se o catálogo mudar entre o plano e a confirmação, a API recusa e a CLI mostra o plano novo.

Templates do Backstage (`kind: Template`) também entram pelo `catalog import`, desde que venham `--repo` e `--ref`: o arquivo local não sabe onde está publicado. Sem eles, o template vira `error` e o resto do plano segue.

## Templates

Um template é o golden path de um tipo de component (`service`, `website`, `library`; ADR 0024). O conteúdo fica no Git, e a plataforma guarda repo, caminho e ref. O `platform init` registra `platform/templates/*` no último commit do checkout que existe no GitHub.

```bash
platform catalog template list
platform catalog template get python-service
platform catalog template render python-service --name demo --output ./demo [--param port=9000]
platform catalog template render --from platform/templates/python-service --name demo --output ./demo
```

O `render` roda localmente: busca o conteúdo no ref registrado (ou lê `--from`), renderiza com os delimitadores do Backstage (`${{ values.x }}`, filtro `dump`), copia como estão os arquivos de `copyWithoutRendering` e grava a origem em `catalog-info.yaml` (`platform.wasp.silvios.me/template: <nome>@<ref>`). Os valores padrão são `name`, `owner`, `system` e `description`; o template declara os extras, passados com `--param`.

Só `platform-admins` alteram o registro:

```bash
platform catalog template create my-api --type service --owner team-platform \
  --repo https://github.com/wasp-foundry/templates --path my-api --ref v1.0.0 [--default]
platform catalog template default my-api
platform catalog template import idp/templates/python-service --repo https://github.com/smsilva/wasp-idp --ref main
platform catalog template delete my-api
```

- Um padrão por tipo: `default` desmarca o anterior. Apagar o padrão enquanto houver outros do mesmo tipo é `409`.
- `import` aceita arquivo ou pasta e lê só definições de template: `kind: Template` do Backstage ou `template.yaml` no formato da plataforma. Os `steps` do scaffolder aparecem no plano como `skip`, com o motivo, e reimportar mantém quem é o padrão.
- O `--owner` é um time que já existe, como nas outras entidades do catálogo. O template do Backstage em `idp/templates/python-service` tem `owner: group:default/guests`: importe-o pelo `platform catalog import` junto com o `Group` `guests`, ou crie o time antes.
