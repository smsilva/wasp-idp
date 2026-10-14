# Backstage import

`idp/catalog/` is the **initial load** of the catalog (ADR 0023). The import **shows the plan**, computed by the Platform API, and **only writes after confirmation**.

```bash
platform catalog import idp/catalog/
```

``` { .text .output title="output" }
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
Resource  shared-pg             create  system platform
—         —                     skip    not a Backstage entity (idp/catalog/communication/greeter/mkdocs.yml#1)
—         —                     skip    not a Backstage entity (idp/catalog/communication/mkdocs.yml#1)

20 to create, 0 to update, 1 unchanged, 2 skipped.
Apply? [y/N]: y
✓ 20 created, 0 updated
```
