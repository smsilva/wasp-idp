# Walkthrough

Roteiro para demonstrar a CLI `platform` partindo do zero: sem cluster, sem config e sem a CLI instalada. Esta página é a sequência para apresentar ou para conferir que tudo continua funcionando; o guia de uso, com cada comando explicado, é a [página principal](../index.md).

!!! info "Última execução"
    Rodado de ponta a ponta em 2026-10-10; os passos 8 a 11 foram refeitos com o provider `local_vcluster` (#183) e o passo 14 (#190) no `platform-local`, no mesmo dia.

## Preparação

Um terminal e um navegador logado na conta Google que vai entrar na plataforma. O provider de ambientes roda dentro do cluster.

| Etapa | Tempo |
|---|---|
| `platform init` do zero | ~4 min |
| Login (device code + Google) | ~1 min, manual |
| Ambiente pronto (vcluster) | ~30 s |
| Roteiro inteiro | ~10 min |

Cada passo mostra o comando e, logo abaixo, a **saída** esperada.

## Roteiro

1. [Do zero ao control plane](01-setup.md) — passos 0 a 4
2. [Login e identidade](02-login.md) — passos 5 a 7
3. [Ambientes](03-environments.md) — passos 8 a 12
4. [Catálogo](04-catalog.md) — passos 13 e 14
5. [Times](05-teams.md) — passo 15
6. [Templates de component](06-templates.md) — passo 16
7. [Contas de nuvem](07-cloud-accounts.md) — passo 17
8. [Limpar e sair](08-cleanup.md) — passo 18
