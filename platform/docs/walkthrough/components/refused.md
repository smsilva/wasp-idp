# What is refused before GitHub

The API checks everything before it writes the request, so a refused create leaves nothing on GitHub:

```bash
platform catalog component create seat-selection \
  --system seat-map

platform catalog component create other-api \
  --system nope

platform catalog component create other-api \
  --system seat-map \
  --param colour=blue
```

``` { .text .output title="output" }
✗ 409: component 'seat-selection' already exists
✗ 422: component 'other-api': system 'nope' not found
✗ 422: params.colour: not a parameter of python-service (port)
```

| Refusal | Code |
|---|---|
| the system does not exist, the template does not exist, a `--param` outside the template's schema | `422` |
| the name is in the catalog or already being created | `409` |
| the connection is not `ready`, or there is no default connection and no `--scm` | `409` |

A repo with the same name created outside the platform stops the creation at `RepoAlreadyExists`, and the platform does not touch that repo. `wasp-foundry/greeting-api`, made earlier by the Backstage scaffolder, shows it:

```bash
platform catalog component create greeting-api \
  --system seat-map \
  --wait
```

``` { .text .output title="output" }
  ✓ Validated: scm connection 'wasp-foundry' is ready
  ✓ Rendered: 19 files from python-service@5adb796c62a44bb2b580dda4ef7d21d49ae82ba9
  … RepoCreated: wasp-foundry/greeting-api exists and was not created by this request: it is left untouched
✗ greeting-api: RepoAlreadyExists: wasp-foundry/greeting-api exists and was not created by this request: it is left untouched
```

`--wait` ends with the way out:

``` { .text .output title="output" }
  rename it, request it again with --replace, or free the name with: platform catalog component creation delete greeting-api
```

The stopped creation keeps the name for 24 h. Until then, `create` with that name answers `409`, says what stopped it and points to the two ways out:

``` { .text .output title="output" }
✗ component 'greeting-api': its last creation stopped at RepoAlreadyExists (wasp-foundry/greeting-api exists and was not created by this request: it is left untouched): pass --replace to request it again, or free the name with: platform catalog component creation delete greeting-api
```

`component creation list` shows the creations you requested, with the step each one stopped at and when it frees its name:

```bash
platform catalog component creation list
```

``` { .text .output title="output" }
NAME          STATUS             STEP         REQUESTED BY                          AGE  FREES IN
greeting-api  RepoAlreadyExists  RepoCreated  9b1c6f0e-3d2a-4c55-8f7e-2a1d0c4b6e11  2m   23h 57m
```

Once the repo on GitHub is dealt with (deleted, or the component renamed), free the name and request it again:

```bash
platform catalog component creation delete greeting-api
```

``` { .text .output title="output" }
✓ creation of greeting-api deleted: greeting-api is free
```

Or do both in one step with `--replace`, which takes the place of the stopped creation:

```bash
platform catalog component create greeting-api \
  --system seat-map \
  --replace \
  --wait
```

Only who requested the creation, or `platform-admins`, may replace or delete it. A creation still running is refused with `409`: it would leave a half-made repo behind.
