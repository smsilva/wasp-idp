# 04 — Ingress and Exposure

**Pilar WAF principal:** Reliability (entrada HA) + Security (TLS, superfície controlada).

## O caminho do tráfego externo até o pod

Expor um app do cluster encadeia quatro peças, cada uma de um domínio:

```text
Cliente
  │  https://app.<spoke>.<root-domain>
  ▼
DNS wildcard (../dns/02)  *.<spoke>...  A-alias → NLB
  ▼
NLB (materializado pelo AWS LB Controller)   ← subnet pública, internet-facing
  ▼
Istio Gateway (pod no cluster)               ← termina TLS, roteia por host/path
  ▼
VirtualService → Service → Pod
```

Cada seta é uma responsabilidade isolada: DNS resolve o nome, o NLB entrega na borda, o Istio
roteia dentro do cluster. Trocar uma não quebra as outras.

## AWS Load Balancer Controller — o NLB nasce de um Service

O **LB Controller** (add-on, tópico 2) observa Services/Ingress e materializa
NLB/ALB **de verdade** na AWS:

- Um `Service type: LoadBalancer` com as annotations certas
  (`aws-load-balancer-type: external`, `nlb-target-type: ip`, `scheme: internet-facing`) faz o
  controller criar um **NLB** público.
- O controller descobre as subnets por **tag** (`kubernetes.io/role/elb` para público,
  `.../internal-elb` para interno — postas em `../network/02`), sem configuração manual de
  subnet.
- Mutações são **escopadas por tag** (`elbv2.k8s.aws/cluster`) na policy IAM — o controller de
  um cluster não mexe no LB de outro (`../security/01`).

O NLB é o ponto público estável; o wildcard DNS aponta a ele (`../dns/02`), e é o mesmo NLB
para todos os apps do cluster (o Istio roteia por host).

## Istio Gateway — roteamento dentro do cluster

Atrás do NLB, o **Istio ingress gateway** (um pod) recebe todo o tráfego e roteia por
host/path via `Gateway` + `VirtualService`:

- **Um NLB, N apps** — o gateway distingue `app1.<spoke>` de `app2.<spoke>` por host; não
  precisa de um LB por app.
- **Gateway selector** — casa o `Gateway` ao pod do gateway pelo label correto
  (`istio: <clusterName>-<clusterId>-istio-gateway`, o rótulo que o chart oficial aplica).
  Selector errado = Gateway não casa o pod = **503** (gotcha real — apêndice).
- Kinds `networking.istio.io/v1` (não `v1alpha3`).

## TLS termina no cluster (cert-manager) ou na borda (ACM)

Duas posturas (detalhe em `../dns/04`):

- **TLS no cluster** — cert-manager emite o cert wildcard por subzona (DNS-01), o Istio gateway
  o usa. É o modelo do PoC (NLB passa TCP; TLS termina no Istio).
- **TLS na borda** — se a exposição for por ALB/CloudFront/APIM, o cert vive no ACM e o TLS
  termina lá. (Na fatia Azure do PoC, a exposição pública é via APIM/Front Door — `../../CLAUDE.md`.)

**Apex de novo:** o wildcard cobre `foo.<spoke>` mas não `<spoke>` em si — expor no apex exige
Record A do apex + apex no SAN do cert + Gateway/VS no host apex (`../dns/02`).

## external-dns e o gateway Istio (gotcha)

external-dns roda `--source=service,ingress` e **não** descobre `Gateway`/`VirtualService`.
Duas saídas:

- **Modelo preferido (wildcard):** o wildcard da subzona já resolve todos os apps → external-dns
  por app é dispensável; o app só precisa de `Gateway`+`VirtualService`.
- **Modelo legado (por-app):** um Ingress-fantasma (`ingressClassName: istio`, backend
  inexistente + annotation `external-dns.alpha.kubernetes.io/target`) publica o A-record, e uma
  `IngressClass istio` inativa existe só para o Ingress passar na validação do LB Controller.

O wildcard (`../dns/`) é o que torna o legado desnecessário.

## Endpoint público vs. privado

- **PoC:** NLB `internet-facing` (exposição direta, praticidade).
- **Alvo hub-and-spoke:** a exposição pode fechar via **VPN/Hub** (NLB `internal`) ou por um
  edge gerenciado; o control plane idealmente **privado** (`00`). Decisão de perímetro por
  ambiente.

## Well-Architected — porquê

| Best practice | Como atende |
|---|---|
| **[REL10 — Use fault isolation to protect your workload](https://docs.aws.amazon.com/wellarchitected/latest/reliability-pillar/use-fault-isolation-to-protect-your-workload.html)** | NLB multi-AZ; `EvaluateTargetHealth` no alias; Istio gateway replicável |
| **[SEC08-BP01 — Implement secure key management](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/sec_protect_data_rest_key_mgmt.html)** | cert-manager (cluster) ou ACM (borda); apex no SAN quando preciso |
| **[SEC05 — Protecting networks](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/protecting-networks.html)** | um NLB por cluster, mutações IAM escopadas por tag |
| **OPS** um LB, N apps | Istio roteia por host — deploy de app novo não cria LB novo |

## Próximo

→ [`05-gitops.md`](05-gitops.md): como as aplicações entram no cluster de forma declarativa.
