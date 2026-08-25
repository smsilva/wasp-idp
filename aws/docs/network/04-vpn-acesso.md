# 04 — VPN de Acesso

**Pilar WAF principal:** Security ([SEC05](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/protecting-networks.html)/[SEC08](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/protecting-data-at-rest.html) — conectividade privada e criptografia em
trânsito) + Reliability ([REL02-BP01](https://docs.aws.amazon.com/wellarchitected/latest/reliability-pillar/rel_planning_network_topology_ha_conn_users.html) — conectividade HA).

## Princípio: a VPN fecha sempre no Hub

Toda VPN — site-to-site (on-prem/outro cloud), acesso do concentrador de TI, ou client VPN
— termina no **Hub**, nunca num spoke. Motivos:

- **Um ponto de entrada** para observar e proteger (não N VPNs espalhadas).
- **Reuso**: uma VPN no Hub serve todos os spokes via TGW, com isolamento por route table.
- **Inserção futura de firewall central** sem tocar nos spokes.

Um spoke **nunca** cria seu próprio VPN Gateway. Se um cluster precisa de acesso via VPN, a
rota é: cluster → spoke attachment → `tgw-rt-<spoke>` → VPN attachment (no Hub) → túnel.

## Tipos de VPN nesta referência

| Tipo | Uso | Termina em |
|---|---|---|
| **Site-to-Site VPN** | on-prem, outro cloud (ex.: Azure), concentrador de TI | Customer Gateway + VPN Connection no Hub |
| **Client VPN** (futuro) | acesso de operadores/desenvolvedores à rede privada | Client VPN Endpoint no Hub, autenticação por certificado/SSO |

Esta rodada foca **site-to-site** (o que o hub-and-spoke exige). Client VPN entra quando o
acesso humano à rede for necessário — mesma regra: fecha no Hub.

## Anatomia de uma Site-to-Site VPN

```text
Peer remoto (IP público)          Hub (AWS)
        │                            │
   CustomerGateway  ◄───────────►  VPNConnection ──► Transit Gateway
        │                            │  (2 túneis IPSec built-in por conexão)
        │                            └─ associação + propagação em tgw-rt-hub
        └─ BGP (ASN do peer)            BGP (amazonSideAsn do TGW)
```

- **1 Customer Gateway por IP de peer remoto** (com `bgpAsn` do peer, quando BGP).
- **1 VPN Connection por Customer Gateway** — a AWS cria **2 túneis IPSec** por conexão
  (não configurável; é redundância nativa).
- Para peers **BGP**: propagação automática do attachment em `tgw-rt-hub` (rotas dinâmicas).
- Para peers **estáticos**: rotas por CIDR remoto declaradas explicitamente.

## BGP + ECMP: alta disponibilidade e performance sem failover manual

- **BGP** anuncia e retira rotas dinamicamente conforme túneis/instâncias sobem e descem —
  sem `apply` no peer remoto a cada mudança de CIDR. Sem BGP, o failover entre os 2 túneis
  depende de rotas estáticas com comportamento imprevisível.
- **ECMP** (Equal-Cost Multi-Path) distribui tráfego por **todos** os túneis ativos ao mesmo
  tempo — não só em failover. No TGW, ECMP funciona **apenas em rotas propagadas** (BGP),
  não estáticas. Por isso se propaga o attachment, em vez de instalar rota estática.

Juntos: qualquer túnel pode cair sem interrupção (HA) **e** a capacidade agregada é a soma
dos túneis (performance) — sem "preferido" estático.

## Redundância para peer active-active (ex.: Azure)

Um peer com **2 IPs públicos** (gateway active-active) exige **2 VPN Connections** (uma por
IP) — senão o 2º IP fica ocioso e o active-active vira active-standby. Com 2 conexões × 2
túneis = **4 túneis IPSec** com BGP em todos.

## Parâmetros de segurança IPSec

| Parâmetro | Valor recomendado | Observação |
|---|---|---|
| Protocolo | IKEv2 | |
| Encriptação | AES256 | |
| Integridade | SHA2-256 | |
| DH group | 14 | AWS não suporta DHGroup24 (padrão de alguns peers) — fixar 14 |
| PSK (shared key) | gerado pela AWS ou acordado externamente | Ver ciclo de vida abaixo |
| Inside CIDRs (APIPA) | `169.254.x.x/30` por túnel | par por túnel para BGP peering |

## Ciclo de vida do PSK

- **PSK gerado pela AWS**: ao criar a VPN Connection, a AWS gera 1 PSK por túnel. No mundo
  Crossplane, é escrito como **K8s Secret** no namespace (via `writeConnectionSecretToRef`)
  — é o ponto de entrega para configurar o lado remoto.
- **PSK acordado externamente**: quando o peer (parceiro/cliente) traz o PSK, ele é lido de
  um secret e informado na criação.

Proteção do PSK = controle de acesso ao secret. A confidencialidade isolada do PSK não é
vetor relevante (IPSec já usa AES256 + IKEv2). Sem rotação automática nesta fase.

## Well-Architected — porquê

| Best practice | Como atende |
|---|---|
| **[SEC08-BP01](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/sec_protect_data_rest_key_mgmt.html)/BP02** criptografia em trânsito | IPSec IKEv2/AES256 em todos os túneis |
| **[SEC05-BP01](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/sec_network_protection_create_layers.html)** entrada única controlada | VPN fecha só no Hub, observável e protegível num ponto |
| **[REL02-BP01](https://docs.aws.amazon.com/wellarchitected/latest/reliability-pillar/rel_planning_network_topology_ha_conn_users.html)** conectividade HA | 2 túneis por conexão + BGP + ECMP; 2 conexões p/ peer active-active |
| **OPS** rotas dinâmicas | BGP elimina toil de atualizar rotas manualmente a cada tenant novo |

## Próximo

→ [`05-dns.md`](05-dns.md): resolução de nomes — zonas por spoke, delegação e resolução
cross-account.
