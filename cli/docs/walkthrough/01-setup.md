# Setup

## 0. Partir do zero

!!! warning
    Apaga o control plane local, os ambientes e as credenciais. O usuário do Keycloak é recriado no primeiro login.

```bash
k3d cluster delete platform-local
rm -rf ~/.config/platform
uv tool uninstall wasp-platform
```

## 1. Pré-requisitos

```bash
docker version --format '{{.Server.Version}}'
k3d version
kubectl version --client
uv --version
```

## 2. Instalar a CLI

```bash
uv tool install --editable cli/
platform --help
```

## 3. Credenciais do Google

O OAuth client do Google é configurado uma vez (veja `platform/keycloak/README.md`). Guarde o id e o secret num cofre de segredos e carregue-os no shell antes do `init`; na tela, mostre só o prefixo:

```bash
export GOOGLE_CLIENT_ID=<id>.apps.googleusercontent.com
export GOOGLE_CLIENT_SECRET=<secret>
echo "${GOOGLE_CLIENT_ID:0:12}… ${GOOGLE_CLIENT_SECRET:0:3}…"
```

## 4. Subir o control plane

```bash
time platform init --target local --admin voce@example.com
cat ~/.config/platform/config.yaml
```

``` { .text .output title="saída" }
creating cluster platform-local …
applying CRDs …
deploying Keycloak …
waiting for Keycloak …
applying the realm platform …
building the Platform API image …
deploying the Platform API …
✓ Platform API at http://127.0.0.1:9090 · config in ~/.config/platform/config.yaml
✓ Keycloak issuer http://localhost:8180/realms/platform

real    2m56s
```
