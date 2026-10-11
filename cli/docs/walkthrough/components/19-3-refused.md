# What is refused before GitHub

The API checks everything before it writes the request, so a refused create leaves nothing on GitHub:

```bash
platform catalog component create greeting-api \
  --system greeter

platform catalog component create other-api \
  --system nope

platform catalog component create other-api \
  --system greeter \
  --param colour=blue
```

``` { .text .output title="output" }
✗ component 'greeting-api' already exists
✗ component 'other-api': system 'nope' not found
✗ params.colour: not a parameter of python-service (port)
```

| Refusal | Code |
|---|---|
| the system does not exist, the template does not exist, a `--param` outside the template's schema | `422` |
| the name is in the catalog or already being created | `409` |
| the connection is not `ready`, or there is no default connection and no `--scm` | `409` |

A repo with the same name created outside the platform stops the creation at `RepoAlreadyExists`, and the platform does not touch that repo.
