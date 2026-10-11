# Backstage template

The Backstage template (`idp/templates/python-service`) is imported too. The scaffolder `steps` **do not run on the platform**, and the plan says why:

```bash
platform catalog template import idp/templates/python-service \
  --repo https://github.com/smsilva/wasp-idp \
  --ref main \
  --dry-run
```

``` { .text .output title="output" }
KIND      NAME                         ACTION  DETAIL
Template  python-service               update  description: … ; source.path: platform/templates/python-service/content → idp/templates/python-service/content; source.ref: 0b81690… → main
Step      python-service/fetch-gitops  skip    fetch:template: renders outside the repo content (targetPath)
Step      python-service/gitops-pr     skip    publish:github:pull-request: GitOps belongs to the release
Step      python-service/publish       skip    publish:github: the platform creates the repo
Step      python-service/register      skip    catalog:register: the platform discovery finds catalog-info.yaml

0 to create, 1 to update, 0 unchanged, 4 skipped.
```

!!! warning "Why `--dry-run`"
    With the same name as the seed, applying would replace the `python-service` source.

Creating, importing, changing the default and deleting are for `platform-admins` only; listing, viewing and rendering are for everyone.
