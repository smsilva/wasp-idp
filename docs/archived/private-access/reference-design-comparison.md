# Reference Design Comparison — PrivateLink Vs TGW

_2026-08-26_

Comparação feita contra um desenho hub-and-spoke de referência (Crossplane/KCL) mantido em outra
trilha. **Achado principal: aquele desenho não tem ingress centralizado — não tem ingress nenhum no
hub.** O hub é **trânsito puro**: TGW + route table + túneis IPSec, e a doc dele declara *"o template
não cria VPCs ou subnets; o TGW hub existe sem attachment de VPC próprio"*. Não há onde pôr um ALB.

O ingress lá é **distribuído**: cada spoke com cluster tem o próprio AWS Load Balancer Controller
(role + policy + Pod Identity) e o próprio ALB, com tags de subnet (`kubernetes.io/role/elb`,
`internal-elb`) para descoberta.

Convergências: hub-and-spoke multi-conta; cross-account por dois ProviderConfigs (equivalente aos
nossos providers aliasados); PrivateLink usado, mas **só para serviços da AWS** (`s3`, `dynamodb`,
`rds`, `secretsmanager`, `sqs`, `ecr.*`, `eks*`); LBC com Pod Identity.

Divergência, e é de propósito, não de qualidade — o eixo é **de onde vem o tráfego**: lá o tráfego
chega de redes privadas de cliente por IPSec (problema = conectividade L3 entre redes que já se
conhecem ⟹ TGW); aqui chega da internet (problema = exposição unidirecional de um serviço).

**Consequência dura:** aquele desenho **não valida** "entrada pública no hub" — valida o oposto. A
decisão de manter ingress único pelo hub foi tomada sabendo disso.

**Mecanismo de isolamento que vale copiar:** TGW sem propagação automática + uma route table por
tenant ⟹ spoke↔spoke não roteia **por ausência de rota, não por deny**; habilitar é aditivo e
explícito. Spoke nasce isolada.

**Ingress: PrivateLink vs TGW — resolvido.** O spec
`docs/superpowers/specs/2026-08-25-private-ingress-via-privatelink.md` continua **válido na
fundamentação** (a citação do whitepaper que separa PrivateLink de TGW por tipo de conectividade), mas
a escolha foi **reaberta e resolvida a favor do TGW** para o caminho hub→spoke: com VPN de cliente
decidida, o TGW entra de qualquer forma e o custo marginal de usá-lo também no ingress cai a zero.

**PrivateLink não morre.** Volta como candidato natural na fatia de **spoke de recursos
compartilhados** (banco, mensageria), onde CIDR sobreposto e autorização por principal de conta valem
dinheiro — ao contrário do caso de ingress, onde não usamos nenhum dos dois.

O que continua válido do spec: o NLB fica na **spoke** (o PrivateLink exige NLB no lado provedor, a
AWS não aceita ALB ali); provar conectividade de dentro antes de expor; e o hub não tem compute
nenhum hoje.
