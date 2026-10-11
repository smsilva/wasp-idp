# Walkthrough

Roteiro para demonstrar a CLI `platform` **partindo do zero**: sem cluster, sem config e sem a CLI instalada. Esta página é a sequência para apresentar ou para conferir que tudo continua funcionando; o guia de uso, com cada comando explicado, é a [página principal](../index.md).

!!! info "Última execução"
    Rodado de ponta a ponta em 2026-10-10; os passos 8 a 11 foram refeitos com o provider `local_vcluster` (#183) e o passo 14 (#190) no `platform-local`, no mesmo dia. O passo 18 (#199) foi rodado em 2026-10-11, com o App `wasp-foundry-platform` criado e instalado na org `wasp-foundry`.

## Preparação

**Um terminal** e **um navegador** logado na conta Google que vai entrar na plataforma. O provider de ambientes roda dentro do cluster.

| Etapa | Tempo |
|---|---|
| `platform init` do zero | ~4 min |
| Login (device code + Google) | ~1 min, manual |
| Ambiente pronto (vcluster) | ~30 s |
| Roteiro inteiro | ~10 min |

Cada passo mostra o comando e, logo abaixo, a **saída** esperada.

## Roteiro


**Preparar o ambiente**

- [0. Partir do zero](setup/00-from-scratch.md)
- [1. Pré-requisitos](setup/01-prerequisites.md)
- [2. Instalar a CLI](setup/02-install.md)
- [3. Credenciais do Google](setup/03-google-credentials.md)
- [4. Subir o control plane](setup/04-control-plane.md)

**Login**

- [5. Sem login, a API recusa](login/05-refused.md)
- [6. Entrar](login/06-sign-in.md)
- [7. Quem sou eu](login/07-whoami.md)

**Ambientes**

- [8. Criar um ambiente](environments/08-create.md)
- [9. O provider por dentro](environments/09-provider.md)
- [10. Usar o ambiente](environments/10-use.md)
- [11. Segundo ambiente, em paralelo](environments/11-second.md)
- [12. Trilha de auditoria](environments/12-audit-trail.md)

**Catálogo**

- [13. Domínios, sistemas e recursos](catalog/13-entities.md)
- [14. Importar o catálogo do Backstage](catalog/14-backstage-import.md)

- [15. Times](15-teams.md)
- [16. Templates de component](16-templates.md)
- [17. Contas de nuvem](17-cloud-accounts.md)
- [18. Connection com o GitHub](18-scm-connection.md)
- [19. Limpar e sair](19-cleanup.md)

Sem navegador: [`scripts/demo/cli-smoke`](cli-smoke.md).

## Ideias para tornar o roteiro repetível

??? abstract "Issues abertas para o roteiro"

    - **Script `scripts/demo/cli-walkthrough` (#178):** roda os passos em sequência, pausa antes de cada um (Enter para seguir) e para no login esperando o device code. Serve para apresentar e para conferir antes de um merge.
    - **Medir (#180):** guardar o tempo de cada etapa (como na tabela acima) para perceber quando o `init` ou o provider ficam mais lentos.
    - **Gravar (#181):** `asciinema rec` durante o roteiro gera um vídeo de terminal leve para o README e para o deck.
    - **Evoluir junto com a CLI (#182):** cada comando novo (`release create`, `catalog component create`) entra aqui como um passo, com a saída esperada.
