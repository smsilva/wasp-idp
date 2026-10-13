# An environment in the account

An environment that names a cloud account is provisioned in it, not as a local vcluster. The account must be `ready`, and it must be yours, shared with one of your teams, or you are in `platform-admins`:

```bash
platform environment create demo-cloud \
  --profile ephemeral \
  --cloud-account demo-aws

platform environment list
```

``` { .text .output title="output" }
provisioning demo-cloud (profile: ephemeral, cloud account: demo-aws) …
demo-cloud: NoProviderForCapability
NAME        PROFILE    ACCOUNT   STATUS                   EXPIRES  OWNER            SHARED
demo-cloud  ephemeral  demo-aws  NoProviderForCapability  —        you@example.com  —
```

- The environment stays `NoProviderForCapability` until the provider that creates things in the account (Crossplane, ADR 0032) is installed (#436): the `local_vcluster` provider leaves it alone.
- It has no vcluster: `environment get --admin`, `environment credential` and `workload deploy|apply|remove|route` answer `409`.
- The account is fixed at creation: the CRD refuses a change, and access to the account is checked only then. An unshare stops new environments, never the ones already there.
- An account in use is not removed: `platform cloud account remove demo-aws` answers `409` with the environment names.

Remove it before the next step:

```bash
platform environment delete demo-cloud
```

``` { .text .output title="output" }
✓ demo-cloud deleting
```
