# Phase 3 — Ingress

Privado primeiro, público depois. O corte entre os dois passos é o que dá sinal limpo: `3.1` fecha
inteiro no lado spoke, `3.2` no lado hub, cada um com um `curl` só.

| # | Passo | Nível | Custo | Aceite |
|---|---|---|---|---|
| `3.1` | LBC + 4ª Pod Identity + NLB interno com IPs fixos + target group + gateway Istio (por GitOps) com `TargetGroupBinding` | T2 | +~US$ 16/mês | `curl` no IP do NLB **pelo túnel** devolve o workload |
| `3.2` | Lado hub: cert wildcard `*.<id>.nonprod.<domínio>` + target group com os IPs do NLB + listener rule no ALB | T3 | +~US$ 16/mês | `curl` em `app.<id>.nonprod.<domínio>` devolve o workload com TLS válido |

## Montagem — variante (B), decidida

```
internet
   │
   ▼  conta network (hub) — permanente
┌──────────────────────────────────────────────────────────┐
│ ALB público, 1 listener :443, N certificados por SNI     │
│   cert *.<id-a>.nonprod.<dom>  → rule Host → TG-A        │
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

- **(A) ALB → IPs de pod direto via TGW** é mais barata (um LB só) e mais elegante, mas o target group
  vive na conta do hub e quem registraria os pods é o LBC, que roda na conta do cluster — **mutação
  cross-account em tempo de execução**, com IP de pod mudando a cada deploy. Concentra dois mecanismos
  não exercitados num passo onde o sinal precisa ser limpo. Migrar para ela depois é trocar o alvo da
  target group do hub e apagar o NLB, com linha de base funcionando para comparar.
- **(C) PrivateLink** custa ~US$ 47/mês e a vantagem que a sustentava era não precisar de TGW — que
  agora existe de qualquer forma. Volta à mesa na fatia de **spoke de recursos compartilhados**, onde
  CIDR sobreposto e autorização por principal valem dinheiro.

## Um NLB por cluster, não por Service

É o que o Istio resolve: um único ingress gateway recebe tudo, `Gateway` declara host/porta e
`VirtualService` roteia por host/path para os Services internos. Publicar aplicação nova é criar um
`VirtualService` — **zero recurso AWS, zero custo, zero `terraform apply`**. Sem mesh, cada
`Service type=LoadBalancer` viraria um NLB próprio (~US$ 16/mês cada) e o hub precisaria de uma target
group por aplicação.

E o hub escala do mesmo jeito: **por listener rule, não por load balancer.** N clientes = 1 ALB +
N certificados + N regras + N target groups. Só o ALB cobra.

**Tetos reais**, conferidos na doc de quotas do ELB — os dois ajustáveis por Service Quotas:

| Quota | Default |
|---|---|
| Certificates per Application Load Balancer (excluindo o default) | **25** |
| Rules per Application Load Balancer (excluindo as default) | 100 |

O certificado aperta primeiro: **25 clientes por ALB** antes de pedir aumento.

## Quem cria o quê

| Peça | Quem cria | Ciclo |
|---|---|---|
| ALB, listener `:443` | Terraform, `connectivity/` | permanente |
| Certificado wildcard `*.<id>.nonprod.<dom>` no ACM | Terraform, `control-plane/` via provider aliasado | do cluster |
| Target group no hub + listener rule + `aws_lb_listener_certificate` | idem | do cluster |
| NLB interno + target group na spoke | Terraform, `control-plane/` | do cluster |
| Service do `istio-ingressgateway` como **`ClusterIP`** | Helm | do cluster |
| ligação pods → target group | **`TargetGroupBinding`** do LBC | do cluster |

**Os manifestos do lado cluster ficam no repo `wasp-gitops`, numa branch dedicada a este
experimento** — o path dentro dele se decide na implementação. Ele já tem `charts/httpbin`, que serve
de workload de teste sem precisar escrever nada novo. Este repo não ganha diretório de GitOps: a
decisão registrada é que config de GitOps vive em repositório próprio.

O `istio-ingressgateway` **deixa de ser `type=LoadBalancer`**. O NLB tem cardinalidade 1 por cluster e
nunca muda — pelo critério cardinalidade × churn é infraestrutura, não workload. E se o LBC o criasse,
o ARN só existiria depois de aplicar o workload, quebrando o apply único.

## Contrato: mais uma chave no `platform-bootstrap`

O que o cluster precisa não é o NLB, é o **ARN da target group** — é o que o `TargetGroupBinding`
consome. Entra como `ingressTargetGroupArn` no ConfigMap que já é o contrato Terraform→GitOps.

Na direção oposta, o hub precisa dos **IPs privados do NLB**. Em vez de caçar ENI por descrição
(frágil, mesma classe do lookup de zona do `2.4`), **fixar os IPs** com
`subnet_mapping { private_ipv4_address = cidrhost(<cidr da subnet privada>, 10) }`. Determinístico,
conhecido em tempo de plan, e o NLB ganha endereço estável entre recriações.

## TLS: ACM no edge, cert-manager só no interno

**O ALB não lê Secret do Kubernetes — só certificado do ACM.** Importar o certificado do cert-manager
no ACM funciona, mas transfere a renovação (~60 dias no Let's Encrypt) para nós.

Caminho adotado: **um wildcard de ACM por cluster**, `*.<id>.nonprod.<domínio>`, com validação por
DNS. Wildcard cobre **um nível só** — `*.nonprod.<dom>` não cobre `app.<id>.nonprod.<dom>`, e `*.*.`
não existe. Renovação é automática enquanto o CNAME de validação permanecer na zona. Custo zero.

Consequência: **acaba a emissão de certificado público por cluster pelo cert-manager** — sem desafio
DNS-01 por cluster, sem risco de rate limit, e o ingress deixa de depender de o cert-manager estar
saudável.

| Trecho | Certificado |
|---|---|
| internet → ALB | wildcard público no **ACM**, renovação automática |
| ALB → NLB → gateway | interno ou HTTP puro — **o ALB não valida certificado de backend**, então autoassinado basta |
| dentro do mesh (mTLS) | cert-manager / Istio |

## Duas armadilhas

- **IP do cliente real:** com ALB na frente, o Istio vê o IP do ALB. O IP do usuário chega em
  `X-Forwarded-For`, e o gateway precisa de `numTrustedProxies` configurado — senão qualquer política
  por IP de origem olha para o lugar errado.
- **ALB é L7, não faz passthrough TCP.** Se um dia o requisito for TLS ponta a ponta até o gateway sem
  re-encriptação, a entrada teria de ser NLB no hub — e aí se perde o roteamento por Host, que é o que
  torna o fan-out por cliente uma regra grátis.
