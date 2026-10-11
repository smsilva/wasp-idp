# Login

Todo comando além de `init` fala com a Platform API, que exige um token do Keycloak.

```bash
platform login
```

```
Opening the browser to sign in …
✓ Logged in as voce@example.com (platform-admins, platform-users)
```

O navegador vai direto à tela do Google e termina em "Login complete. You can return to the terminal.". Por trás, a CLI usa Authorization Code com PKCE e recebe o código num listener temporário em `127.0.0.1`.

Sem navegador nesta máquina (SSH, container), use o device code e abra a URL em qualquer outro dispositivo:

```bash
platform login --use-device-code
```

```
Open http://localhost:8180/realms/platform/device?user_code=ABCD-EFGH
and confirm the code ABCD-EFGH
✓ Logged in as voce@example.com (platform-admins, platform-users)
```

Para testes sem ninguém (`scripts/demo/cli-smoke`), o target local tem dois usuários de teste: `platform login --test-user` (`platform-users`) e `--test-admin` (`platform-admins`). As opções ficam fora do `--help` e recusam outro target; o motivo e o que o `init` cria estão em `platform/keycloak/README.md`.

```bash
platform whoami
```

```
voce@example.com (platform-admins, platform-users)
```

O `whoami` pergunta à API quem ela vê; não lê o token localmente. Os tokens ficam em `~/.config/platform/credentials` (permissão `0600`), e a CLI renova o access token sozinha quando faltam menos de 60 s para ele expirar. `platform logout` revoga a sessão no Keycloak e apaga o arquivo.

!!! warning
    O Keycloak precisa ser alcançado em `localhost:8180` pelo navegador: é o endereço que o Google aceita como redirect. Em SSH, use `--use-device-code` com um túnel (`ssh -L 8180:localhost:8180`).
