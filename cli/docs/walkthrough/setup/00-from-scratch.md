# From scratch

!!! warning
    Apaga o control plane local, os ambientes e as credenciais. O usuário do Keycloak é recriado no primeiro login.

```bash
k3d cluster delete platform-local

rm -rf ~/.config/platform

make cli-uninstall
```
