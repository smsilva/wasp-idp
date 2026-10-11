# SCM connections

Uma connection diz à plataforma em que org criar repos e com que credencial (ADR 0025). Nesta fatia, só GitHub, e só `platform-admins` a gerenciam.

```bash
platform scm connection add wasp-foundry \
  --vendor github \
  --org wasp-foundry \
  --default
```

O `add` abre o navegador na Platform API, que manda o manifesto do App `<org>-platform` para o GitHub. Quem confirma precisa ser owner da org. O GitHub devolve a chave direto para a plataforma, que a guarda num Secret que a API não lê; a CLI imprime o link de instalação. Instale em **All repositories** e rode:

```bash
platform scm connection verify wasp-foundry --wait
```

| Status | O que fazer |
|---|---|
| `AppNotCreated` | o App ainda não foi criado: rode o `add` de novo (o link vale 10 min e é de uso único) |
| `NotInstalled` | instale o App na org pelo `installUrl` do `get` |
| `NotAllRepositories` | a instalação cobre só alguns repos: troque para All repositories |
| `MissingPermissions` | falta permissão no App (a mensagem lista); atualize e aceite na org |
| `ready` | validada; o controller revalida a cada 6 h |

Outras formas e comandos:

```bash
platform scm connection add wasp-foundry \
  --vendor github \
  --org wasp-foundry \
  --app-id 123456 \
  --private-key-file key.pem

platform scm connection add wasp-foundry \
  --vendor github \
  --org wasp-foundry \
  --no-browser

platform scm connection list

platform scm connection get wasp-foundry

platform scm connection default wasp-foundry

platform scm connection remove wasp-foundry
```

- `--app-id` com `--private-key-file` usa um App que já existe, sem navegador. A chave vai para a plataforma e não fica no `~/.config/platform`.
- `--no-browser` só imprime a URL, para abrir em outra máquina.
- `remove` apaga a connection e a chave. O App continua no GitHub; quando foi a plataforma que o criou, a saída mostra onde apagá-lo.
