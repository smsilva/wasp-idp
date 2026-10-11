# The plan of an environment

`deploy` acts on one workload. The **plan** declares every workload of an environment in one file, as a helmfile does for Helm releases, and `apply` writes a revision for each one that changes:

```bash
cat > demo.yaml <<PLAN
environment: demo
workloads:
  hello-api:
    version: 0.3.0
    replicas: 2
PLAN

platform workload apply \
  --file demo.yaml \
  --dry-run
```

``` { .text .output title="output" }
WORKLOAD        ACTION  FROM  TO        REVISION
hello-api@demo  add     —     0.3.0 ×2  —
demo: 1 to add, 0 to change, 0 to remove
dry run: nothing applied
```

- The environment comes from the file; each key under `workloads` is an instance, named after its component in phase 1 (`component:`, if given, must equal the key).
- Each workload takes `version` or `branch` (the newest version built from it, pinned in the revision) and optionally `replicas` (1 by default).
- The API diffs the plan against the newest revision of each workload: `add` when it does not run, `change` when the version or the replicas differ or the newest revision failed, `unchanged` otherwise.

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
WORKLOAD        ACTION  FROM  TO        REVISION
hello-api@demo  add     —     0.3.0 ×2  6
demo: 1 to add, 0 to change, 0 to remove
✓ hello-api@demo revision 6: 0.3.0 running · 2/2 replicas available
WORKLOAD        ACTION     FROM      TO        REVISION
hello-api@demo  unchanged  0.3.0 ×2  0.3.0 ×2  —
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
WORKLOAD        ACTION  FROM      TO  REVISION
hello-api@demo  remove  0.3.0 ×2  —   7
demo: 0 to add, 0 to change, 1 to remove
✓ hello-api@demo revision 7: removed from demo
```
