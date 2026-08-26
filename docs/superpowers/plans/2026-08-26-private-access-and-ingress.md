# Private access and centralized ingress

Plano iterativo: cada passo é testável isolado, e as decisões ainda abertas caem o mais tarde
possível. Substitui o desenho de `2026-08-25-private-ingress-via-privatelink.md`, que continua
válido na fundamentação (citações da AWS) mas cuja escolha PrivateLink-vs-TGW foi reaberta.

## Decisões que sustentam o plano

| # | Decisão | Motivo |
|---|---|---|
| 1 | **Ingress único, pelo hub.** Nenhuma spoke expõe acesso a si direto na internet | vale para qualquer entrada — logo VGW em spoke também está fora |
| 2 | **`Site-to-Site VPN` por cliente**, terminando no TGW do hub | um attachment por cliente ⟹ route table de tenant isola nas **duas** direções, sem depender de security group |
| 3 | **Acesso de manutenção: AWS Client VPN no hub, autenticação SAML** pelo Identity Center | conceder e revogar acesso a uma pessoa **é a demonstração**; e authorization rule por grupo dá CIDR-por-grupo, impossível com certificado |
| 4 | **TGW + Client VPN ficam de pé entre sessões**, destruídos ao fim do dia | o que prende o endpoint público não é `kubectl`, é o Terraform |
| 5 | **Fronteira de state segue o ciclo de vida, não a conta** | recurso da conta hub cujo ciclo é o do spoke vai no state do spoke |

### O que prende o endpoint público da API do EKS

Não é operação humana: `src/helm/modules/*` usam os providers `helm`/`kubernetes` configurados a
partir de `aws_eks_cluster_auth` — **quem fala com o API server é a máquina que roda
`terraform apply`**. Fechar o endpoint sem caminho privado não é hardening, é quebrar o
provisionamento. Por isso o acesso privado vem **antes** do resto.

Consequência: o critério de aceite de fechar o endpoint é **um `terraform apply` completo com a VPN
conectada**, não uma verificação pontual.

## Níveis de permanência

| Nível | O que | Custo | Ciclo |
|---|---|---|---|
| **T0** | `state-backend`, `network-foundation` (2 regiões), cert de servidor no ACM | ~zero (ACM importado é grátis) | permanente |
| **T1** | TGW + Client VPN endpoint + associação | ~US$ 0,15/h ≈ US$ 110/mês | de pé durante o dia, destruído à noite |
| **T2** | spoke + EKS + charts + attachment + `tgw-rt-<spoke>` | ~US$ 165/mês | sobe, valida, desce |
| **T3** | ALB, segunda spoke mínima, VPN de cliente (AWS) + VPN Gateway (Azure) | ~US$ 0,27/h no pico | por fatia |

**Sem `prevent_destroy` no T1** — ele é destruído de propósito todo dia. A proteção é o script
`destroy` dizer em voz alta o que se perde. `prevent_destroy` continua só no bucket de state.

**O material de client não muda entre recriações** (os certificados são T0), mas **o DNS do endpoint
muda**. Daí um requisito duro do script: `vpn config` exporta a configuração do endpoint corrente a
cada uso; nunca cachear `.ovpn`.

## Fronteira de state

| Recurso | Conta | Ciclo | State |
|---|---|---|---|
| TGW, `tgw-rt-hub` | `network` | permanente | `connectivity/` |
| Client VPN endpoint, associação, rota do supernet, SAML provider | `network` | permanente | `connectivity/` |
| Attachment da VPC spoke | `cicd` | do spoke | `control-plane/` |
| `tgw-rt-<spoke>` + associação + propagação | `network` | **do spoke** | `control-plane/` (provider aliasado) |
| Rotas remotas nas RTs da VPC spoke | `cicd` | do spoke | `control-plane/` |
| Authorization rules por grupo | `network` | por spoke, mas é config | `connectivity/` (lista em variável) |
| ALB + listener `:443` | `network` | permanente | `connectivity/` |
| Cert wildcard do cluster no ACM + validação | `network` | **do cluster** | `control-plane/` (provider aliasado) |
| Target group do hub + listener rule + anexo do cert | `network` | **do cluster** | `control-plane/` (provider aliasado) |
| NLB interno + target group | `cicd` | do cluster | `control-plane/` |

**Rota é topologia** — uma só, para `10.0.0.0/12`, permanente. **Authorization rule é política** —
uma por CIDR por grupo, cresce com os spokes.

### O corte `hub | spoke+cluster` sobrevive ao TGW

Item que estava aberto desde a camada 2, agora fechado, por dois motivos verificáveis:

1. O egress de internet da spoke **não passa a atravessar o hub**: `0.0.0.0/0` continua indo para o
   NAT da própria spoke; o TGW só acrescenta rota para `10.0.0.0/12`. O raciocínio do teardown
   (pod → NAT → IGW → API do ELB tem de sobreviver até o último nó sair) fica intacto.
2. A única referência cross-state nova é *attachment → TGW*, e a **AWS recusa deletar um TGW com
   attachment vivo**. A proteção é da API, não de convenção.

**Ressalva:** cai por terra se um dia o `0.0.0.0/0` da spoke apontar para o TGW (egress
centralizado). Aí a camada tem de ser reunificada.

## Nova raiz: `aws/terraform/connectivity/us-east-1/`

Separada de `network-foundation/` de propósito: aquela raiz é **deliberadamente de custo zero**, e
isso é propriedade de segurança (pode ser deixada ligada sem pensar). Lê as subnets do hub por
`data` com filtro de tag, como a camada 2 já faz — não `terraform_remote_state`.

Conteúdo: TGW com `default_route_table_association` e `default_route_table_propagation`
**desabilitados** (é o que torna o isolamento por tenant possível), `tgw-rt-hub`, cert de servidor
no ACM, `aws_iam_saml_provider`, Client VPN endpoint com `split_tunnel = true` e
`client_cidr_block` **fora do supernet** (proposta `100.64.0.0/22` — mínimo /22, sem sobreposição
com `10.0.0.0/12` nem com CIDR de cliente), associação a uma subnet privada do hub, rota para
`10.0.0.0/12`, authorization rules por grupo.

## Sequência

Numeração **`fase.passo`**. Passo descoberto durante a execução entra com **sufixo de letra**
(`2.3a`) para não empurrar os seguintes — referência escrita em commit ou handoff continua válida.
Se alguma fase passar de 9 passos, padronizar a fase inteira com dois dígitos (`2.01`).

### Fase 1 — Preparação · grátis ou quase, independe de tudo o resto

| # | Passo | Nível | Custo | Aceite |
|---|---|---|---|---|
| `1.1` | Tags `kubernetes.io/role/{elb,internal-elb}` em `src/network` | — | zero | `terraform test` offline |
| `1.2` | `generate-tfvars` descobre o IP público → `public_access_cidrs = ["<ip>/32"]` | — | zero | teste offline; apply do laptop segue funcionando; API recusa de outro IP |
| `1.3` | Raiz `dns/`: hosted zone `nonprod.<domínio>` + delegação NS no Azure, dois providers | T0 | ~US$ 0,50/mês | `dig NS nonprod.<domínio>` responde pelos name servers do Route 53 |

### Fase 2 — Acesso privado · o que destrava fechar a API

| # | Passo | Nível | Custo | Aceite |
|---|---|---|---|---|
| `2.1` | **PORTÃO:** verificar o client da AWS VPN nesta distro | — | zero | client instala, abre e completa login SAML |
| `2.2` | `connectivity/`: TGW + cert de servidor no ACM + SAML provider + Client VPN + associação + rota do supernet | T1 | ~US$ 0,15/h | túnel sobe com identidade do Identity Center; IP de `100.64.0.0/22`; target network `associated` |
| `2.3` | Attachment da spoke + `tgw-rt-<spoke>` + rotas + authorization rule do grupo para `10.2.0.0/16` | T2 | +US$ 0,05/h | pelo túnel, alcança IP privado dentro da spoke |
| `2.4` | DNS: zona privada do cluster associada à VPC hub + `dns_servers` | T2 | zero | `dig` devolve IP privado; `kubectl get nodes` pelo túnel |
| `2.5` | `endpointPublicAccess = false` | — | zero | **`terraform apply` completo com VPN conectada**; de fora, recusa |

### Fase 3 — Ingress · privado primeiro, público depois

| # | Passo | Nível | Custo | Aceite |
|---|---|---|---|---|
| `3.1` | LBC + 4ª Pod Identity + NLB interno com IPs fixos + target group + gateway Istio (por GitOps) com `TargetGroupBinding` | T2 | +~US$ 16/mês | `curl` no IP do NLB **pelo túnel** devolve o workload |
| `3.2` | Lado hub: cert wildcard `*.<id>.nonprod.<domínio>` + target group com os IPs do NLB + listener rule no ALB | T3 | +~US$ 16/mês | `curl` em `app.<id>.nonprod.<domínio>` devolve o workload com TLS válido |

### Fase 4 — Provas de isolamento · os únicos aceites negativos

| # | Passo | Nível | Custo | Aceite |
|---|---|---|---|---|
| `4.1` | Segunda spoke mínima (VPC + `t4g.nano`) + grupo `cliente-a` + authorization rule por grupo | T3 | ~US$ 3/mês | **prova 1:** operador do grupo A alcança a spoke A e **não** a B; tirar do grupo derruba o acesso |
| `4.2` | `azure/terraform/simulated-client/`: VPN Gateway active-active com BGP + `tgw-rt-cliente-a` | T3 | +~US$ 36/mês AWS, ~US$ 0,19/h Azure | **prova 2:** a rede Azure alcança **só** a spoke dela; `search-transit-gateway-routes` não devolve o CIDR da spoke B na route table do cliente A |

### Por que nesta ordem

- **A fase 1 é grátis e independente.** O `/32` do `1.2` sozinho é a maior redução de superfície da
  lista — hoje o endpoint aceita `0.0.0.0/0` — e não quebra o apply do laptop.
- **`2.1` antes de `2.2`:** o maior risco do caminho de acesso não está na AWS, está no client na máquina.
  Descobrir depois de criar recurso que cobra por hora seria caro.
- **O acesso subiu para antes do LBC.** Testar workload sem caminho privado obriga a expor coisa
  publicamente só para conseguir olhar. Com o túnel pronto antes, o teste do `3.1` é `curl` num NLB
  **interno** — o alvo real, não um proxy dele.
- **`4.1` e `4.2` são os únicos com aceite negativo.** Até ali só se provou que o tráfego *chega*; nada
  provou que o que não deve chegar **não chega**. E eles provam coisas **diferentes**, em pontos de
  aplicação diferentes — um não substitui o outro:

  | Mecanismo | Onde é aplicado | O que prova |
  |---|---|---|
  | authorization rule por grupo | endpoint do Client VPN | que **uma pessoa** só alcança a spoke do grupo dela |
  | route table por attachment | tabela de rotas do TGW | que a **rede inteira** de um cliente só alcança a spoke dele |

  O `4.1` vem antes por ser quase de graça: a segunda spoke **não precisa de cluster** — basta VPC com
  algo que responda. E é o 7 que demonstra conceder/revogar, que foi o motivo de escolher SAML.

## O ambiente de cliente do `4.2` fica no Azure

Decidido: VPN Gateway gerenciado, não strongSwan em VM. Mais lento e mais caro, mas é "cliente com
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
recurso mais lento de todo o plano. Planejar a sessão do `4.2` em torno disso.

### Raiz: `azure/terraform/simulated-client/`, com os dois lados do túnel

A dependência entre as clouds é uma **cadeia**, não um ciclo — e é por isso que cabe numa raiz só:

```
PIPs do VPN Gateway (Azure)  →  Customer Gateway (AWS)  →  VPN Connection (AWS)
   →  IPs externos dos túneis + PSK  →  Local Network Gateway + Connection (Azure)
```

Em duas raízes isso exigiria três applies alternados (Azure → AWS → Azure) num recurso que leva 40
min para nascer. Numa raiz com os dois providers, o Terraform ordena sozinho.

O lado AWS do túnel mora aqui também, via provider `aws` aliasado — **pela mesma regra de ciclo de
vida** já aplicada a `tgw-rt-<spoke>` e à listener rule do ALB: Customer Gateways, VPN Connections e
a route table do cliente morrem quando o cliente simulado morre.

| Lado | Conteúdo |
|---|---|
| Azure | resource group, VNet `10.50.0.0/16`, **`GatewaySubnet`** (o nome é obrigatório e literal), 2 public IPs, `azurerm_virtual_network_gateway` active-active com BGP ASN 65515, Local Network Gateways, Connections, e uma VM pequena para responder |
| AWS (aliasado) | 2 Customer Gateways (um por PIP), 2 VPN Connections no TGW, `tgw-rt-cliente-a` + associação + rotas |

A raiz cria também o slot `azure/terraform/`, onde a trilha Azure pausada pode aterrar depois.

### Onde o isolamento é aplicado — o mecanismo que o `4.2` prova

**Route table por cliente, não só por spoke.** Se o attachment de VPN do cliente A associasse à
`tgw-rt-hub` — que tem todas as spokes propagadas — ele alcançaria todas, e a prova falharia. O
desenho correto é simétrico:

| Route table | Associada a | Contém |
|---|---|---|
| `tgw-rt-spoke-a` | attachment da VPC spoke A | CIDR da spoke A + `10.50.0.0/16` (volta para o cliente A) |
| `tgw-rt-cliente-a` | attachment de VPN do cliente A | **só** o CIDR da spoke A |

Cliente A não tem rota para a spoke B, e spoke A não tem rota para a rede do cliente B. Acrescentar
um cliente é acrescentar rota nos **dois** lados — explícito e aditivo, nunca por default.

O aceite tem duas formas, e vale fazer as duas: assertion por API
(`aws ec2 search-transit-gateway-routes` não devolve o CIDR da spoke B na route table do cliente A) e
conexão real que estoura o timeout contra um listener vivo na spoke B.

### Detalhes do `2.2` (SAML) que já custaram tempo em outros lugares

- **Mapeamento de atributos:** o Client VPN espera `NameID` com o usuário e `memberOf` com os
  grupos, e `memberOf` tem de carregar os **IDs** dos grupos do Identity Center, não os nomes. Errar
  dá túnel que sobe e não alcança nada, com erro pouco informativo.
- **Cert de servidor é obrigatório em qualquer tipo de autenticação.** Como o domínio ainda é questão
  aberta, é autoassinado (`easy-rsa`) importado no ACM.
- **Portal self-service exige uma segunda aplicação SAML.** Vale para a demo: a pessoa entra com o
  próprio SSO e baixa a configuração, sem arquivo por e-mail.
- **Nunca `authorize_all_groups = true`** — perde-se CIDR-por-grupo, que é metade do valor de (a).

### Saídas se o `2.1` falhar

1. Rodar o client numa VM/contêiner com distro suportada só para conectar.
2. Abordagem comunitária que dirige `openvpn` puro capturando a resposta SAML num listener local —
   **de terceiros, não verificada**; se for tentar, é no `2.1`.
3. Cair para certificado mútuo temporariamente, **sabendo que se perde a demo de conceder/revogar** —
   é desbloqueio, não alternativa.

### Risco conhecido do `2.4`

A zona privada do endpoint do EKS é criada pela AWS e **não é output do `aws_eks_cluster`** — achá-la
exige `data "aws_route53_zone"` casando pelo hostname do endpoint, o que é frágil, e ela é
**recriada a cada provisão do cluster**. Plano B: **Route 53 Resolver inbound endpoint na spoke** com
`dns_servers` do Client VPN apontando para os IPs dele — robusto e generaliza para N spokes, mas
custa ~US$ 0,25/h em 2 AZs. Começar pela associação (grátis) e cair para o Resolver se travar.

## Montagem da fase 3 — variante (B), decidida

```
internet
   │
   ▼  conta network (hub) — permanente
┌──────────────────────────────────────────────────────────┐
│ ALB público, 1 listener :443, N certificados por SNI     │
│   cert *.<id-a>.sandbox.<dom>  → rule Host → TG-A        │
│   TG-A type=ip → IPs FIXOS do NLB da spoke A             │
└──────────────────────┬───────────────────────────────────┘
                       │ TGW (rota 10.0.0.0/12)
                       ▼  conta cicd (spoke) — do cluster
┌──────────────────────────────────────────────────────────┐
│ NLB interno, IPs fixados por subnet_mapping              │
│   TG type=ip → pods do istio-ingressgateway              │
│                       │                                  │
│ istio-ingressgateway  │  Service ClusterIP               │
│   + TargetGroupBinding ─┘  (não type=LoadBalancer)       │
│   Gateway + VirtualService → svc-a, svc-b, svc-c         │
└──────────────────────────────────────────────────────────┘
```

### Por que (B) e não as outras duas

- **(A) ALB → IPs de pod direto via TGW** é mais barata (um LB só) e mais elegante, mas o target
  group vive na conta do hub e quem registraria os pods é o LBC, que roda na conta do cluster —
  **mutação cross-account em tempo de execução**, com IP de pod mudando a cada deploy. Concentra dois
  mecanismos não exercitados num passo onde o sinal precisa ser limpo. Migrar para ela depois é
  trocar o alvo da target group do hub e apagar o NLB, com linha de base funcionando para comparar.
- **(C) PrivateLink** custa ~US$ 47/mês e a vantagem que a sustentava era não precisar de TGW — que
  agora existe de qualquer forma. Volta à mesa na fatia de **spoke de recursos compartilhados**, onde
  CIDR sobreposto e autorização por principal valem dinheiro.

### Um NLB por cluster, não por Service

É o que o Istio resolve: um único ingress gateway recebe tudo, `Gateway` declara host/porta e
`VirtualService` roteia por host/path para os Services internos. Publicar aplicação nova é criar um
`VirtualService` — **zero recurso AWS, zero custo, zero `terraform apply`**. Sem mesh, cada
`Service type=LoadBalancer` viraria um NLB próprio (~US$ 16/mês cada) e o hub precisaria de uma
target group por aplicação.

E o hub escala do mesmo jeito: **por listener rule, não por load balancer.** N clientes = 1 ALB +
N certificados + N regras + N target groups. Só o ALB cobra.

### Quem cria o quê

| Peça | Quem cria | Ciclo |
|---|---|---|
| ALB, listener `:443` | Terraform, `connectivity/` | permanente |
| Certificado wildcard `*.<id>.sandbox.<dom>` no ACM | Terraform, `control-plane/` via provider aliasado | do cluster |
| Target group no hub + listener rule + `aws_lb_listener_certificate` | idem | do cluster |
| NLB interno + target group na spoke | Terraform, `control-plane/` | do cluster |
| Service do `istio-ingressgateway` como **`ClusterIP`** | Helm | do cluster |
| ligação pods → target group | **`TargetGroupBinding`** do LBC | do cluster |

O `istio-ingressgateway` **deixa de ser `type=LoadBalancer`**. O NLB tem cardinalidade 1 por cluster
e nunca muda — pelo critério cardinalidade × churn é infraestrutura, não workload. E se o LBC o
criasse, o ARN só existiria depois de aplicar o workload, quebrando o apply único.

### Contrato: mais uma chave no `platform-bootstrap`

O que o cluster precisa não é o NLB, é o **ARN da target group** — é o que o `TargetGroupBinding`
consome. Entra como `ingressTargetGroupArn` no ConfigMap que já é o contrato Terraform→GitOps.

Na direção oposta, o hub precisa dos **IPs privados do NLB**. Em vez de caçar ENI por descrição
(frágil, mesma classe do lookup de zona do `2.4`), **fixar os IPs** com
`subnet_mapping { private_ipv4_address = cidrhost(<cidr da subnet privada>, 10) }`. Determinístico,
conhecido em tempo de plan, e o NLB ganha endereço estável entre recriações.

### TLS: ACM no edge, cert-manager só no interno

**O ALB não lê Secret do Kubernetes — só certificado do ACM.** Importar o certificado do cert-manager
no ACM funciona, mas transfere a renovação (~60 dias no Let's Encrypt) para nós.

Caminho adotado: **um wildcard de ACM por cluster**, `*.<id>.sandbox.<domínio>`, com validação por
DNS. Wildcard cobre **um nível só** — `*.sandbox.<dom>` não cobre `app.<id>.sandbox.<dom>`, e
`*.*.` não existe. Renovação é automática enquanto o CNAME de validação permanecer na zona. Custo
zero.

Consequência: **acaba a emissão de certificado público por cluster pelo cert-manager** — sem desafio
DNS-01 por cluster, sem risco de rate limit, e o ingress deixa de depender de o cert-manager estar
saudável.

| Trecho | Certificado |
|---|---|
| internet → ALB | wildcard público no **ACM**, renovação automática |
| ALB → NLB → gateway | interno ou HTTP puro — **o ALB não valida certificado de backend**, então autoassinado basta |
| dentro do mesh (mTLS) | cert-manager / Istio |

**Teto a conferir antes de prometer escala:** há limite de certificados por listener de ALB (dezenas,
aumentável por cota) — mesma família do teto de 15 CIDRs.

### Duas armadilhas

- **IP do cliente real:** com ALB na frente, o Istio vê o IP do ALB. O IP do usuário chega em
  `X-Forwarded-For`, e o gateway precisa de `numTrustedProxies` configurado — senão qualquer política
  por IP de origem olha para o lugar errado.
- **ALB é L7, não faz passthrough TCP.** Se um dia o requisito for TLS ponta a ponta até o gateway
  sem re-encriptação, a entrada teria de ser NLB no hub — e aí se perde o roteamento por Host, que é
  o que torna o fan-out por cliente uma regra grátis.

## DNS: nova raiz `aws/terraform/dns/`, com dois providers

Subzona delegada, não o domínio inteiro: **`nonprod.wasp.silvios.me`** para o Route 53, na conta
`network`. O apex continua no Azure DNS, então a trilha Azure não migra nada.

Nomes resultantes: cluster em `<id>.nonprod.<domínio>`, aplicações em `app.<id>.nonprod.<domínio>`,
certificado wildcard `*.<id>.nonprod.<domínio>`. Um ambiente novo é uma subzona nova delegada do
mesmo jeito — e cada uma é sua própria fronteira de permissão.

**A delegação é código, não passo manual.** A raiz usa dois providers:

```hcl
provider "aws"     { profile = var.network_profile, region = "us-east-1" }
provider "azurerm" { features {} }

resource "aws_route53_zone" "nonprod" {
  name = "nonprod.${var.base_domain}"
  lifecycle { prevent_destroy = true }
}

# a delegação, do lado Azure, cabeada direto nos name servers que a AWS acabou de dar
resource "azurerm_dns_ns_record" "delegation" {
  name                = "nonprod"
  zone_name           = var.base_domain
  resource_group_name = var.azure_dns_resource_group
  ttl                 = 300
  records             = aws_route53_zone.nonprod.name_servers
}
```

Destruir a raiz remove o registro NS no Azure junto — sem resíduo apontando para name servers que
não existem mais.

**Raiz própria, sem região na state key**, por dois motivos: hosted zone pública é **global**, então
não cabe em `network-foundation/<região>/`; e se a zona morasse em `connectivity/` (destruído toda
noite) ela renasceria com **name servers novos** todo dia — com a delegação automatizada isso até se
corrigiria sozinho, mas a propagação de NS não é instantânea e o edge ficaria intermitente sem
motivo. Zona é T0: ~US$ 0,50/mês, `prevent_destroy`, e a automação existe para quando a recriação
*for* necessária, não como licença para recriar.

**Ganho de permissão:** a subzona delegada é a fronteira de blast radius do DNS — o external-dns
dentro do cluster recebe acesso só a ela, e não tem como tocar o apex. Com o domínio inteiro
delegado, essa separação não existiria.

**Risco dos dois providers no mesmo state:** sem credencial Azure válida, o `plan` falha mesmo para
mudança que só toca AWS. Manter o recurso de delegação atrás de um `local.manage_delegation` para
poder desligar sem editar o resto.

## Scripts

`aws/terraform/connectivity/us-east-1/scripts/` — mesmo molde da camada 2 (`PIPESTATUS[0]`, log com
timestamp em `logs/` gitignored, opções longas, 2 espaços, variáveis sempre entre aspas):

| Script | O que faz |
|---|---|
| `generate-tfvars` | descobre VPC/subnets do hub por tag, valida que `client_cidr_block` não colide com o supernet nem com rota existente, confere região aprovada na SCP |
| `apply` | `plan` → confirma → aplica → log |
| `destroy` | **recusa** se houver attachment no TGW fora deste state; diz o que se perde antes de confirmar |

`aws/scripts/`:

| Script | O que faz |
|---|---|
| `vpn` | `config` exporta a configuração do endpoint corrente (o DNS muda a cada recriação); `status` confere interface, rota para `10.0.0.0/12`, DNS e resolução do endpoint do cluster — **na ordem em que quebram**. `connect` é manual, pelo client da AWS |
| `platform-status` | percorre as raízes, diz o que está aplicado por nível e soma o custo/h — antídoto para "esqueci ligado" e, mais importante, para "achei que era resíduo e destruí o T1" |

## Custo

| Estado | US$/h | US$/mês |
|---|---|---|
| T0 + T1 parado | ~0,15 | ~110 |
| \+ conexão VPN ativa | +0,05 por conexão | só enquanto conectado |
| \+ T2 | +0,23 | +165 |
| \+ T3 no pico da fase 4 | +0,27 | — |

No pico: ALB ~0,0225 + segunda spoke ~0,004 + VPN connection ~0,05 na AWS + VPN Gateway ~0,19 no
Azure. Uma sessão de 7 h com tudo ligado custa ~US$ 5 além da base — e o VPN Gateway do Azure é
mais da metade disso.

## Fora do plano, de propósito

- **DNS público e TLS** — dependem da base de domínio, ainda aberta. A sequência termina em HTTP no
  DNS do ALB.
- **Spoke de recursos compartilhados** (banco, mensageria) — vira sequência própria depois da
  fase 3, quando se saberá se o TGW já está pago. Dois padrões candidatos: TGW com propagação seletiva
  (qualquer protocolo, exige CIDR não sobreposto, autorização bidirecional contida por SG) e
  PrivateLink por serviço (unidirecional, por principal, admite CIDR sobreposto, mas é um endpoint
  por serviço por consumidora).
- **Rodar o `apply` de dentro da rede** — CodeBuild em VPC tiraria o laptop do caminho crítico e é o
  destino natural numa conta cujo papel é *Deployments*. Outra fatia.

## Itens ainda em aberto neste plano

1. **Teto de certificados por listener de ALB** — conferir a cota antes de prometer escala.

Resolvidos nas rodadas anteriores: variante do ingress (**B**); dono do ALB (`connectivity/` para o
ALB, `control-plane/` para o que é por-spoke); emissão do certificado (**um wildcard de ACM por
cluster**); conta da hosted zone pública (`network`); lugar do DNS na sequência (`1.3`); base do
domínio (**subzona `nonprod.` delegada, com a delegação automatizada por provider `azurerm`**); e
onde mora o cliente simulado (**`azure/terraform/simulated-client/`, com os dois lados do túnel numa
raiz só**).
