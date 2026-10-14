# Run it again

Running it again writes nothing:

```bash
platform catalog import idp/catalog/
```

``` { .text .output title="output" }
KIND      NAME                  ACTION     DETAIL
Domain    bookstore             unchanged
...

0 to create, 0 to update, 21 unchanged, 2 skipped.
nothing to do
```

The catalog now holds what the import created:

```bash
platform catalog list
```

``` { .text .output title="output" }
KIND      NAME                  PARENT         OWNER
Domain    bookstore             —              team-alpha
Domain    communication         —              team-alpha
Domain    messaging             communication  team-alpha
Domain    notifications         communication  team-beta
Domain    platform              —              team-platform
System    bookinfo              bookstore      team-alpha
System    greeter               messaging      team-alpha
System    notifier              notifications  team-beta
System    platform              platform       team-platform
Resource  development           platform       team-platform
Resource  greeting-avatars      greeter        team-alpha
Resource  greeting-db           greeter        team-alpha
Resource  greeting-events       greeter        team-alpha
Resource  notification-db       notifier       team-beta
Resource  notification-jobs     notifier       team-beta
Resource  notification-reports  notifier       team-beta
Resource  production            platform       team-platform
Resource  shared-pg             platform       team-platform
```
