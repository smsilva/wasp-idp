# HANDOFF

> **Arquivo único.** Este repo NÃO usa `HANDOFF.local.md` — a divisão versionado/local foi
> desfeita em 2026-08-25, porque duplicava contexto e cada sessão tinha de reconciliar os dois.
> Frente ativa, estado aplicado e backlog vivem aqui. `HANDOFF.local.md` segue no `.gitignore`
> como rede de segurança; se aparecer um, é resíduo — consolidar aqui e apagar.
>
> **Account IDs desta Organization estão neste arquivo, deliberadamente.** São de uma conta
> pessoal descartável para exercitar a PoC; nada aqui vai para ambiente real. E-mails de root
> **não** entram (PII, e um handoff não precisa deles) — ficam em `CLAUDE.local.md`.

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

## Estado aplicado na AWS

Snapshot de 2026-08-25. **Conferir antes de confiar** — a camada 2 cobra por hora e pode já ter
sido destruída:

```bash
cd aws/terraform/control-plane && terraform state list | wc --lines   # 39 = de pé; 0 = destruída
```

| Camada | Conta | State key | Custo/mês | Estado |
|---|---|---|---|---|
| `state-backend` | `network` | `state-backend/` | centavos | aplicada |
| `network-foundation/us-east-1` | `network` | `network-foundation/us-east-1/` | **zero** | aplicada |
| `network-foundation/us-west-2` | `network` | `network-foundation/us-west-2/` | **zero** | aplicada |
| `control-plane` | `cicd` | `control-plane/` | **~US$ 165** | aplicada 2026-08-25 |

Bucket de state: `tfstate-o-e4r8ndteju`, na conta `network`.

### Camada 1 — VPCs hub (custo recorrente zero)

| Região | VPC | CIDR | Subnets |
|---|---|---|---|
| `us-east-1` | `vpc-087a169b8e8dfc7d5`, tag `Name = poc-hub-vpc` | `10.1.0.0/16` | públicas `10.1.0.0/20`, `10.1.16.0/20`; privadas `10.1.32.0/20`, `10.1.48.0/20` |
| `us-west-2` | — | `10.3.0.0/16` | idem, derivadas por `cidrsubnet()` |

**Sem NAT Gateway em nenhuma das duas.** Sem TGW nada roteia pelo hub, e um NAT custaria ~US$ 32/mês
servindo zero tráfego. As subnets privadas não têm saída para a internet — intencional.

### Camada 2 — Control Plane (conta `cicd`, `us-east-1`)

| Recurso | Valor |
|---|---|
| VPC spoke | `10.2.0.0/16`; públicas `10.2.0.0/20`, `10.2.16.0/20`; privadas `10.2.32.0/20` = `subnet-093dc591660611891`, `10.2.48.0/20` = `subnet-0d3dd1f8a55a7f31b` |
| Cluster EKS | `control-plane`, Kubernetes **1.36** (nós `v1.36.2-eks-b3f9404`) |
| Nós | 2× `t3.medium` `ON_DEMAND` |
| NAT | **ligado** — ao contrário do hub, os nós dependem dele |
| Charts | ArgoCD `10.4.0`, ESO `2.9.0`, Crossplane `2.4.0` (canal `stable`) |
| Contexto kubectl | `arn:aws:eks:us-east-1:270222614208:cluster/control-plane` |

Roles de Pod Identity, todas na conta `cicd`:

| Role | Namespace | ServiceAccount |
|---|---|---|
| `control-plane-crossplane` | `crossplane-system` | `crossplane` |
| `control-plane-external-secrets` | `external-secrets` | `external-secrets` |
| `control-plane-ebs-csi` | `kube-system` | `ebs-csi-controller-sa` |

Mais `control-plane-cluster` e `control-plane-node` (roles do EKS, não Pod Identity).

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

### Frente A — bootstrap de contas / Organization

Objetivo: percorrer a sequência de provisionamento passo a passo, corrigindo doc e scripts
contra o whitepaper AWS conforme cada passo é executado de verdade. **Regra adotada: sempre
manter o vocabulário de "Organizing Your AWS Environment Using Multiple Accounts"; divergir só
com motivo registrado.**

Forma da Organization, inspecionada na API. Organization `o-e4r8ndteju`, root `r-f11d`,
região de trabalho `us-east-1`.

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

**Aprovar uma região é `--regions` e vale para a Organization inteira.**
`./apply-baseline-service-control-policy --regions <r1>,<r2>` reescreve `DenyOutsideApprovedRegions`
em todos os targets — não há como liberar região só numa conta por essa via. Sem isso, um
`terraform apply` fora das regiões aprovadas falha no primeiro `Create*` com
`explicit deny in a service control policy`, e o erro parece bug de código.

**Ordem que funcionou melhor que a documentada:** aplicar a SCP na OU **antes** de criar a conta
nela. O desenho original em `aws/docs/accounts/CLAUDE.md` listava ⑤b (criar conta) antes de ⑥
(SCPs); inverter faz a conta encontrar a OU já protegida ao ser movida. Não elimina a janela
Root→OU, encurta. O script é idempotente, então rodá-lo de novo é seguro.

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

### Frente B — Terraform (camadas 1 e 2) e Crossplane / EKS

**A camada 2 está aplicada e verificada (2026-08-25).** As 8 tasks do plano
`docs/superpowers/plans/2026-08-25-terraform-control-plane.md` foram executadas: 1–7 em TDD
offline, um commit por task, e a 8 aplicou na AWS.

Um `terraform apply`, **39 recursos**, ~13 min, **sem `-target`**. Isso fecha a pergunta que
estava aberta no desenho: providers `kubernetes`/`helm` configurados a partir de outputs do módulo
do cluster resolvem na hora do apply. O que quebraria é **data source** desses providers no plan —
por isso o `platform-bootstrap` tem de continuar sendo `resource`.

Verificado no cluster: 2 nós `Ready`, 12 pods `Running` nos três namespaces de plataforma, as 7
chaves do ConfigMap `platform-bootstrap`, e `AWS_CONTAINER_CREDENTIALS_FULL_URI` no pod do
Crossplane.

**Consequência para o item 3 de Known Broken:** a access key de longa duração do `crossplane-poc`
**é eliminável** — no EKS o Crossplane roda com credencial por Pod Identity, sem access key
nenhuma. Ela só sobrevive na trilha k3d, que não suporta Pod Identity.

Três scripts em `aws/terraform/control-plane/scripts/`:

| Script | O que faz |
|---|---|
| `generate-tfvars` | Descobre na AWS o que a camada precisa e gera o `terraform.tfvars`. **Só leitura.** Valida antes de gerar arquivo: tag da VPC hub univoca, CIDR livre, região aprovada na SCP, bucket existente |
| `apply` | `plan` → confirma → aplica → guarda log com timestamp em `logs/` |
| `destroy` | Confere Crossplane sem recurso vivo e contexto kubectl correto → destrói → guarda log |

Os dois últimos leem o exit code por `PIPESTATUS[0]`: o `tee` sempre retorna 0, e sem isso um
apply que falhou passaria por sucesso.

#### Cross-account + Fase 4 (Crossplane no k3d)

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

## Achados a providenciar — sessões próximas

Levantados ao aplicar a camada 2 (2026-08-25). Ordenados por dependência, não por gravidade.

**Bloqueiam a fatia de ingress privado:**

1. **Não existe conectividade hub → spoke.** Verificado na API das duas contas: zero TGW, zero
   attachment, zero peering, zero endpoint service. As route tables do hub só têm `10.1.0.0/16`
   (local) e `0.0.0.0/0` (IGW). **Nada alcança `10.2`.** A experiência multi-região provou reuso do
   módulo, não conectividade — e o mesmo vale para hub↔spoke.
2. **O AWS Load Balancer Controller não está instalado.** A camada 2 entrega ESO, ArgoCD e
   Crossplane. Sem LBC, `Service type=LoadBalancer` cai no provider in-tree legado (Classic LB),
   que não dá NLB interno com `target-type: ip`. Precisa de `src/helm/modules/aws-lbc` + uma quarta
   Pod Identity.
3. **Escolher o padrão: PrivateLink ou TGW.** Fundamentação e citação da AWS na seção
   *Ingress centralizado* abaixo.

**Postura de segurança do que já está aplicado:**

4. **O endpoint da API do EKS é público para `0.0.0.0/0`.** `endpointPublicAccess = true` e
   `public_access_cidrs = []` (a variável documenta que vazio significa `0.0.0.0/0`);
   `endpointPrivateAccess` também `true`. **Plano distinto do ingress de workload** — este é o
   *management plane*. Fechar exige alcançar a API de dentro da VPC, logo depende do item 1.
5. **`bootstrapClusterCreatorAdminPermissions` está `true` na camada 2 e `false` no cluster do
   chart Crossplane.** Divergência não decidida, herdada de caminhos diferentes. `true` é
   conveniente (o profile que aplica já tem admin); `false` é a postura estrita. Escolher e
   justificar.
6. **A VPC default da `cicd` segue de pé em toda região**, com security group aberto. Já estava em
   Known Broken, mas agora há workload real na conta.

**Dívida de processo, barata:**

7. **Nunca fixar versão de Kubernetes em documento de plano.** O plano trazia `1.34`; o default do
   EKS já era `1.36`, e o suporte padrão do `1.34` termina em **2026-12-01** — o cluster nasceria
   com upgrade vencendo. O `generate-tfvars` descobre a versão; o plano não deveria ter opinião.
   Mesma regra para versão de chart e de addon.
8. **A race de Pod Identity do EBS CSI não existe no Terraform.** No chart Crossplane obrigou a
   separar as fases 65 e 68 (`aws/CLAUDE.md`); aqui o grafo de dependências já ordena addon depois
   da association, e o controller subiu com **0 restarts**. Não é lei da natureza — é limitação do
   Crossplane sem `depends_on` real. Quando o chart for aposentado, a nota sai junto.
9. **Sobrou um `control-plane.tfplan` duplicado** no diretório da camada 2. Gitignored, mas
   confunde: apagar.
10. **Sob `mock_provider`, data source de provider devolve valor sintético.** Qualquer assertion
    sobre JSON computado pelo provider passa sem verificar nada — foi como duas assertions ficaram
    vazias. Regra: policy document via `jsonencode`, não `data "aws_iam_policy_document"`. Aplicado
    nos módulos novos; **auditar se há outro lugar no repo com a mesma armadilha.**

## Ingress centralizado: o que a AWS de fato recomenda

Pesquisado em 2026-08-25 no whitepaper *[Building a Scalable and Secure Multi-VPC AWS Network
Infrastructure](https://docs.aws.amazon.com/whitepapers/latest/building-scalable-secure-multi-vpc-network-infrastructure/welcome.html)*
(pub. 2024-04-17), porque a escolha estava sendo feita por intuição.

A AWS **não** elege um vencedor — ela separa por **tipo de conectividade**, e diz explicitamente
que arquiteturas reais misturam as duas:

> **AWS PrivateLink** — Use AWS PrivateLink when you have a client/server set up where you want to
> allow one or more consumer VPCs unidirectional access to a specific service or set of instances
> in the service provider VPC (…) This is also a good option when client and servers in the two
> VPCs have overlapping IP addresses.
>
> **VPC peering and Transit Gateway** — Use VPC peering and Transit Gateway when you want to enable
> layer-3 IP connectivity between VPCs.
>
> — [AWS PrivateLink](https://docs.aws.amazon.com/whitepapers/latest/building-scalable-secure-multi-vpc-network-infrastructure/aws-privatelink.html)

Aplicando ao caso *ALB público no hub → httpbin no spoke*: o hub é **consumer**, o httpbin é o
**service**, o acesso é **unidirecional**. É a descrição literal do caso de uso do PrivateLink.

**Onde o TGW é a recomendação:** a seção
[Centralized inbound inspection](https://docs.aws.amazon.com/whitepapers/latest/building-scalable-secure-multi-vpc-network-infrastructure/centralized-inbound-inspection.html)
usa *"AWS Transit Gateway acting as a central hub for routing traffic"* — mas o que ela centraliza
é **inspeção** (Gateway Load Balancer, Network Firewall, IDS/IPS). Sem requisito de inspeção, o TGW
está resolvendo um problema que não existe aqui. Note que a arquitetura WAF+ALB que o mesmo
capítulo mostra é **por-ALB, distribuída** — a própria AWS a classifica como *"best suited for HTTP
header inspection and distributed inspections"*.

Três razões próprias do repo que reforçam PrivateLink para esta fatia:

- **Não invalida o corte de state documentado.** `aws/terraform/README.md` registra que
  `hub | spoke+cluster` é seguro *hoje porque não há TGW* — os nós não roteiam pelo hub. Ligar TGW
  obriga a revisitar esse raciocínio agora. PrivateLink não toca route table nenhuma.
- **Não consome o teto de CIDR.** O `/12` dá 15 `/16` e região multiplica (questão aberta abaixo).
  PrivateLink permite CIDR sobreposto entre spokes; TGW não.
- **Menor privilégio de rede:** expõe um serviço autorizado por principal de conta, não um CIDR.

O whitepaper também registra que **ALB pode ser target de NLB**, o que permite combinar roteamento
L7 do ALB com PrivateLink — relevante se o ingress no hub precisar de path-based routing.

**Alternativa que não passa pelo hub:** CloudFront com *VPC origins* alcança um ALB privado sem
exposição pública. Satisfaz "cluster não expõe LB público", mas **abandona o ingress centralizado
na conta de rede** — é outra topologia, não uma variante desta.

TGW continua sendo a resposta eventual para egress centralizado e tráfego spoke↔spoke. Não é
ou-um-ou-outro.

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
   Bloqueado por k3d não suportar Pod Identity. **Deixou de ser hipótese em 2026-08-25:** no EKS da
   camada 2 o pod do Crossplane subiu com `AWS_CONTAINER_CREDENTIALS_FULL_URI`, ou seja, Pod
   Identity sem access key nenhuma. A access key sobrevive só na trilha k3d.
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
6. **VPC+EKS provisionados na spoke da conta `cicd`** desde 2026-08-25 — *intentional*, sob
   autorização explícita, com intenção declarada de **não deixar de pé**. Se ainda estiver vivo,
   cobra ~US$ 165/mês. Nenhum EKS em `wasp-nonprod` (aquela é a spoke de projeto, ainda vazia).
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

**Primeira pergunta, antes de qualquer código: o cluster está de pé?** Ele cobra por hora.

```bash
cd wasp-idp
git branch --show-current                       # esperado: feat/control-plane-layer
cd aws/terraform/control-plane
terraform state list | wc --lines               # 39 = de pé (~US$ 0,23/h); 0 = destruída
```

Se estiver de pé e não houver trabalho ativo nele: `./scripts/destroy`. Se estiver destruída e for
preciso subir de novo, o state fica no bucket e a sequência é curta:

```bash
./scripts/generate-tfvars --force
terraform init -backend-config="bucket=tfstate-o-e4r8ndteju"
./scripts/apply
```

O `terraform apply`/`destroy` roda por `! <comando>` — o classifier de auto-mode bloqueia para o
agente. O `apply` sem tty falha de propósito, informando o caminho do plano salvo; use `--yes`
quando não houver terminal.

**O plano da camada 2 está concluído** (8 de 8 tasks). Regressão offline, 45 testes, 0 falhas:

```bash
cd aws/terraform
for m in src/network src/state-backend src/pod-identity src/cluster src/nodegroup \
         src/helm/modules/external-secrets src/helm/modules/argo-cd src/helm/modules/crossplane \
         network-foundation/us-east-1 network-foundation/us-west-2 control-plane; do
  (cd "${m}" && terraform init -backend=false >/dev/null && terraform test)
done
```

Contexto de desenho, se for preciso reconstruir o raciocínio:

```bash
code docs/superpowers/specs/2026-08-25-terraform-bootstrap-module-design.md
code docs/superpowers/plans/2026-08-25-terraform-control-plane.md
```

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
cat azure-kubernetes/examples/cluster_argocd_ingress_istio/main.tf
grep -rn oidc azure-kubernetes/src/helm/modules/argo-cd/  # o padrão ESO→argocd-secret
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
- [x] **Design do módulo aprovado.** `docs/superpowers/specs/2026-08-25-terraform-bootstrap-module-design.md`.
- [x] Conta `cicd` criada — o **pré-requisito duro** do `terraform apply` está cumprido.
- [x] **Camada 1 do Terraform APLICADA**, com state remoto no S3 e lock nativo. Custo recorrente
      zero (sem NAT). 17 testes offline, 0 falhas.
- [x] **Bucket de state desacoplado de qualquer região.** Raiz própria `state-backend/`, com
      `prevent_destroy`. Antes ele vivia no state da `network-foundation` de `us-east-1` e um
      `terraform destroy` daquele hub levaria o mapa de toda a infraestrutura. Migração por
      blocos `removed`/`import`, sem cirurgia de state.
- [x] **`network-foundation` virou uma raiz por região**, cada uma com state key própria —
      elimina o footgun de alternar backend com `init -reconfigure`.
- [x] **Reuso do módulo entre regiões PROVADO:** segundo hub aplicado numa segunda região sem
      alterar uma linha de `src/network`. Isolamento verificado — `plan -destroy` de uma região
      não alcança a outra nem o bucket.
- [x] **`us-west-2` aprovada na SCP baseline.** `--regions` reescreve a policy em todos os
      targets; não dá para liberar região só numa conta por essa via.
- [x] **Plano da camada 2 escrito e executado por inteiro** (8 tasks). Custo real: **~US$ 165/mês**
      — EKS ~73 + NAT ~32 + 2×`t3.medium` ~60. Os ~US$ 105 registrados antes omitiam os nós.
- [x] **Camada 2 APLICADA e verificada.** 39 recursos, um único apply sem `-target`. Pod Identity
      funcionando nos três consumidores.
- [x] Três scripts operacionais da camada 2 (`generate-tfvars`, `apply`, `destroy`).
- [ ] **Destruir a camada 2** se ainda estiver de pé — a intenção declarada foi não deixar ligada.
- [ ] **Fatia de ingress privado** (httpbin no cluster, entrada pelo hub, cluster sem LB público):
      AWS LBC + quarta Pod Identity, NLB interno, endpoint service no spoke, interface endpoint e
      ALB no hub. Padrão escolhido: **PrivateLink** — fundamentação e citação na seção
      *Ingress centralizado*. Ganha plano próprio.
- [ ] **Fechar o endpoint público da API do EKS** (`public_access_cidrs`). Depende de alcançar a API
      de dentro da VPC, logo depende da fatia acima.
- [ ] Instalar o **AWS Load Balancer Controller** como `src/helm/modules/aws-lbc` — pré-requisito da
      fatia de ingress e de qualquer `Service type=LoadBalancer` sério.
- [ ] Decidir `bootstrapClusterCreatorAdminPermissions`: `true` (camada 2) ou `false` (chart).
- [ ] Enviar `feat/control-plane-layer` para PR — tem código, apply e verificação. Não pushada.
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

## Completed Work

### Camada 2 do Terraform — escrita, aplicada e verificada (2026-08-25)

Dez commits em `feat/control-plane-layer`. Tasks 1–7 em TDD offline, um commit por task; Task 8 é o
apply.

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

Regressão da árvore inteira: **45 testes em 11 diretórios, 0 falhas** — a camada 1 segue intacta.

O que o root compõe: VPC spoke `10.2.0.0/16` + EKS + node group + três Pod Identities (EBS CSI,
ESO, Crossplane) + os três charts + o ConfigMap `platform-bootstrap`, que é o contrato com o
GitOps — nenhum manifesto do lado GitOps carrega account id ou VPC id hardcoded.

**Quatro correções ao plano, exigidas pelos próprios testes do plano** (não são escolha de estilo —
sem elas os testes não passavam honestamente):

- **`jsonencode` no lugar de `data.aws_iam_policy_document`** nos módulos `pod-identity` e
  `cluster`. Sob `mock_provider "aws"` o data source devolve valor sintético, o provider rejeita com
  `"assume_role_policy" contains an invalid JSON policy: not a JSON object`, e as asserções sobre
  `sts:TagSession` no trust nunca poderiam passar.
- **A asserção das três Pod Identities comparava `role_arn` com `null`.** O ARN só existe depois do
  apply, então a condição era ineliminavelmente *unknown* no plan. Passou a verificar `role_name`,
  que deriva de `var.name`.
- `kubernetes_config_map` → `kubernetes_config_map_v1` (o primeiro está deprecado no provider 3.x).
- A cláusula morta `cidrsubnet("10.0.0.0/12", 4, 0) != null` saiu da validação de `vpc_cidr`, com um
  `can()` em volta do `tonumber` para CIDR malformado falhar limpo.

**Decisões de desenho confirmadas pelo apply real:**

- **Apply único, sem `-target`.** Comprovado. `platform-bootstrap` como `resource`, não data source.
- **VPC hub por `data "aws_vpc"`** num provider aliasado para a conta `network`, não por
  `terraform_remote_state` — acoplamento ao recurso, não ao arquivo de state.
- **Providers `helm`/`kubernetes` na faixa 3.x.** No helm 3.x `kubernetes` é atributo, não bloco.
- **Versões de chart conferidas nos repositórios**, não herdadas: ESO `2.9.0`, argo-cd `7.7.7` →
  **`10.4.0`** (ArgoCD 3.5.1, atravessa um major), crossplane `2.3.1` → **`2.4.0`** do canal
  `stable` (o ArtifactHub indexa `master`, que publica RCs).
- `aws/eks/scripts/install-crossplane` segue em `2.3.1` — trilha k3d, atualização separada.

### Camada 1 do Terraform (2026-08-25, anterior)

Bucket de state em raiz própria com `prevent_destroy`, desacoplado de qualquer região; uma raiz por
região com state key própria. Reuso do módulo entre regiões provado com um segundo hub em
`us-west-2` sem alterar uma linha de `src/network`. Isolamento verificado: `plan -destroy` de uma
região não alcança a outra nem o bucket.

> Before trusting anything time-sensitive above, run `git status`, `git diff`, and `git log` against the base branch.
