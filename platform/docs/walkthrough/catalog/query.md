# Query

`get` shows what **depends** on the entity:

```bash
platform catalog list

platform catalog system get reservations
```

``` { .text .output title="output" }
system/reservations
  domain       booking
  owner        team-alpha
  description  —
  dependents   resource/passengers-db

next:

  platform catalog domain get booking

  platform catalog resource get passengers-db
```

`next:` goes up to the parent and down to the dependents. `--hide-empty` leaves out the `description  —` line.
