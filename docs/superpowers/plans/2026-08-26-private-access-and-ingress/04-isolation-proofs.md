# Phase 4 — Isolation proofs

Os únicos passos com **aceite negativo**. Até aqui só se provou que o tráfego *chega*; nada provou
que o que não deve chegar **não chega** — que é a afirmação que a arquitetura inteira vende.

| # | Passo | Nível | Custo | Aceite |
|---|---|---|---|---|
| `4.1` | Segunda spoke mínima (VPC + `t4g.nano`) + grupo `cliente-a` + authorization rule por grupo | T3 | ~US$ 3/mês | **prova 1:** operador do grupo A alcança a spoke A e **não** a B; tirar do grupo derruba o acesso |
| `4.2` | `azure/terraform/simulated-client/`: VPN Gateway active-active com BGP + `tgw-rt-cliente-a` | T3 | +~US$ 36/mês AWS, ~US$ 0,19/h Azure | **prova 2:** a rede Azure alcança **só** a spoke dela; `search-transit-gateway-routes` não devolve o CIDR da spoke B na route table do cliente A |

Os dois provam coisas **diferentes**, em pontos de aplicação diferentes — um não substitui o outro:

| Mecanismo | Onde é aplicado | O que prova |
|---|---|---|
| authorization rule por grupo | endpoint do Client VPN | que **uma pessoa** só alcança a spoke do grupo dela |
| route table por attachment | tabela de rotas do TGW | que a **rede inteira** de um cliente só alcança a spoke dele |

## `4.1` — a prova barata, e a demo

A segunda spoke **não precisa de cluster**: VPC mais uma `t4g.nano` que responda basta para o teste
negativo ter alvo real. Isso derruba o custo de ~US$ 73/mês (segundo EKS) para ~US$ 3/mês.

É também a demonstração que motivou escolher SAML: criar usuário no Identity Center → pôr no grupo
`cliente-a` → ele conecta e alcança só a spoke A → tirar do grupo → perde o acesso. Nada disso existe
com autenticação por certificado.

## `4.2` — o ambiente de cliente fica no Azure

Decidido: **VPN Gateway gerenciado**, não strongSwan em VM. Mais lento e mais caro, mas é "cliente com
concentrador de verdade" — suporta BGP e active-active, que é o caso real.

Parâmetros que vêm do desenho de referência e não precisam ser redescobertos:

- **ASN BGP do lado Azure é 65515** (fixo do VPN Gateway); lado AWS usa `amazonSideAsn` 64512.
- **Inside CIDRs dos túneis em `169.254.21.0–169.254.22.255`**, `/30` cada, sem sobreposição entre
  túneis do mesmo hub — restrição específica de peering com Azure.
- **Active-active = 2 IPs públicos = 2 Customer Gateways = 2 VPN Connections = 4 túneis.**
- **VNet em `10.50.0.0/16`** — fora de `10.0.0.0/12`, então não consome o teto de 15 spokes e não
  colide com nada nosso.
- **BGP, não rotas estáticas** — é o que um cliente real faz, dá ECMP e failover sem intervenção, e
  evita rejeição de CIDR duplicado na route table.

**Armadilha operacional:** o VPN Gateway do Azure leva **30–45 min para provisionar** — de longe o
recurso mais lento de todo o plano. Planejar a sessão em torno disso.

### Raiz `azure/terraform/simulated-client/`, com os dois lados do túnel

A dependência entre as clouds é uma **cadeia**, não um ciclo — e é por isso que cabe numa raiz só:

```
PIPs do VPN Gateway (Azure)  →  Customer Gateway (AWS)  →  VPN Connection (AWS)
   →  IPs externos dos túneis + PSK  →  Local Network Gateway + Connection (Azure)
```

Em duas raízes isso exigiria três applies alternados (Azure → AWS → Azure) num recurso que leva 40 min
para nascer. Numa raiz com os dois providers, o Terraform ordena sozinho.

O lado AWS do túnel mora aqui também, via provider `aws` aliasado — **pela mesma regra de ciclo de
vida** já aplicada a `tgw-rt-<spoke>` e à listener rule do ALB: Customer Gateways, VPN Connections e a
route table do cliente morrem quando o cliente simulado morre.

| Lado | Conteúdo |
|---|---|
| Azure | resource group, VNet `10.50.0.0/16`, **`GatewaySubnet`** (o nome é obrigatório e literal), 2 public IPs, `azurerm_virtual_network_gateway` active-active com BGP ASN 65515, Local Network Gateways, Connections, e uma VM pequena para responder |
| AWS (aliasado) | 2 Customer Gateways (um por PIP), 2 VPN Connections no TGW, `tgw-rt-cliente-a` + associação + rotas |

A raiz cria também o slot `azure/terraform/`, onde a trilha Azure pausada pode aterrar depois.

### O mecanismo que esta prova exercita

**Route table por cliente, não só por spoke.** Se o attachment de VPN do cliente A associasse à
`tgw-rt-hub` — que tem todas as spokes propagadas — ele alcançaria todas, e a prova falharia. O
desenho correto é simétrico:

| Route table | Associada a | Contém |
|---|---|---|
| `tgw-rt-spoke-a` | attachment da VPC spoke A | CIDR da spoke A + `10.50.0.0/16` (volta para o cliente A) |
| `tgw-rt-cliente-a` | attachment de VPN do cliente A | **só** o CIDR da spoke A |

Cliente A não tem rota para a spoke B, e spoke A não tem rota para a rede do cliente B. Acrescentar um
cliente é acrescentar rota nos **dois** lados — explícito e aditivo, nunca por default.

O aceite tem duas formas, e vale fazer as duas: assertion por API
(`aws ec2 search-transit-gateway-routes` não devolve o CIDR da spoke B na route table do cliente A) e
conexão real que estoura o timeout contra um listener vivo na spoke B.
