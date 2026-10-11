# Teams

## 15. Times

Como admin, entre no `team-alpha`, criado no [catálogo](04-catalog.md#13-catalogo) (ADR 0026). O time chega ao token no próximo login.

```bash
platform team member add team-alpha voce@example.com
platform team get team-alpha
platform login
platform whoami
```

``` { .text .output title="saída" }
✓ voce@example.com added to team-alpha
team-alpha: 1 member(s)
EMAIL             USERNAME
voce@example.com  voce@example.com
voce@example.com (platform-admins, platform-users, team-alpha)
```

Compartilhe um ambiente com o time. Quem está nele passa a vê-lo no `environment list` e a receber o kubeconfig:

```bash
platform environment share demo --team team-alpha
platform environment list
platform environment unshare demo --team team-alpha
```

``` { .text .output title="saída" }
✓ demo shared with team-alpha
NAME            PROFILE    STATUS  EXPIRES  OWNER             SHARED
demo            ephemeral  ready   52m      voce@example.com  team-alpha
greetings-test  ephemeral  ready   48m      voce@example.com  —
✓ demo no longer shared with team-alpha
```

Um time em uso não é apagado: o catálogo importado no [passo 14](04-catalog.md#14-importar-o-catalogo-do-backstage) tem entidades do `team-alpha`.

```bash
platform team delete team-alpha
```

``` { .text .output title="saída" }
✗ 409: team 'team-alpha' is still in use: domain/communication, …; unshare or change the owner first
```
