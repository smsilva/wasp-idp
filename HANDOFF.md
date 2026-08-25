# HANDOFF

## Why

Exercitar a PoC AWS EKS-via-Crossplane (arquitetura de referência hub-and-spoke) na conta
AWS pessoal do Silvio, genérica, antes de qualquer ambiente corporativo. `aws/` foi copiada
de um exemplo interno e genericizada (placeholders `<...>` para valores por-conta/segredos;
valores genéricos concretos como `platform.example.com`/`poc-eks` onde o token é YAML/
Crossplane executável). Valores reais ficam em `CLAUDE.local.md` (gitignored).

Topologia decidida: **conta única no bootstrap → hub-and-spoke real via cross-account**. O
Crossplane roda no **Control Plane** (k3d) autenticando como o IAM user da conta `network`, e
provisiona VPC+EKS numa conta **spoke** (não na `network`, que é só rede/conectividade) via
ProviderConfig com `assumeRoleChain`. TGW real adiado (Gap 2 — migração futura aditiva).
Rejeitado: TGW agora; CIDR fixo; `<...>` em campos executáveis.

**Sequência de provisionamento vigente: −1 → 0 → 2 → 5** (`decisions.md` §8). A Fase 1
(Global Accelerator + tenant registry) está **pulada**: escopo atual é só projetos internos,
sem cliente externo. Pular a Fase 1 **não** autoriza assumir região fixa — a indireção do §5
(nome sem região no que o usuário vê, TTL curto de DNS, tenant na chave primária) continua
obrigatória.

**Alvo do próximo trabalho de código: módulo Terraform que substitui o bootstrap feito hoje
pelo k3d.** Escopo **fino** decidido: Terraform entrega VPC hub + VPC spoke + EKS + nodegroup
+ Pod Identity base + **ESO** + ArgoCD + Crossplane core, e para. istio, cert-manager,
external-dns, ALB controller e route53 zone/wildcard vêm por GitOps. Critério: cardinalidade ×
churn — Terraform para o que se cria uma vez por região, GitOps para o que muda toda semana.
Rejeitado: **paridade total** (Terraform instalando os addons, como faz o exemplo Azure de
referência) e o padrão **seed cluster / hub-of-hubs** (`decisions.md` §7 — cria dependência de
disponibilidade e não elimina o Terraform, só o esconde).

**Fronteira do ArgoCD RESOLVIDA (2026-08-25).** ArgoCD sobe **sem ingress** (`ClusterIP` +
`port-forward`); **ESO entra** no Terraform; o trio DNS fica fora. A binária original estava
mal-posta: o que destrava OIDC é o **ESO** (entregador do client secret, como no exemplo Azure,
via merge de `ExternalSecret` em `argocd-secret`), e ESO **não depende de DNS**. A única peça do
OIDC que exige o trio é a URL — e `http://localhost` é exceção aceita pelo Google, caminho que
este repo já prova com o Backstage em `:7007`. Design completo em
`docs/superpowers/specs/2026-08-25-terraform-bootstrap-module-design.md`.

**O pré-requisito da Frente B foi cumprido (2026-08-25):** a OU `Deployments` e a conta `cicd`
**existem na AWS**, com SCP baseline herdada e profile local validado. O módulo põe o EKS de
plataforma nela, e mover EKS entre contas seria rebuild — por isso a conta tinha de vir antes do
primeiro `terraform apply`. Veio.

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
`network` colidiria com o XR `Network` que ele renderiza. Chart `hub` → conta `network`.

O prefixo `poc-idp/` no Secrets Manager (`poc-idp/crossplane-poc-credentials`) é o nome real
de um secret na AWS, não apelido do cluster — **não renomear**.

**`cluster-zero` é da trilha Azure (AKS), pausada — não é o Control Plane da AWS.** No contexto
AWS nunca dizer "cluster zero". O plano `docs/superpowers/plans/2026-08-07-cluster-zero-terraform.md`
aponta para `infra/terraform/cluster-zero/README.md`, que **nunca existiu em nenhum branch** —
é link para artefato não construído, não doc desatualizada. Não apagar: é registro de desenho
de outra trilha.

**Hierarquia de fontes AWS** (confundi-las já produziu claim sem fonte no repo): **WAF** diz
*por quê* isolar por conta e **nomeia zero contas e zero OUs**; o **whitepaper** nomeia OUs
(`Security`, `Infrastructure`, `Workloads`, `Sandbox`, `Deployments`, …); o **SRA** nomeia
contas (`Shared Services`, `Network`, …). Tabela em `aws/docs/accounts/01-organizations-and-ous.md`.

## In Progress

### Frente A — bootstrap de contas / Organization

Objetivo: percorrer a sequência de provisionamento passo a passo, corrigindo doc e scripts
contra o whitepaper AWS conforme cada passo é executado de verdade. **Regra adotada: sempre
manter o vocabulário de "Organizing Your AWS Environment Using Multiple Accounts"; divergir só
com motivo registrado.**

Forma da Organization, inspecionada na API. **Account IDs, OU IDs e e-mails ficam em
`CLAUDE.local.md`** — este arquivo é versionado e a convenção do repo é não carregar valor real.

```
Root
├── ACC  <management>                        (management — não hospeda nada; SCP não a afeta)
├── OU   Security
│   └── ACC  log-archive
├── OU   Infrastructure
│   └── ACC  Network                         (Connectivity Account)
├── OU   Deployments
│   └── ACC  cicd                            (Control Plane — Crossplane + ArgoCD)
└── OU   Workloads
    ├── OU   NonProd
    │   └── ACC  wasp-nonprod
    └── OU   Production                      (vazia)
```

Conferir o estado real a qualquer momento:

```bash
AWS_PROFILE=personal aws organizations list-roots --query 'Roots[0].Id' --output text
AWS_PROFILE=personal aws organizations list-accounts \
  --query 'Accounts[].{Name:Name,Status:Status}' --output table
```

**A OU `Deployments` e a conta `cicd` foram criadas em 2026-08-25** pelos scripts do repo, nesta
ordem: `create-organizational-unit-structure` → `apply-baseline-service-control-policy` (para a
OU já ter guardrails quando a conta chegasse) → `create-account`. A conta nasce na Root e é
movida; a SCP da OU não vale nessa janela, e aplicá-la antes é o que encurta a exposição.

Profile local `cicd` acrescentado ao `~/.aws/config` (backup em `~/.aws/config.bak-20260825`),
assume de `OrganizationAccountAccessRole` validado. **SCP comprovada na prática, não presumida:**
`ec2:DescribeVpcs` em `us-west-2` volta com deny explícito de `DenyOutsideApprovedRegions`, e em
`us-east-1` funciona.

Pendências da conta nova: **sem permission set** no Identity Center (acesso só por switch-role) e
**VPC default em toda região**, como qualquer conta nova — a spoke do Terraform é separada, e a
default fica como candidata a limpeza (security group default aberto).

**Passos ①–⑥ concluídos.** SCPs baseline verificadas em todos os targets:

| Target | SCPs (além de `FullAWSAccess`) |
|---|---|
| Root | `DenyLeaveOrganization`, `ProtectCloudTrail` |
| `Security` | `DenyOutsideApprovedRegions`, `RequireImdsv2`, `DenyRootUser` |
| `Infrastructure` | idem |
| `Workloads` | idem (herdado por `NonProd`/`Production`) |
| `Deployments` | idem (anexadas em 2026-08-25, antes da conta `cicd` chegar) |

Região aprovada: `us-east-1`. CloudTrail organizacional `organization-trail` (multi-region,
log file validation) + bucket `cloudtrail-<organization-id>` na `log-archive` (BPA, versionamento,
SSE-S3, `BucketOwnerEnforced`, deny non-TLS). Custo estimado **< US$ 1/mês**.

**Passo ⑦ parcial.** Identity Center (IDs da instância e do identity store em `CLAUDE.local.md`):

```
management     AdministratorAccess  usuário nominal     <- deveria ser grupo
log-archive    ReadOnlyAccess       grupo platform-admins
Network        (nenhuma — só OrganizationAccountAccessRole)
wasp-nonprod   (nenhuma — idem)
cicd           (nenhuma — idem; nasceu assim em 2026-08-25)
```

Break-glass ([SEC03-BP03 — Establish emergency access process](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/sec_permissions_emergency_process.html))
documentado em `aws/docs/accounts/04-cross-account-access.md`; controles (MFA no root, alarme
de uso) pendentes.

E-mail do root da `Network` migrado de `+hub@` para `+network@` (fluxo de root no console —
**não existe API** para isso; `put-account-name` muda só o nome).

**Novo passo ⑤b na sequência:** criar a conta `cicd` na OU `Deployments`. Uma conta só, tratada
como produção — o whitepaper recomenda rodar CI/CD em *"production deployment accounts"*, então
**não existe `cicd-nonprod`**. Contas da OU `Infrastructure` também não têm variante de
ambiente, por recomendação explícita do whitepaper.

### Frente B — Crossplane / EKS

Cross-account + Fase 4 (split de charts + identidade) prontos e validados offline:

- **ProviderConfigs por conta:** `network` (credencial direta, `provider-config-network.yaml`,
  aplicado por `configure-aws-creds`) e `wasp-nonprod` (assumeRoleChain,
  `provider-config-wasp-nonprod.yaml` com `${SPOKE_ACCOUNT_ID}` via envsubst, aplicado por
  `configure-account-access`). Sem PC `default` — falha-fechado.
- **Role `crossplane-wasp-nonprod`** na conta `wasp-nonprod`: trust p/ `crossplane-poc` da
  `Network` + PowerUserAccess + inline `CrossplaneEksRoleManagement`. Assume validado com as
  creds reais do `crossplane-poc`. Substituiu `crossplane-sandbox` (recriada — IAM não
  renomeia in-place; a antiga foi removida).
- **Identidade = `metadata.name`** (Crossplane v2, sem `spec.id`): external-names e label `env`
  derivam dele. Spoke e cluster compartilham o `metadata.name`. `providerConfigName`
  OBRIGATÓRIO, enum `[network, wasp-nonprod]`.
- **Charts `aws/platform/charts/{hub,spoke,cluster}`**: um release por célula. Helper
  `aws/eks/scripts/random-id` (5 chars).
- **Control Plane renomeado:** default `--cluster-name` = `control-plane` (contexto
  `k3d-control-plane`) em 8 scripts; `EnvironmentConfig` `control-plane-config` com label
  `platform.example.com/control-plane`.

O ciclo real já foi provado antes do rename (com o chart antigo): `helm install` criou VPC
`10.1.0.0/16`+NAT, `helm uninstall` destruiu tudo (teardown limpo AWS-side). Orquestrador
`environment/` marcado BLOCKED (incompatível com `metadata.name`; rework = sketches
`resources/examples/topology/05-07`).

**Custo atual: zero.** Nenhuma VPC/EKS de pé. Cadeia renomeada validada ponta a ponta
(2026-08-24) recriando o Control Plane do zero: 8 providers `Healthy`, 4 functions `Healthy`,
XRDs `network`/`cluster` `Established`, ProviderConfigs sem resíduo de nome antigo.

**Achado da validação:** `install-crossplane` nascia com `--servers 3` (default herdado do
track Azure, que só documentava lentidão) e neste host (8 cores) isso quebrava o **quorum do
etcd** — crash-loop persistente, não simples atraso. Fix: `--servers 1`; providers `Healthy` em
~4 min sem restart. Default do script alterado. Ver `aws/CLAUDE.md`.

**Divergência conhecida entre implementação e alvo:** hoje o chart `platform/charts/hub`
renderiza um XR `Network` — o hub VPC é criado **por Crossplane a partir do k3d**, não por
Terraform como a Fase 2 prescreve. Interpretação adotada: degrau de bootstrap consciente. É
justamente essa divergência que o módulo Terraform vem fechar.

### Frente C — documentação de arquitetura (`aws/docs/`)

Oito domínios: `bootstrap`, `network`, `accounts`, `security`, `dns`, `compute`,
`observability`, `tenancy`. Os sete primeiros descrevem estado real ou alvo próximo;
**`tenancy/` é puramente prospectivo** — desenho, nada aplicado numa conta.

Adicionado nesta sessão:

- **Domínio `tenancy/`** a partir da [SaaS Lens](https://docs.aws.amazon.com/wellarchitected/latest/saas-lens/saas-lens.html)
  (lens oficial do WAF, pub. 2023-04-04): modelos silo/pool/bridge, conta por tenant, OU por
  geografia, teto do CIDR.
- **`security/08-control-plane-identity.md`**: com N control planes regionais são **1 role de
  origem por control plane** (Pod Identity) + **1 role de destino por conta-alvo** (IAM é
  global) + **zero** para o EKS de workload gerenciado.
- **Correções de afirmações erradas**, todas na família conta × região × papel: `accounts/00`
  dizia que a conta de conectividade é "1 por região" (é uma só, global); a mesma tabela
  contradizia a decisão de conta por projeto **por ambiente** e omitia o papel de control
  plane; `security/04` tratava control plane em EKS como hipótese; `security/CLAUDE.md` dizia
  "sem roles cross-account (conta única)" quando a role já existia e estava validada.
- **Claim sem fonte corrigido:** `aws/CLAUDE.md` afirmava que automação moraria numa
  `shared-services`; o SRA define essa conta como AD/messaging/metadata (serviços que times
  *consomem*). Orquestração de deploy é a OU `Deployments` do whitepaper.
- Nomes de arquivo e H1 migrados para inglês; corpo segue pt-BR. Slot
  `Infrastructure/shared-services` removido da árvore (pré-existente, vazio, especulativo).

**A SaaS Lens confirma por escrito uma regra que `decisions.md` §3 já havia derivado sozinho:**
mesmo com recursos dedicados, um silo *"still relies on a shared identity, onboarding, and
operational experience"* — é isso que, segundo a AWS, separa SaaS de *managed service*.

## Open Questions / Hypotheses

- **Conflação em `decisions.md` §2:** a spoke de plataforma roda *"auth, discovery, ArgoCD,
  Crossplane"*. `auth` e `discovery` são runtime de aplicação **no caminho da requisição** —
  não são build/validate/promote/release, logo não pertencem a uma conta de CI/CD pela
  definição da própria OU. Se ficarem lá, a conta deixa de ser `Deployments`. Mesmo eixo da
  decisão 6 do §11 (escopo do identity layer); resolver junto.
- **Em qual conta fica a hosted zone pública** (`network` ou `cicd`): o whitepaper põe Route 53
  Resolver na `network`; zona pública do produto é discutível. Registrado como `[ABERTO]` na
  Fase 0 do §8.
- **Teto do plano de CIDR: 15 spokes.** `/16` por spoke em `10.0.0.0/12`, e **região
  multiplica** — 10 tenants em 2 regiões estoura. Quatro caminhos em
  `aws/docs/network/01-cidr-addressing.md`; a escolha depende de saber se spoke de tenant
  precisa de rota privada para o hub ou só é alcançada pela API da AWS e pelo endpoint do
  cluster. É a única decisão irreversível da cadeia.
- **Session tags em `assumeRoleChain`:** a opção 2 de contenção regional
  (`aws:RequestedRegion` = `aws:PrincipalTag/region`) depende de o provider-aws propagar tags
  de sessão. **Não verificado.** Se não propagar, a condição nunca casa e tudo é negado.
- **Base do domínio:** `wasp.silvios.me` em Azure DNS; delegar subzona (ex.:
  `aws.wasp.silvios.me`) para Route53 ou o domínio inteiro? Sem `<hosted-zone-id>` as fatias
  DNS/ingress/TLS ficam bloqueadas; rede/EKS/Pod Identity/ESO rodam sem isso.
- **Parametrizar** valores de `CLAUDE.local.md` (chart values? env? EnvironmentConfig?) —
  decidir após execução ponta a ponta.
- **Rework do orquestrador `environment/`** (BLOCKED): sob `metadata.name`, filhos compostos
  ganham nome hasheado → o cruzamento por label compartilhado não funciona. Conserto desenhado
  em `resources/examples/topology/05-07` (injetar `subnetIds` do `Network.status` no Cluster em
  vez de casar por label; exige `function-kcl` ou Network publicar arrays). Adiado — os charts
  diretos não dependem dele. `compute/06-crossplane-map.md` registra o alvo: **remover
  `Environment`; `Cluster` é o topo**.
- **`tenancy/04-crossplane-map.md` não escrito de propósito** — depende do schema do registry
  de tenants (§11 decisão 1). Ausência é deliberada, não esquecimento.
- **Retenção do bucket de auditoria** (lifecycle → Glacier após N dias, expiração após M
  anos): decisão de compliance, deliberadamente adiada. É o único custo do CloudTrail que
  cresce sozinho e para sempre.
- **Conta `security-tooling`** desenhada como slot, não criada — vira pré-requisito quando
  GuardDuty/Config/Security Hub entrarem.
- **Contas `Monitoring` / `Operations Tooling`** (OU `Infrastructure`) são os slots canônicos
  da observabilidade centralizada; nenhuma existe. Registrado em `observability/CLAUDE.md`.
- **`Sandbox` como conceito** fica reservado para outra coisa (conta de brincar, desconectada
  da rede, sem attachment no TGW) — não é o ambiente de teste do projeto, que é
  `<projeto>-nonprod`.
- Track paralelo (Azure cluster-zero + Backstage multi-tenant) pausado; não é o foco.

## Known Broken

1. **Break-glass documentado, controles ausentes** — *unexpected*: MFA no root da management
   account e das contas-membro **não verificado**; alarme de uso de root **não existe**
   (CloudTrail já captura, falta a regra EventBridge); ensaio nunca executado. Ver
   `aws/docs/accounts/CLAUDE.md`, decisões em aberto 4 e 5.
2. **Management account com `AdministratorAccess` atribuído a usuário, não a grupo** —
   *unexpected*: viola a própria regra `--group` da doc, na conta mais privilegiada. Migrar
   para `platform-admins` (atribuir o grupo antes de revogar o usuário).
3. **Credencial-raiz do Crossplane é access key de longa duração** — *intentional*: contraria
   [SEC02-BP02](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/sec_identities_unique.html).
   Bloqueado por k3d não suportar Pod Identity; só desaparece quando o Control Plane virar EKS.
   **Mitigação barata ainda não aplicada:** a própria BP recomenda reduzir o IAM user a só
   `sts:AssumeRole` para uma role específica — hoje ele tem `PowerUserAccess` direto.
4. **Link quebrado em `docs/superpowers/plans/2026-08-07-cluster-zero-terraform.md`** →
   `infra/terraform/cluster-zero/README.md` — *intentional*: aponta para artefato da trilha
   Azure que nunca foi construído. Não é doc desatualizada.
5. **Valores reais em docs genéricas** — *unexpected*: `aws/docs/bootstrap/00-crossplane-iam-user.md:91`
   tem account id real hardcoded; `accounts/03-provisioning.md` e `accounts/scripts/create-account`
   têm e-mail real. Contraria a convenção de genericização; pré-existente.
   **Parcialmente corrigido em 2026-08-25:** a árvore da Organization neste arquivo tinha os 5
   account IDs e e-mails; foi genericizada e os valores passaram a `CLAUDE.local.md`. Os três
   arquivos acima continuam pendentes.
6. VPC+EKS ainda NÃO provisionados numa spoke — *intentional*: custo alto, só sob autorização
   explícita. A conta `cicd` já existe e está vazia — criar a conta não custa nada; o EKS custa.
7. `crossplane render` não injeta defaults do XRD — *intentional* (limitação da ferramenta):
   passar `providerConfigName`/`metadata.name` explícitos no XR de teste. `providerConfigName`
   é OBRIGATÓRIO (sem default): XR sem ele é rejeitado, não há fallback.
8. `enum` de `providerConfigName` inclui `wasp-nonprod` (nome específico da conta) nos XRDs
   versionados — *intentional*: trade-off aceito vs. genericização; comentário instrui
   ajustar a lista `[network, wasp-nonprod]` por instância.
9. `aws/eks/apps/echo/templates/*.yaml` falham em parser YAML puro — *intentional*: Helm
   templates (`{{ }}`).
10. `revoke-permission-set` só foi exercido no caminho feliz (revogação real da
    `log-archive`); os ramos "atribuição inexistente" e "permission set inexistente" nunca
    rodaram.
11. `idp/app-config.production.yaml` `guest: {}`; `idp/packages/backend/src/index.ts`
    `allow-all` policy; `idp/packages/backend/src/googleAuthModule.ts`
    `dangerouslyAllowSignInWithoutUserInCatalog: true` — *intentional* (PoC).

## How to Resume

**A sessão parou num gate de revisão, não numa falha nem numa decisão pendente.** O design do
módulo está escrito e commitado; falta o Silvio revisar:

```bash
cd /home/silvios/git/wasp-idp
code docs/superpowers/specs/2026-08-25-terraform-bootstrap-module-design.md
```

Aprovado, invocar `superpowers:writing-plans`. **Nenhum código antes disso.**

**A referência funcional é a Composition, não as fases do chart.**
As Compositions Crossplane do repositório de referência interno (caminho em `CLAUDE.local.md`)
decompõem o monólito `environment-eks` em três abstrações, que mapeiam 1:1 nos submódulos:

| Abstração | Camadas | Submódulo Terraform |
|---|---|---|
| `Network` | L1a (16 MRs, VPC→RTA) | `src/network` |
| `Cluster` | L1c IAM + L2 EKS/addons/ponte | `src/cluster`, `src/nodegroup`, `src/pod-identity` |
| `ClusterBootstrap` | L3 Route53 + L4 Releases + L5 Objects | `src/helm/modules/*` — **é aqui que o escopo fino corta** |

Não usar `aws/eks/chart/templates/` como referência: é a mesma coisa menos decomposta e com
bugs já corrigidos do outro lado.

Contexto de apoio, se for preciso reconstruir o raciocínio:

```bash
sed -n '/^## 7\. IaC/,/^## 8\./p' decisions.md      # cardinalidade × churn; os dois Crossplanes
sed -n '/^### Fase 2/,/^### Fase 3/p' decisions.md   # o que a Fase 2 entrega
ls aws/eks/chart/templates/                          # as 28 fases que o k3d faz hoje
cat /home/silvios/git/azure-kubernetes/examples/cluster_argocd_ingress_istio/main.tf
grep -rn oidc /home/silvios/git/azure-kubernetes/src/helm/modules/argo-cd/  # o padrão ESO→argocd-secret
```

O exemplo Azure é a referência de **estrutura** pedida: raiz compõe submódulos de `src/`, com
flags `local.install_*` e, por addon, o tripé *workload-identity → role assignment → helm
module*. No lado AWS o tripé equivalente é *Pod Identity association → inline policy → Helm
release*, que é exatamente como as fases `80/82/84`, `86/88` e `100/102` já estão organizadas.

**Achados a não reaprender:**

- O exemplo Azure tem `install_app_of_apps_infra = false`. Mesmo a referência de "paridade total"
  mantém o handoff para GitOps desligado — ela prova a estrutura, não a fronteira.
- **As ~40 `ClusterUsage` do teardown ordenado não têm tradução em Terraform** — são uma aresta de
  dependência construída à mão porque `Network` e `Cluster` são XRs distintos e
  `matchControllerRef` só casa o mesmo owner. Terraform destrói em ordem reversa nativamente.
  **Mas só se rede e cluster estiverem no mesmo state** — por isso o corte de camadas é
  `hub | spoke+cluster`, nunca `rede | cluster`. Separar reintroduz o bug sem o mecanismo que o
  compensava.
- **EBS CSI pertence à abstração `Cluster` (L2b)**, ao lado do `eks-pod-identity-agent`. Não é
  adição opcional — uma afirmação anterior nesta sessão dizia o contrário e estava errada.
- Trust de Pod Identity exige `sts:TagSession` além de `sts:AssumeRole`.
- `authentication_mode = "API"` — sem `aws-auth` ConfigMap.
- A `Network` de referência tem as 4 subnets **hardcoded** em `172.16.{1,2,3,4}.0/24` e marca
  parametrizar como follow-up. **Não herdar:** nosso plano é `10.0.0.0/12` com `/16` por spoke, e
  CIDR é a única decisão irreversível da cadeia. `src/network` calcula com `cidrsubnet()`.

Se o Control Plane k3d tiver sido destruído e for preciso reproduzir o estado atual:

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

Pré-requisitos: VPN corporativa **desconectada** (senão o pull de `xpkg.upbound.io` falha com
`x509` e depois `connection reset`) e SSO admin ativo (`aws sso login --profile personal`).
`install-crossplane` default é `--servers 1` — não usar 3 neste host.

Perfis locais: `network`, `wasp-nonprod` e `cicd`, todos assumindo
`OrganizationAccountAccessRole` a partir de `personal`. Backup do `~/.aws/config` antes do
rename dos profiles: `~/.aws/config.bak-20260824`.

Os scripts de `aws/docs/accounts/scripts/` que criam recursos reais devem ser rodados
manualmente via `! <script>` — o classifier de auto-mode bloqueia.

## Next Steps

### Frente A — contas

- [x] Vocabulário do whitepaper aplicado em doc, scripts e na Organization real.
- [x] CloudTrail organizacional + conta `log-archive` + bucket de auditoria.
- [x] **Passo ⑥ — SCPs baseline** em Root/Security/Infrastructure/Workloads (`us-east-1`).
      SCP **não** afeta a management account.
- [x] Permission set de rotina da `log-archive` em `ReadOnlyAccess`.
- [x] E-mail do root da `Network` alinhado (`+hub@` → `+network@`).
- [x] Break-glass documentado; IDs do WAF conferidos contra as páginas oficiais.
- [x] OU `Deployments` + `--ou deployments` + SCP baseline escritos nos scripts.
- [x] **Aplicada** a OU `Deployments` + SCP baseline nela + conta `cicd` criada e movida
      (IDs em `CLAUDE.local.md`). Profile local validado; deny de região comprovado.
- [ ] Atribuir permission set à conta `cicd` — nasceu sem nenhum.
- [ ] Decidir se as VPCs default da `cicd` (uma por região) saem. Higiene, não bloqueio.
- [ ] Atribuir permission set a `Network` e `wasp-nonprod`
      (`./assign-permission-set --account <conta> --group platform-admins`) — elimina o
      switch-role via `OrganizationAccountAccessRole`.
- [ ] Migrar a atribuição da management account de usuário `silvios` para grupo
      `platform-admins` (atribuir o grupo **antes** de revogar o usuário).
- [ ] Verificar/habilitar MFA no root da management account e das contas-membro.
- [ ] Criar a regra de alarme de uso de root (CloudTrail → EventBridge → notificação).
- [ ] Decidir retenção/lifecycle do bucket `cloudtrail-<organization-id>`.

### Frente B — Terraform + Crossplane / EKS

- [x] **Fase 4:** split de charts + identidade `metadata.name` + PCs por conta.
- [x] Validar a cadeia renomeada recriando o Control Plane do zero. Custo zero.
- [x] Escopo do módulo Terraform: **fino**, com conta `cicd` na OU `Deployments`.
- [x] **Fronteira do ArgoCD decidida:** sem ingress, ESO dentro, trio DNS fora.
- [ ] **Design do módulo escrito — em revisão pelo Silvio.**
      `docs/superpowers/specs/2026-08-25-terraform-bootstrap-module-design.md`. Aprovado o
      design, o próximo passo é `superpowers:writing-plans`. Nenhum código antes disso.
- [x] Conta `cicd` criada — o **pré-requisito duro** do `terraform apply` está cumprido.
- [ ] Escrever o plano da camada 2 (`platform-cell`) — agora desbloqueado.
- [ ] Escrever o design do script `follow` determinístico (equivalente ao
      `azure-kubernetes/scripts/follow-creation/follow`) — decidido que ganha spec própria.
- [ ] Reduzir o IAM user `crossplane-poc` a só `sts:AssumeRole` (mitigação de SEC02-BP02 que
      não depende de migrar para EKS).
- [ ] Decidir base do domínio (delegar `wasp.silvios.me`/subzona → Route53) antes das fatias
      DNS/ingress/TLS.
- [ ] Definir estratégia de parametrização dos valores de `CLAUDE.local.md`.
- [ ] **Fase 5** (alternativa se o Terraform for adiado): aplicar `hub` → `spoke` (`10.2`,
      `wasp-nonprod`) → esperar Ready → `cluster` (EKS). Custo alto.

### Frente C — documentação

- [x] Domínio `tenancy/` (SaaS Lens), `security/08`, correções de conta × região × papel.
- [x] Nomes de arquivo e H1 em inglês; hierarquia de fontes WAF → whitepaper → SRA.
- [ ] Resolver a conflação de `decisions.md` §2 (auth/discovery vs. conta de CI/CD) junto com
      a decisão 6 do §11.
- [ ] Remover os valores reais que sobraram em docs genéricas (item 5 de Known Broken).
- [ ] `tenancy/04-crossplane-map.md`, quando o schema do registry de tenants existir.

> Before trusting anything time-sensitive above, run `git status`, `git diff`, and `git log` against the base branch.
