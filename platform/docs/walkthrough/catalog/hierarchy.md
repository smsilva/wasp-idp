# Create the hierarchy

The owner of an entity is **a team that already exists** (ADR 0026): `team-alpha`, from [Teams](../teams/create.md).

One domain, one subdomain, a system inside it and a resource of the system, all owned by `team-alpha`:

``` { .text .plan title="what will be created" }
communication           domain
└── messaging           subdomain
    └── greeter         system
        └── greeting-db resource · database
```

The commands, in the order in which each entity needs the previous one:

```bash
platform catalog domain create communication \
  --owner team-alpha

platform catalog domain create messaging \
  --parent communication \
  --owner team-alpha

platform catalog system create greeter \
  --domain messaging \
  --owner team-alpha

platform catalog resource create greeting-db \
  --type database \
  --system greeter \
  --owner team-alpha
```
