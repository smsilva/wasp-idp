# From scratch

!!! warning
    Deletes the local control plane, the environments and the credentials. The Keycloak user is recreated on first sign-in.

```bash
k3d cluster delete platform-local

rm -rf ~/.config/platform

make cli-uninstall
```
