# Centralized ingress via hub

**Status:** Aceito

## Contexto

Tráfego de entrada (aceite público de requisições) pode ser distribuído por spoke (cada spoke com
seu próprio ponto de entrada) ou centralizado num único ponto no hub. O desenho de referência usado
como base (comparação em
[`docs/archived/private-access/reference-design-comparison.md`](../archived/private-access/reference-design-comparison.md))
é trânsito puro, com ingress distribuído por spoke — não valida a escolha de "entrada pública no
hub", a decisão foi tomada sabendo disso.

## Decisão

**Ingress único, pelo hub.** Nenhuma spoke expõe acesso a si direto na internet — vale para
qualquer entrada, logo VGW numa spoke também está fora.

## Consequências

Um único ALB (ou ponto de entrada) no hub vira ponto único de falha e de escala (ver ADR 0009 e o
teto de certificados/rules por ALB em Open Questions). O horizonte declarado — ingress por célula —
fica fora de escopo por ora, precisamente para manter o ALB do hub numa camada descartável em vez
de crítica.
