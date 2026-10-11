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
```
