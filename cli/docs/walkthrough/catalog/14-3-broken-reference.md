# Broken reference

A broken reference shows up in the plan with the entity, the field and the file, and **nothing is applied**:

```bash
printf 'apiVersion: backstage.io/v1alpha1\nkind: System\nmetadata:\n  name: orphan\nspec:\n  owner: team-alpha\n  domain: nowhere\n' > /tmp/orphan.yaml

platform catalog import /tmp/orphan.yaml
```

``` { .text .output title="output" }
KIND    NAME    ACTION  DETAIL
System  orphan  error   spec.domain: domain 'nowhere' not found (/tmp/orphan.yaml#1)

0 to create, 0 to update, 0 unchanged, 0 skipped, 1 error.
✗ fix the errors above; nothing was applied
```
