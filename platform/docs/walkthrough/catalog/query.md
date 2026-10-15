# Query

`get` shows what **depends** on the entity:

```bash
platform catalog list

platform catalog system get greeter
```

``` { .text .output title="output" }
system/greeter
  domain       messaging
  owner        team-alpha
  description  —
  dependents   resource/greeting-db

next:

  platform catalog domain get messaging

  platform catalog resource get greeting-db
```

`next:` goes up to the parent and down to the dependents. `--hide-empty` leaves out the `description  —` line.
