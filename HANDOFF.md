# HANDOFF

> **Arquivo único.** Este repo NÃO usa `HANDOFF.local.md` — a divisão versionado/local foi desfeita
> em 2026-08-25, porque duplicava contexto e cada sessão tinha de reconciliar os dois. Frente ativa,
> estado aplicado e backlog vivem aqui. `HANDOFF.local.md` segue no `.gitignore` como rede de
> segurança; se aparecer um, é resíduo — consolidar aqui e apagar.
>
> **Account IDs desta Organization estão neste arquivo, deliberadamente.** São de uma conta pessoal
> descartável para exercitar a PoC; nada aqui vai para ambiente real. E-mails de root **não** entram
> (PII, e um handoff não precisa deles) — ficam em `CLAUDE.local.md`.
>
> **Repo público.** Não citar nomes de empresa, de projeto interno ou caminho de repo interno aqui
> nem em conversa. Dizer "a trilha corporativa". Lista de tokens proibidos em `CLAUDE.local.md`.

## Why

Exercitar a PoC AWS EKS-via-Crossplane (arquitetura de referência hub-and-spoke) na conta AWS pessoal
do Silvio, genérica, antes de qualquer ambiente corporativo. `aws/` foi genericizada a partir de um
exemplo interno (placeholders `<...>` para valores por-conta/segredos; valores genéricos concretos
como `platform.example.com`/`poc-eks` onde o token é YAML/Crossplane executável). Valores reais ficam
em `CLAUDE.local.md` (gitignored).

Topologia: **conta única no bootstrap → hub-and-spoke real via cross-account**. Rejeitado: CIDR fixo;
`<...>` em campos executáveis.

**Sequência de provisionamento vigente: −1 → 0 → 2 → 5** (`decisions.md` §8). A Fase 1 (Global
Accelerator + tenant registry) está **pulada**: escopo atual é só projetos internos, sem cliente
externo. Pular a Fase 1 **não** autoriza assumir região fixa — a indireção do §5 (nome sem região no
que o usuário vê, TTL curto de DNS, tenant na chave primária) continua obrigatória.

**Escopo do Terraform: fino.** Entrega VPC hub + VPC spoke + EKS + nodegroup + Pod Identity base +
ESO + ArgoCD + Crossplane core, e para. istio, cert-manager, external-dns, ALB controller e
zona/wildcard de DNS vêm por GitOps. Critério: cardinalidade × churn. Rejeitado: **paridade total** e
o padrão **seed cluster / hub-of-hubs** (`decisions.md` §7).

### Bifurcação de trilhas (2026-08-26)

A restrição de **concentrador de VPN a montante da AWS** (todas as conexões de cliente passam por um
concentrador corporativo; os CIDRs que chegam já vêm normalizados e sem colisão) pertence à trilha
corporativa e é explorada **fora deste repo**. As camadas Terraform daqui já foram levadas para lá,
com todo vocabulário local trocado por `PLACEHOLDER-*`, regressão offline verificada lá, e as duas
lacunas (TGW, tags de LBC) documentadas como ponto de entrada em vez de implementadas às cegas.

**Aqui não há concentrador.** O desenho assume `Site-to-Site VPN` por cliente. **Não importar
resposta de uma trilha para a outra** — a bifurcação existe para impedir isso.

## Vocabulário (ler antes de qualquer coisa)

"hub" cobria três eixos independentes e a ambiguidade custou tempo. Dois foram renomeados; só o
topológico mantém o termo:

| Eixo | Nome correto | Nome antigo |
|---|---|---|
| **Conta AWS** de conectividade | `network` — Connectivity Account, OU `Infrastructure` | "conta hub", profile `hub`, ProviderConfig `hub` |
| **Papel topológico** de rede | `hub` — único uso legítimo. Par de `spoke`; chart `platform/charts/hub`, VPC hub, TGW | (inalterado) |
| **Control plane** Crossplane (k3d) | **Control Plane** / `control-plane` | "hub k3d", `poc-eks-hub-config` |
| **Conta** do Control Plane | `cicd`, na OU `Deployments` | `platform` |

`network` é canônico no whitepaper *Organizing Your AWS Environment Using Multiple Accounts*, no AWS
SRA e no Landing Zone Accelerator. A AWS **não** nomeia contas como "Hub".

O chart `platform/charts/hub` **não** foi renomeado de propósito: ali "hub" é topologia, e `network`
colidiria com o XR `Network` que ele renderiza.

O prefixo `poc-idp/` no Secrets Manager (`poc-idp/crossplane-poc-credentials`) é o nome real de um
secret na AWS, não apelido do cluster — **não renomear**.

**`sandbox` não é ambiente de teste.** Está reservado para "conta de brincar, desconectada da rede".
O ambiente de teste é `<projeto>-nonprod` — e por isso a subzona de DNS decidida é `nonprod.`, não
`sandbox.`, apesar de os nomes de cluster de hoje usarem `sandbox.`.

**`cluster-zero` é da trilha Azure (AKS), pausada — não é o Control Plane da AWS.** No contexto AWS
nunca dizer "cluster zero". O plano `docs/superpowers/plans/2026-08-07-cluster-zero-terraform.md`
aponta para `infra/terraform/cluster-zero/README.md`, que **nunca existiu em nenhum branch** — é link
para artefato não construído, não doc desatualizada. Não apagar: é registro de desenho de outra
trilha.

**Hierarquia de fontes AWS:** **WAF** diz *por quê* isolar por conta e **nomeia zero contas e zero
OUs**; o **whitepaper** nomeia OUs (`Security`, `Infrastructure`, `Workloads`, `Sandbox`,
`Deployments`, …); o **SRA** nomeia contas (`Shared Services`, `Network`, …). Tabela em
`aws/docs/accounts/01-organizations-and-ous.md`.

## Estado aplicado na AWS

Snapshot de 2026-08-26. **Custo recorrente: só centavos.** Nada foi aplicado nesta sessão — foi
sessão de desenho.

| Camada | Conta | State key | Custo/mês | Estado |
|---|---|---|---|---|
| `state-backend` | `network` | `state-backend/` | centavos | aplicada |
| `network-foundation/us-east-1` | `network` | `network-foundation/us-east-1/` | **zero** | aplicada |
| `network-foundation/us-west-2` | `network` | `network-foundation/us-west-2/` | **zero** | aplicada |
| `control-plane` | `cicd` | `control-plane/` | ~US$ 165 quando de pé | **destruída** (state com 0 recursos) |

Bucket de state: `tfstate-o-e4r8ndteju`, na conta `network`. Nenhum cluster k3d de pé.

**Atenção para as próximas sessões:** o plano ativo introduz um nível **T1 que fica de pé de
propósito** (TGW + Client VPN, ~US$ 0,15/h ≈ US$ 110/mês). Quando existir, **não presumir resíduo e
destruir** — a regra "nada fica de pé entre sessões" passa a ter exceção declarada. Ele é derrubado
ao fim do dia, não ao fim da tarefa.

### Camada 1 — VPCs hub (custo recorrente zero)

| Região | VPC | CIDR | Subnets |
|---|---|---|---|
| `us-east-1` | `vpc-087a169b8e8dfc7d5`, tag `Name = poc-hub-vpc` | `10.1.0.0/16` | públicas `10.1.0.0/20`, `10.1.16.0/20`; privadas `10.1.32.0/20`, `10.1.48.0/20` |
| `us-west-2` | — | `10.3.0.0/16` | idem, derivadas por `cidrsubnet()` |

**Sem NAT Gateway em nenhuma das duas** — sem TGW nada roteia pelo hub, e um NAT custaria ~US$ 32/mês
servindo zero tráfego. **Isso muda quando o TGW entrar**, e o `2.2` do plano é onde a decisão volta.

### Camada 2 — Control Plane, quando aplicada (conta `cicd`, `us-east-1`)

Referência do último apply real, para reconhecer o padrão — **IDs de VPC/subnet mudam a cada apply**:
VPC spoke `10.2.0.0/16`; EKS `control-plane` Kubernetes **1.36**; 2× `t3.medium` `ON_DEMAND`; NAT
**ligado** (os nós dependem dele); charts ArgoCD `10.4.0`, ESO `2.9.0`, Crossplane `2.4.0` (canal
`stable`).

Roles de Pod Identity, na conta `cicd`: `control-plane-crossplane`
(`crossplane-system`/`crossplane`), `control-plane-external-secrets`
(`external-secrets`/`external-secrets`), `control-plane-ebs-csi`
(`kube-system`/`ebs-csi-controller-sa`). Mais `control-plane-cluster` e `control-plane-node` (roles do
EKS, não Pod Identity).

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

Fora do supernet, já reservados pelo plano ativo: `100.64.0.0/22` (client CIDR do Client VPN) e
`10.50.0.0/16` (VNet do cliente simulado no Azure).

## In Progress

### Frente D — acesso privado + ingress centralizado (ATIVA, nada implementado)

**Plano em `docs/superpowers/plans/2026-08-26-private-access-and-ingress/`** — **um arquivo por
fase**, para não encher o contexto:

| Arquivo | Conteúdo |
|---|---|
| `README.md` | decisões, numeração, níveis de permanência, fronteira de state, ordem, scripts transversais, custo, escopo |
| `01-preparation.md` | `1.1` tags do LBC · `1.2` `/32` na API · `1.3` raiz `dns/` |
| `02-private-access.md` | `2.1` portão do client · `2.2` `connectivity/` · `2.3` attachment · `2.4` DNS privado · `2.5` fechar a API |
| `03-ingress.md` | `3.1` NLB interno + gateway Istio · `3.2` lado hub com cert e listener rule |
| `04-isolation-proofs.md` | `4.1` e `4.2`, as duas provas negativas |

Ler o `README.md` mais a fase corrente — ~240 linhas em vez de 430. **Nenhuma decisão de desenho em
aberto; o que resta é executar.**

Numeração `fase.passo`; passo descoberto executando entra com **sufixo de letra** (`2.3a`) para não
empurrar os seguintes. Se uma fase passar de 9 passos, padronizar a fase inteira com dois dígitos.

**A descoberta que reordenou tudo:** o que prende o endpoint público da API do EKS **não é `kubectl`,
é o Terraform** — os providers `helm`/`kubernetes` falam com o API server a partir de onde o apply
roda. Acesso privado deixou de ser hardening no fim da fila e virou pré-requisito de operabilidade, e
o critério de aceite de fechar o endpoint (`2.5`) é **um apply completo com a VPN conectada**.

Decisões fechadas nesta frente:

1. **Ingress único, pelo hub.** Nenhuma spoke expõe acesso a si direto na internet — vale para
   qualquer entrada, logo VGW em spoke também está fora.
2. **`Site-to-Site VPN` por cliente**, terminando no TGW do hub. Um attachment por cliente ⟹ route
   table de tenant isola nas **duas** direções.
3. **Acesso de manutenção: AWS Client VPN no hub, autenticação SAML** pelo Identity Center. Escolhido
   sobre certificado mútuo porque **conceder e revogar acesso a uma pessoa é a demonstração**, e
   porque `access_group_id` dá **CIDR por grupo** — com certificado todo portador alcança tudo que
   estiver autorizado. Preço: o client da AWS no Linux é aplicação desktop, então `connect` não é
   scriptável.
4. **TGW + Client VPN de pé durante o dia, destruídos à noite.** Sem `prevent_destroy` neles.
5. **Fronteira de state segue o ciclo de vida, não a conta.**
6. **Ingress variante B:** ALB no hub → NLB interno na spoke (do Terraform, IPs fixados) → pods do
   `istio-ingressgateway`, que vira `ClusterIP` com `TargetGroupBinding`. Nada cruza conta em tempo
   de execução, só em provisionamento.
7. **Um wildcard de ACM por cluster**, `*.<id>.nonprod.<domínio>`, com validação por DNS e renovação
   automática. Encerra a emissão de certificado público por cluster pelo cert-manager, que fica só
   com o interno.
8. **Subzona `nonprod.` delegada ao Route 53 na conta `network`**, com a delegação **em código**
   (raiz `dns/` com providers `aws` + `azurerm`). O apex segue no Azure DNS.
9. **Cliente simulado do `4.2` no Azure**, VPN Gateway gerenciado active-active com BGP, numa raiz só
   (`azure/terraform/simulated-client/`) que contém **os dois lados do túnel**.

### Frente A — bootstrap de contas / Organization

Organization `o-e4r8ndteju`, root `r-f11d`, região de trabalho `us-east-1`.

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
`us-west-2`. CloudTrail organizacional `organization-trail` + bucket `cloudtrail-<organization-id>` na
`log-archive` (BPA, versionamento, SSE-S3, `BucketOwnerEnforced`, deny non-TLS), < US$ 1/mês.

**Ordem que funcionou melhor que a documentada:** aplicar a SCP na OU **antes** de criar a conta nela.
Não elimina a janela Root→OU, encurta. Os scripts são idempotentes.

**Aprovar região é `--regions` e vale para a Organization inteira.**
`./apply-baseline-service-control-policy --regions <r1>,<r2>` reescreve `DenyOutsideApprovedRegions`
em todos os targets — não há como liberar região só numa conta por essa via. Sem isso um
`terraform apply` fora das regiões aprovadas falha no primeiro `Create*` com
`explicit deny in a service control policy`, e o erro parece bug de código. **Comprovado.**

**Passo ⑦ parcial.** Identity Center (IDs em `CLAUDE.local.md`): `management` com
`AdministratorAccess` num **usuário nominal** (deveria ser grupo); `log-archive` com `ReadOnlyAccess`
no grupo `platform-admins`; `Network`, `wasp-nonprod` e `cicd` **sem permission set** — acesso só por
`OrganizationAccountAccessRole`.

**O Identity Center vira dependência dura do plano ativo:** o `2.2` exige uma aplicação SAML
customizada nele, e as authorization rules do Client VPN referenciam **IDs de grupo**. Grupos
previstos: `platform-admins` (já existe) e `cliente-a` (a criar no `4.1`).

### Frente B — Terraform e Crossplane / EKS

**Camadas 1 e 2 escritas, aplicadas e verificadas.** Um `terraform apply`, **39 recursos**, ~13 min,
**sem `-target`** — providers `kubernetes`/`helm` configurados a partir de outputs do módulo do
cluster resolvem na hora do apply. O que quebraria é **data source** desses providers no plan; por
isso o `platform-bootstrap` tem de continuar sendo `resource`.

Três scripts em `aws/terraform/control-plane/scripts/`:

| Script | O que faz |
|---|---|
| `generate-tfvars` | Descobre na AWS o que a camada precisa e gera o `terraform.tfvars`. **Só leitura.** Valida antes de gerar arquivo: tag da VPC hub univoca, CIDR livre, região aprovada na SCP, bucket existente |
| `apply` | `plan` → confirma → aplica → guarda log com timestamp em `logs/` |
| `destroy` | Confere Crossplane sem recurso vivo e contexto kubectl correto → destrói → guarda log |

Os dois últimos leem o exit code por `PIPESTATUS[0]`: o `tee` sempre retorna 0, e sem isso um apply
que falhou passaria por sucesso.

#### Trilha k3d (cross-account + Fase 4)

Pronta e validada offline; é a trilha que o Terraform vem substituir.

- **ProviderConfigs por conta:** `network` (credencial direta) e `wasp-nonprod` (assumeRoleChain,
  `${SPOKE_ACCOUNT_ID}` via envsubst). **Sem PC `default`** — falha-fechado.
- **Role `crossplane-wasp-nonprod`** na conta `wasp-nonprod`: trust p/ `crossplane-poc` da `Network`
  + PowerUserAccess + inline `CrossplaneEksRoleManagement`. Assume validado com creds reais.
- **Identidade = `metadata.name`** (Crossplane v2, sem `spec.id`). `providerConfigName` OBRIGATÓRIO,
  enum `[network, wasp-nonprod]`.
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
prospectivo**. `network/03-transit-gateway-isolation.md`, `network/04-vpn-access.md` e o domínio
`dns/` inteiro já prescrevem o que o plano ativo implementa.

## O que a comparação com o desenho de referência ensinou (2026-08-26)

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

## Ingress: PrivateLink vs TGW — resolvido

O spec `docs/superpowers/specs/2026-08-25-private-ingress-via-privatelink.md` continua **válido na
fundamentação** (a citação do whitepaper que separa PrivateLink de TGW por tipo de conectividade), mas
a escolha foi **reaberta e resolvida a favor do TGW** para o caminho hub→spoke: com VPN de cliente
decidida, o TGW entra de qualquer forma e o custo marginal de usá-lo também no ingress cai a zero.

**PrivateLink não morre.** Volta como candidato natural na fatia de **spoke de recursos
compartilhados** (banco, mensageria), onde CIDR sobreposto e autorização por principal de conta valem
dinheiro — ao contrário do caso de ingress, onde não usamos nenhum dos dois.

O que continua válido do spec: o NLB fica na **spoke** (o PrivateLink exige NLB no lado provedor, a
AWS não aceita ALB ali); provar conectividade de dentro antes de expor; e o hub não tem compute
nenhum hoje.

## Open Questions / Hypotheses

- **Conflação em `decisions.md` §2:** a spoke de plataforma roda *"auth, discovery, ArgoCD,
  Crossplane"*. `auth` e `discovery` são runtime de aplicação **no caminho da requisição** — não são
  build/validate/promote/release, logo não pertencem a uma conta de CI/CD pela definição da própria
  OU. Mesmo eixo da decisão 6 do §11; resolver junto.
- **Teto do plano de CIDR: 15 spokes**, e **região multiplica** — 10 tenants em 2 regiões estoura.
  Quatro caminhos em `aws/docs/network/01-cidr-addressing.md`. Única decisão irreversível.
- **Teto de 25 certificados por ALB** (excluindo o default) e 100 rules, ambos ajustáveis por Service
  Quotas. O certificado aperta primeiro ⟹ 25 clientes por ALB. Mesma família do teto de CIDR: saber
  antes de prometer escala.
- **Session tags em `assumeRoleChain`:** a contenção regional por
  `aws:RequestedRegion` = `aws:PrincipalTag/region` depende de o provider-aws propagar tags de sessão.
  **Não verificado.** Se não propagar, a condição nunca casa e tudo é negado.
- **Client da AWS VPN no Linux** — é o portão `2.1` do plano. Se não rodar nesta distro, três saídas
  escritas lá; a terceira (certificado mútuo) custa a demo de conceder/revogar.
- **Zona privada do endpoint do EKS** não é output do `aws_eks_cluster` e é recriada a cada provisão —
  o lookup por hostname é frágil. Plano B (Resolver inbound endpoint) custa ~US$ 0,25/h. Risco do
  `2.4`.
- **Parametrizar** valores de `CLAUDE.local.md` (chart values? env? EnvironmentConfig?).
- **Rework do orquestrador `environment/`** (BLOCKED): sob `metadata.name`, filhos compostos ganham
  nome hasheado → o cruzamento por label compartilhado não funciona. Conserto desenhado em
  `resources/examples/topology/05-07`. Adiado. `compute/06-crossplane-map.md` registra o alvo:
  **remover `Environment`; `Cluster` é o topo**.
- **`tenancy/04-crossplane-map.md` não escrito de propósito** — depende do schema do registry de
  tenants (§11 decisão 1).
- **Retenção do bucket de auditoria** (lifecycle → Glacier, expiração): decisão de compliance adiada.
  É o único custo do CloudTrail que cresce sozinho e para sempre.
- **Conta `security-tooling`** desenhada como slot, não criada — vira pré-requisito quando
  GuardDuty/Config/Security Hub entrarem.
- **Contas `Monitoring` / `Operations Tooling`** (OU `Infrastructure`) são os slots canônicos da
  observabilidade centralizada; nenhuma existe.
- **Trilha Azure pausada ganhou destino:** `azure/terraform/simulated-client/` cria o slot
  `azure/terraform/`, onde `cluster-zero` pode aterrar depois.

## Known Broken

1. **`src/network` não aplica as tags de descoberta do AWS Load Balancer Controller** — *unexpected*:
   falta `kubernetes.io/role/elb` nas públicas e `kubernetes.io/role/internal-elb` nas privadas. Sem
   elas o LBC não encontra onde criar load balancer, e o sintoma é obscuro. **É o passo `1.1`.**
2. **`src/network` não tem nada de TGW** — *intentional* até a decisão de VPN; agora é lacuna: falta
   attachment, associação/propagação em `tgw-rt-<spoke>` e rotas para CIDRs remotos. **É o `2.3`.**
3. **Endpoint da API do EKS público para `0.0.0.0/0`** quando a camada 2 está de pé — *intentional*:
   `public_access_cidrs = []` (vazio significa o mundo). **Mitigação barata é o `1.2`** (`/32`);
   fechar de vez é o `2.5`, e depende de VPN + DNS.
4. **Break-glass documentado, controles ausentes** — *unexpected*: MFA no root da management account e
   das contas-membro **não verificado**; alarme de uso de root **não existe** (CloudTrail já captura,
   falta a regra EventBridge); ensaio nunca executado.
5. **Management account com `AdministratorAccess` atribuído a usuário, não a grupo** — *unexpected*:
   viola a própria regra `--group` da doc, na conta mais privilegiada. Migrar para `platform-admins`
   (atribuir o grupo **antes** de revogar o usuário).
6. **Credencial-raiz do Crossplane é access key de longa duração** — *intentional*: contraria
   [SEC02-BP02](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/sec_identities_unique.html).
   Sobrevive **só na trilha k3d**, que não suporta Pod Identity — no EKS o pod subiu com
   `AWS_CONTAINER_CREDENTIALS_FULL_URI`, sem access key. **Mitigação não aplicada:** reduzir o IAM
   user a só `sts:AssumeRole`; hoje tem `PowerUserAccess` direto.
7. **`bootstrapClusterCreatorAdminPermissions` divergente** — *unexpected*: `true` na camada 2,
   `false` no cluster do chart Crossplane. Herdado de caminhos diferentes, não decidido.
8. **VPC default da `cicd` de pé em toda região**, com security group aberto — *unexpected*, e há
   workload real na conta quando a camada 2 sobe.
9. **Link quebrado em `docs/superpowers/plans/2026-08-07-cluster-zero-terraform.md`** →
   `infra/terraform/cluster-zero/README.md` — *intentional*: artefato da trilha Azure nunca
   construído.
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
    Regra: policy document via `jsonencode`. **Auditar se há outro lugar no repo com a mesma
    armadilha.**

## How to Resume

**Custo hoje é zero.** Confirmar antes de confiar:

```bash
cd wasp-idp/aws/terraform/control-plane
terraform state list | wc --lines   # 0 = destruída; 39 = de pé (~US$ 0,23/h)
k3d cluster list                    # esperado: vazio
```

Branch de trabalho: `feat/private-ingress-privatelink`.

**O trabalho ativo é executar o plano, começando pelo `1.1`** — offline, grátis, com `terraform test`
de aceite:

```bash
code docs/superpowers/plans/2026-08-26-private-access-and-ingress/README.md
code docs/superpowers/plans/2026-08-26-private-access-and-ingress/01-preparation.md
```

Se for preciso subir a camada 2 para experimentar:

```bash
cd aws/terraform/control-plane
./scripts/generate-tfvars --force
terraform init -backend-config="bucket=tfstate-o-e4r8ndteju"
./scripts/apply
```

`terraform apply`/`destroy` rodam por `! <comando>` — o classifier de auto-mode bloqueia para o
agente. O `apply` sem tty falha de propósito, informando o caminho do plano salvo; usar `--yes` quando
não houver terminal. O mesmo vale para os scripts de `aws/docs/accounts/scripts/` que criam recursos
reais.

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

Pré-requisitos: VPN corporativa **desconectada** (senão o pull de `xpkg.upbound.io` falha com `x509` e
depois `connection reset`) e SSO admin ativo (`aws sso login --profile personal`).

### Achados a não reaprender

**Terraform / camadas**

- **A referência funcional do provisionamento EKS são as Compositions Crossplane**, não as fases do
  chart `aws/eks/chart/templates/`.
- **As ~40 `ClusterUsage` do teardown ordenado não têm tradução em Terraform** — são aresta de
  dependência construída à mão. Terraform destrói em ordem reversa nativamente, **mas só se rede e
  cluster estiverem no mesmo state** — por isso o corte é `hub | spoke+cluster`, nunca `rede |
  cluster`.
- **O corte `hub | spoke+cluster` sobrevive ao TGW** (item que estava aberto desde a camada 2): o
  egress da spoke continua saindo pelo NAT dela (`0.0.0.0/0` não passa a apontar para o TGW), e a AWS
  **recusa deletar TGW com attachment vivo** — proteção da API, não de convenção. **Cai** se um dia
  houver egress centralizado pelo hub.
- **EBS CSI pertence à abstração `Cluster` (L2b)**, ao lado do `eks-pod-identity-agent`.
- Trust de Pod Identity exige `sts:TagSession` além de `sts:AssumeRole`.
- `authentication_mode = "API"` — sem `aws-auth` ConfigMap.
- A `Network` de referência tem as 4 subnets **hardcoded** em `172.16.{1,2,3,4}.0/24`. **Não herdar.**
- **A race de Pod Identity do EBS CSI não existe no Terraform** — o grafo já ordena addon depois da
  association.
- **Nunca fixar versão de Kubernetes (nem de chart, nem de addon) em documento de plano.** O
  `generate-tfvars` descobre.

**Load balancer e TLS**

- **`TargetGroupBinding` aceita target group criado fora do controller** — a doc do LBC descreve
  provisionar o LB *"completely outside of Kubernetes"*. `networking.ingress` é o campo que faz o
  controller cuidar das regras de SG para targets IP. Logo **Terraform pode ser dono do NLB sem
  quebrar o apply único**.
- **Ler IPs privados de NLB é frágil** — `aws_lb` não os expõe. **Fixar** com
  `subnet_mapping { private_ipv4_address = cidrhost(...) }`.
- **O ALB só lê certificado do ACM**, nunca Secret do Kubernetes. E **não valida certificado de
  backend** — no trecho ALB→NLB→gateway, autoassinado basta.
- **Wildcard cobre um nível só e `*.*.` não existe** — daí ser um wildcard por cluster.
- **Um NLB por cluster, não por Service** — o fan-out por aplicação acontece no mesh, de graça. E o
  hub escala **por listener rule**, também de graça.
- **`X-Forwarded-For` + `numTrustedProxies`**: com ALB na frente, o Istio vê o IP do ALB.

**Rede / VPN**

- **TGW nasce com association/propagation default LIGADOS** — desligar os dois é o que torna
  isolamento por tenant possível.
- **TGW entrega roteamento IP, não resolução de nome.**
- **Route table por spoke não isola cliente de cliente** — é preciso route table **por cliente**
  também.
- **Client VPN com SAML exige o client da AWS**; **cert de servidor é obrigatório em qualquer tipo de
  autenticação**; `memberOf` tem de carregar **IDs** de grupo, não nomes; **nunca**
  `authorize_all_groups = true`.
- **`client_cidr_block` precisa de /22 ou maior**, sem sobreposição — daí `100.64.0.0/22`.
- **Azure VPN Gateway leva 30–45 min para provisionar**; a subnet tem de se chamar literalmente
  `GatewaySubnet`; ASN do lado Azure é **65515**; inside CIDRs em `169.254.21.0–169.254.22.255`, `/30`
  cada.
- **Raiz com dois providers de cloud:** sem credencial do segundo, o `plan` falha mesmo para mudança
  que só toca o primeiro. Guardar atrás de `local.manage_*`.

## Next Steps

### Frente D — executar o plano (prioridade)

- [x] Plano completo, sem decisão de desenho em aberto, um arquivo por fase.
- [ ] **`1.1`** — tags `kubernetes.io/role/{elb,internal-elb}` em `src/network`. Offline, grátis,
      `terraform test` de aceite. **É por aqui que se começa.**
- [ ] **`1.2`** — `generate-tfvars` descobre o IP público → `public_access_cidrs = ["<ip>/32"]`.
- [ ] **`1.3`** — raiz `aws/terraform/dns/`: hosted zone `nonprod.` + delegação NS no Azure.
- [ ] **`2.1` (PORTÃO)** — verificar o client da AWS VPN nesta distro **antes** de criar recurso que
      cobra.
- [ ] **`2.2`–`2.5`** — `connectivity/`, attachment, DNS privado, fechar a API.
- [ ] **`3.1`–`3.2`** — NLB interno + gateway Istio; depois lado hub com cert e listener rule.
- [ ] **`4.1`–`4.2`** — as duas provas negativas.
- [ ] Criar `aws/terraform/scripts/` com `vpn` e `platform-status` (não existe ainda).
- [ ] Abrir branch dedicada em `wasp-gitops` para os manifestos do lado cluster; path interno decidido
      na implementação.

### Frente B — Terraform + Crossplane / EKS

- [ ] Decidir `bootstrapClusterCreatorAdminPermissions`: `true` (camada 2) ou `false` (chart).
- [ ] Ligar NAT no hub quando o TGW entrar — a decisão de deixá-lo desligado valia só sem TGW.
- [ ] Escrever o design do script `follow` determinístico (ganha spec própria).
- [ ] Reduzir o IAM user `crossplane-poc` a só `sts:AssumeRole`.
- [ ] Definir estratégia de parametrização dos valores de `CLAUDE.local.md`.

### Frente A — contas

- [ ] Criar o grupo `cliente-a` no Identity Center (pré-requisito do `4.1`).
- [ ] Atribuir permission set à conta `cicd` — nasceu sem nenhum.
- [ ] Atribuir permission set a `Network` e `wasp-nonprod`
      (`./assign-permission-set --account <conta> --group platform-admins`).
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

### Desenho de acesso privado e ingress — plano fechado (2026-08-26)

Frente inteira desenhada e escrita como plano executável em quatro fases, sem decisão de desenho em
aberto. Ordem descoberta, não presumida: o acesso privado subiu para antes do ingress quando ficou
claro que **quem fala com o API server é o Terraform**, não o operador.

Nove decisões fechadas — ingress único pelo hub, VPN por cliente, Client VPN com SAML, T1 permanente
durante o dia, fronteira de state por ciclo de vida, ingress variante B, wildcard de ACM por cluster,
subzona `nonprod.` com delegação em código, e cliente simulado no Azure com os dois lados do túnel
numa raiz só.

Quatro achados que mudaram o rumo:

- **O desenho de referência não tem ingress no hub** — o hub dele é trânsito puro, sem VPC. Ingress
  centralizado ficou sem precedente interno, e a decisão foi tomada sabendo disso.
- **Route table de tenant só isola nas duas direções se o attachment for por cliente.** Com attachment
  agregado, a entrada depende de security group — uma camada, a mais interna.
- **`TargetGroupBinding` aceita target group externo**, o que permite Terraform ser dono do NLB sem
  quebrar o apply único.
- **O ALB não lê Secret do Kubernetes**, o que move o certificado público do cert-manager para o ACM e
  encerra a emissão por cluster.

Fechou também o item aberto desde a camada 2: **o corte `hub | spoke+cluster` sobrevive ao TGW**.

### Port das camadas Terraform para a trilha corporativa (2026-08-26)

Árvore `aws/terraform/` levada para lá numa branch própria: 8 módulos de `src/` sem alteração, três
raízes, scripts, testes, mais README, CLAUDE.md e spec de desenho adaptados. Todo vocabulário local
trocado por `PLACEHOLDER-*`; zero account id, zero nome de bucket, zero nome de conta daqui.
Regressão offline verificada **lá**: 43 testes em 10 diretórios, 0 falhas. As duas lacunas (TGW e tags
de LBC) foram deixadas documentadas como ponto de entrada, não implementadas às cegas.

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
carrega account id ou VPC id hardcoded. **O plano ativo acrescenta a chave `ingressTargetGroupArn` a
esse contrato.**

**Quatro correções ao plano exigidas pelos próprios testes:** `jsonencode` no lugar de
`data.aws_iam_policy_document` (sob `mock_provider` o data source devolve valor sintético e o provider
rejeita); a asserção das Pod Identities passou a verificar `role_name` em vez de `role_arn`, que é
ineliminavelmente *unknown* no plan; `kubernetes_config_map` → `kubernetes_config_map_v1`; e a
cláusula morta `cidrsubnet("10.0.0.0/12", 4, 0) != null` saiu da validação de `vpc_cidr`.

**Versões conferidas nos repositórios, não herdadas:** ESO `2.9.0`, argo-cd `7.7.7` → **`10.4.0`**
(atravessa um major), crossplane `2.3.1` → **`2.4.0`** do canal `stable`.

### Camada 1 do Terraform (2026-08-25)

Bucket de state em raiz própria com `prevent_destroy`, desacoplado de qualquer região; uma raiz por
região com state key própria. Reuso do módulo entre regiões provado com um segundo hub em `us-west-2`
sem alterar uma linha de `src/network`. Isolamento verificado: `plan -destroy` de uma região não
alcança a outra nem o bucket.

### Frente A — contas (2026-08-24/25)

Vocabulário do whitepaper aplicado em doc, scripts e na Organization real. CloudTrail organizacional +
conta `log-archive` + bucket de auditoria. SCPs baseline em Root/Security/Infrastructure/Workloads/
Deployments. Permission set de rotina da `log-archive` em `ReadOnlyAccess`. Break-glass documentado.
OU `Deployments` + conta `cicd` criadas e movidas, com deny de região comprovado na prática.

### Frente C — documentação (2026-08-24/26)

Domínio `tenancy/` a partir da SaaS Lens; `security/08-control-plane-identity.md`; correções na
família conta × região × papel; nomes de arquivo e H1 em inglês; hierarquia de fontes WAF →
whitepaper → SRA. Nesta sessão, os `CLAUDE.md` de `network/`, `dns/` e `terraform/` ganharam as
armadilhas descobertas no desenho.

A SaaS Lens confirma por escrito o que `decisions.md` §3 já havia derivado: mesmo com recursos
dedicados, um silo *"still relies on a shared identity, onboarding, and operational experience"* — é
isso que separa SaaS de *managed service*.

> Before trusting anything time-sensitive above, run `git status`, `git diff`, and `git log` against the base branch.
