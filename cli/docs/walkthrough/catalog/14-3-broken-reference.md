# Broken reference

A broken reference shows up in the plan with the entity, the field and the file, and **nothing is applied**. This System points to a domain that does not exist:

``` { .yaml title="/tmp/orphan.yaml" }
apiVersion: backstage.io/v1alpha1
kind: System
metadata:
  name: orphan
spec:
  owner: team-alpha
  domain: nowhere
```

Save it and import:

```bash
cat > /tmp/orphan.yaml <<'EOF'
apiVersion: backstage.io/v1alpha1
kind: System
metadata:
  name: orphan
spec:
  owner: team-alpha
  domain: nowhere
EOF

platform catalog import /tmp/orphan.yaml
```

``` { .text .output title="output" }
KIND    NAME    ACTION  DETAIL
System  orphan  error   spec.domain: domain 'nowhere' not found (/tmp/orphan.yaml#1)

0 to create, 0 to update, 0 unchanged, 0 skipped, 1 error.
✗ fix the errors above; nothing was applied
```
