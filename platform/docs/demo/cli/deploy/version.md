# Deploy the branch

```bash
platform workload deploy \
  --component seat-selection \
  --environment demo \
  --branch feat/seat-pick \
  --wait
```

``` { .text .output title="output" }
✓ seat-selection@demo revision 1: 0.1.0-seat-pick.b5f9569 running · 1/1 replicas available
  url           http://seat-selection.demo.localhost:7080/
  resource      db (postgres, provision): Ready
  resource      dns (dns, provision): Ready
  resource      route (route, provision): Ready
```

`--branch` takes the newest version built from it.
