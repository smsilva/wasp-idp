# Hub ALB lives in the connectivity layer (T1)

**Status:** Aceito

## Contexto

O ALB do hub (ADR 0008) precisa viver nalguma camada Terraform. Três candidatas: a
`network-foundation` (T0, custo zero, permanente), a `connectivity/` (T1, descartável, contém o
TGW/Client VPN), ou uma raiz própria de "ingress do hub".

## Decisão

**O ALB do hub vive na `connectivity/` (T1).** Razão de maior peso: **sem TGW o ALB não alcança
spoke nenhuma** — sozinho ele seria só um listener servindo 404 — então o ciclo de vida dele
acompanha o do TGW, não o da VPC (regra geral do ADR 0007 aplicada aqui). Composabilidade por região
não discrimina T0 de T1: a `network-foundation` também é uma raiz por região, então "existir uma vez
por região" não é argumento a favor dela.

Rejeitados:
- **ALB na `network-foundation`** — tiraria o custo-zero da T0 e amarraria o ingress a uma camada
  que não sabe se há conectividade nenhuma.
- **Raiz própria** — uma quinta camada só para um recurso, sem outro componente que justifique o
  ciclo de vida próprio.

## Consequências

**O teardown noturno da `connectivity/` (03) derruba o ingress público de todas as células.** Isso é
aceito como consequência, não como bug — é o preço de manter o ALB numa camada descartável em vez de
crítica, e reforça o horizonte (fora de escopo) de ingress por célula do ADR 0004.
