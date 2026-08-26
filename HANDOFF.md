# HANDOFF

> **Arquivo único.** Este repo NÃO usa `HANDOFF.local.md` — a divisão versionado/local foi
> desfeita em 2026-08-25, porque duplicava contexto e cada sessão tinha de reconciliar os dois.
> Frente ativa, estado aplicado e backlog vivem aqui. `HANDOFF.local.md` segue no `.gitignore`
> como rede de segurança; se aparecer um, é resíduo — consolidar aqui e apagar.
>
> **Account IDs desta Organization estão neste arquivo, deliberadamente.** São de uma conta
> pessoal descartável para exercitar a PoC; nada aqui vai para ambiente real. E-mails de root
> **não** entram (PII, e um handoff não precisa deles) — ficam em `CLAUDE.local.md`.
>
> **Repo público.** Não citar nomes de empresa, de projeto interno ou caminho de repo interno aqui
> nem em conversa — nem no plural "os repos". Dizer "a trilha corporativa". Lista de tokens
> proibidos em `CLAUDE.local.md`.

## Why

Exercitar a PoC AWS EKS-via-Crossplane (arquitetura de referência hub-and-spoke) na conta
AWS pessoal do Silvio, genérica, antes de qualquer ambiente corporativo. `aws/` foi genericizada
a partir de um exemplo interno (placeholders `<...>` para valores por-conta/segredos; valores
genéricos concretos como `platform.example.com`/`poc-eks` onde o token é YAML/Crossplane
executável). Valores reais ficam em `CLAUDE.local.md` (gitignored).

Topologia: **conta única no bootstrap → hub-and-spoke real via cross-account**. Rejeitado: CIDR
fixo; `<...>` em campos executáveis.

**Sequência de provisionamento vigente: −1 → 0 → 2 → 5** (`decisions.md` §8). A Fase 1
(Global Accelerator + tenant registry) está **pulada**: escopo atual é só projetos internos,
sem cliente externo. Pular a Fase 1 **não** autoriza assumir região fixa — a indireção do §5
(nome sem região no que o usuário vê, TTL curto de DNS, tenant na chave primária) continua
obrigatória.

**Escopo do Terraform: fino.** Entrega VPC hub + VPC spoke + EKS + nodegroup + Pod Identity base
+ ESO + ArgoCD + Crossplane core, e para. istio, cert-manager, external-dns, ALB controller e
route53 zone/wildcard vêm por GitOps. Critério: cardinalidade × churn. Rejeitado: **paridade
total** e o padrão **seed cluster / hub-of-hubs** (`decisions.md` §7).

### Bifurcação de trilhas (2026-08-26)

A restrição de **concentrador de VPN a montante da AWS** (todas as conexões de cliente passam por
um concentrador corporativo; os CIDRs que chegam já vêm normalizados e sem colisão) pertence à
trilha corporativa e é explorada **fora deste repo**. As camadas Terraform daqui já foram levadas
para lá, com todo vocabulário local trocado por `PLACEHOLDER-*`.

**Aqui não há concentrador.** O desenho assume `Site-to-Site VPN` por cliente. **Não importar
resposta de uma trilha para a outra** — a bifurcação existe para impedir isso.

## Vocabulário (ler antes de qualquer coisa)

"hub" cobria três eixos independentes e a ambiguidade custou tempo. Dois foram renomeados;
só o topológico mantém o termo:

| Eixo | Nome correto | Nome antigo |
|---|---|---|
| **Conta AWS** de conectividade | `network` — Connectivity Account, OU `Infrastructure` | "conta hub", profile `hub`, ProviderConfig `hub` |
| **Papel topológico** de rede | `hub` — único uso legítimo. Par de `spoke`; chart `platform/charts/hub`, VPC hub, TGW | (inalterado) |
| **Control plane** Crossplane (k3d) | **Control Plane** / `control-plane` | "hub k3d", `poc-eks-hub-config` |
| **Conta** do Control Plane | `cicd`, na OU `Deployments` | `platform` |

`network` é canônico no whitepaper *Organizing Your AWS Environment Using Multiple Accounts*,
no AWS SRA e no Landing Zone Accelerator. A AWS **não** nomeia contas como "Hub".

O chart `platform/charts/hub` **não** foi renomeado de propósito: ali "hub" é topologia, e
`network` colidiria com o XR `Network` que ele renderiza.

O prefixo `poc-idp/` no Secrets Manager (`poc-idp/crossplane-poc-credentials`) é o nome real
de um secret na AWS, não apelido do cluster — **não renomear**.

**`cluster-zero` é da trilha Azure (AKS), pausada — não é o Control Plane da AWS.** No contexto
AWS nunca dizer "cluster zero". O plano `docs/superpowers/plans/2026-08-07-cluster-zero-terraform.md`
aponta para `infra/terraform/cluster-zero/README.md`, que **nunca existiu em nenhum branch** — é
link para artefato não construído, não doc desatualizada. Não apagar: é registro de desenho de
outra trilha.

**Hierarquia de fontes AWS:** **WAF** diz *por quê* isolar por conta e **nomeia zero contas e zero
OUs**; o **whitepaper** nomeia OUs (`Security`, `Infrastructure`, `Workloads`, `Sandbox`,
`Deployments`, …); o **SRA** nomeia contas (`Shared Services`, `Network`, …). Tabela em
`aws/docs/accounts/01-organizations-and-ous.md`.

## Estado aplicado na AWS

Snapshot de 2026-08-26. **Custo recorrente: só centavos.** A camada 2 foi destruída.

| Camada | Conta | State key | Custo/mês | Estado |
|---|---|---|---|---|
| `state-backend` | `network` | `state-backend/` | centavos | aplicada |
| `network-foundation/us-east-1` | `network` | `network-foundation/us-east-1/` | **zero** | aplicada |
| `network-foundation/us-west-2` | `network` | `network-foundation/us-west-2/` | **zero** | aplicada |
| `control-plane` | `cicd` | `control-plane/` | ~US$ 165 quando de pé | **destruída** (state com 0 recursos) |

Bucket de state: `tfstate-o-e4r8ndteju`, na conta `network`. Nenhum cluster k3d de pé
(`k3d cluster list` vazio).

### Camada 1 — VPCs hub (custo recorrente zero)

| Região | VPC | CIDR | Subnets |
|---|---|---|---|
| `us-east-1` | `vpc-087a169b8e8dfc7d5`, tag `Name = poc-hub-vpc` | `10.1.0.0/16` | públicas `10.1.0.0/20`, `10.1.16.0/20`; privadas `10.1.32.0/20`, `10.1.48.0/20` |
| `us-west-2` | — | `10.3.0.0/16` | idem, derivadas por `cidrsubnet()` |

**Sem NAT Gateway em nenhuma das duas** — sem TGW nada roteia pelo hub, e um NAT custaria
~US$ 32/mês servindo zero tráfego. As subnets privadas não têm saída para a internet. **Isso muda
quando o TGW entrar.**

### Camada 2 — Control Plane, quando aplicada (conta `cicd`, `us-east-1`)

Referência do último apply real, para reconhecer o padrão — **IDs de VPC/subnet mudam a cada
apply**: VPC spoke `10.2.0.0/16`; EKS `control-plane` Kubernetes **1.36**; 2× `t3.medium`
`ON_DEMAND`; NAT **ligado** (os nós dependem dele); charts ArgoCD `10.4.0`, ESO `2.9.0`,
Crossplane `2.4.0` (canal `stable`).

Roles de Pod Identity, na conta `cicd`: `control-plane-crossplane` (`crossplane-system`/`crossplane`),
`control-plane-external-secrets` (`external-secrets`/`external-secrets`), `control-plane-ebs-csi`
(`kube-system`/`ebs-csi-controller-sa`). Mais `control-plane-cluster` e `control-plane-node` (roles
do EKS, não Pod Identity).

Tempos do apply: EKS 11m09s, node group 2m, addon `aws-ebs-csi-driver` 6m28s,
`eks-pod-identity-agent` 9s, release do Crossplane 42s, apply completo **~13 min**.

### Alocação de CIDR do supernet `10.0.0.0/12`

| N | CIDR | Conta | Papel |
|---|---|---|---|
| 0 | `10.0.0.0/16` | — | reservado à Organization |
| 1 | `10.1.0.0/16` | `network` | VPC **hub** `us-east-1` |
| 2 | `10.2.0.0/16` | `cicd` | VPC **spoke** do Control Plane |
| 3 | `10.3.0.0/16` | `network` | VPC **hub** `us-west-2` |
| 4–15 | `10.4`–`10.15` | — | livres |

**É a única decisão irreversível da cadeia.** Teto de 15, e região multiplica.

## In Progress

### Frente D — acesso privado + ingress centralizado (ATIVA)

**Plano escrito: `docs/superpowers/plans/2026-08-26-private-access-and-ingress.md`** — sequência de
9 passos, cada um testável isolado, com níveis de permanência, fronteira de state, scripts e custo.
Ler ele; o resumo aqui é só para saber se vale abrir.

Decisões fechadas:

1. **Ingress único, pelo hub.** Nenhuma spoke expõe acesso a si direto na internet.
2. **`Site-to-Site VPN` por cliente**, terminando no TGW do hub — um attachment por cliente ⟹
   isolamento nas duas direções por route table de tenant.
3. **Acesso de manutenção: AWS Client VPN no hub com autenticação SAML** pelo Identity Center.
   Escolhido sobre certificado porque **conceder e revogar acesso a uma pessoa é a demonstração**, e
   porque authorization rule por grupo dá CIDR-por-grupo. Preço: o client da AWS no Linux é
   aplicação desktop, então `connect` não é scriptável — é o portão do passo 1a.
4. **TGW + Client VPN de pé durante o dia, destruídos à noite.** Base permanente sai de ~zero para
   ~US$ 110/mês enquanto ligada.
5. **Fronteira de state segue o ciclo de vida, não a conta** — `tgw-rt-<spoke>` vive na conta hub
   mas no state do spoke.

**A descoberta que reordenou tudo:** o que prende o endpoint público da API do EKS não é `kubectl`,
é o **Terraform** — os providers `helm`/`kubernetes` falam com o API server a partir de onde o apply
roda. Acesso privado deixou de ser hardening no fim da fila e virou pré-requisito de operabilidade.

**O corte de state `hub | spoke+cluster` sobrevive ao TGW** (item que estava aberto): o egress da
spoke continua saindo pelo NAT dela, e a AWS recusa deletar TGW com attachment vivo. Cai se um dia
houver egress centralizado.

Quatro itens ainda abertos dentro do plano, listados no fim dele: variante do passo 6 (ALB → IP de
pod via TGW, ALB → NLB interno, ou PrivateLink), dono do ALB, desenho do cliente simulado, e conta
da hosted zone pública.

### Frente A — bootstrap de contas / Organization

Forma da Organization, inspecionada na API. Organization `o-e4r8ndteju`, root `r-f11d`, região de
trabalho `us-east-1`.

```
Root  r-f11d
├── ACC  221047292361  Silvio Silva          (management — não hospeda nada; SCP não a afeta)
├── OU   ou-f11d-ig5lcrlr  Security
│   └── ACC  995122007318  log-archive
├── OU   ou-f11d-8l7pbxgp  Infrastructure
│   └── ACC  094289743086  Network           (Connectivity Account — VPC hub)
├── OU   ou-f11d-rd0jp025  Deployments
│   └── ACC  270222614208  cicd              (Control Plane — Crossplane + ArgoCD + ESO)
└── OU   ou-f11d-j7fnwqmx  Workloads
    ├── OU   ou-f11d-7nadx2es  NonProd
    │   └── ACC  832721568602  wasp-nonprod
    └── OU   ou-f11d-vyxw3s7r  Production     (vazia)
```

| Conta | Profile local | ProviderConfig | Credencial |
|---|---|---|---|
| `Network` `094289743086` | `network` | `network` | IAM user `crossplane-poc` (direta) |
| `wasp-nonprod` `832721568602` | `wasp-nonprod` | `wasp-nonprod` | role `crossplane-wasp-nonprod` (assumeRoleChain) |
| `cicd` `270222614208` | `cicd` | — | `OrganizationAccountAccessRole` via `personal` |
| management `221047292361` | `personal` | — | SSO `AdministratorAccess` |

Casing: o nome na Organizations é `Network` (maiúsculo, igual ao LZA); identificadores técnicos
(profile, ProviderConfig, enum) usam `network` minúsculo.

**Passos ①–⑥ concluídos.** SCPs baseline em todos os targets: Root com `DenyLeaveOrganization` +
`ProtectCloudTrail`; `Security`, `Infrastructure`, `Workloads` e `Deployments` com
`DenyOutsideApprovedRegions`, `RequireImdsv2`, `DenyRootUser`. Regiões aprovadas: `us-east-1`,
`us-west-2`. CloudTrail organizacional `organization-trail` + bucket `cloudtrail-<organization-id>`
na `log-archive` (BPA, versionamento, SSE-S3, `BucketOwnerEnforced`, deny non-TLS), < US$ 1/mês.

**Ordem que funcionou melhor que a documentada:** aplicar a SCP na OU **antes** de criar a conta
nela. Não elimina a janela Root→OU, encurta. Os scripts são idempotentes.

**Aprovar região é `--regions` e vale para a Organization inteira.**
`./apply-baseline-service-control-policy --regions <r1>,<r2>` reescreve `DenyOutsideApprovedRegions`
em todos os targets — não há como liberar região só numa conta por essa via. Sem isso um
`terraform apply` fora das regiões aprovadas falha no primeiro `Create*` com
`explicit deny in a service control policy`, e o erro parece bug de código. **Comprovado:**
`ec2:DescribeVpcs` em região não aprovada volta com deny explícito.

**Passo ⑦ parcial.** Identity Center (IDs em `CLAUDE.local.md`): `management` com
`AdministratorAccess` num **usuário nominal** (deveria ser grupo); `log-archive` com `ReadOnlyAccess`
no grupo `platform-admins`; `Network`, `wasp-nonprod` e `cicd` **sem permission set** — acesso só
por `OrganizationAccountAccessRole`.

Pendências da conta `cicd`: sem permission set, e **VPC default em toda região** (security group
default aberto), como qualquer conta nova.

### Frente B — Terraform e Crossplane / EKS

**Camadas 1 e 2 escritas, aplicadas e verificadas.** Um `terraform apply`, **39 recursos**, ~13 min,
**sem `-target`** — isso fecha a dúvida do desenho: providers `kubernetes`/`helm` configurados a
partir de outputs do módulo do cluster resolvem na hora do apply. O que quebraria é **data source**
desses providers no plan; por isso o `platform-bootstrap` tem de continuar sendo `resource`.

Três scripts em `aws/terraform/control-plane/scripts/`:

| Script | O que faz |
|---|---|
| `generate-tfvars` | Descobre na AWS o que a camada precisa e gera o `terraform.tfvars`. **Só leitura.** Valida antes de gerar arquivo: tag da VPC hub univoca, CIDR livre, região aprovada na SCP, bucket existente |
| `apply` | `plan` → confirma → aplica → guarda log com timestamp em `logs/` |
| `destroy` | Confere Crossplane sem recurso vivo e contexto kubectl correto → destrói → guarda log |

Os dois últimos leem o exit code por `PIPESTATUS[0]`: o `tee` sempre retorna 0, e sem isso um apply
que falhou passaria por sucesso.

#### Trilha k3d (Cross-account + Fase 4)

Pronta e validada offline; é a trilha que o Terraform vem substituir.

- **ProviderConfigs por conta:** `network` (credencial direta) e `wasp-nonprod` (assumeRoleChain,
  `${SPOKE_ACCOUNT_ID}` via envsubst). **Sem PC `default`** — falha-fechado.
- **Role `crossplane-wasp-nonprod`** na conta `wasp-nonprod`: trust p/ `crossplane-poc` da
  `Network` + PowerUserAccess + inline `CrossplaneEksRoleManagement`. Assume validado com creds
  reais.
- **Identidade = `metadata.name`** (Crossplane v2, sem `spec.id`). `providerConfigName`
  OBRIGATÓRIO, enum `[network, wasp-nonprod]`.
- **Charts `aws/platform/charts/{hub,spoke,cluster}`**, um release por célula. Helper
  `aws/eks/scripts/random-id`.
- Ciclo real provado antes do rename: `helm install` criou VPC+NAT, `helm uninstall` destruiu tudo.
  Orquestrador `environment/` **BLOCKED**.
- **`install-crossplane` usa `--servers 1`.** Com 3, o etcd embutido perde quórum neste host (8
  cores) ao instalar os providers — crash-loop persistente, não lentidão.

**Divergência conhecida:** o chart `platform/charts/hub` renderiza um XR `Network` — o hub VPC nasce
**por Crossplane a partir do k3d**, não por Terraform como a Fase 2 prescreve. Degrau de bootstrap
consciente; é a divergência que o Terraform fecha.

### Frente C — documentação de arquitetura (`aws/docs/`)

Oito domínios: `bootstrap`, `network`, `accounts`, `security`, `dns`, `compute`, `observability`,
`tenancy`. Os sete primeiros descrevem estado real ou alvo próximo; **`tenancy/` é puramente
prospectivo**. `network/03-transit-gateway-isolation.md` e `04-vpn-access.md` já existem e
prescrevem TGW com route table por spoke e "a VPN fecha sempre no hub" — são o alvo da Frente D.

## O que a comparação com o desenho de referência ensinou (2026-08-26)

Comparação feita contra um desenho hub-and-spoke de referência (Crossplane/KCL) mantido em outra
trilha. **Achado principal: aquele desenho não tem ingress centralizado — não tem ingress nenhum no
hub.** O hub é **trânsito puro**: TGW + route table + túneis IPSec, e a doc dele declara *"o template
não cria VPCs ou subnets; o TGW hub existe sem attachment de VPC próprio"*. Não há onde pôr um ALB.

O ingress lá é **distribuído**: cada spoke com cluster tem o próprio AWS Load Balancer Controller
(role + policy + Pod Identity) e o próprio ALB, com tags de subnet
(`kubernetes.io/role/elb`, `internal-elb`) para descoberta.

Convergências: hub-and-spoke multi-conta; cross-account por dois ProviderConfigs (equivalente aos
nossos providers aliasados); PrivateLink usado, mas **só para serviços da AWS** (`s3`, `dynamodb`,
`rds`, `secretsmanager`, `sqs`, `ecr.*`, `eks*`); LBC com Pod Identity.

Divergência, e é de propósito, não de qualidade — o eixo é **de onde vem o tráfego**: lá o tráfego
chega de redes privadas de cliente por IPSec (problema = conectividade L3 entre redes que já se
conhecem ⟹ TGW); aqui chega da internet (problema = exposição unidirecional de um serviço).

**Consequência dura:** aquele desenho **não valida** "entrada pública no hub" — valida o oposto. Se
insistirmos no ALB no hub, é sem precedente, e a pergunta aberta *"`network` é conta de conectividade;
hospedar ALB de aplicação lá é discutível"* ganha uma resposta empírica: **lá ninguém hospedou.** A
decisão de manter ingress único pelo hub foi tomada sabendo disso.

**Mecanismo de isolamento que vale copiar:** TGW sem propagação automática + uma route table por
tenant ⟹ spoke↔spoke não roteia **por ausência de rota, não por deny**; habilitar é aditivo e
explícito (declarar o CIDR do vizinho + propagar o attachment). Spoke nasce isolada.

## Ingress: PrivateLink ou TGW — decisão REABERTA

O desenho anterior (`docs/superpowers/specs/2026-08-25-private-ingress-via-privatelink.md`) escolhia
**PrivateLink** com citação da AWS, e continua correto **na fundamentação**:

> **AWS PrivateLink** — Use AWS PrivateLink when you have a client/server set up where you want to
> allow one or more consumer VPCs unidirectional access to a specific service or set of instances
> in the service provider VPC (…) also a good option when client and servers (…) have overlapping IP
> addresses.
>
> **VPC peering and Transit Gateway** — Use (…) when you want to enable layer-3 IP connectivity
> between VPCs.
>
> — *Building a Scalable and Secure Multi-VPC AWS Network Infrastructure* (2024-04-17)

**Mas a comparação que sustentava a escolha caiu.** Ela pesava *"ligar TGW custa uma peça nova e
obriga a revisitar o corte de state"* contra *"PrivateLink não toca route table"*. Com VPN de cliente
decidida, **o TGW entra de qualquer forma** — o custo marginal de usá-lo também no caminho hub→spoke
cai para perto de zero, e PrivateLink passa a ter de se justificar por outro motivo (isolamento por
principal, CIDR sobreposto), não por evitar o TGW.

**Não tratar a decisão do spec como fechada.** O que continua válido dele: o NLB fica na **spoke**
(imposição do PrivateLink: `aws_vpc_endpoint_service` recebe `network_load_balancer_arns`, e a AWS
não aceita ALB ali); o passo 5 (provar conectividade de dentro do hub antes de expor) não se pula; o
hub não tem compute nenhum hoje.

**Resolvido do spec:** a pergunta *"`TargetGroupBinding` com NLB criado por Terraform funciona?"* —
**sim**. A doc do LBC descreve provisionar o load balancer *"completely outside of Kubernetes"* e
ainda gerenciar os targets pelo Service; `networking.ingress` é o campo que faz o controller cuidar
das regras de SG para targets IP. Logo **Terraform pode ser dono do NLB sem quebrar o apply único**.
Ressalva: o CR pode referenciar qualquer target group — exige RBAC em cenário multi-tenant.

**Ainda em aberto, e depende da topologia:** qual raiz Terraform é dona dos recursos do lado hub
(interface endpoint / ALB). Três opções levantadas: raiz nova `private-ingress/` com dois providers
(preserva `hub | spoke+cluster`, casa com a fatia ser efêmera); tudo no root `control-plane/` via
`local.install_*` (zero plumbing, mas põe recursos da VPC hub no state da camada 2 — um destroy da
camada 1 deixa de ser seguro); ou hub em `network-foundation/` e spoke em `control-plane/` (respeita
o corte, custa o apply único). **Pergunta não respondida** — foi substituída pela discussão de VPN.

## Open Questions / Hypotheses

- **Acesso de manutenção** — a pergunta ativa. Ver Frente D.
- **Dono dos recursos do lado hub no Terraform** — ver seção de ingress.
- **Conflação em `decisions.md` §2:** a spoke de plataforma roda *"auth, discovery, ArgoCD,
  Crossplane"*. `auth` e `discovery` são runtime de aplicação **no caminho da requisição** — não são
  build/validate/promote/release, logo não pertencem a uma conta de CI/CD pela definição da própria
  OU. Mesmo eixo da decisão 6 do §11; resolver junto.
- **Em qual conta fica a hosted zone pública** (`network` ou `cicd`). Mesma família da pergunta "ALB
  de aplicação numa conta de conectividade".
- **Teto do plano de CIDR: 15 spokes**, e **região multiplica** — 10 tenants em 2 regiões estoura.
  Quatro caminhos em `aws/docs/network/01-cidr-addressing.md`. Única decisão irreversível.
- **Session tags em `assumeRoleChain`:** a contenção regional por
  `aws:RequestedRegion` = `aws:PrincipalTag/region` depende de o provider-aws propagar tags de
  sessão. **Não verificado.** Se não propagar, a condição nunca casa e tudo é negado.
- **Base do domínio:** `wasp.silvios.me` está em Azure DNS; delegar subzona (ex.
  `aws.wasp.silvios.me`) para Route53 ou o domínio inteiro? Sem `<hosted-zone-id>` as fatias
  DNS/ingress/TLS ficam bloqueadas; rede/EKS/Pod Identity/ESO rodam sem isso.
- **Parametrizar** valores de `CLAUDE.local.md` (chart values? env? EnvironmentConfig?).
- **Rework do orquestrador `environment/`** (BLOCKED): sob `metadata.name`, filhos compostos ganham
  nome hasheado → o cruzamento por label compartilhado não funciona. Conserto desenhado em
  `resources/examples/topology/05-07` (injetar `subnetIds` do `Network.status` no Cluster em vez de
  casar por label; exige `function-kcl` ou Network publicar arrays). Adiado.
  `compute/06-crossplane-map.md` registra o alvo: **remover `Environment`; `Cluster` é o topo**.
- **`tenancy/04-crossplane-map.md` não escrito de propósito** — depende do schema do registry de
  tenants (§11 decisão 1). Ausência é deliberada.
- **Retenção do bucket de auditoria** (lifecycle → Glacier após N dias, expiração após M anos):
  decisão de compliance adiada. É o único custo do CloudTrail que cresce sozinho e para sempre.
- **Conta `security-tooling`** desenhada como slot, não criada — vira pré-requisito quando
  GuardDuty/Config/Security Hub entrarem.
- **Contas `Monitoring` / `Operations Tooling`** (OU `Infrastructure`) são os slots canônicos da
  observabilidade centralizada; nenhuma existe.
- **`Sandbox` como conceito** fica reservado para conta de brincar, desconectada da rede — não é o
  ambiente de teste do projeto, que é `<projeto>-nonprod`.
- Track paralelo (Azure cluster-zero + Backstage multi-tenant) pausado.

## Known Broken

1. **`src/network` não aplica as tags de descoberta do AWS Load Balancer Controller** —
   *unexpected*, achado nesta sessão: falta `kubernetes.io/role/elb` nas públicas e
   `kubernetes.io/role/internal-elb` nas privadas. Sem elas o LBC não encontra onde criar load
   balancer, e o sintoma é obscuro. Bug latente, não hipótese — o desenho de referência tem isso
   como flag explícita.
2. **`src/network` não tem nada de TGW** — *intentional* até agora, mas passou a ser lacuna com a
   decisão de VPN: falta attachment, associação/propagação em `tgw-rt-<spoke>` e rotas para CIDRs
   remotos.
3. **Break-glass documentado, controles ausentes** — *unexpected*: MFA no root da management account
   e das contas-membro **não verificado**; alarme de uso de root **não existe** (CloudTrail já
   captura, falta a regra EventBridge); ensaio nunca executado.
4. **Management account com `AdministratorAccess` atribuído a usuário, não a grupo** —
   *unexpected*: viola a própria regra `--group` da doc, na conta mais privilegiada. Migrar para
   `platform-admins` (atribuir o grupo **antes** de revogar o usuário).
5. **Credencial-raiz do Crossplane é access key de longa duração** — *intentional*: contraria
   [SEC02-BP02](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/sec_identities_unique.html).
   Sobrevive **só na trilha k3d**, que não suporta Pod Identity — no EKS da camada 2 o pod subiu com
   `AWS_CONTAINER_CREDENTIALS_FULL_URI`, sem access key. **Mitigação barata não aplicada:** reduzir o
   IAM user a só `sts:AssumeRole` para uma role específica; hoje tem `PowerUserAccess` direto.
6. **Endpoint da API do EKS público para `0.0.0.0/0`** quando a camada 2 está de pé —
   *intentional*: `endpointPublicAccess = true` e `public_access_cidrs = []` (vazio significa
   `0.0.0.0/0`). É **management plane**, plano distinto do ingress de workload; fechar exige alcançar
   a API de dentro da VPC.
7. **`bootstrapClusterCreatorAdminPermissions` divergente** — *unexpected*: `true` na camada 2,
   `false` no cluster do chart Crossplane. Herdado de caminhos diferentes, não decidido.
8. **VPC default da `cicd` de pé em toda região**, com security group aberto — *unexpected*, e agora
   há workload real na conta.
9. **Link quebrado em `docs/superpowers/plans/2026-08-07-cluster-zero-terraform.md`** →
   `infra/terraform/cluster-zero/README.md` — *intentional*: aponta para artefato da trilha Azure
   nunca construído.
10. **Valores reais em docs genéricas** — *unexpected*: `aws/docs/bootstrap/00-crossplane-iam-user.md:91`
    tem account id hardcoded; `accounts/03-provisioning.md` e `accounts/scripts/create-account` têm
    e-mail real. Pré-existente.
11. `crossplane render` não injeta defaults do XRD — *intentional*: passar
    `providerConfigName`/`metadata.name` explícitos no XR de teste. `providerConfigName` é
    OBRIGATÓRIO, sem fallback.
12. `enum` de `providerConfigName` inclui `wasp-nonprod` (nome específico de conta) nos XRDs
    versionados — *intentional*: trade-off aceito vs. genericização.
13. `aws/eks/apps/echo/templates/*.yaml` falham em parser YAML puro — *intentional*: Helm templates.
14. `revoke-permission-set` só foi exercido no caminho feliz; os ramos "atribuição inexistente" e
    "permission set inexistente" nunca rodaram.
15. `idp/app-config.production.yaml` `guest: {}`; `idp/packages/backend/src/index.ts` `allow-all`
    policy; `idp/packages/backend/src/googleAuthModule.ts`
    `dangerouslyAllowSignInWithoutUserInCatalog: true` — *intentional* (PoC).
16. **Sob `mock_provider`, data source de provider devolve valor sintético** — *intentional*
    (limitação do framework): assertion sobre JSON computado pelo provider passa sem verificar nada.
    Regra: policy document via `jsonencode`. Aplicado nos módulos novos; **auditar se há outro lugar
    no repo com a mesma armadilha.**

## How to Resume

**Custo hoje é zero** — camada 2 destruída, nenhum k3d de pé. Confirmar antes de confiar:

```bash
cd wasp-idp/aws/terraform/control-plane
terraform state list | wc --lines   # 0 = destruída; 39 = de pé (~US$ 0,23/h)
k3d cluster list                    # esperado: vazio
```

**O trabalho ativo é desenho, não código.** Retomar respondendo a pergunta de acesso de manutenção
da Frente D, com este contexto carregado:

```bash
code docs/superpowers/specs/2026-08-25-private-ingress-via-privatelink.md
code aws/docs/network/03-transit-gateway-isolation.md
code aws/docs/network/04-vpn-access.md
cat aws/docs/network/CLAUDE.md   # a armadilha do attachment agregado
```

Se for preciso subir a camada 2 para experimentar:

```bash
cd aws/terraform/control-plane
./scripts/generate-tfvars --force
terraform init -backend-config="bucket=tfstate-o-e4r8ndteju"
./scripts/apply
```

`terraform apply`/`destroy` rodam por `! <comando>` — o classifier de auto-mode bloqueia para o
agente. O `apply` sem tty falha de propósito, informando o caminho do plano salvo; usar `--yes`
quando não houver terminal. O mesmo vale para os scripts de `aws/docs/accounts/scripts/` que criam
recursos reais.

Regressão offline (45 testes, 11 diretórios, 0 falhas):

```bash
cd aws/terraform
for m in src/network src/state-backend src/pod-identity src/cluster src/nodegroup \
         src/helm/modules/external-secrets src/helm/modules/argo-cd src/helm/modules/crossplane \
         network-foundation/us-east-1 network-foundation/us-west-2 control-plane; do
  (cd "${m}" && terraform init -backend=false >/dev/null && terraform test)
done
```

Se o Control Plane k3d tiver de ser reproduzido:

```bash
k3d cluster list                       # confirmar antes de assumir
aws/eks/scripts/install-crossplane     # k3d "control-plane" (1 server) + Crossplane
aws/eks/scripts/install-providers --timeout 900s
aws/eks/scripts/install-functions      # OBRIGATÓRIO: toda Composition é mode: Pipeline

set -a; source <(AWS_PROFILE=network aws secretsmanager get-secret-value \
  --secret-id poc-idp/crossplane-poc-credentials --region us-east-1 \
  --query SecretString --output text \
  | jq -r '"AWS_ACCESS_KEY_ID=" + .aws_access_key_id, "AWS_SECRET_ACCESS_KEY=" + .aws_secret_access_key'); set +a
aws/eks/scripts/configure-aws-creds
aws/eks/scripts/configure-account-access --name wasp-nonprod --account-id <spoke-account-id>
```

Pré-requisitos: VPN corporativa **desconectada** (senão o pull de `xpkg.upbound.io` falha com `x509`
e depois `connection reset`) e SSO admin ativo (`aws sso login --profile personal`).

**Achados a não reaprender:**

- **A referência funcional do provisionamento EKS são as Compositions Crossplane**, não as fases do
  chart `aws/eks/chart/templates/` — as fases são a mesma coisa menos decomposta e com bugs já
  corrigidos do outro lado.
- **As ~40 `ClusterUsage` do teardown ordenado não têm tradução em Terraform** — são aresta de
  dependência construída à mão porque `Network` e `Cluster` são XRs distintos. Terraform destrói em
  ordem reversa nativamente, **mas só se rede e cluster estiverem no mesmo state** — por isso o corte
  é `hub | spoke+cluster`, nunca `rede | cluster`.
- **EBS CSI pertence à abstração `Cluster` (L2b)**, ao lado do `eks-pod-identity-agent`. Não é adição
  opcional.
- Trust de Pod Identity exige `sts:TagSession` além de `sts:AssumeRole`.
- `authentication_mode = "API"` — sem `aws-auth` ConfigMap.
- A `Network` de referência tem as 4 subnets **hardcoded** em `172.16.{1,2,3,4}.0/24`. **Não
  herdar:** `src/network` calcula com `cidrsubnet()`.
- **A race de Pod Identity do EBS CSI não existe no Terraform** — o grafo já ordena addon depois da
  association, e o controller subiu com 0 restarts. É limitação do Crossplane sem `depends_on` real.
- **Nunca fixar versão de Kubernetes (nem de chart, nem de addon) em documento de plano.** O plano da
  camada 2 trazia `1.34` quando o default do EKS já era `1.36`, com suporte padrão terminando em
  2026-12-01 — o cluster nasceria devendo upgrade. O `generate-tfvars` descobre.

## Next Steps

### Frente D — acesso privado + ingress (prioridade)

Plano em `docs/superpowers/plans/2026-08-26-private-access-and-ingress.md`. Executar na ordem.

Numeração `fase.passo`; passo descoberto executando entra com sufixo de letra (`2.3a`) para não
empurrar os seguintes.

- [x] Acesso de manutenção decidido: **Client VPN + SAML** no hub.
- [x] Níveis de permanência, fronteira de state e o corte `hub | spoke+cluster` sob TGW.
- [x] Ingress decidido (variante **B**), certificado (**wildcard de ACM por cluster**), DNS (subzona
      `nonprod.` delegada com a delegação em código) e onde mora o cliente simulado.
- [ ] **Fase 1 — preparação, grátis:** `1.1` tags de descoberta do LBC; `1.2` `/32` no
      `public_access_cidrs`; `1.3` raiz `dns/` + delegação.
- [ ] **`2.1` é PORTÃO** — verificar o client da AWS VPN nesta distro **antes** de criar recurso que
      cobra. Três saídas escritas no plano se falhar.
- [ ] **Fase 2 (`2.2`–`2.5`)** — TGW + Client VPN + attachment + DNS privado + fechar a API.
- [ ] **Fase 3 (`3.1`–`3.2`)** — NLB interno e gateway Istio; depois o lado hub com cert e listener
      rule.
- [ ] **Fase 4 (`4.1`–`4.2`)** — as duas provas negativas.
- [ ] Conferir a cota de certificados por listener de ALB (único item aberto do plano).

### Frente B — Terraform + Crossplane / EKS

- [ ] **Adicionar as tags de descoberta do LBC em `src/network`** — Known Broken 1, independe de
      qualquer decisão de topologia. É o item mais barato da lista.
- [ ] **TGW em `src/network`:** `transit_gateway_id` + `remote_cidrs` opcionais → attachment,
      associação/propagação em `tgw-rt-<spoke>`, rotas nas RTs. **Ao fazer, revisitar o corte de
      state** `hub | spoke+cluster`: ele era seguro só enquanto não havia TGW.
- [ ] Instalar o **AWS Load Balancer Controller** como `src/helm/modules/aws-lbc` + 4ª Pod Identity.
      A policy IAM é grande (~200 linhas); decidir se entra `jsonencode` num arquivo próprio do root
      ou como `aws_iam_policy` em `src/pod-identity`.
- [ ] **Fechar o endpoint público da API do EKS** (`public_access_cidrs`) — depende de alcançar a API
      de dentro da VPC.
- [ ] Decidir `bootstrapClusterCreatorAdminPermissions`: `true` (camada 2) ou `false` (chart).
- [ ] Ligar NAT no hub quando o TGW entrar — a decisão de deixá-lo desligado vale só sem TGW.
- [ ] Escrever o design do script `follow` determinístico (ganha spec própria).
- [ ] Reduzir o IAM user `crossplane-poc` a só `sts:AssumeRole`.
- [ ] Decidir base do domínio (delegar `wasp.silvios.me`/subzona → Route53) antes das fatias
      DNS/ingress/TLS.
- [ ] Definir estratégia de parametrização dos valores de `CLAUDE.local.md`.

### Frente A — contas

- [ ] Atribuir permission set à conta `cicd` — nasceu sem nenhum.
- [ ] Atribuir permission set a `Network` e `wasp-nonprod`
      (`./assign-permission-set --account <conta> --group platform-admins`) — elimina o switch-role.
- [ ] Migrar a atribuição da management account de usuário para grupo `platform-admins` (atribuir o
      grupo **antes** de revogar o usuário).
- [ ] Verificar/habilitar MFA no root da management account e das contas-membro.
- [ ] Criar a regra de alarme de uso de root (CloudTrail → EventBridge → notificação).
- [ ] Decidir retenção/lifecycle do bucket `cloudtrail-<organization-id>`.
- [ ] Decidir se as VPCs default da `cicd` saem. Higiene, não bloqueio.

### Frente C — documentação

- [ ] Resolver a conflação de `decisions.md` §2 (auth/discovery vs. conta de CI/CD) junto com a
      decisão 6 do §11.
- [ ] Remover os valores reais que sobraram em docs genéricas (Known Broken 10).
- [ ] `tenancy/04-crossplane-map.md`, quando o schema do registry de tenants existir.
- [ ] Auditar o repo por outros usos de `data "aws_iam_policy_document"` sob `mock_provider`
      (Known Broken 16).

## Completed Work

### Desenho de ingress e VPN — decisões e comparação com a referência (2026-08-26)

Ingress único pelo hub e VPN de cliente por `Site-to-Site` no hub decididos. Comparação com um
desenho hub-and-spoke de referência de outra trilha produziu três achados que mudaram o rumo: aquele
hub **não tem ingress** (é trânsito puro, sem VPC), o ingress lá é **distribuído por spoke com LBC
próprio**, e **route table de tenant só isola nas duas direções se o attachment for por cliente** —
com attachment agregado, a entrada fica dependente de security group. Registrado em
`aws/docs/network/CLAUDE.md`.

Resolvida a pergunta aberta do spec de PrivateLink: `TargetGroupBinding` **aceita** target group
criado fora do controller, então Terraform pode ser dono do NLB sem quebrar o apply único.

Camadas Terraform levadas para a trilha corporativa, com vocabulário local trocado por
`PLACEHOLDER-*`, regressão offline verificada lá, e as duas lacunas (TGW, tags de LBC)
documentadas como ponto de entrada em vez de implementadas às cegas.

### Camada 2 do Terraform — escrita, aplicada, verificada e destruída (2026-08-25/26)

Tasks 1–7 em TDD offline, Task 8 é o apply.

| Task | Módulo | Testes |
|---|---|---|
| 1 | `src/pod-identity` | 4 |
| 2 | `src/cluster` | 6 |
| 3 | `src/nodegroup` | 4 |
| 4 | `src/helm/modules/external-secrets` | 3 |
| 5 | `src/helm/modules/argo-cd` | 4 |
| 6 | `src/helm/modules/crossplane` | 2 |
| 7 | root `control-plane/` | 5 |
| 8 | apply na AWS | 39 recursos |

Regressão da árvore inteira: **45 testes em 11 diretórios, 0 falhas**.

O root compõe VPC spoke `10.2.0.0/16` + EKS + node group + três Pod Identities + os três charts + o
ConfigMap `platform-bootstrap`, que é o contrato com o GitOps — nenhum manifesto do lado GitOps
carrega account id ou VPC id hardcoded.

**Quatro correções ao plano exigidas pelos próprios testes:** `jsonencode` no lugar de
`data.aws_iam_policy_document` (sob `mock_provider` o data source devolve valor sintético e o
provider rejeita com *"contains an invalid JSON policy"*); a asserção das Pod Identities passou a
verificar `role_name` em vez de `role_arn`, que é ineliminavelmente *unknown* no plan;
`kubernetes_config_map` → `kubernetes_config_map_v1`; e a cláusula morta
`cidrsubnet("10.0.0.0/12", 4, 0) != null` saiu da validação de `vpc_cidr`.

**Versões conferidas nos repositórios, não herdadas:** ESO `2.9.0`, argo-cd `7.7.7` → **`10.4.0`**
(ArgoCD 3.5.1, atravessa um major), crossplane `2.3.1` → **`2.4.0`** do canal `stable` (o ArtifactHub
indexa `master`, que publica RCs). `aws/eks/scripts/install-crossplane` segue em `2.3.1` — trilha
k3d, atualização separada.

Destruída em seguida, como planejado. Custo atual zero.

### Camada 1 do Terraform (2026-08-25)

Bucket de state em raiz própria com `prevent_destroy`, desacoplado de qualquer região; uma raiz por
região com state key própria. Reuso do módulo entre regiões provado com um segundo hub em `us-west-2`
sem alterar uma linha de `src/network`. Isolamento verificado: `plan -destroy` de uma região não
alcança a outra nem o bucket.

### Frente A — contas (2026-08-24/25)

Vocabulário do whitepaper aplicado em doc, scripts e na Organization real. CloudTrail organizacional
+ conta `log-archive` + bucket de auditoria. SCPs baseline em Root/Security/Infrastructure/Workloads/
Deployments. Permission set de rotina da `log-archive` em `ReadOnlyAccess`. Break-glass documentado.
OU `Deployments` + conta `cicd` criadas e movidas, com deny de região comprovado na prática.

### Frente C — documentação (2026-08-24/25)

Domínio `tenancy/` a partir da SaaS Lens; `security/08-control-plane-identity.md`; correções na
família conta × região × papel; nomes de arquivo e H1 em inglês; hierarquia de fontes WAF →
whitepaper → SRA. A SaaS Lens confirma por escrito o que `decisions.md` §3 já havia derivado: mesmo
com recursos dedicados, um silo *"still relies on a shared identity, onboarding, and operational
experience"* — é isso que separa SaaS de *managed service*.

> Before trusting anything time-sensitive above, run `git status`, `git diff`, and `git log` against the base branch.
