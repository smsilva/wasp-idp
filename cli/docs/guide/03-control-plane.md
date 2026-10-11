# Control plane

O login usa o Google através do Keycloak. Exporte as credenciais do OAuth client antes do `init`; o passo a passo do lado do Google está em `platform/keycloak/README.md`. Sem elas, o `init` sobe tudo e avisa que o login com Google fica desligado.

```bash
export GOOGLE_CLIENT_ID=<id>.apps.googleusercontent.com
export GOOGLE_CLIENT_SECRET=<secret>
platform init --target local --admin voce@example.com
```

```
creating cluster platform-local …
applying CRDs …
building the Platform API image …
deploying the Platform API …
deploying Keycloak …
waiting for Keycloak …
applying the realm platform …
✓ Platform API at http://127.0.0.1:9090 · config in ~/.config/platform/config.yaml
✓ Keycloak issuer http://localhost:8180/realms/platform
```

O e-mail do `--admin` entra no grupo `platform-admins` no primeiro login com Google; os demais usuários caem só em `platform-users`. O `init` lembra o `--admin` e as credenciais do Google, então as execuções seguintes não precisam repeti-los.

Para registrar [contas AWS](13-cloud-accounts.md), passe também `--aws-profile <profile>`: a credencial desse profile do `~/.aws` vira a credencial base da plataforma, e o `init` sobe o provider `aws_account`. O `init` também lembra essa credencial. Se ela for temporária (SSO ou role assumida), o `init` avisa quando expira e precisa ser refeito; o recomendado é um IAM user dedicado, com permissão só para `sts:AssumeRole` e `sts:GetCallerIdentity`.

Rodar de novo é seguro: o cluster é reaproveitado.

```bash
platform init --target local
```

```
cluster platform-local already exists, reusing it
…
```

```bash
cat ~/.config/platform/config.yaml
```

```yaml
target: local
api_url: http://127.0.0.1:9090
context: k3d-platform-local
issuer: http://localhost:8180/realms/platform
client_id: platform-cli
```
