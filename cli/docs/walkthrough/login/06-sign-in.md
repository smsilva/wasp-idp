# Sign in

```bash
platform login --use-device-code
```

Abra a URL impressa no navegador e passe pelas telas: **confirmar o código**, **entrar com Google**, **revisar o perfil** (só no primeiro login) e **autorizar o terminal**. O terminal termina em `✓ Logged in as voce@example.com (platform-admins, platform-users)`.

!!! tip
    `platform login` sem flag abre o navegador padrão sozinho. Use o device code quando o navegador padrão estiver em outra conta Google, ou numa apresentação, para mostrar as telas do Keycloak.
