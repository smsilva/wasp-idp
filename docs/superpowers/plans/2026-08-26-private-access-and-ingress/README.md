# Private access and centralized ingress

Plano iterativo: cada passo é testável isolado, e as decisões ainda abertas caem o mais tarde
possível. Substitui o desenho de `../2026-08-25-private-ingress-via-privatelink.md`, que continua
válido na fundamentação (citações da AWS) mas cuja escolha PrivateLink-vs-TGW foi reaberta.

**Um arquivo por fase** — ler só a do trabalho corrente. Este arquivo tem o que atravessa todas.

| Fase | Arquivo | Entrega |
|---|---|---|
| 1 | [`01-preparation.md`](01-preparation.md) | tags do LBC, `/32` na API, raiz `dns/` — grátis ou quase |
| 2 | [`02-private-access.md`](02-private-access.md) | TGW + Client VPN + DNS privado, e fechar a API |
| 3 | [`03-ingress.md`](03-ingress.md) | NLB interno + gateway Istio, depois ALB no hub com TLS |
| 4 | [`04-isolation-proofs.md`](04-isolation-proofs.md) | as duas provas negativas |

## Decisões que sustentam o plano

| # | Decisão | Motivo |
|---|---|---|
| 1 | **Ingress único, pelo hub.** Nenhuma spoke expõe acesso a si direto na internet | vale para qualquer entrada — logo VGW em spoke também está fora |
| 2 | **`Site-to-Site VPN` por cliente**, terminando no TGW do hub | um attachment por cliente ⟹ route table de tenant isola nas **duas** direções, sem depender de security group |
| 3 | **Acesso de manutenção: AWS Client VPN no hub, autenticação SAML** pelo Identity Center | conceder e revogar acesso a uma pessoa **é a demonstração**; e authorization rule por grupo dá CIDR-por-grupo, impossível com certificado. O preço que esta decisão pagava — client desktop, `connect` não scriptável — **caiu no `2.1`**: a 6.0.1 traz CLI |
| 4 | **TGW + Client VPN ficam de pé entre sessões**, destruídos ao fim do dia | o que prende o endpoint público não é `kubectl`, é o Terraform |
| 5 | **Fronteira de state segue o ciclo de vida, não a conta** | recurso da conta hub cujo ciclo é o do spoke vai no state do spoke |

### O que prende o endpoint público da API do EKS

Não é operação humana: `src/helm/modules/*` usam os providers `helm`/`kubernetes` configurados a
partir de `aws_eks_cluster_auth` — **quem fala com o API server é a máquina que roda
`terraform apply`**. Fechar o endpoint sem caminho privado não é hardening, é quebrar o
provisionamento. Por isso o acesso privado vem **antes** do resto.

Consequência: o critério de aceite de fechar o endpoint é **um `terraform apply` completo com a VPN
conectada**, não uma verificação pontual.

## Numeração

**`fase.passo`**. Passo descoberto durante a execução entra com **sufixo de letra** (`2.3a`) para não
empurrar os seguintes — referência escrita em commit ou handoff continua válida. Se alguma fase
passar de 9 passos, padronizar a fase inteira com dois dígitos (`2.01`).

## Níveis de permanência

| Nível | O que | Custo | Ciclo |
|---|---|---|---|
| **T0** | `state-backend`, `network-foundation` (2 regiões), raiz `dns/` | ~zero | permanente |
| **T1** | TGW + Client VPN endpoint + associação + **certificado do ACM** | ~US$ 0,15/h ≈ US$ 110/mês (certificado público é grátis) | de pé durante o dia, destruído à noite |
| **T2** | spoke + EKS + charts + attachment + `tgw-rt-<spoke>` + NLB interno | ~US$ 180/mês | sobe, valida, desce |
| **T3** | ALB, segunda spoke mínima, VPN de cliente (AWS) + VPN Gateway (Azure) | ~US$ 0,27/h no pico | por fatia |

**Sem `prevent_destroy` no T1** — ele é destruído de propósito todo dia. A proteção é o script
`destroy` dizer em voz alta o que se perde. `prevent_destroy` fica no bucket de state e na hosted
zone, onde destruição nunca é a intenção.

**O material de client não muda entre recriações, mas o DNS do endpoint muda.** Daí um requisito duro
do script: `vpn config` exporta a configuração do endpoint corrente a cada uso; nunca cachear `.ovpn`.

O certificado saiu do T0 e entrou no T1 no `2.2`, e o argumento sobrevive melhor assim: com
**certificado público do ACM**, o que o `.ovpn` embute é a cadeia da CA da Amazon, estável entre
emissões. A estabilidade que importava vinha da CA, não da vida longa do recurso — então reemitir todo
dia não custa nada ao operador, só alguns minutos de validação por DNS em cada apply.

## Fronteira de state

| Recurso | Conta | Ciclo | State |
|---|---|---|---|
| Hosted zone `nonprod.` + delegação NS no Azure | `network` + Azure | permanente | `dns/` |
| TGW, `tgw-rt-hub` | `network` | permanente | `connectivity/` |
| Certificado do endpoint + registro de validação | `network` | do endpoint | `connectivity/` |
| Client VPN endpoint, associação, rota do supernet, SAML provider | `network` | permanente | `connectivity/` |
| Authorization rules por grupo | `network` | por spoke, mas é config | `connectivity/` (lista em variável) |
| ALB + listener `:443` | `network` | permanente | `connectivity/` |
| Attachment da VPC spoke | `cicd` | do spoke | `control-plane/` |
| `tgw-rt-<spoke>` + associação + propagação | `network` | **do spoke** | `control-plane/` (provider aliasado) |
| Rotas remotas nas RTs da VPC spoke | `cicd` | do spoke | `control-plane/` |
| Cert wildcard do cluster no ACM + validação | `network` | **do cluster** | `control-plane/` (provider aliasado) |
| Target group do hub + listener rule + anexo do cert | `network` | **do cluster** | `control-plane/` (provider aliasado) |
| NLB interno + target group | `cicd` | do cluster | `control-plane/` |
| Customer Gateways + VPN Connections + `tgw-rt-cliente-a` | `network` | do cliente simulado | `azure/terraform/simulated-client/` |

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

## Por que nesta ordem

- **A fase 1 é grátis e independente.** O `/32` do `1.2` sozinho é a maior redução de superfície da
  lista — hoje o endpoint aceita `0.0.0.0/0` — e não quebra o apply do laptop.
- **`2.1` antes de `2.2`:** o maior risco do caminho de acesso não está na AWS, está no client na
  máquina. Descobrir depois de criar recurso que cobra por hora seria caro.
- **O acesso vem antes do LBC.** Testar workload sem caminho privado obriga a expor coisa
  publicamente só para conseguir olhar. Com o túnel pronto antes, o teste do `3.1` é `curl` num NLB
  **interno** — o alvo real, não um proxy dele.
- **`4.1` e `4.2` são os únicos com aceite negativo.** Até ali só se provou que o tráfego *chega*;
  nada provou que o que não deve chegar **não chega**. E provam coisas **diferentes**, em pontos de
  aplicação diferentes — um não substitui o outro:

  | Mecanismo | Onde é aplicado | O que prova |
  |---|---|---|
  | authorization rule por grupo | endpoint do Client VPN | que **uma pessoa** só alcança a spoke do grupo dela |
  | route table por attachment | tabela de rotas do TGW | que a **rede inteira** de um cliente só alcança a spoke dele |

  O `4.1` vem antes por ser quase de graça — a segunda spoke **não precisa de cluster** — e por ser
  ele que demonstra conceder/revogar, o motivo de ter escolhido SAML.

## Scripts

`aws/terraform/scripts/` — transversais, servem qualquer fase. O `vpn` fica um pouco fora do lugar
ali (não é Terraform), mas isso custa menos que criar uma quarta pasta de scripts no repo:

| Script | O que faz |
|---|---|
| `vpn` | `config` exporta a configuração do endpoint corrente (o DNS muda a cada recriação) e a importa por `aws-vpn-client import-profile`; `status` confere interface, rota para `10.0.0.0/12`, DNS e resolução do endpoint do cluster — **na ordem em que quebram**. `connect` chama `aws-vpn-client connect` (**scriptável a partir da 6.0.1**; ver `2.1`), e **não** trata import bem-sucedido como configuração válida — a validação do CA é no `connect` |
| `platform-status` | percorre as raízes, diz o que está aplicado por nível e soma o custo/h — antídoto para "esqueci ligado" e, mais importante, para "achei que era resíduo e destruí o T1" |

Scripts de raiz (`generate-tfvars`, `apply`, `destroy`) seguem o molde da camada 2 —
`PIPESTATUS[0]`, log com timestamp em `logs/` gitignored, opções longas, 2 espaços, variáveis sempre
entre aspas. Os da `connectivity/` estão descritos em [`02-private-access.md`](02-private-access.md).

## Custo

| Estado | US$/h | US$/mês |
|---|---|---|
| T0 + T1 parado | ~0,15 | ~110 |
| \+ conexão VPN ativa | +0,05 por conexão | só enquanto conectado |
| \+ T2 | +0,25 | +180 |
| \+ T3 no pico da fase 4 | +0,27 | — |

No pico: ALB ~0,0225 + segunda spoke ~0,004 + VPN connection ~0,05 na AWS + VPN Gateway ~0,19 no
Azure. Uma sessão de 7 h com tudo ligado custa ~US$ 5 além da base — e o VPN Gateway do Azure é mais
da metade disso.

## Fora do plano, de propósito

- **Spoke de recursos compartilhados** (banco, mensageria) — vira sequência própria depois da fase 3,
  quando se saberá se o TGW já está pago. Dois padrões candidatos: TGW com propagação seletiva
  (qualquer protocolo, exige CIDR não sobreposto, autorização bidirecional contida por SG) e
  PrivateLink por serviço (unidirecional, por principal, admite CIDR sobreposto, mas é um endpoint
  por serviço por consumidora).
- **Rodar o `apply` de dentro da rede** — CodeBuild em VPC tiraria o laptop do caminho crítico e é o
  destino natural numa conta cujo papel é *Deployments*. Outra fatia.
- **`prod.`** — a subzona de produção segue o mesmo desenho de delegação; não entra agora.

## Itens em aberto

Nenhum. Todas as decisões de desenho estão fechadas; o que resta é executar.

Fechados ao longo do desenho: acesso de manutenção (**Client VPN + SAML**), níveis de permanência,
fronteira de state, o corte `hub | spoke+cluster` sob TGW, variante do ingress (**B**), dono do ALB,
emissão do certificado (**wildcard de ACM por cluster**), conta da hosted zone (`network`), base do
domínio (**subzona `nonprod.` delegada, delegação em código**), onde mora o cliente simulado
(**`azure/terraform/simulated-client/`**) e a cota de certificados por ALB (**25, ajustável**).
