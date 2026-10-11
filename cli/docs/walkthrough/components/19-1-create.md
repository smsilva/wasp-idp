# Create a component

With the connection `ready` (step 18.3), and the system recreated after the cleanup of step 13.5, `component create` creates the repo from the default template of the type, pushes the rendered content as the first commit and registers the component in the catalog. `--prd` seeds `docs/prd.md` with your text (`-` reads stdin); without it, the template's skeleton stays:

```bash
cat > /tmp/idea.md <<'IDEA'
# Problem

People want to be greeted by name.
IDEA

platform catalog domain create communication \
  --owner team-alpha

platform catalog system create greeter \
  --domain communication \
  --owner team-alpha

platform catalog component create hello-api \
  --system greeter \
  --prd /tmp/idea.md \
  --wait
```

``` { .text .output title="output" }
  ✓ Validated: scm connection 'wasp-foundry' is ready
  ✓ Rendered: 15 files from python-service@64a8698f877a28f4c99d5b20aa74003b91c57ea2
  ✓ RepoCreated: wasp-foundry/hello-api created (public)
  ✓ Pushed: first commit 9ba3ad4 on main
  ✓ Protected: main changes only by pull request (no approval required)
  ✓ Registered: in the catalog (lifecycle: experimental)
✓ golden path “python-service” (default for service): repo wasp-foundry/hello-api created
✓ registered in the catalog (lifecycle: experimental)
✓ docs/prd.md and AGENTS.md added to the repo
✓ app-spec.yaml generated: container, postgres, route /
```

- The owner is your team when you have only one (`team-alpha`, joined in step 15.1); otherwise pass `--owner`.
- `--template` picks another template, `--type` the default of another type, `--param key=value` fills the template's extra parameters.
- The visibility comes from the connection (`public` unless it says otherwise); `--visibility private` overrides it. `main` is protected: it changes only by pull request, with no approval required. On a GitHub Free org, branch protection only exists on public repos: a private repo is still created, and `--wait` ends with a `⚠ main of … is not protected` warning ([reference](../../reference/catalog.md#components)).
- Without `--wait`, the command returns at once and `platform catalog component get hello-api` shows the steps.
- A creation is removed 24 h after it ends; the component stays in the index.
