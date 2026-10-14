# CLI configuration

`platform init` leaves the CLI pointed at the control plane it created.

```bash
cat ~/.config/platform/config.yaml
```

``` { .text .output title="output" }
target: local
api_url: http://127.0.0.1:9090
context: k3d-platform-local
issuer: http://localhost:8180/realms/platform
client_id: platform-cli
```
