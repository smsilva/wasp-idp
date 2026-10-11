# Catalog entities

O dono de uma entidade é **um time que já existe** (ADR 0026). Como admin, crie o `team-alpha` antes de tudo.

!!! step "Criar o time e a hierarquia"

    Um domínio, um subdomínio, um sistema dentro dele e um recurso do sistema, todos do `team-alpha`:

    ``` { .text .plan title="o que vai ser criado" }
    team-alpha              time · dono de tudo abaixo
    communication           domínio
    └── messaging           subdomínio
        └── greeter         sistema
            └── greeting-db recurso · database
    ```

    Os comandos, na ordem em que cada entidade precisa da anterior:

    ```bash
    platform team create team-alpha

    platform catalog domain create communication \
      --owner team-alpha

    platform catalog domain create messaging \
      --parent communication \
      --owner team-alpha

    platform catalog system create greeter \
      --domain messaging \
      --owner team-alpha

    platform catalog resource create greeting-db \
      --type database \
      --system greeter \
      --owner team-alpha
    ```

!!! step "Consultar"

    O `get` mostra quem **depende** da entidade:

    ```bash
    platform catalog list

    platform catalog system get greeter
    ```

    ``` { .text .output title="saída" }
    system/greeter
      domain       messaging
      owner        team-alpha
      description  —
      dependents   resource/greeting-db
    ```

!!! step "Um domínio com dependentes não sai"

    ```bash
    platform catalog domain delete messaging
    ```

    ``` { .text .output title="saída" }
    ✗ 409: domain 'messaging' has dependents: system/greeter
    ```

!!! step "Por baixo, são CRDs"

    ```bash
    kubectl get domains.catalog.platform.wasp.silvios.me \
      --context k3d-platform-local \
      --namespace platform-system
    ```

    ``` { .text .output title="saída" }
    NAME            PARENT          OWNER
    communication                   team-alpha
    messaging       communication   team-alpha
    ```

!!! tip "O catálogo é da plataforma"
    Funciona com o Backstage parado.

!!! step "Limpar, na ordem inversa"

    ```bash
    platform catalog resource delete greeting-db

    platform catalog system delete greeter

    platform catalog domain delete messaging

    platform catalog domain delete communication
    ```
