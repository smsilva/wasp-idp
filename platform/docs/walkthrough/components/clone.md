# Clone the component

The repo of a component comes from the catalog, so cloning it does not need the org or the repo name:

```bash
platform catalog component clone seat-selection
```

``` { .text .output title="output" }
# git clone git@github.com:wasp-foundry/seat-selection.git
Cloning into 'seat-selection'...
```

The CLI prints the `git clone` it runs and lets the output and the exit code of `git` through. Git uses your own credentials (your SSH key, or the HTTPS credential helper): the platform hands out none.

A name the catalog does not know is refused before `git` runs, and so is a component still being created:

``` { .text .output title="output" }
✗ 404: component 'nope' not found: see the components with platform catalog component list
✗ other-api is still being created: follow it with platform catalog component get other-api
```
