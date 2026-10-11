# Templates

## 16. Templates de component

Um template é o golden path de um tipo de component (ADR 0024). O conteúdo fica no Git; a plataforma guarda só o registro (repo, caminho e ref). O `platform init` registra os templates de `platform/templates/` no commit do checkout, e o primeiro de cada tipo vira o padrão.

```bash
platform catalog template list
platform catalog template get python-service
```

``` { .text .output title="saída" }
NAME            TYPE     REF                                       DEFAULT  SOURCE
python-service  service  0b81690231edcd5920c1f774efc0325c80a4b0a4  yes      https://github.com/smsilva/wasp-idp/platform/templates/python-service/content
template/python-service
  type         service
  default      yes
  repo         https://github.com/smsilva/wasp-idp
  path         platform/templates/python-service/content
  ref          0b81690231edcd5920c1f774efc0325c80a4b0a4
  owner        team-platform
  description  FastAPI service with CI to GHCR, Dockerfile and app-spec.yaml
  parameters
    port (integer, default 8000): Port the container listens on.
```

O `render` gera localmente o que o `component create` vai gerar, buscando o conteúdo no ref registrado. Serve para quem escreve template:

```bash
platform catalog template render python-service --name demo --output /tmp/demo --param port=9000
grep 9000 /tmp/demo/Dockerfile
grep template: /tmp/demo/catalog-info.yaml
```

``` { .text .output title="saída" }
✓ rendered into /tmp/demo
EXPOSE 9000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "9000"]
    platform.wasp.silvios.me/template: python-service@0b81690231edcd5920c1f774efc0325c80a4b0a4
```

Um padrão por tipo: marcar outro desmarca o anterior, e o padrão só sai depois que outro assume.

```bash
platform catalog template create go-service --type service --owner team-platform \
  --repo https://github.com/smsilva/wasp-idp --path platform/templates/python-service/content --ref main
platform catalog template default go-service
platform catalog template delete go-service
platform catalog template default python-service
platform catalog template delete go-service
```

``` { .text .output title="saída" }
✓ template go-service created
✓ template go-service is the default for service
✗ 409: template 'go-service' is the default for type 'service': make another one the default first (python-service)
✓ template python-service is the default for service
✓ template go-service deleted
```

O template do Backstage (`idp/templates/python-service`) também entra. Os `steps` do scaffolder não rodam na plataforma, e o plano diz por quê:

```bash
platform catalog template import idp/templates/python-service \
  --repo https://github.com/smsilva/wasp-idp \
  --ref main \
  --dry-run
```

``` { .text .output title="saída" }
KIND      NAME                         ACTION  DETAIL
Template  python-service               update  description: … ; source.path: platform/templates/python-service/content → idp/templates/python-service/content; source.ref: 0b81690… → main
Step      python-service/fetch-gitops  skip    fetch:template: renders outside the repo content (targetPath)
Step      python-service/gitops-pr     skip    publish:github:pull-request: GitOps belongs to the release
Step      python-service/publish       skip    publish:github: the platform creates the repo
Step      python-service/register      skip    catalog:register: the platform discovery finds catalog-info.yaml

0 to create, 1 to update, 0 unchanged, 4 skipped.
```

!!! warning "Por que `--dry-run`"
    Com o mesmo nome do seed, aplicar trocaria a fonte do `python-service`.

Criar, importar, mudar o padrão e apagar são só para `platform-admins`; listar, ver e renderizar, para todos.
