# Run it again

Running it again writes nothing:

```bash
platform catalog import \
  idp/catalog/airline/tailwind/ \
  idp/catalog/org.yaml \
  idp/catalog/platform.yaml
```

``` { .text .output title="output" }
KIND       NAME                        ACTION     DETAIL
Group      team-airport                unchanged
...

0 to create, 0 to update, 34 unchanged, 11 skipped.
nothing to do
```

The catalog now holds what the import created:

```bash
platform catalog list
```

``` { .text .output title="output" }
KIND      NAME           PARENT         OWNER
Domain    airport        tailwind       team-airport
Domain    booking        tailwind       team-booking
Domain    crew           tailwind       team-crew
Domain    flight-ops     tailwind       team-flight-ops
Domain    loyalty        tailwind       team-loyalty
Domain    platform       —              team-platform
Domain    tailwind       —              team-tailwind-architecture
System    bag-tracking   airport        team-airport
System    boarding-pass  airport        team-airport
System    fares          booking        team-booking
System    flight-search  booking        team-booking
System    flight-status  flight-ops     team-flight-ops
System    miles          loyalty        team-loyalty
System    platform       platform       team-platform
System    reservations   booking        team-booking
System    rostering      crew           team-crew
System    schedules      flight-ops     team-flight-ops
System    seat-map       airport        team-airport
System    tiers          loyalty        team-loyalty
Resource  development    platform       team-platform
Resource  fares-cache    fares          team-booking
Resource  flight-events  flight-status  team-flight-ops
Resource  passengers-db  reservations   team-booking
Resource  production     platform       team-platform
Resource  shared-pg      platform       team-platform
```
