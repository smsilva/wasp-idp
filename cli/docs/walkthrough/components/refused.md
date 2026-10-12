# What is refused before GitHub

The API checks everything before it writes the request, so a refused create leaves nothing on GitHub:

```bash
platform catalog component create hello-api \
  --system greeter

platform catalog component create other-api \
  --system nope

platform catalog component create other-api \
  --system greeter \
  --param colour=blue
```

``` { .text .output title="output" }
✗ component 'hello-api' already exists
✗ component 'other-api': system 'nope' not found
✗ params.colour: not a parameter of python-service (port)
```

| Refusal | Code |
|---|---|
| the system does not exist, the template does not exist, a `--param` outside the template's schema | `422` |
| the name is in the catalog or already being created | `409` |
| the connection is not `ready`, or there is no default connection and no `--scm` | `409` |

A repo with the same name created outside the platform stops the creation at `RepoAlreadyExists`, and the platform does not touch that repo. `wasp-foundry/greeting-api`, made earlier by the Backstage scaffolder, shows it:

```bash
platform catalog component create greeting-api \
  --system greeter \
  --wait
```

``` { .text .output title="output" }
  ✓ Validated: scm connection 'wasp-foundry' is ready
  ✓ Rendered: 15 files from python-service@64a8698f877a28f4c99d5b20aa74003b91c57ea2
  … RepoCreated: wasp-foundry/greeting-api exists and was not created by this request: it is left untouched
✗ greeting-api: RepoAlreadyExists: wasp-foundry/greeting-api exists and was not created by this request: it is left untouched
```
