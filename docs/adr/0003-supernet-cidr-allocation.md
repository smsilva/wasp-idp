# Supernet CIDR allocation

**Status:** Aceito

## Contexto

Cada VPC (hub ou spoke) precisa de um CIDR que não colida com as demais, atravessando contas e
regiões. Sem um plano de alocação, cada camada nova arrisca escolher um bloco que já está em uso
em outra conta/região.

## Decisão

Supernet `10.0.0.0/12`, alocado por `/16` no segundo octeto, **agrupado por região em `/14`
contíguos**:

| N | CIDR | Região (`/14`) | Conta | Papel |
|---|---|---|---|---|
| 0 | `10.0.0.0/16` | us-east-1 (`10.0.0.0/14`) | — | reservado à Organization |
| 1 | `10.1.0.0/16` | us-east-1 | `network` | VPC hub `us-east-1` |
| 2 | `10.2.0.0/16` | us-east-1 | `cicd` | VPC spoke do Control Plane |
| 3 | `10.3.0.0/16` | us-east-1 | — | livre |
| 4 | `10.4.0.0/16` | us-west-2 (`10.4.0.0/14`) | `network` | VPC hub `us-west-2` |
| 5 | `10.5.0.0/16` | us-west-2 | `cicd` | VPC spoke `us-west-2` |
| 6–7 | `10.6`–`10.7` | us-west-2 | — | livres |
| 8–15 | `10.8`–`10.15` | 2 regiões futuras | — | livres |

**Amendado em 2026-09-01 (issue #15):** a versão original alocava por **ordem de criação**
(`10.3` era o hub de `us-west-2`), o que torna impossível dar a cada região um bloco contíguo —
qualquer `/14` de `us-east-1` começando em `10.0` engole o `10.3`. Como um pool regional de IPAM
exige `locale` por região, e locale é imutável, a alocação por ordem de criação inviabilizaria a
adoção do IPAM sem re-endereçar VPC. `us-west-2` foi movida de `10.3`/`10.4` para `10.4`/`10.5`
enquanto aquela raiz tinha **0 recursos aplicados** — custo de duas linhas; com VPC de pé seria
recriação. Ver `aws/docs/network/08-ipam.md`.

Fora do supernet, já reservados pelo plano ativo: `100.64.0.0/22` (client CIDR do Client VPN) e
`10.50.0.0/16` (VNet do cliente simulado no Azure).

## Consequências

**É a única decisão irreversível da cadeia inteira.** Teto de 15 spokes, e cada região nova
multiplica o consumo — 10 tenants em 2 regiões já estoura o supernet. Mudar o esquema depois exige
renumerar VPCs já aplicadas, o que derruba rotas e attachments existentes.

Um IPAM Scope da AWS resolveria a alocação manual (a raiz pediria só o tamanho da rede, não o
CIDR). **Avaliado e decidido em [ADR 0015](0015-defer-ipam-adoption.md):** adiado, com gatilhos
declarados e um modelo mínimo executável guardado em `aws/terraform/spikes/ipam/`.

**O que esta decisão NÃO cobre, e por isso é o risco vivo:** nada impede que duas regiões recebam
o mesmo `/16`. Os CIDRs são literais nos `locals` de cada raiz regional, e a única asserção
existente compara hub vs célula **dentro da mesma raiz** — não há fonte única de verdade
verificável por máquina entre raízes. É o anti-pattern *"relying on manual IP address management
processes"* de REL02-BP05. Rastreado como issue própria; ver ADR 0015.
