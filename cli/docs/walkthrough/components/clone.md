# Clone the component

The repo of a component comes from the catalog, so cloning it does not need the org or the repo name:

```bash
platform catalog component clone hello-api
```

``` { .text .output title="output" }
# git clone git@github.com:wasp-foundry/hello-api.git
Cloning into 'hello-api'...
```

The CLI prints the `git clone` it runs and lets the output and the exit code of `git` through. Git uses your own credentials (your SSH key, or the HTTPS credential helper): the platform hands out none.

SSH is the default. `--https` clones over HTTPS, and `--directory` picks where:

```bash
platform catalog component clone hello-api \
  --https \
  --directory /tmp/hello-api
```

``` { .text .output title="output" }
# git clone https://github.com/wasp-foundry/hello-api.git /tmp/hello-api
Cloning into '/tmp/hello-api'...
```

To make HTTPS the default, add `git_protocol: https` to `~/.config/platform/config.yaml`; `--https` still wins over a `git_protocol: ssh` there.

A name the catalog does not know is refused before `git` runs, and so is a component still being created:

``` { .text .output title="output" }
✗ 404: component 'nope' not found: see the components with platform catalog component list
✗ other-api is still being created: follow it with platform catalog component get other-api
```
