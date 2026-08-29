# Supernet CIDR allocation

**Status:** Aceito

## Contexto

Cada VPC (hub ou spoke) precisa de um CIDR que não colida com as demais, atravessando contas e
regiões. Sem um plano de alocação, cada camada nova arrisca escolher um bloco que já está em uso
em outra conta/região.

## Decisão

Supernet `10.0.0.0/12`, alocado por `/16` no segundo octeto:

| N | CIDR | Conta | Papel |
|---|---|---|---|
| 0 | `10.0.0.0/16` | — | reservado à Organization |
| 1 | `10.1.0.0/16` | `network` | VPC hub `us-east-1` |
| 2 | `10.2.0.0/16` | `cicd` | VPC spoke do Control Plane |
| 3 | `10.3.0.0/16` | `network` | VPC hub `us-west-2` |
| 4–15 | `10.4`–`10.15` | — | livres |

Fora do supernet, já reservados pelo plano ativo: `100.64.0.0/22` (client CIDR do Client VPN) e
`10.50.0.0/16` (VNet do cliente simulado no Azure).

## Consequências

**É a única decisão irreversível da cadeia inteira.** Teto de 15 spokes, e cada região nova
multiplica o consumo — 10 tenants em 2 regiões já estoura o supernet. Mudar o esquema depois exige
renumerar VPCs já aplicadas, o que derruba rotas e attachments existentes.

Um IPAM Scope da AWS resolveria a alocação manual (a raiz pediria só o tamanho da rede, não o
CIDR), mas fica para depois da fase em curso — ver issue de `network-foundation` sobre IPAM.
