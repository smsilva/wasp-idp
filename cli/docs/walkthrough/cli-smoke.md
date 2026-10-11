# Without a browser

O roteiro tem **um passo humano, o login**. O `scripts/demo/cli-smoke` (#179) roda o fluxo **sem ninguém**: `init`, login com o usuário de teste (`platform-users`), a recusa `403` ao criar um domínio, um ambiente criado com `--wait` e apagado, login com o admin de teste, `catalog import idp/catalog/` (aplicado e depois `nothing to do`), os templates (`list` como usuário comum, recusa `403` no `create`, `render` do seed sem nenhum `${{` restante, plano do import do template do Backstage com os `steps` ignorados), uma cloud account (`409` pedindo `--aws-profile` sem credencial base; com ela, uma role que a plataforma não assume fica `TrustNotEstablished`, e outro usuário não a vê nem registra a mesma role) e `logout`. Ele para na primeira falha, com código diferente de zero.

```bash
scripts/demo/cli-smoke              # do zero, com platform init

scripts/demo/cli-smoke # reaproveita o platform-local que já está no ar \
  --skip-init
```

!!! note
    Os usuários `platform-smoke` e `platform-smoke-admin` e o client `platform-smoke` existem **só no target local**. A justificativa do password grant está em `platform/keycloak/README.md`.
