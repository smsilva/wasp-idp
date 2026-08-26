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
| **T3** | ALB, cliente simulado, segunda spoke | ~US$ 125/mês no pico | por fatia |

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

| # | Passo | Nível | Custo | Aceite |
|---|---|---|---|---|
| **0a** | Tags `kubernetes.io/role/{elb,internal-elb}` em `src/network` | — | zero | `terraform test` offline |
| **0b** | `generate-tfvars` descobre o IP público → `public_access_cidrs = ["<ip>/32"]` | — | zero | teste offline; apply do laptop segue funcionando |
| **1a** | **PORTÃO:** verificar o client da AWS VPN nesta distro Linux | — | zero | client instala, abre e completa login SAML |
| **1b** | `connectivity/`: TGW + cert ACM + SAML provider + Client VPN + associação + rota | T1 | ~US$ 0,15/h | túnel sobe com identidade do Identity Center; IP de `100.64.0.0/22`; target network `associated` |
| **2** | Attachment + `tgw-rt-<spoke>` + rotas; authorization rule do grupo para `10.2.0.0/16` | T2 | +US$ 0,05/h | pelo túnel, alcança IP privado dentro da spoke |
| **3** | DNS: zona privada do cluster associada à VPC hub + `dns_servers` | T2 | zero | `dig` devolve IP privado; `kubectl get nodes` pelo túnel |
| **4** | `endpointPublicAccess = false` | — | zero | **`terraform apply` completo com VPN conectada**; de fora, recusa |
| **5** | LBC + 4ª Pod Identity + workload de teste | T2 | camada 2 | NLB **interno** `active`, targets `healthy`, `curl` pelo túnel |
| **6** | ALB público no hub → workload na spoke | T3 | +~US$ 16/mês | `curl` no DNS do ALB devolve o workload |
| **7** | `Site-to-Site VPN` de cliente simulado (strongSwan noutra VPC) | T3 | +~US$ 36/mês | cliente simulado alcança **só** a spoke dele |
| **8** | Segunda spoke + **provas negativas** | T3 | +~US$ 73/mês | cliente A não alcança spoke B; **operador do grupo A não alcança spoke B**; tirar do grupo derruba o acesso |

### Por que nesta ordem

- **0a/0b são grátis e offline.** O `/32` sozinho é a maior redução de superfície da lista — hoje o
  endpoint aceita `0.0.0.0/0` — e não quebra o apply do laptop.
- **1a antes de 1b:** o maior risco do caminho de acesso não está na AWS, está no client na máquina.
  Descobrir depois de criar recurso que cobra por hora seria caro.
- **O acesso subiu para antes do LBC.** Testar workload sem caminho privado obriga a expor coisa
  publicamente só para conseguir olhar. Com o túnel pronto antes, o teste do passo 5 é `curl` num NLB
  **interno** — o alvo real, não um proxy dele.
- **O passo 8 é o único com aceite negativo.** Até ali só se provou que o tráfego *chega*; nada
  provou que o que não deve chegar **não chega**.

### Detalhes de 1b (SAML) que já custaram tempo em outros lugares

- **Mapeamento de atributos:** o Client VPN espera `NameID` com o usuário e `memberOf` com os
  grupos, e `memberOf` tem de carregar os **IDs** dos grupos do Identity Center, não os nomes. Errar
  dá túnel que sobe e não alcança nada, com erro pouco informativo.
- **Cert de servidor é obrigatório em qualquer tipo de autenticação.** Como o domínio ainda é questão
  aberta, é autoassinado (`easy-rsa`) importado no ACM.
- **Portal self-service exige uma segunda aplicação SAML.** Vale para a demo: a pessoa entra com o
  próprio SSO e baixa a configuração, sem arquivo por e-mail.
- **Nunca `authorize_all_groups = true`** — perde-se CIDR-por-grupo, que é metade do valor de (a).

### Saídas se 1a falhar

1. Rodar o client numa VM/contêiner com distro suportada só para conectar.
2. Abordagem comunitária que dirige `openvpn` puro capturando a resposta SAML num listener local —
   **de terceiros, não verificada**; se for tentar, é no 1a.
3. Cair para certificado mútuo temporariamente, **sabendo que se perde a demo de conceder/revogar** —
   é desbloqueio, não alternativa.

### Risco conhecido do passo 3

A zona privada do endpoint do EKS é criada pela AWS e **não é output do `aws_eks_cluster`** — achá-la
exige `data "aws_route53_zone"` casando pelo hostname do endpoint, o que é frágil, e ela é
**recriada a cada provisão do cluster**. Plano B: **Route 53 Resolver inbound endpoint na spoke** com
`dns_servers` do Client VPN apontando para os IPs dele — robusto e generaliza para N spokes, mas
custa ~US$ 0,25/h em 2 AZs. Começar pela associação (grátis) e cair para o Resolver se travar.

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
| \+ T3 no pico do passo 8 | +0,17 | +125 |

Uma sessão de 7 h com tudo ligado no pico custa ~US$ 4 além da base.

## Fora do plano, de propósito

- **DNS público e TLS** — dependem da base de domínio, ainda aberta. A sequência termina em HTTP no
  DNS do ALB.
- **Spoke de recursos compartilhados** (banco, mensageria) — vira sequência própria depois do passo
  6, quando se saberá se o TGW já está pago. Dois padrões candidatos: TGW com propagação seletiva
  (qualquer protocolo, exige CIDR não sobreposto, autorização bidirecional contida por SG) e
  PrivateLink por serviço (unidirecional, por principal, admite CIDR sobreposto, mas é um endpoint
  por serviço por consumidora).
- **Rodar o `apply` de dentro da rede** — CodeBuild em VPC tiraria o laptop do caminho crítico e é o
  destino natural numa conta cujo papel é *Deployments*. Outra fatia.

## Itens ainda em aberto neste plano

1. **Variante do passo 6:** ALB no hub com target group `type=ip` apontando **direto para IPs de
   pod** via TGW (elimina o NLB interno; `TargetGroupBinding` cross-account é padrão documentado do
   LBC), contra ALB → **IPs do NLB interno** (mais peças, alvo estável por AZ), contra
   **PrivateLink**. Não decidido.
2. **Quem é dono do ALB do passo 6** — `connectivity/` (permanente, coerente com ser edge do hub) ou
   raiz própria da fatia. Depende de 1.
3. **Desenho do cliente simulado** dos passos 7–8: VPC separada com strongSwan em EC2 fazendo papel
   de concentrador, CIDR, e como provar a prova negativa sem ambiguidade.
4. **Em qual conta fica a hosted zone pública**, quando o domínio for decidido.
