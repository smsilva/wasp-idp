# Cleanup

## 18. Limpar e sair

```bash
platform environment delete demo
platform environment delete greetings-test
kubectl --context k3d-platform-local get namespaces | grep env- || echo "no environments"
platform logout
platform whoami
```

``` { .text .output title="saída" }
✓ Logged out
✗ not logged in: run 'platform login'
```

!!! tip
    O `platform-local` continua no ar para a próxima rodada; para desmontar tudo, volte ao [passo 0](01-setup.md#0-partir-do-zero).

## Sem navegador: `scripts/demo/cli-smoke`

O roteiro tem um passo humano, o login. O `scripts/demo/cli-smoke` (#179) roda o fluxo sem ninguém: `init`, login com o usuário de teste (`platform-users`), a recusa `403` ao criar um domínio, um ambiente criado com `--wait` e apagado, login com o admin de teste, `catalog import idp/catalog/` (aplicado e depois `nothing to do`), os templates (`list` como usuário comum, recusa `403` no `create`, `render` do seed sem nenhum `${{` restante, plano do import do template do Backstage com os `steps` ignorados), uma cloud account (`409` pedindo `--aws-profile` sem credencial base; com ela, uma role que a plataforma não assume fica `TrustNotEstablished`, e outro usuário não a vê nem registra a mesma role) e `logout`. Ele para na primeira falha, com código diferente de zero.

```bash
scripts/demo/cli-smoke              # do zero, com platform init
scripts/demo/cli-smoke --skip-init  # reaproveita o platform-local que já está no ar
```

!!! note
    Os usuários `platform-smoke` e `platform-smoke-admin` e o client `platform-smoke` existem só no target local. A justificativa do password grant está em `platform/keycloak/README.md`.

## Ideias para tornar o roteiro repetível

??? abstract "Issues abertas para o roteiro"

    - **Script `scripts/demo/cli-walkthrough` (#178):** roda os passos em sequência, pausa antes de cada um (Enter para seguir) e para no login esperando o device code. Serve para apresentar e para conferir antes de um merge.
    - **Medir (#180):** guardar o tempo de cada etapa (como na tabela acima) para perceber quando o `init` ou o provider ficam mais lentos.
    - **Gravar (#181):** `asciinema rec` durante o roteiro gera um vídeo de terminal leve para o README e para o deck.
    - **Evoluir junto com a CLI (#182):** cada comando novo (`release create`, `catalog component create`) entra aqui como um passo, com a saída esperada.
