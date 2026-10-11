# Login

## 5. Sem login, a API recusa

```bash
platform environment list
```

``` { .text .output title="saída" }
✗ not logged in: run 'platform login'
```

## 6. Entrar

```bash
platform login --use-device-code
```

Abra a URL impressa no navegador e passe pelas telas: confirmar o código, entrar com Google, revisar o perfil (só no primeiro login) e autorizar o terminal. O terminal termina em `✓ Logged in as voce@example.com (platform-admins, platform-users)`.

!!! tip
    `platform login` sem flag abre o navegador padrão sozinho. Use o device code quando o navegador padrão estiver em outra conta Google, ou numa apresentação, para mostrar as telas do Keycloak.

## 7. Quem sou eu

```bash
platform whoami
platform whoami --output json
```

!!! note
    O `sub` é o ID imutável do usuário no Keycloak; é ele que vai para a trilha de auditoria.
