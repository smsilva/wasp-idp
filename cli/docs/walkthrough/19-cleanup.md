# Cleanup

```bash
platform environment delete demo

platform environment delete greetings-test

kubectl --context k3d-platform-local get namespaces | grep env- || echo "no environments"

platform logout

platform whoami
```

``` { .text .output title="saída" }
✓ Logged out
✗ not logged in: run 'platform login'
```

!!! tip
    O `platform-local` continua no ar para a próxima rodada; para desmontar tudo, volte ao [passo 0](setup/00-from-scratch.md).
