# A database in the shared instance

The binding policy of an environment changes how its resources are made, without touching the Score. With `postgres` in mode `compose`, the Forager no longer starts a Postgres per workload: it creates a role and a database of their own in `shared-pg`, the shared Postgres that `platform init` installs in `platform-local`. Only `platform-admins` set the policy, since it decides where data lives.

```bash
platform environment policy set demo --file - <<'POLICY'
provisioners:
  - type: postgres
    mode: compose
    params:
      instance: shared-pg
POLICY
```

``` { .text .output title="output" }
✓ demo: policy set
LAYER        TYPE      CLASS  ID  MODE       PARAMS
environment  postgres  —      —   compose    instance=shared-pg
default      postgres  —      —   provision  —
```

`platform environment policy get demo` shows the same table: the policy of the environment, then the platform default, in the order the Forager reads them. The first row that matches the resource wins.

The same version `0.5.0` of step 21.7, deployed after a `workload remove`:

```bash
platform workload deploy \
  --component hello-api \
  --environment demo \
  --version 0.5.0 \
  --wait

platform workload get \
  --component hello-api \
  --environment demo
```

``` { .text .output title="output" }
✓ hello-api@demo revision 10: 0.5.0 running · 1/1 replicas available
hello-api@demo (Available)
  ...
  resource      db (postgres, compose): Ready
```

The app now connects to its own database in `shared-pg`:

``` { .text .output title="output" }
  current_database
---------------------
 hello-api-db-<hash>
(1 row)
```

- `PGHOST` is `shared-pg.resources`: each vcluster replicates the `shared-pg` Service of the host into its namespace `resources`. `PGDATABASE` and `PGUSER` are `hello-api-db-<hash>`, and the role connects only to its own database.
- `workload remove` drops the database and the role. Deleting the environment does too, and its policy goes with it.
- An environment that already has the database in another mode keeps it: the revision ends `ResourceModeChanged`, and changing the mode takes a `workload remove` and a new deploy.
- `compose` needs `params.instance`: without it, `policy set` is refused.

!!! note
    `shared-pg` is in the catalog as the Resource `shared-pg` of `team-platform` (System `platform`), imported from `idp/catalog/platform.yaml`. Its admin password is in the Secret `shared-pg-admin` of `platform-resources`, read only by the Forager. Environments created before this version have no `shared-pg.resources`: create them again.
