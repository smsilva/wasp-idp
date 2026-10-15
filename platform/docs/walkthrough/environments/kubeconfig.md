# Write the kubeconfig

`get` on a ready environment writes the kubeconfig to `~/.config/platform/environments/`:

```bash
platform environment get demo

kubeconfig=~/.config/platform/environments/demo.kubeconfig
```

``` { .text .output title="output" }
demo: ready
  vcluster running in namespace env-demo, API on 127.0.0.1:7100
  kubectl --kubeconfig ~/.config/platform/environments/demo.kubeconfig get nodes
  workloads at http://*.demo.localhost:7080

next:

  platform workload deploy \
    --component <component> \
    --environment demo \
    --version <version>

  platform workload list \
    --environment demo

  platform environment policy get demo
```
