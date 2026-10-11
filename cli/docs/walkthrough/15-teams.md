# Teams

Como admin, entre no `team-alpha`, criado no [catálogo](catalog/13-entities.md) (ADR 0026). O time chega ao token **no próximo login**.

!!! step "Entrar no time"

    ```bash
    platform team member add team-alpha voce@example.com

    platform team get team-alpha
    ```

    ``` { .text .output title="saída" }
    ✓ voce@example.com added to team-alpha
    team-alpha: 1 member(s)
    EMAIL             USERNAME
    voce@example.com  voce@example.com
    ```

!!! step "Renovar o token"

    ```bash
    platform login

    platform whoami
    ```

    ``` { .text .output title="saída" }
    voce@example.com (platform-admins, platform-users, team-alpha)
    ```

!!! step "Compartilhar um ambiente"

    Quem está no time passa a ver o ambiente no `environment list` e a **receber o kubeconfig**:

    ```bash
    platform environment share demo \
      --team team-alpha

    platform environment list
    ```

    ``` { .text .output title="saída" }
    ✓ demo shared with team-alpha
    NAME            PROFILE    STATUS  EXPIRES  OWNER             SHARED
    demo            ephemeral  ready   52m      voce@example.com  team-alpha
    greetings-test  ephemeral  ready   48m      voce@example.com  —
    ```

!!! step "Descompartilhar"

    ```bash
    platform environment unshare demo \
      --team team-alpha
    ```

    ``` { .text .output title="saída" }
    ✓ demo no longer shared with team-alpha
    ```

**Um time em uso não é apagado:** o catálogo importado no [passo 14](catalog/14-backstage-import.md) tem entidades do `team-alpha`.

```bash
platform team delete team-alpha
```

``` { .text .output title="saída" }
✗ 409: team 'team-alpha' is still in use: domain/communication, …; unshare or change the owner first
```
