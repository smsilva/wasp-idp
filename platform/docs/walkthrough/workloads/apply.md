# The plan of an environment

`deploy` acts on one workload. The **plan** declares every workload of an environment in one file, as a helmfile does for Helm releases, and `apply` writes a revision for each one that changes:

```bash
cat > demo.yaml <<PLAN
environment: demo
workloads:
  hello-api:
    branch: feat/greetings
    replicas: 2
PLAN

platform workload apply \
  --file demo.yaml \
  --dry-run
```

``` { .text .output title="output" }
WORKLOAD        ACTION  FROM  TO                          REVISION
hello-api@demo  add     —     0.1.0-greetings.b5f9569 ×2  —
demo: 1 to add, 0 to change, 0 to remove
dry run: nothing applied
```

- The environment comes from the file; each key under `workloads` is an instance, named after its component unless `component:` names another one (an extra instance, see [Another instance of the same component](instances.md)).
- Each workload takes `version` or `branch` (the newest version built from it, pinned in the revision) and optionally `replicas` (1 by default) and `resourceClasses` (resource to class, as `deploy --resource-class`, see [A database that already exists](resources/bind.md)).
- The API diffs the plan against the newest revision of each workload: `add` when it does not run, `change` when the version, the replicas or the resource classes differ or the newest revision failed, `unchanged` otherwise.

Apply it and wait for the rollouts:

```bash
platform workload apply \
  --file demo.yaml \
  --wait

platform workload apply \
  --file demo.yaml \
  --dry-run
```

``` { .text .output title="output" }
WORKLOAD        ACTION  FROM  TO                          REVISION
hello-api@demo  add     —     0.1.0-greetings.b5f9569 ×2  6
demo: 1 to add, 0 to change, 0 to remove
✓ hello-api@demo revision 6: 0.1.0-greetings.b5f9569 running · 2/2 replicas available
  url           http://hello-api.demo.localhost:7080/
  resource      db (postgres, provision): Ready
  resource      dns (dns, provision): Ready
  resource      route (route, provision): Ready
WORKLOAD        ACTION     FROM                        TO                          REVISION
hello-api@demo  unchanged  0.1.0-greetings.b5f9569 ×2  0.1.0-greetings.b5f9569 ×2  —
demo: 0 to add, 0 to change, 0 to remove
dry run: nothing applied
```

Applying the same plan again writes nothing. Every workload of the plan is authorized and resolved before the first revision: a version missing from the index, or a component outside your teams, refuses the whole plan.

Without `--prune`, workloads that the plan leaves out stay as they are. With it, each one gets a remove revision. An empty plan (`workloads: {}`) with `--prune` empties the environment:

```bash
cat > empty.yaml <<PLAN
environment: demo
workloads: {}
PLAN

platform workload apply \
  --file empty.yaml \
  --prune \
  --wait
```

``` { .text .output title="output" }
WORKLOAD        ACTION  FROM                        TO  REVISION
hello-api@demo  remove  0.1.0-greetings.b5f9569 ×2  —   7
demo: 0 to add, 0 to change, 1 to remove
✓ hello-api@demo revision 7: removed from demo
```
