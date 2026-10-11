# Backstage import

O `idp/catalog/` é a **carga inicial** do catálogo (ADR 0023). O import **mostra o plano**, calculado pela Platform API, e **só grava depois da confirmação**.

```bash
platform catalog import idp/catalog/
```

``` { .text .output title="saída" }
KIND      NAME                  ACTION     DETAIL
Group     team-alpha            unchanged
Group     team-beta             create
Group     team-platform         create
Domain    bookstore             create
Domain    communication         create
Domain    platform              create
Domain    messaging             create  parent communication
Domain    notifications         create  parent communication
System    bookinfo              create  domain bookstore
System    greeter               create  domain messaging
System    notifier              create  domain notifications
System    platform              create  domain platform
Resource  development           create  system platform
Resource  greeting-avatars      create  system greeter
Resource  greeting-db           create  system greeter
Resource  greeting-events       create  system greeter
Resource  notification-db       create  system notifier
Resource  notification-jobs     create  system notifier
Resource  notification-reports  create  system notifier
Resource  production            create  system platform
—         —                     skip    not a Backstage entity (idp/catalog/communication/greeter/mkdocs.yml#1)
—         —                     skip    not a Backstage entity (idp/catalog/communication/mkdocs.yml#1)

19 to create, 0 to update, 1 unchanged, 2 skipped.
Apply? [y/N]: y
✓ 19 created, 0 updated
```

Rodar de novo não grava nada:

```bash
platform catalog import idp/catalog/
```

``` { .text .output title="saída" }
KIND      NAME                  ACTION     DETAIL
Domain    bookstore             unchanged
...

0 to create, 0 to update, 20 unchanged, 2 skipped.
nothing to do
```

Uma referência quebrada aparece no plano com a entidade, o campo e o arquivo, e **nada é aplicado**:

```bash
printf 'apiVersion: backstage.io/v1alpha1\nkind: System\nmetadata:\n  name: orphan\nspec:\n  owner: team-alpha\n  domain: nowhere\n' > /tmp/orphan.yaml

platform catalog import /tmp/orphan.yaml
```

``` { .text .output title="saída" }
KIND    NAME    ACTION  DETAIL
System  orphan  error   spec.domain: domain 'nowhere' not found (/tmp/orphan.yaml#1)

0 to create, 0 to update, 0 unchanged, 0 skipped, 1 error.
✗ fix the errors above; nothing was applied
```
