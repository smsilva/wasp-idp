# Private ingress via PrivateLink

Desenho da fatia que põe um workload HTTP no cluster da camada 2 e o alcança **de fora**, com a
entrada pública na conta `network` (hub) e **nenhum load balancer público na conta do cluster**.

Estado: **desenhado, não implementado.** Levantado em 2026-08-25 com a camada 2 de pé; o cluster foi
destruído logo depois, então nada aqui foi executado.

## Por que PrivateLink e não Transit Gateway

Não é preferência. O whitepaper *[Building a Scalable and Secure Multi-VPC AWS Network
Infrastructure](https://docs.aws.amazon.com/whitepapers/latest/building-scalable-secure-multi-vpc-network-infrastructure/aws-privatelink.html)*
(pub. 2024-04-17) separa as duas tecnologias por tipo de conectividade:

> **AWS PrivateLink** — Use AWS PrivateLink when you have a client/server set up where you want to
> allow one or more consumer VPCs unidirectional access to a specific service or set of instances in
> the service provider VPC (…) This is also a good option when client and servers in the two VPCs
> have overlapping IP addresses.
>
> **VPC peering and Transit Gateway** — Use VPC peering and Transit Gateway when you want to enable
> layer-3 IP connectivity between VPCs.

O caso desta fatia é *client/server unidirecional para um serviço específico*: o hub é **consumer**,
o httpbin é o **service**. Não se quer conectividade L3 entre `10.1` e `10.2`.

O TGW **é** a recomendação da AWS quando o que se centraliza é **inspeção** — a seção
[Centralized inbound inspection](https://docs.aws.amazon.com/whitepapers/latest/building-scalable-secure-multi-vpc-network-infrastructure/centralized-inbound-inspection.html)
usa *"Transit Gateway acting as a central hub for routing traffic"* com Gateway Load Balancer ou
Network Firewall. Sem requisito de IDS/IPS, TGW resolve um problema que esta fatia não tem.

Detalhe que corrige uma suposição comum: a arquitetura WAF+ALB do mesmo capítulo é **distribuída,
por-ALB** — a própria AWS a classifica como *"best suited for HTTP header inspection and distributed
inspections"*. Ingress centralizado na conta de rede não é a única forma recomendada.

O whitepaper também diz, explicitamente, que arquiteturas reais **misturam** as tecnologias. TGW
continua sendo a resposta eventual para egress centralizado e tráfego spoke↔spoke.

### Três razões próprias deste repo

1. **Não invalida o corte de state documentado.** `aws/terraform/README.md` registra que
   `hub | spoke+cluster` é seguro *hoje porque não há TGW* — os nós não roteiam pelo hub. Ligar TGW
   obriga a revisitar esse raciocínio antes de qualquer coisa. PrivateLink não toca route table.
2. **Não consome o teto de CIDR.** O supernet `10.0.0.0/12` dá 15 `/16` e região multiplica —
   questão aberta em `aws/docs/network/01-cidr-addressing.md`. PrivateLink admite CIDR sobreposto
   entre spokes; TGW não.
3. **Menor privilégio de rede:** expõe um serviço autorizado por principal de conta, não um CIDR.

## Topologia

```
internet
   │
   ▼
┌─ conta network (094289743086) — VPC hub 10.1.0.0/16 ──────────────┐
│                                                                   │
│  ALB público            subnets públicas 10.1.0.0/20, 10.1.16.0/20│
│     │  target group type=ip                                       │
│     ▼                                                             │
│  Interface Endpoint     subnets privadas 10.1.32.0/20, 10.1.48.0/20│
│  (ENIs com IP em 10.1.32.x / 10.1.48.x)                           │
└───────────────────────────────┬───────────────────────────────────┘
                                │ PrivateLink (unidirecional)
┌───────────────────────────────▼───────────────────────────────────┐
│  VPC Endpoint Service                                             │
│     │  allowed principal = conta network                          │
│     ▼                                                             │
│  NLB INTERNO            subnets privadas 10.2.32.0/20, 10.2.48.0/20│
│     │  target type=ip → IPs dos pods                              │
│     ▼                                                             │
│  httpbin (Deployment + Service)                                   │
│                                                                   │
│  conta cicd (270222614208) — VPC spoke 10.2.0.0/16                │
└───────────────────────────────────────────────────────────────────┘
```

Sem route table nova, sem attachment, sem CIDR novo. O tráfego atravessa a fronteira de conta pelo
endpoint service, não por rota.

## Pré-requisito que hoje não existe: AWS Load Balancer Controller

A camada 2 entrega ESO, ArgoCD e Crossplane. **Não** entrega o LBC. Sem ele:

- `Service type=LoadBalancer` cai no cloud provider in-tree legado, que cria **Classic LB**
- não há `target-type: ip` (targeting direto de pod), que é o que o endpoint service precisa
- não há `scheme: internal` controlado por annotation de forma confiável

Então o primeiro artefato da fatia é `aws/terraform/src/helm/modules/aws-lbc`, mais uma **quarta Pod
Identity** no root. Segue o mesmo molde dos três charts existentes — chart, namespace, `wait = true`,
versão fixada, `values` por `yamlencode`.

O que **não** foi levantado ainda e é o primeiro trabalho da próxima sessão: **a policy IAM do
LBC**. Ela é grande (ELB, EC2 describe, WAF, ACM, shield) e a AWS publica um JSON de referência no
repositório do controller. Decidir se entra inline via `jsonencode` no root — coerente com o resto,
mas são ~200 linhas — ou como `aws_iam_policy` própria em `src/pod-identity`.

## Ordem de implementação (walk skeleton)

Fatia fina end-to-end antes de qualquer refinamento, conforme a regra do repo.

| # | Passo | Entrega verificável |
|---|---|---|
| 1 | `src/helm/modules/aws-lbc` + 4ª Pod Identity | pods do controller `Running`, sem erro de IAM no log |
| 2 | httpbin + `Service` com NLB **interno** | NLB `active`, `scheme: internal`, targets `healthy` |
| 3 | `aws_vpc_endpoint_service` no spoke, principal = conta `network` | `ServiceState: Available` |
| 4 | `aws_vpc_endpoint` (Interface) nas subnets privadas do hub | endpoint `available`, ENIs com IP em `10.1.32.x` |
| 5 | **prova de conectividade** de dentro do hub | `curl` do IP privado do endpoint devolve resposta do httpbin |
| 6 | ALB público no hub, target group `type=ip` → IPs do endpoint | `curl` do DNS do ALB devolve resposta do httpbin |

O passo 5 é o que fecha a fatia conceitualmente — dali em diante é só expor. **Não pular:** se falhar
no 6 sem ter provado o 5, não se sabe se o problema é PrivateLink ou ALB.

### Obstáculo do passo 5: o hub não tem compute nenhum

A VPC hub tem VPC, subnets, IGW e route tables. Nada mais — e **NAT desligado**, então subnet privada
não tem saída. Para rodar um `curl` de dentro do hub:

- **Opção barata:** `t3.micro` numa subnet **pública** do hub, com IP público e security group
  restrito ao IP de origem. ~US$ 0,01/h. Alcança o endpoint porque está na mesma VPC.
- **Opção sem porta aberta:** SSM Session Manager — mas exige três interface endpoints
  (`ssm`, `ssmmessages`, `ec2messages`) ou NAT. Mais caro e mais peças para uma prova pontual.

Recomendado: a primeira, destruída junto com a fatia.

## Custo enquanto de pé

| Item | ~US$/h | ~US$/mês |
|---|---|---|
| NLB interno (spoke) | 0,0225 | 16 |
| Interface Endpoint (2 AZs) | 0,020 | 15 |
| VPC Endpoint Service | 0 | 0 |
| ALB público (hub) | 0,0225 | 16 |
| `t3.micro` de teste | 0,0104 | — (descartável) |
| **subtotal da fatia** | **~0,075** | **~47** |
| camada 2 já existente | ~0,23 | ~165 |

Mais data processing por GB nos três (NLB, endpoint, ALB) — irrelevante em teste.

**Nada disto fica de pé entre sessões.** A camada 2 sobe, valida, desce.

## Fronteira: o que é Terraform e o que não é

Coerente com `../../decisions.md` §7 (cardinalidade × churn) e com o ADR de que **apps são helm puro
fora do Crossplane**:

- **Terraform:** LBC, Pod Identity, endpoint service, interface endpoint, ALB, instância de teste.
  Tudo isso é infraestrutura criada uma vez por célula.
- **Não-Terraform:** o httpbin. É workload — manifesto ou helm puro aplicado contra o contexto do
  EKS, como `aws/eks/apps/` já faz.

Consequência prática: o `aws_vpc_endpoint_service` depende do ARN do NLB, que só existe depois de o
Service do httpbin ser aplicado. Ou seja, **a fatia não é um único `terraform apply`** — há uma
barreira no meio. Duas saídas:

1. Aceitar duas fases (Terraform → aplicar workload → Terraform), o que contraria o padrão de apply
   único da camada 2.
2. Criar o NLB **por Terraform** (`aws_lb` interno, target group `ip` vazio) e deixar o LBC apenas
   registrar os pods via `TargetGroupBinding`. O apply volta a ser único e o Terraform passa a ser
   dono do NLB — que é o recurso que atravessa a fronteira de conta, então talvez deva ser dele
   mesmo.

**A opção 2 parece certa e não foi validada.** É a primeira decisão de desenho da próxima sessão.

## Perguntas abertas

- **`TargetGroupBinding` com NLB criado por Terraform** funciona como esperado? É o CRD que o LBC
  instala; a alternativa é `Service type=LoadBalancer` com o LBC dono do NLB.
- **Em qual conta fica o ALB público?** O desenho põe no hub (`network`), coerente com ingress
  centralizado. Mas `network` é conta de conectividade — hospedar um ALB de aplicação lá é a mesma
  discussão de fronteira que `decisions.md` §2 tem em aberto para auth/discovery.
- **Health check atravessa PrivateLink?** O target group do ALB no hub aponta para os IPs do
  endpoint. O health check do ALB sai do hub — precisa confirmar que o endpoint o repassa e que o
  security group do endpoint permite.
- **Certificado/TLS e DNS** ficam fora desta fatia de propósito: dependem da base de domínio, que é
  questão aberta (`wasp.silvios.me` está em Azure DNS). A fatia termina em HTTP no DNS do ALB.
- **Fechar o endpoint público da API do EKS** (`public_access_cidrs`) é trabalho vizinho e depende da
  mesma conectividade, mas é o **management plane** — decisão separada, não pendurar nesta fatia.

## Estado de referência da camada 2 (medido em 2026-08-25)

Números do apply real, úteis para saber o que é normal na próxima vez:

| Recurso | Tempo de criação |
|---|---|
| Cluster EKS | 11m 09s |
| Node group | 2m 00s |
| Addon `aws-ebs-csi-driver` | 6m 28s |
| Addon `eks-pod-identity-agent` | 9s |
| Release do Crossplane | 42s |
| ConfigMap `platform-bootstrap` | 2s |
| **apply completo** | **~13 min** |

Versões de addon resolvidas pela AWS (o Terraform não as fixa — `addon_version` é *known after
apply*):

| Addon | Versão |
|---|---|
| `aws-ebs-csi-driver` | `v1.64.0-eksbuild.1` |
| `eks-pod-identity-agent` | `v1.3.10-eksbuild.3` |

Security group do cluster: `sg-0daabea18f82503aa` (recriado a cada apply — anotado só como
referência de que existe e é gerado pela AWS, não pelo módulo).

**IDs de VPC/subnet mudam a cada apply.** Os do apply de 2026-08-25 estão em `HANDOFF.md`; servem
para reconhecer o padrão de CIDR, não para reuso.
