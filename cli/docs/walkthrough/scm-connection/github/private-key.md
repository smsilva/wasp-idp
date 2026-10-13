# The GitHub App private key stays off this machine

```bash
grep --recursive "BEGIN" ~/.config/platform || echo "no key here"

kubectl exec deploy/platform-api \
  --context k3d-platform-local \
  --namespace platform-system \
  -- grep --count BEGIN /var/lib/platform/journal.jsonl
```

``` { .text .output title="output" }
no key here
0
```
