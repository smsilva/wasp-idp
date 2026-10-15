# Create the hierarchy

The owner of an entity is **a team that already exists** (ADR 0026): `team-alpha`, from [Teams](../teams/create.md).

One domain of the airline Tailwind Air, one subdomain, a system inside it and a resource of the system, all owned by `team-alpha`:

``` { .text .plan title="what will be created" }
tailwind                  domain
└── booking               subdomain
    └── reservations      system
        └── passengers-db resource · database
```

The commands, in the order in which each entity needs the previous one:

```bash
platform catalog domain create tailwind \
  --owner team-alpha

platform catalog domain create booking \
  --parent tailwind \
  --owner team-alpha

platform catalog system create reservations \
  --domain booking \
  --owner team-alpha

platform catalog resource create passengers-db \
  --type database \
  --system reservations \
  --owner team-alpha
```

``` { .text .output title="output" }
✓ domain tailwind created
✓ domain booking created
✓ system reservations created
✓ resource passengers-db created
```
