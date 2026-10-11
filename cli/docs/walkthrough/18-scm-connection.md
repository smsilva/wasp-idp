# SCM connection

A connection diz à plataforma **em que org criar repos** e **com que credencial** (ADR 0025). Só `platform-admins` a gerenciam.

``` { .text .plan title="o que vai ser criado" }
wasp-foundry                connection · a padrão
└── wasp-foundry-platform   GitHub App da org wasp-foundry, em todos os repositórios
```

!!! step "Criar o App"

    === "App novo, pelo navegador"

        O `add` abre o navegador na Platform API, que manda o **manifesto** do App `<org>-platform` para o GitHub. O GitHub devolve a chave **direto para a plataforma**, sem passar pela máquina de quem roda o comando.

        ```bash
        platform scm connection add wasp-foundry \
          --vendor github \
          --org wasp-foundry \
          --default
        ```

        ``` { .text .output title="saída" }
        → opening the browser to create the GitHub App "wasp-foundry-platform" …
        ✓ app created (id 5274859) · private key stored by the platform
        → install it on the org: https://github.com/apps/wasp-foundry-platform/installations/new
          then run: platform scm connection verify wasp-foundry --wait
        ```

        No GitHub, quem confirma precisa ser **owner da org**. Nome e permissões já vêm do manifesto: só confirme em **Create GitHub App for wasp-foundry**.

        ![Tela do GitHub para criar o App wasp-foundry-platform pelo manifesto](images/scm-01-create-app.png){ .screenshot loading=lazy width="540" }

        !!! tip
            `--no-browser` só imprime a URL, para abrir em outra máquina. Ela é **de uso único** e vale **10 minutos**; rodar o `add` de novo emite outra.

    === "App que já existe"

        Entra sem navegador, com a chave baixada do GitHub. A chave vai para a plataforma e **não fica** no `~/.config/platform`.

        ```bash
        platform scm connection add wasp-foundry \
          --vendor github \
          --org wasp-foundry \
          --app-id 123456 \
          --private-key-file wasp-foundry-platform.private-key.pem \
          --wait
        ```

!!! step "Instalar na org"

    O GitHub volta para a plataforma, que leva à instalação:

    ![Página "App created" da Platform API, com o botão Install on wasp-foundry](images/scm-02-app-created.png){ .screenshot loading=lazy width="500" }

    Instale em **All repositories**; as permissões são as do manifesto:

    ![Tela de instalação do App na org wasp-foundry, com All repositories marcado](images/scm-03-install.png){ .screenshot loading=lazy width="500" }

    Até aqui, a connection fica `NotInstalled`, e o `get` mostra o link:

    ```bash
    platform scm connection get wasp-foundry
    ```

    ``` { .text .output title="saída" }
    wasp-foundry (default): NotInstalled
      the App wasp-foundry-platform is not installed on wasp-foundry: https://github.com/apps/wasp-foundry-platform/installations/new
      vendor:       github
      org:          wasp-foundry
      app:          wasp-foundry-platform (id 5274859)
      install:      https://github.com/apps/wasp-foundry-platform/installations/new
    ```

!!! step "Verificar"

    Depois da instalação, o GitHub volta para a página "App installed", que **já pede a verificação**:

    ![Página "App installed" da Platform API, que já pediu a verificação](images/scm-04-app-installed.png){ .screenshot loading=lazy width="500" }

    ```bash
    platform scm connection verify wasp-foundry \
      --wait

    platform scm connection list
    ```

    ``` { .text .output title="saída" }
    ✓ wasp-foundry ready (wasp-foundry, all repositories)
    NAME          VENDOR  ORG           STATUS  DEFAULT  VALIDATED
    wasp-foundry  github  wasp-foundry  ready   yes      2026-10-11T14:52:26Z
    ```

    O `get` mostra a instalação e as permissões conferidas:

    ```bash
    platform scm connection get wasp-foundry
    ```

    ``` { .text .output title="saída" }
    wasp-foundry (default): ready
      the App is installed on every repository of the org with the permissions it needs
      vendor:       github
      org:          wasp-foundry
      app:          wasp-foundry-platform (id 5274859)
      installation: 170292387
      repositories: all
      permissions:  actions:write, administration:write, contents:write, metadata:read, pull_requests:write, workflows:write
      validated:    2026-10-11T14:52:26Z
    ```

| Status | O que fazer | `verify --wait` |
|---|---|---|
| `AppNotCreated` | rode o `add` de novo | — |
| `NotInstalled` | instale o App pelo `installUrl` do `get` | espera |
| `NotAllRepositories` | troque a instalação para All repositories | para |
| `MissingPermissions` | atualize o App e aceite na org (a mensagem lista o que falta) | para |
| `ready` | nada; o controller revalida a cada 6 h | termina |

!!! step "A chave não fica nesta máquina, nem no journal"

    ```bash
    grep --recursive "BEGIN" ~/.config/platform || echo "no key here"

    kubectl exec deploy/platform-api \
      --context k3d-platform-local \
      --namespace platform-system \
      -- grep --count BEGIN /var/lib/platform/journal.jsonl
    ```

    ``` { .text .output title="saída" }
    no key here
    0
    ```

!!! step "Remover"

    Remover apaga a connection e a chave. O App **continua no GitHub**, e a saída diz onde apagá-lo:

    ```bash
    platform scm connection remove wasp-foundry
    ```

    ``` { .text .output title="saída" }
    ✓ connection wasp-foundry removed, with its private key
      the GitHub App still exists; an org owner deletes it at https://github.com/organizations/wasp-foundry/settings/apps/wasp-foundry-platform (Advanced → Delete GitHub App)
    ```
