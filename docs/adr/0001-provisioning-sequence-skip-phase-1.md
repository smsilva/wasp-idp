# Provisioning sequence skips Phase 1

**Status:** Aceito · 2026-08-26

## Contexto

O plano de referência (`decisions.md` §8) numera as fases de provisionamento de −1 a 8. A Fase 1
(Global Accelerator + tenant registry) resolve roteamento e nomeação para múltiplos clientes
externos. O escopo atual do repositório é só projetos internos, sem cliente externo — a Fase 1 não
tem o que servir ainda.

## Decisão

Sequência vigente: **−1 → 0 → 2 → 5**. A Fase 1 fica pulada por ora.

Pular a Fase 1 **não** autoriza assumir região fixa: a indireção do §5 (nome sem região no que o
usuário vê, TTL curto de DNS, tenant na chave primária) continua obrigatória mesmo sem Global
Accelerator. A indireção é uma propriedade do desenho, não uma entrega da Fase 1.

## Consequências

Qualquer trabalho de nomeação/roteamento tem de manter a indireção (não hardcodar região no nome
visível ao usuário) mesmo sem o mecanismo de Fase 1 implementado. Reintroduzir a Fase 1 mais tarde
não deve exigir renomear nada que já exista.
