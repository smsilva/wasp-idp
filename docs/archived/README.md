# Archived Docs

Narrativa de trabalho concluído que saiu de `HANDOFF.md` (raiz) para não acumular sem limite lá —
essa é a única razão desta pasta existir. `CLAUDE.md` é a referência viva (como o projeto funciona
hoje, decisões que ainda valem); aqui é histórico (o que aconteceu, e por quê).

## Estrutura

- Uma pasta por tema (`bootstrap/`, `accounts/`, `private-access/`, `terraform-layers/`, ...).
- Um arquivo por entrega, nome em inglês, curto e descritivo do tópico (ex.:
  `step-2-1-vpn-client-gate.md`, não `entrega-2026-08-26.md`).
- `index.md` é o único ponto de entrada: lista toda entrega, agrupada por tema, com data e link.

## Regras

- **Nunca apagar um arquivo já indexado** — só adicionar linha nova em `index.md`.
- Toda entrega nova exige as duas edições juntas: criar o arquivo aqui **e** adicionar a linha em
  `index.md`. Um sem o outro é órfão ou entrada morta.
- Isto guarda o que já aconteceu. Decisão de arquitetura que ainda orienta trabalho futuro pertence a
  `CLAUDE.md`, não aqui — mover para cá é para quando ela virou apenas contexto histórico.
