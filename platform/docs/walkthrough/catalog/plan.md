# Backstage import

`idp/catalog/airline/tailwind/` is the catalog of Tailwind Air, a fictional airline: a top domain `tailwind`, one subdomain per business area (`booking`, `airport`, `flight-ops`, `loyalty`, `crew`), their systems, the resources shared across them and one team per area. With the teams of `idp/catalog/org.yaml` and the platform's own system of `idp/catalog/platform.yaml`, it is the **initial load** of the catalog (ADR 0023). The import **shows the plan**, computed by the Platform API, and **only writes after confirmation**.

```bash
platform catalog import \
  idp/catalog/airline/tailwind/ \
  idp/catalog/org.yaml \
  idp/catalog/platform.yaml
```

``` { .text .output title="output" }
KIND       NAME                        ACTION     DETAIL
Group      team-airport                create
Group      team-alpha                  unchanged
Group      team-beta                   create
Group      team-booking                create
Group      team-crew                   create
Group      team-flight-ops             create
Group      team-loyalty                create
Group      team-platform               create
Group      team-tailwind-architecture  create
Domain     platform                    create
Domain     tailwind                    create
Domain     airport                     create     parent tailwind
Domain     booking                     create     parent tailwind
Domain     crew                        create     parent tailwind
Domain     flight-ops                  create     parent tailwind
Domain     loyalty                     create     parent tailwind
System     bag-tracking                create     domain airport
System     boarding-pass               create     domain airport
System     fares                       create     domain booking
System     flight-search               create     domain booking
System     flight-status               create     domain flight-ops
System     miles                       create     domain loyalty
System     platform                    create     domain platform
System     reservations                create     domain booking
System     rostering                   create     domain crew
System     schedules                   create     domain flight-ops
System     seat-map                    create     domain airport
System     tiers                       create     domain loyalty
Resource   development                 create     system platform
Resource   fares-cache                 create     system fares
Resource   flight-events               create     system flight-status
Resource   passengers-db               create     system reservations
Resource   production                  create     system platform
Resource   shared-pg                   create     system platform
Component  bag-tracker                 skip       lives in the repo catalog-info.yaml; indexed by discovery (#205)
Component  boarding-pass-issuer        skip       lives in the repo catalog-info.yaml; indexed by discovery (#205)
Component  fares-engine                skip       lives in the repo catalog-info.yaml; indexed by discovery (#205)
Component  flight-finder               skip       lives in the repo catalog-info.yaml; indexed by discovery (#205)
Component  flight-tracker              skip       lives in the repo catalog-info.yaml; indexed by discovery (#205)
Component  miles-ledger                skip       lives in the repo catalog-info.yaml; indexed by discovery (#205)
Component  reservation-desk            skip       lives in the repo catalog-info.yaml; indexed by discovery (#205)
Component  roster-planner              skip       lives in the repo catalog-info.yaml; indexed by discovery (#205)
Component  seat-selection              skip       lives in the repo catalog-info.yaml; indexed by discovery (#205)
Component  web-checkin                 skip       lives in the repo catalog-info.yaml; indexed by discovery (#205)
API        seats                       skip       lives in the repo catalog-info.yaml; indexed by discovery (#205)

33 to create, 0 to update, 1 unchanged, 11 skipped.
Apply? [y/N]: y
✓ 33 created, 0 updated
```

The Components and the API `seats` are `skip`: they live in the `catalog-info.yaml` of each repo and reach the platform through discovery (#205), never through the import.
