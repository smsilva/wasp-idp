# Create an environment

```bash
platform environment create greetings-test \
  --profile ephemeral \
  --expires 1h \
  --wait
```

```
provisioning greetings-test (profile: ephemeral) …
  NoProviderForCapability
  Provisioning
✓ greetings-test ready
```

A API aceita o pedido e grava um `Environment`; o status começa em `NoProviderForCapability`. O provider `local_vcluster`, que roda dentro do `platform-local`, assume o pedido em seguida e instala um vcluster no namespace `env-greetings-test`. Leva cerca de 30 s.

Sem `--wait`, o comando volta logo e o ambiente segue sendo criado:

```bash
platform environment list
```

```
NAME            PROFILE    STATUS  EXPIRES  OWNER             SHARED
greetings-test  ephemeral  ready   59m      voce@example.com  —
```

A lista mostra os seus ambientes e os compartilhados com os seus [times](12-teams.md). `--all` mostra todos, sem kubeconfig; para `platform-admins`, o padrão já é todos.
