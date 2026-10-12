# A database that already exists

Some branches need data that is already there, such as a database restored from a backup. Mode `bind` points a resource at a database that exists. The Forager creates nothing and drops nothing: it hands the workload the address and copies the password from a Secret the platform team keeps. The branch picks a **class**, and the policy decides what the class binds to. The developer never sees the credential.

The platform team restores the database (here by hand, in `shared-pg`) and keeps its password in a Secret of `platform-resources` labeled `platform.wasp.silvios.me/bindable=true`. The Forager copies only labeled Secrets, so a policy cannot point at the passwords it generates itself or at the admin of a shared instance.

```bash
kubectl --namespace platform-resources create secret generic restored-db \
  --from-literal password=<password>
kubectl --namespace platform-resources label secret restored-db \
  platform.wasp.silvios.me/bindable=true
```

A `platform-admins` member adds a `bind` item with `class: restored` to the policy of the environment. The item without a class still serves every other deploy:

```bash
platform environment policy set demo --file - <<'POLICY'
provisioners:
  - type: postgres
    mode: compose
    params:
      instance: shared-pg
  - type: postgres
    class: restored
    mode: bind
    params:
      secretRef: restored-db
      host: shared-pg.resources
      database: restored
      username: restored
POLICY
```

``` { .text .output title="output" }
✓ demo: policy set
LAYER        TYPE      CLASS     ID  MODE       PARAMS
environment  postgres  —         —   compose    instance=shared-pg
environment  postgres  restored  —   bind       database=restored, host=shared-pg.resources, secretRef=restored-db, username=restored
default      postgres  —         —   provision  —
```

The deploy asks for the class with `--resource-class <resource>=<class>`, repeatable for more resources:

```bash
platform workload deploy \
  --component hello-api \
  --environment demo \
  --version 0.5.0 \
  --resource-class db=restored \
  --wait

platform workload get \
  --component hello-api \
  --environment demo
```

``` { .text .output title="output" }
✓ hello-api@demo revision 12: 0.5.0 running · 1/1 replicas available
hello-api@demo (Available)
  ...
  resource      db (postgres, bind, class restored): Ready
```

The app connects to the restored database:

``` { .text .output title="output" }
 current_database
------------------
 restored
(1 row)
```

- The class is an override of the revision, like `--replicas`. `rollback` keeps it, and a resource the version does not have is refused (`422`).
- A class with no item in the policy ends as `ResourcesNotSupported`. The branch never gets an empty database in its place.
- Changing the class of a resource that already exists ends as `ResourceModeChanged`, just like changing the mode. `workload remove` and a new deploy change it.
- `workload remove` deletes only the copy of the Secret in the vcluster. The database and the Secret of `platform-resources` stay.
- In a plan, the class goes under `resourceClasses` (`resourceClasses: {db: restored}`): `workload apply` shows the instance as `unchanged` with the same class, and as `change` without it.

!!! note
    The Forager copies the password once, when the resource becomes `Ready`. A password changed afterwards in the source Secret is not propagated: `workload remove` and a new deploy pick it up.
