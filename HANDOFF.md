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

Snapshot de 2026-08-26. **Custo recorrente: só centavos.** A última sessão não aplicou nada na AWS — o
portão `2.1` é verificação local. O `2.2` é o primeiro passo que cobra por hora.

| Camada | Conta | State key | Custo/mês | Estado |
|---|---|---|---|---|
| `state-backend` | `network` | `state-backend/` | centavos | aplicada |
| `network-foundation/us-east-1` | `network` | `network-foundation/us-east-1/` | **zero** | aplicada |
| `network-foundation/us-west-2` | `network` | `network-foundation/us-west-2/` | **zero** | aplicada |
| `control-plane` | `cicd` | `control-plane/` | ~US$ 165 quando de pé | **destruída** (state com 0 recursos) |
| `dns` | `network` + Azure | `dns/` | ~US$ 0,50 | **aplicada** — subzona `nonprod.`, delegação verificada |
| `connectivity/us-east-1` | `network` | `connectivity/us-east-1/` | ~US$ 110 quando de pé | **escrita, não aplicada** — T1 |

Bucket de state: `tfstate-o-e4r8ndteju`, na conta `network`. Nenhum cluster k3d de pé.

**Subida por camada:** `aws/terraform/scripts/up-NN-<camada>`, numerados pela ordem de dependência, mais `up-all`. Sequência, custos e as nove armadilhas que os scripts pegam antes de tocar em nada estão em `aws/terraform/README.md`. As camadas 03 (`connectivity`, ~US$ 110/mês) e 04 (`control-plane`, ~US$ 165/mês) **não** entram no `up-all` por default — exigem `--with-connectivity` / `--with-control-plane`.

**Atenção para as próximas sessões:** a camada 03 é um nível **T1 que fica de pé de propósito**
(TGW + Client VPN, ~US$ 0,15/h ≈ US$ 110/mês). Quando estiver aplicada, **não presumir resíduo e
destruir** — a regra "nada fica de pé entre sessões" passa a ter exceção declarada. Ele é derrubado
ao fim do dia, não ao fim da tarefa. E não esquecer ligada:
`connectivity/us-east-1/scripts/destroy`.

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

### Frente D — acesso privado + ingress centralizado (ATIVA, **`2.2` planejada, apply pendente**)

**Último passo:** `2.2` escrita e verde offline (22 testes, 14 mutações, 13 capturadas). O passo de
console foi concluído nesta sessão: aplicação SAML `hub-client-vpn` criada no Identity Center
(management account), attribute mappings (`Subject`→`${user:email}`/emailAddress,
`memberOf`→`${user:groups}`/unspecified) salvos, grupo `platform-admins` atribuído, metadata XML
baixado para `aws/terraform/connectivity/us-east-1/saml-metadata.xml` (gitignored, 2504 caracteres).
`generate-tfvars` rodou limpo e um `terraform plan` confirmou **12 recursos a criar**, plano limpo —
mas **o apply NÃO rodou ainda** (bloqueado pelo classifier do agente; pedido ao usuário via `!`, sem
confirmação de conclusão registrada nesta sessão). `terraform state list` na raiz `connectivity/`
está vazio — **verificar isso primeiro** ao retomar.

**Achado do plan, ainda não registrado no plano em si:** o Client VPN cobra por **associação de
subnet**, não por endpoint. Com 2 subnets privadas do hub (uma por AZ), o custo real do T1 é
~US$ 0,20/h (~US$ 146/mês parado), não os ~US$ 0,15/h (~US$ 110) que o `README.md` do plano ainda
documenta. Decidido manter as duas associações (redundância de AZ); atualizar a tabela de custo do
plano quando alguém voltar a editá-la.

```bash
cd aws/terraform/connectivity/us-east-1
terraform state list          # vazio? o apply não rodou — retomar por aqui
```

Se vazio, retomar com:

```bash
cd aws/terraform
./scripts/up-03-connectivity --yes    # tfvars e metadata já prontos; plano já validado
```

**Aceite do `2.2`:** túnel sobe com identidade do Identity Center, IP vindo de `100.64.0.0/22`, target
network `associated`, e o **login SAML completa** — este último não pôde ser testado nem no `2.1` nem
nesta sessão (exige o endpoint de pé). Verificar também se `aws-vpn-client connect` sob SAML abre o
navegador sozinho (ver Known Broken / Open Questions).

**Convenção de branch: uma por FASE**, `feat/private-access-phase-<n>` — não por passo. Os passos de
uma fase editam os mesmos dois arquivos de doc (`HANDOFF.md` e o arquivo da fase), então por passo
garantiria conflito em cada merge sem ganho de revisão.


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
   estiver autorizado. O preço que esta decisão pagava (client desktop, `connect` não scriptável)
   **caiu no `2.1`**: a versão 6.0.1 do client traz CLI.
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

### Frente E — scripts shell em inglês (ATIVA, parcial)

Regra corrigida pelo usuário nesta sessão: scripts shell (comentários, `show_usage`, mensagens de
log/erro) são em **inglês**, mesmo em projeto cujos `.md` são em português. Regra global gravada em
`~/git/linux/claude/rules/language.md`.

**Convertidos e commitados nesta sessão:** `aws/terraform/scripts/` (lib, up-00 a up-04, up-all),
`aws/terraform/connectivity/us-east-1/scripts/` (generate-tfvars, destroy),
`aws/terraform/control-plane/scripts/` (generate-tfvars, apply, destroy), e os 13 scripts de
`aws/docs/accounts/scripts/`.

**Convertidos mas NÃO commitados** (working tree, verificar `git status` ao retomar):
`aws/eks/scripts/check`, `configure-access`, `configure-account-access`, `configure-aws-creds`,
`install-crossplane`, `load-crossplane-creds`, `random-id`. `bash -n` passou em todos.

**Ainda em português, não tocados** (são os maiores e mais arriscados de quebrar — scripts que
provisionam/destroem EKS de verdade, fase a fase):

- `aws/eks/scripts/provision-eks` — ~215 linhas, todos os comentários de fase em português
- `aws/eks/scripts/teardown` — destrutivo, comentários de ordem inversa das fases
- `aws/eks/apps/deploy`
- `aws/eks/apps/clean`

Converter estes quatro por último e com cuidado extra: cada comentário documenta uma decisão de
ordenação (race de Pod Identity, dependência entre fases) que não pode se perder na tradução — reler
o comentário inteiro antes de traduzir frase a frase, não fazer find/replace ingênuo.

`scripts/cluster-zero/`, `scripts/install.sh`, `scripts/configure.sh` já estavam em inglês — nada a
fazer ali.

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
- ~~**Client da AWS VPN no Linux**~~ — **RESOLVIDO no `2.1`:** roda, 24.04 é suportado oficialmente, e
  desde a 6.0.1 tem CLI. As três saídas de contingência não foram usadas; ficam escritas em
  `02-private-access.md` para o caso de a distro mudar.
- **`aws-vpn-client connect` sob SAML abre o navegador sozinho?** Não verificado — o `--auth-user-pass`
  do CLI é usuário/senha, e a tentativa contra endpoint sintético morreu na validação do CA antes de
  tentar o túnel. Se **não** abrir, `connect` volta a depender da GUI para o handshake e o script `vpn`
  fica com `config`/`status` só. **Responde-se no apply do `2.2`**, e é o que decide o desenho do script.
- **O certificado do endpoint tem nome (`vpn.<subzona>`) diferente do hostname de conexão.** O
  raciocínio é que o client usa `remote-cert-tls server`, que confere extended key usage e não nome, e
  que `verify-x509-name` não entra na configuração exportada. **Não verificado contra um túnel real** —
  se o handshake recusar por nome, a saída é voltar ao autoassinado importado (a decisão descartada) ou
  acrescentar o hostname do endpoint ao SAN, que não se conhece antes de criar o endpoint. Risco do
  apply do `2.2`.
- **Quantas subnets privadas o hub tem por AZ, e o custo da associação.** A AWS cobra por associação de
  target network, então associar as duas subnets privadas dobra essa parcela em troca de redundância de
  AZ. O plano assume duas; se o custo apertar, uma resolve para PoC.
- **Zona privada do endpoint do EKS** não é output do `aws_eks_cluster` e é recriada a cada provisão —
  o lookup por hostname é frágil. Plano B (Resolver inbound endpoint) custa ~US$ 0,25/h. Risco do
  `2.4`.
- **Parametrizar** valores de `CLAUDE.local.md` (chart values? env? EnvironmentConfig?).
- **Domínio pessoal em arquivo versionado:** `01-preparation.md:88` cita o domínio real por extenso,
  vindo do desenho original. Não está na lista de tokens proibidos (que é sobre a trilha corporativa),
  mas é identidade num repo público. Decidir se vira `<domínio>` como no resto. **Não mexido de
  propósito** — é decisão de quem escreveu.
- **Quantas asserções do repo dependem de um único `override_resource`?** Uma só prova o valor, não a
  ligação (ver `Next Steps`). `routing.tftest.hcl` é da mesma família e nunca foi olhada sob essa lente.
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

1. ~~**`src/network` não aplica as tags de descoberta do AWS Load Balancer Controller.**~~
   **RETIRADO — o item estava errado.** As duas tags estão no módulo desde `b32eb68`, o commit
   inicial dele. O achado veio da leitura do desenho de referência, não do código, e sobreviveu a
   duas sessões de handoff sem ninguém abrir o `main.tf`. Fechado no `1.1` com o teste que faltava
   (`src/network/tests/tags.tftest.hcl`). **Lição: achado sobre módulo do repo se confere no módulo.**
2. **`src/network` não tem nada de TGW** — *intentional*. O TGW em si passou a existir na camada 03
   (`connectivity/`), com association e propagation default desligados. O que falta é o lado do spoke:
   attachment, associação/propagação em `tgw-rt-<spoke>` e rotas para CIDRs remotos. **É o `2.3`.**
3. **Endpoint da API do EKS público para `0.0.0.0/0`** — *era* `public_access_cidrs = []`, e vazio
   significa o mundo. **Fechado no `1.2` no que dá para fechar offline:** a variável do root não tem
   default, lista vazia é erro de validação no módulo e `0.0.0.0/0` é recusado no root mesmo
   explícito. **Falta a confirmação com a camada 2 de pé** (o apply do laptop segue funcionando; a API
   recusa de outro IP) — os dois critérios exigem ~US$ 165/mês ligados. Fechar de vez é o `2.5`, que
   depende de VPN + DNS.
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
16. **Asserção com um único `override_resource` prova o valor, não a ligação** — *unexpected*, e
    genérico: se o consumidor tiver o valor **fixo no código** igual ao injetado, a asserção passa sem
    haver fio. Comprovado no `1.3` — a mutação que colava name servers à mão passou **verde**. Corrigido
    ali com dois runs de valores e tamanhos diferentes. **Auditar o resto do repo.**
17. ~~**`up-03-connectivity` não existe**~~ — **RETIRADO:** existe, e a raiz `connectivity/us-east-1/`
    também. Fora do `up-all` por default (`--with-connectivity`), pelo mesmo critério de custo da 04.
18. **Sem `status`/`platform-status` em `aws/terraform/scripts/`** — *unexpected*: não há como
    perguntar "o que está de pé e quanto custa por hora". Fica perigoso na fase 2, que introduz um
    nível T1 que fica de pé **de propósito** e não pode ser confundido com resíduo.
19. **Sob `mock_provider`, data source de provider devolve valor sintético** — *intentional*
    (limitação do framework): assertion sobre JSON computado pelo provider passa sem verificar nada.
    Regra: policy document via `jsonencode`, ou `override_data` para tornar a ligação real (é o que a
    camada 03 faz com VPC, subnets e hosted zone). **Auditar se há outro lugar no repo com a mesma
    armadilha.**
20. **Ordenação por referência não é testável offline** — *intentional*, e é limitação de framework,
    não do código: o endpoint do Client VPN referencia
    `aws_acm_certificate_validation.vpn.certificate_arn` **para nascer depois** da validação, mas esse
    ARN é idêntico ao de `aws_acm_certificate.vpn.arn` — a mutação que troca uma referência pela outra
    **passa verde** (verificada). Está escrito no teste em vez de escondido. Só o apply pega: o sintoma
    é endpoint criado com certificado `PENDING_VALIDATION`, e aparece na conexão do operador.
21. **`connection_log_options.enabled = false` no endpoint do Client VPN** — *intentional*: logging por
    conexão exige log group, que é custo e retenção a decidir. O que se perde é a trilha de quem
    conectou quando. Hardening, não operabilidade.
22. **Portal self-service do Client VPN não configurado** — *intentional*: exige uma **segunda**
    aplicação SAML no Identity Center. Vale para a demo (a pessoa baixa a própria configuração em vez
    de receber arquivo por e-mail); fora por ora.

## How to Resume

**Primeiro comando — o SSO cai sozinho e leva os três profiles juntos** (`network` e `cicd` assumem
role a partir de `personal`):

```bash
for p in personal network cicd; do printf '%-10s ' "${p}"; aws sts get-caller-identity --profile "${p}" --query Arn --output text; done
```

ARN vazio ⟹ `! aws sso login --profile personal` (abre navegador; o agente não roda). A sessão do `az`
expira **independentemente** — conferir com `az account show`.

**Custo hoje: ~US$ 0,50/mês** (a subzona de DNS, que fica de pé de propósito). Confirmar o resto:

```bash
cd wasp-idp/aws/terraform/control-plane
terraform state list | wc --lines   # 0 = destruída; 39 = de pé (~US$ 0,23/h)
k3d cluster list                    # esperado: vazio
```

**Subir camada é por script, na ordem** (`aws/terraform/README.md` tem a tabela com custos e
dependências):

```bash
cd wasp-idp/aws/terraform
./scripts/up-all                      # 00 state-backend → 01 network → 02 dns; centavos/mês
./scripts/up-04-control-plane --yes   # ~US$ 165/mês; fora do up-all de propósito
```

Sem tty, os `up-*` salvam o plano, dizem onde está e saem com erro em vez de assumir o sim. **Plano
salvo não sobrevive à expiração de credencial** — replanejar, não reaproveitar.

Branch corrente: `feat/private-access-phase-2`. A fase 1 foi mergeada em `main` por fast-forward e
empurrada. Convenção — uma branch por fase — registrada em **In Progress**.

**O trabalho ativo é o `2.2`**, primeiro passo da cadeia que cobra por hora:

```bash
code docs/superpowers/plans/2026-08-26-private-access-and-ingress/README.md
code docs/superpowers/plans/2026-08-26-private-access-and-ingress/02-private-access.md
```

O client da VPN já está instalado nesta máquina (6.0.1, portão `2.1`). Conferir em vez de reinstalar:

```bash
aws-vpn-client --version          # 6.0.1 — se o comando não existir, alguém instalou por `latest`
systemctl is-active aws-client-vpn-daemon.service
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

**O `terraform.tfvars` local ficou desatualizado de propósito:** o `1.2` acrescentou
`public_access_cidrs` **sem default**, então qualquer `plan` falha pedindo a variável até rodar
`./scripts/generate-tfvars --force`. É a falha-fechado funcionando, não regressão.

Regressão offline (**86 testes**, 13 diretórios, 0 falhas — a lista abaixo inclui `connectivity`):

```bash
cd aws/terraform
for m in src/network src/state-backend src/pod-identity src/cluster src/nodegroup \
         src/helm/modules/external-secrets src/helm/modules/argo-cd src/helm/modules/crossplane \
         network-foundation/us-east-1 network-foundation/us-west-2 control-plane dns \
         connectivity/us-east-1; do
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
- **`curl | tr` engole a falha do `curl`** — o exit code do pipeline é o do `tr`. Mesma família do
  `PIPESTATUS[0]` do `apply`/`destroy`, em roupa nova. Sem pipe, e `--fail` para transformar HTTP ≥
  400 em exit code. E o exit code **não basta**: portal cativo devolve HTML com 200, então o formato
  do que voltou também é validado.

**Load balancer e TLS**

- **As tags de papel do LBC não têm fallback:** o controller **não examina route table** para deduzir
  público/privado (o controller in-tree examina; o LBC não). Já estão em `src/network`, com teste.
- **A tag `kubernetes.io/cluster/<nome>` é opcional a partir do LBC `2.1.2`** e só desempata entre
  clusters que compartilham a VPC — fora daqui de propósito, porque `src/network` não conhece nome de
  cluster. Inverte se um dia dois clusters dividirem uma VPC.
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
- **O client da AWS VPN roda nesta máquina, e desde a 6.0.1 é scriptável** (portão `2.1`,
  2026-08-26). Ubuntu 24.04 AMD64 é oficialmente suportado — 22.04, 24.04 e 26.04 estão na doc — e o
  build hoje é GTK/Electron, não o Mono/WPF que exigia distro antiga. O pacote instala `awsvpnclient`
  (GUI), o serviço `aws-client-vpn-daemon` e o CLI `/usr/local/bin/aws-vpn-client`, que gerencia
  perfil **sem `sudo`** e reconhece `auth-type: saml` a partir de `auth-federate`.
- **`latest` do client entrega a 5.4.1, que NÃO tem CLI.** O repo apt da doc e
  `.../GTK/latest/awsvpnclient_amd64.deb` servem a linha 5.x; o CLI só existe na **6.0.1**, que exige
  URL de versão explícita (`.../GTK/6.0.1/...`) e conferência do sha256 das release notes. Instalar
  por `latest` é **regressão silenciosa de capacidade** — o pacote instala, a GUI abre, e o
  `aws-vpn-client` simplesmente não existe.
- **`import-profile` aceita configuração que `connect` recusa.** A validação do CA acontece no
  `connect` (`Invalid configuration file`), não no import. Import bem-sucedido não prova configuração
  boa — o script `vpn` não pode tratar como prova.
- **Se `connect` sob SAML abre o navegador sozinho, ainda não se sabe.** O `--auth-user-pass` do CLI é
  usuário/senha, não SAML, e a tentativa contra endpoint sintético morreu na validação antes do túnel.
  Responde-se no `2.2`. As portas que o client reserva para SAML são **8096–8115** (não 35001).
- **`client_cidr_block` precisa de /22 ou maior**, sem sobreposição — daí `100.64.0.0/22`.
- **`transit_gateway_configuration` no endpoint do Client VPN é armadilha para quem destrói a camada
  todo dia.** O bloco existe e pareceria mais direto que associar subnet, mas o attachment que ele cria
  leva *"several hours"* para deletar, o provider **não espera**, e isso **impede deletar o TGW**.
  Associação por subnet é o caminho — e é o que põe as ENIs na VPC hub, de onde o resolver da VPC é
  alcançável (o `2.4` depende disso).
- **Subnet privada serve como target network.** A exigência de rota para o IGW é dos *Prerequisites* do
  tutorial de mutual auth, onde o túnel É o caminho de internet. Os requisitos de target network pedem
  `/27` com 20 IPs livres e uma subnet por AZ. **E a AWS acrescenta a rota local da VPC sozinha** na
  associação — a rota que se escreve é a do supernet, e as duas convivem por prefixo mais longo.
- **Aplicação SAML do Identity Center não pode ser Terraform.** *"The `CreateApplication` API only
  supports custom OAuth 2.0 applications. Creation of 3rd party SAML or OAuth 2.0 applications require
  setup to be done through the associated app service or AWS console."* O metadata XML entra por
  arquivo; o `generate-tfvars` da camada 03 imprime o roteiro quando falta.
- **O certificado do endpoint pode ser público do ACM, validado por DNS** — não precisa ser
  autoassinado importado, e isso ficou possível quando a camada de DNS entregou a subzona. Compra duas
  coisas: **nenhuma chave privada em state nem em disco**, e rotação automática que o Client VPN
  acompanha (*"whether through ACM auto-rotation..."*). O nome do certificado **não** casa com o
  hostname do endpoint, e não precisa: o client usa `remote-cert-tls server`, que confere extended key
  usage, não nome.
- **O `NameID` da assertion tem de ser e-mail.** Exigência escrita da doc de federated authentication,
  junto com: assertion e resposta assinadas, um IdP só por endpoint, sem single logout, e as portas do
  handshake reservadas na máquina do cliente.
- **As portas do handshake SAML divergem entre duas páginas da AWS:** o guia do usuário Linux diz
  `8096–8115`, o guia do administrador diz `35001`. Não afirmar uma sem conferir qual guia; o ACS URL da
  aplicação SAML usa `35001`.
- **Azure VPN Gateway leva 30–45 min para provisionar**; a subnet tem de se chamar literalmente
  `GatewaySubnet`; ASN do lado Azure é **65515**; inside CIDRs em `169.254.21.0–169.254.22.255`, `/30`
  cada.
- **Raiz com dois providers de cloud:** sem credencial do segundo, o `plan` falha mesmo para mudança
  que só toca o primeiro. Guardar atrás de `local.manage_*`.

## Next Steps

### Frente D — executar o plano (prioridade)

- [x] Plano completo, sem decisão de desenho em aberto, um arquivo por fase.
- [x] **`1.1`** — tags do LBC em `src/network`: já estavam no código; entregue o teste que faltava.
- [x] **`1.2`** — `public_access_cidrs` sem default no root, invariante no módulo, IP descoberto pelo
      `generate-tfvars`. **Offline provado (6 mutações); os dois critérios que exigem a camada 2 de pé
      seguem pendentes** — verificar na próxima vez que ela subir.
- [x] **`1.3`** — raiz `aws/terraform/dns/` **aplicada e verificada**: subzona
      `nonprod.<domínio>` (`Z087731898SD8PA9OXYR`, conta `network`) + NS na pai no Azure, delegação
      confirmada por `dig +trace` atravessando as duas clouds. **Fase 1 completa.**
- [x] **`2.1` (PORTÃO)** — **passou.** Client 6.0.1 instalado, GUI abre, CLI gerencia perfil SAML sem
      `sudo`. Derrubou a premissa de que `connect` não é scriptável. Branch
      `feat/private-access-phase-2`, a partir de `main` já com a fase 1 mergeada.
- [x] **`2.2`** — raiz `connectivity/us-east-1/` escrita: TGW isolado por default, cert público do ACM
      validado por DNS, provider SAML, endpoint, associação por AZ, rota do supernet, authorization rule
      por grupo. Mais `up-03-connectivity`, `generate-tfvars` e `destroy`. **22 testes, 13/14 mutações.**
- [x] Pré-requisito de console do `2.2` — aplicação SAML `hub-client-vpn` criada no Identity Center,
      attribute mappings salvos, grupo `platform-admins` atribuído, metadata baixado.
- [ ] **Confirmar/rodar o apply do `2.2`.** `terraform plan` já validou 12 recursos limpo; verificar
      `terraform state list` em `connectivity/us-east-1/` primeiro — pode já ter sido aplicado fora
      desta sessão. Se vazio: `./scripts/up-03-connectivity --yes` (tfvars e metadata já prontos).
      É o primeiro recurso que cobra por hora (~US$ 0,20/h com 2 associações — não ~0,15/h).
- [ ] Testar se o login SAML completa (aceite do `2.2`) e se `aws-vpn-client connect` sob SAML abre o
      navegador sozinho — nenhum dos dois foi possível verificar sem o endpoint de pé.
- [ ] **`2.3`–`2.5`** — attachment, DNS privado, fechar a API.
- [ ] Verificar os dois critérios pendentes do `1.2` na próxima vez que a camada 4 subir: o apply do
      laptop segue funcionando, e a API recusa de outro IP.
- [ ] Auditar asserções do repo que dependem de um único `override_resource` (Known Broken 16).
- [ ] **`3.1`–`3.2`** — NLB interno + gateway Istio; depois lado hub com cert e listener rule.
- [ ] **`4.1`–`4.2`** — as duas provas negativas.
- [x] Criar `aws/terraform/scripts/` — feito, com `lib` + `up-00`/`up-01`/`up-02`/`up-04`/`up-all`.
- [ ] Acrescentar `status` a `aws/terraform/scripts/` (o `platform-status` do plano): o que está de pé
      por nível e quanto custa/h. Antídoto para "esqueci ligado" e para "achei que era resíduo e
      destruí o T1".
- [ ] Acrescentar `vpn` a `aws/terraform/scripts/`: `config` exporta e importa o perfil, `status`
      confere na ordem em que quebra, `connect` chama `aws-vpn-client connect` — **scriptável**, ao
      contrário do que o plano assumia.
- [x] `up-03-connectivity` nasceu com a raiz `connectivity/`, fora do `up-all` por default.
- [ ] Abrir branch dedicada em `wasp-gitops` para os manifestos do lado cluster; path interno decidido
      na implementação.
- [ ] Atualizar a tabela de custo do T1 em `docs/superpowers/plans/.../README.md`: Client VPN cobra
      por associação de subnet, não por endpoint — o real é ~US$ 0,20/h com 2 AZs, não ~0,15/h.

### Frente E — scripts shell em inglês

- [ ] Commitar os 7 scripts já convertidos em `aws/eks/scripts/` (estão na working tree).
- [ ] Converter `aws/eks/scripts/provision-eks`, `teardown`, `aws/eks/apps/deploy`, `aws/eks/apps/clean`
      — os quatro maiores e mais arriscados; reler cada comentário de fase antes de traduzir, várias
      decisões de ordenação (races de Pod Identity) estão documentadas só ali.

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
- [ ] Auditar asserções que dependem de um único `override_resource`: elas provam o valor, não a
      ligação. Duas com valores diferentes provam. Descoberto no `1.3`.

## Completed Work

### `2.2` — a raiz `connectivity/` escrita, e três desvios que a execução impôs (2026-08-26)

TGW isolado por default, certificado do ACM, provider SAML e Client VPN completo, em
`aws/terraform/connectivity/us-east-1/`. **22 testes offline, 14 mutações, 13 capturadas.** Custo até
aqui: zero — nada tocou a AWS além de leitura de documentação.

**Três desvios do esboço, cada um por achado, não por preferência:**

- **O certificado virou público do ACM validado por DNS.** O esboço descartava a opção porque *"cert
  público exigiria o domínio, que só chega no `1.3`"* — e o `1.3` chegou. Compra nenhuma chave privada
  em state nem em disco, e rotação automática que o Client VPN acompanha. Isso **moveu o certificado de
  T0 para T1**, e o argumento sobrevive melhor: a estabilidade que importava (material de client
  inalterado entre recriações) vem da CA pública da Amazon, não da vida longa do recurso.
- **`transit_gateway_configuration` ficou de fora**, apesar de existir e parecer mais direto que
  associar subnet: o attachment que aquele bloco cria leva horas para deletar, o provider não espera, e
  isso impede deletar o TGW — incompatível com destruir a camada toda noite.
- **Subnet privada confirmada como target network.** A exigência de rota para o IGW que preocupava é dos
  *Prerequisites* do tutorial de mutual auth, não dos requisitos de target network.

**O passo que não é código, e a razão:** a aplicação SAML no Identity Center **não pode ser Terraform**
— a API `CreateApplication` só cria aplicação OAuth 2.0 customizada. O `generate-tfvars` para e imprime
o roteiro completo (ACS URL `http://127.0.0.1:35001`, audience `urn:amazon:webservices:clientvpn`,
`Subject` → `${user:email}`, `memberOf` → `${user:groups}`) em vez de deixar o apply falhar num provider
com mensagem que não explica o que falta.

**Cinco coisas aprendidas escrevendo os testes**, todas registradas em `aws/terraform/CLAUDE.md`:

- **Bloco repetível do provider costuma ser SET, não lista** — `authentication_options[0]` não compila
  (*"set elements do not have addressable keys"*). Para bloco único, `one(...)`.
- **`override_resource` substitui os atributos computados por inteiro.** Sobrescrever só o `arn` de
  `aws_acm_certificate` deixa `domain_validation_options` como set vazio, e o erro parece bug do código.
- **Validação de schema do provider roda sob `mock_provider`** — é client-side. O
  `aws_iam_saml_provider` recusa metadata com menos de 1000 caracteres no plan, então a fixture tem de
  ser realista em **tamanho**, não só em forma.
- **Validações de uma variável são todas avaliadas, não param na primeira.** Duas chamando `cidrhost`
  fazem um valor malformado produzir *"Call to function cidrhost failed"* em vez da mensagem que
  explica. Cadeia precisa de guarda `!can(...) || <condição>`.
- **Ordenação por referência não é testável offline.** O endpoint referencia
  `aws_acm_certificate_validation.vpn.certificate_arn` para nascer depois da validação, mas o ARN é
  idêntico ao do certificado — a mutação passa verde. Escrito no teste, não escondido.

O `up-all` mudou: `connectivity` saiu do "roda se o diretório existir" e virou `--with-connectivity`,
pelo mesmo critério de custo da 04. Antes, criar a raiz teria feito o `up-all` ligar ~US$ 110/mês por
default — o oposto do que o script promete.

### `2.1` — o portão do client passou, e derrubou uma premissa do plano (2026-08-26)

Branch `feat/private-access-phase-2`, a partir de `main` já com a fase 1 mergeada por fast-forward.
Custo: zero — nada tocou a AWS, só a máquina local.

**O risco que motivou o portão não existe mais.** A doc lista **Ubuntu 22.04, 24.04 e 26.04 (AMD64)**
como suportados; esta máquina é 24.04.4 x86_64 sob GNOME/X11. O client de hoje é build GTK/Electron
(o caminho de download é `/GTK/`), não o Mono/WPF que exigia distro antiga e era a origem do medo.

Instalado o **6.0.1** por URL de versão, sha256 conferido contra as release notes. `dpkg --install`
exit 0, `apt-get check` limpo, daemon `enabled`+`active`, GUI abrindo e renderizando, CLI respondendo.
Perfil SAML sintético importado, listado, lido por `get-config` e apagado — **tudo sem `sudo`**, e o
client classificou `auth-type: saml` a partir do `auth-federate`. Portas 8096–8115 livres. Nenhum
resíduo: perfil apagado, `/tmp` limpo.

**A premissa que caiu:** a decisão 3 do plano pagava como preço *"o client da AWS no Linux é aplicação
desktop, então `connect` não é scriptável"*. A **6.0.1 (12/08/2026)** instala
`/usr/local/bin/aws-vpn-client`, com `connect`, `disconnect`, `import-profile`, `get-config`,
`get-connection-status`, `list-connections`, `put-preference`. O script `vpn` deixa de ser
`config`/`status` só.

Três coisas aprendidas que valem mais que o resultado do portão:

- **`latest` é uma armadilha.** `.../GTK/latest/` e o repo apt da própria doc entregam **5.4.1**
  (25/08/2026), que **não tem CLI** — a AWS mantém o 5.x como linha default enquanto o 6.0.x é major
  mais novo e não promovido. Data maior, capacidade menor. E a falha é silenciosa: instala, a GUI abre,
  e o `aws-vpn-client` só não existe.
- **Dependência satisfeita por `Provides` conta.** O 6.0.1 declara `libgtk-3-0` e `libasound2`, que
  **não existem com esse nome no noble** — a transição t64 renomeou os dois. Instala porque
  `libgtk-3-0t64` e `libasound2t64` declaram `Provides` com versão. Conferir `apt-cache policy` do nome
  declarado e concluir "não existe, vai quebrar" é errado.
- **`import-profile` aceita o que `connect` recusa.** A validação do CA é no `connect`
  (`Invalid configuration file`), não no import. O script `vpn` não pode tratar import bem-sucedido
  como configuração válida.

**O que o portão não podia provar:** o aceite escrito no passo pedia "completa login SAML", e completar
login SAML exige o endpoint e a aplicação SAML — que são o `2.2`. O critério foi movido para lá, junto
com a pergunta que sobrou: se `aws-vpn-client connect` num perfil SAML abre o navegador sozinho.

### Sequência de provisionamento em scripts, e a camada 2 de DNS aplicada (2026-08-26)

**Fase 1 do plano completa.** A preocupação que motivou o trabalho era a sequência: a ordem das
camadas existia só na cabeça de quem já tinha rodado.

`aws/terraform/scripts/` — um script por camada, numerado pela ordem de dependência, mais `up-all`
que roda a sequência parando na primeira falha. `scripts/lib` é sourced e concentra o encanamento
(log com timestamp, `PIPESTATUS[0]`, confirmação, descoberta do bucket pelo id da Organization) —
"um script por camada" não podia significar cinco cópias disso.

A ordem, e por quê: 00 `state-backend` antes de tudo porque nenhuma outra raiz inicializa o backend
sem o bucket; 01 `network-foundation` antes de 04 porque a 04 lê a VPC hub por `tag:Name`; 02 `dns` é
independente das outras, mas pré-requisito de certificado e ingress; 03 `connectivity` ainda não
existe e o `up-all` a pula avisando; 04 `control-plane` **não entra por default** (~US$ 165/mês contra
centavos das três primeiras).

**Três armadilhas viraram guarda executável**, em vez de parágrafo de README: bucket de state
inexistente (o `up-00` para e imprime o bootstrap manual — a raiz guarda o próprio state no bucket que
gerencia, e automatizar às cegas um passo de uma vez esconde o problema); região negada pela SCP (o
`up-01` faz um `describe-vpcs` antes do primeiro `Create*`); e **zona pai que já tem NS para o label**
(o `up-02` recusa — delegação antiga colide no apply e a mensagem do Azure não diz que a causa é um
record set preexistente).

**Camada 2 aplicada e verificada.** Subzona `nonprod.<domínio>`, `Z087731898SD8PA9OXYR`, conta
`network`, 2 record sets. Delegação provada por `dig +trace`: o name server do Azure entrega a
delegação e o do Route 53 responde o SOA — a cadeia atravessa as duas clouds. Propagação quase
imediata.

Três coisas aprendidas na execução:

- **A pai já tinha uma delegação NS no mesmo formato** (`NS sandbox` → zona Azure). O `NS nonprod`
  ficou ao lado dela, apontando para o Route 53 em vez de para outra zona Azure. Nada de novo na pai —
  e foi o que justificou o guard de colisão do `up-02`.
- **O TTL 300 está no NS da PAI, não na subzona.** O `NS` dentro da zona do Route 53 nasce com 172800
  (default da AWS). Quem governa a repropagação da delegação é o da pai — que é o que se configurou.
- **A conta `network` não tem permission set**, então ver a zona no console exige switch-role para
  `OrganizationAccountAccessRole`. Já era item do backlog da Frente A; agora incomoda na prática.

### `1.3` — raiz `dns/` escrita, e o que um `override_resource` não prova (2026-08-26)

Subzona `nonprod.<domínio>` no Route 53 da conta `network` + registro NS de delegação na zona pai no
Azure DNS, numa raiz com dois providers de cloud. **9 runs, 0 falhas. `apply` pendente.**

Quatro desvios do esboço do plano, todos deliberados: `manage_delegation` é **variável** e não
`local` (um `local` não é alcançável por teste, e o propósito — desligar sem editar o resto — se
mantém); valores em `terraform.tfvars` e não inline (única raiz assim: nas outras o inline é decisão
de desenho, aqui é **identidade de quem roda**, e o repo é público); `subzone_label` como variável,
para `prod.` ser outra instância e não exceção; e `azurerm ~> 5.0`, conferido no registry em vez de
herdado do repo Azure pessoal (`~> 4.x`).

**O achado, e vale muito além deste passo: um `override_resource` testa o VALOR, dois testam a
LIGAÇÃO.** `name_servers` só existe depois do apply, então a asserção que prova
delegação-como-código precisa de override. Mas com uma lista fixa no `main.tf` igual aos valores
injetados, a asserção passa sem haver fio — e foi o que aconteceu: a mutação que colava os name
servers à mão passou **verde**. O conserto são dois runs com overrides de valores e tamanhos
diferentes; nenhuma lista fixa satisfaz os dois. Verificado nas duas direções.

**Auditar o repo por asserções com um único `override_resource`** — a de `routing.tftest.hcl` (NAT na
subnet pública) é da mesma família e já usa IDs distintos entre si de propósito, mas não foi checada
sob esta lente.

Regressão: **64 testes em 12 diretórios, 0 falhas** (eram 55).

### `1.2` — endpoint da API restrito ao IP de quem aplica (2026-08-26)

Branch `feat/lbc-subnet-discovery-tags` (o `1.2` seguiu na mesma).

**A fronteira foi a decisão do passo**, e ela se dividiu em duas por natureza do que se protege:

| Onde | O que | Natureza |
|---|---|---|
| `src/cluster` | recusa lista vazia **se** o endpoint público está ligado; recusa CIDR sem prefixo | **semântica da AWS** — vazio é `0.0.0.0/0`, e a armadilha vale para qualquer chamador |
| `control-plane` | variável **sem default**; recusa `0.0.0.0/0` mesmo explícito | **política da célula** — abrir exige editar a validação, ato visível em diff |
| `generate-tfvars` | descobre o IP em `checkip.amazonaws.com`, escreve o `/32`; `--public-access-cidr` (repetível) desliga a descoberta | o script já existia para descobrir antes de gerar arquivo |

Sem default é o que fecha o `Known Broken 3`: omitir a variável era o caminho silencioso para o
mundo, e agora é erro de validação antes de qualquer chamada à AWS. Custo do fechamento: o
`terraform.tfvars` local precisa ser regenerado.

**Seis mutações rodadas, seis capturadas.** Duas ensinaram algo:

- **Condição de `validation` tem de referenciar a própria variável.** Trocar por `true` para testar
  não deixa o teste vermelho — deixa a configuração inválida, e **nenhum run executa**. Mutação de
  validação precisa **enfraquecer** (`length(...) >= 0`), não remover. Duas tentativas foram
  perdidas nisso.
- **A invariante do módulo torna o fio do root impossível de cortar calado:** apagar o
  `public_access_cidrs = var.public_access_cidrs` deixa a lista vazia e o módulo derruba o plan no
  primeiro run. Só a mutação que passa um CIDR **válido mas errado** isola a asserção do root — e é
  ela que a justifica.

**O que NÃO foi verificado:** os outros dois critérios de aceite do passo (*o apply do laptop segue
funcionando*, *a API recusa de outro IP*) exigem a camada 2 de pé, ~US$ 165/mês. Ficam para a próxima
vez que ela subir.

Regressão: **55 testes em 11 diretórios, 0 falhas** (eram 49). Nada tocou a AWS além de um GET em
`checkip.amazonaws.com`.

### `1.1` — tags de descoberta do LBC, e a lição sobre achado não conferido (2026-08-26)

Branch `feat/lbc-subnet-discovery-tags`, a partir de `main`.

**O passo não era o que o plano dizia.** `Known Broken 1` e o `1.1` afirmavam que `src/network` não
aplicava `kubernetes.io/role/{elb,internal-elb}`. As duas tags estão no módulo desde `b32eb68`, o
commit inicial dele, com comentário explicando o propósito. O achado nasceu da comparação com o
desenho de referência — que trata as tags como flag explícita de spoke — e foi registrado como bug do
código sem ninguém abrir o `main.tf`. Atravessou duas sessões de handoff assim.

O que de fato faltava era o critério de aceite escrito no próprio passo: **nenhum dos dois arquivos de
teste olhava tag alguma**. Entregue `src/network/tests/tags.tftest.hcl`, 4 runs — perda da tag
pública, perda da privada, cruzamento das duas famílias, e inversão da ordem do `merge`.

**Quatro mutações rodadas, quatro capturas**, cada uma pela asserção pretendida. A quarta só passou a
valer depois de a `var.tags` do teste **colidir de propósito** com a tag de papel, e com o valor
errado: sem colisão, inverter `merge(var.tags, {papel})` para `merge({papel}, var.tags)` passava sem
ser notado. Todo `alltrue` tem contagem ao lado — `alltrue([])` é `true`.

Duas decisões fechadas, com a doc do EKS no lugar de memória: **a tag `kubernetes.io/cluster/<nome>`
fica fora** (opcional desde o LBC `2.1.2`, só desempata clusters que dividem VPC, e o módulo não
conhece nome de cluster); e **as tags de papel não têm fallback**, porque o LBC não examina route
table como o controller in-tree.

Regressão da árvore: **49 testes em 11 diretórios, 0 falhas** (eram 45). Custo: zero, nada tocou a
AWS.

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
