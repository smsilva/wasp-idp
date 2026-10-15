# Create a component

With the platform configured ([The platform is ready](../ready.md)), a developer starts here. The system `seat-map` came with the [Backstage import](../catalog/plan.md). `component create` creates the repo from the default template of the type, pushes the rendered content as the first commit and registers the component in the catalog. `--prd` seeds `docs/prd.md` with your text (`-` reads stdin); without it, the template's skeleton stays. The idea of this component:

``` { .markdown title="/tmp/idea.md" }
# Problem

People want to be greeted by name.
```

Save it and create the component:

```bash
cat > /tmp/idea.md <<'IDEA'
# Problem

People want to be greeted by name.
IDEA

platform catalog component create hello-api \
  --system seat-map \
  --prd /tmp/idea.md \
  --wait
```

``` { .text .output title="output" }
  ✓ Validated: scm connection 'wasp-foundry' is ready
  ✓ Rendered: 19 files from python-service@5adb796c62a44bb2b580dda4ef7d21d49ae82ba9
  ✓ RepoCreated: wasp-foundry/hello-api created (public)
  ✓ Pushed: first commit c11d7df on main
  ✓ Protected: main changes only by pull request (no approval required)
  ✓ Registered: in the catalog (lifecycle: experimental)
✓ golden path “python-service” (default for service): repo wasp-foundry/hello-api created
✓ registered in the catalog (lifecycle: experimental)
✓ docs/prd.md and AGENTS.md added to the repo
✓ app-spec.yaml generated: container, postgres, route /
```

- The owner is your team when you have only one (`team-alpha`, [joined earlier](../teams/create.md)); otherwise pass `--owner`.
- `--template` picks another template, `--type` the default of another type, `--param key=value` fills the template's extra parameters.
- The visibility comes from the connection (`public` unless it says otherwise); `--visibility private` overrides it. `main` is protected: it changes only by pull request, with no approval required. On a GitHub Free org, branch protection only exists on public repos: a private repo is still created, and `--wait` ends with a `⚠ main of … is not protected` warning ([reference](../../reference/catalog.md#components)).
- Without `--wait`, the command returns at once and `platform catalog component get hello-api` shows the steps.
- A creation is removed 24 h after it ends; the component stays in the index.
