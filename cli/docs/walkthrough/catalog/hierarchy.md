# Create the team and the hierarchy

The owner of an entity is **a team that already exists** (ADR 0026). As an admin, create `team-alpha` first.

One domain, one subdomain, a system inside it and a resource of the system, all owned by `team-alpha`:

``` { .text .plan title="what will be created" }
team-alpha              team · owner of everything below
communication           domain
└── messaging           subdomain
    └── greeter         system
        └── greeting-db resource · database
```

The commands, in the order in which each entity needs the previous one:

```bash
platform team create team-alpha

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
