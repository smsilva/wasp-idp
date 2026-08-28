# HANDOFF

> **Arquivo único, sem par local.** Este repo não gera `HANDOFF.local.md` — a divisão
> versionado/local duplicava contexto e cada sessão tinha de reconciliar os dois (última
> consolidação: 2026-08-27). Frente ativa, estado aplicado e backlog vivem só aqui. Narrativa
> detalhada de trabalho concluído vai para `docs/archived/` (índice em `docs/archived/index.md`), não
> fica acumulando aqui.
>
> **Account IDs desta Organization estão neste arquivo, deliberadamente.** São de uma conta pessoal
> descartável para exercitar a PoC; nada aqui vai para ambiente real. E-mails de root e qualquer
> outro dado que identifique pessoa/empresa **não** entram — ficam em `CLAUDE.local.md`.
>
> **Repo público.** Não citar nomes de empresa, de projeto interno ou caminho de repo interno aqui
> nem em conversa. Dizer "a trilha corporativa". Lista de tokens proibidos e varredura em
> `CLAUDE.local.md`.

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

Snapshot de 2026-08-27, **fim da sessão do aceite `2.4`+`2.5`**, derrubado ao término. **Custo por hora
de volta a zero**, verificado por `terraform state list` (0, 0, 3, 13 — bate com o esperado).

| Camada | Conta | State key | Custo/mês | Estado |
|---|---|---|---|---|
| `state-backend` | `network` | `state-backend/` | centavos | aplicada |
| `network-foundation/us-east-1` | `network` | `network-foundation/us-east-1/` | **zero** | aplicada |
| `network-foundation/us-west-2` | `network` | `network-foundation/us-west-2/` | **zero** | aplicada |
| `control-plane` | `cicd` | `control-plane/` | ~US$ 165 (~US$ 0,23/h) quando de pé | **destruída** (state com 0 recursos) |
| `dns` | `network` + Azure | `dns/` | ~US$ 0,50 | **aplicada** — subzona `nonprod.` + RAM sharing da Organization |
| `connectivity/us-east-1` | `network` | `connectivity/us-east-1/` | ~US$ 0,20/h (~US$ 146/mês) quando de pé | **destruída** (state com 0 recursos) |

**Custo por hora agora: ~US$ 0,43/h** (0,20 da 03 + 0,23 da 04). **Derrubar na ordem inversa antes de
encerrar a sessão** — comando em How to Resume. Se esta seção ainda disser "DE PÉ" numa sessão futura,
não presumir que é o T1 de propósito (esse é só a camada 03) — a 04 nunca fica de um dia para o outro.

> **Ordem de teardown, agora exercitada e não só documentada:** `control-plane/scripts/destroy`
> **antes** de `connectivity/us-east-1/scripts/destroy`. O attachment da spoke vive no state da
> control-plane, e a AWS recusa deletar TGW com attachment vivo. O guard do `destroy` da
> connectivity impõe isso — recusa com exit 1 e nomeia quem destruir primeiro.

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

### Frente D — acesso privado + ingress centralizado (ATIVA, **Fase 2 COMPLETA, Fase 3 é a próxima**)

**Fase 2 (acesso privado) fechada 2026-08-27: aceite conjunto `2.4`+`2.5` PASSOU**, os cinco
critérios (`up-03` aplicado, túnel conectado com SAML, `up-04` aplicado com endpoint já fechado,
`dig` resolveu `10.2.x.x` de primeira, `kubectl` responde com túnel e falha por rede sem ele).
Narrativa completa, incidente de recuperação (dois applies mortos por timeout, recuperados sem
duplicata) e achados em
[`docs/archived/private-access/step-2-4-2-5-apply.md`](docs/archived/private-access/step-2-4-2-5-apply.md).

**Derrubado ao fim da sessão** — `control-plane` (14 recursos) e `connectivity` (18 recursos), 0
falhas, custo/h de volta a zero, confirmado por `terraform state list` (`0, 0, 3, 13`).

**Achado extra no teardown, corrigido na mesma sessão:** o `destroy` do `control-plane` morreu no meio
na primeira tentativa (TGW attachment/rota destruídos antes de os consumidores da API do Kubernetes
terminarem — `dial tcp ...:443: i/o timeout`), recuperado sem duplicata. Causa raiz corrigida em
`aws/terraform/control-plane/main.tf`: seis recursos de rede ganharam `depends_on` explícito nos
quatro consumidores da API (`kubernetes_config_map_v1.platform_bootstrap`, `module.crossplane`,
`module.external_secrets`, `module.argo_cd`). `validate` + 21 testes offline passam; **a aresta em si
só é provada por um `destroy` real — verificar isso na próxima vez que a camada 04 subir e descer**.

**Próxima frente: Fase 3 (ingress) — `3.1`–`3.2`, ainda não começada.** NLB interno + gateway Istio na
spoke, depois o lado hub (ALB, certificado, listener rule). Roteiro em `03-ingress.md`. Primeiro passo
prático: subir `up-all` → `up-03` → conectar túnel → `up-04` (mesma sequência da Fase 2, que agora
prova o `depends_on` novo de quebra) antes de escrever o Terraform novo da Fase 3.

**O passo de console do `2.2` continua válido e não precisa ser refeito:** aplicação SAML
`hub-client-vpn` no Identity Center (management account), attribute mappings
(`Subject`→`${user:email}`/emailAddress, `memberOf`→`${user:groups}`/unspecified), grupo
`platform-admins` atribuído. **O metadata XML NÃO sobrevive a troca de máquina/sessão** (achado do
`2.4`+`2.5`, contrariando o que esta seção dizia antes) — se `saml-metadata.xml` estiver ausente, a
aplicação já existe no Identity Center e só precisa ser rebaixada: **Applications → nome da aplicação
→ Actions → Edit configuration**, não o fluxo de criação. Roteiro completo em `02-private-access.md`.
Exemplo de formato versionado em `aws/terraform/connectivity/us-east-1/saml-metadata.xml.example`.
Ideia registrada para parar de perder esse arquivo entre sessões:
`docs/superpowers/specs/2026-08-27-saml-metadata-secrets-manager.md` (cachear no Secrets Manager).

**`aws-vpn-client` também não sobrevive a troca de máquina/sessão** (mesmo achado) — conferir sempre
com `aws-vpn-client --version`, nunca assumir pelo registro de uma sessão anterior. Reinstalar pela
mesma URL versionada (`.../GTK/6.0.1/awsvpnclient_amd64.deb`, sha256 contra as release notes oficiais)
se ausente — nunca por `latest` (entrega 5.4.1, sem CLI).

**Custo do T1 ainda por corrigir no plano:** o Client VPN cobra por **associação de subnet**, não
por endpoint. Com 2 subnets privadas do hub, o real é ~US$ 0,20/h (~US$ 146/mês), não os
~US$ 0,15/h (~US$ 110) que o `README.md` do plano documenta. Decidido manter as duas associações
(redundância de AZ).

O `~/trash/hub.ovpn` que sobrou de qualquer sessão anterior está **inválido**: a DNS name do endpoint
muda a cada recriação da camada 03, então reexportar sempre, nunca reaproveitar. Comandos nos passos
3–4 da sequência de subida, em **How to Resume**.

**Avaliação registrada, não implementada, sobre a orquestração da subida em si:** se vale trocar o
padrão bash por Terragrunt (recomendação é não trocar agora) e o alvo declarado pelo usuário de tirar
agente/humano do loop de provisionamento (pipeline de CI/CD — item já em "Targets" deste arquivo, ainda
sem desenho). Os obstáculos concretos descobertos nesta sessão (SAML manual, endpoint privado só
alcançável por VPN de operador, timeout de sessão interativa matando applies longos) estão em
`docs/superpowers/specs/2026-08-27-terraform-orchestration-tooling.md`.

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
   **Nota do `2.3`:** o Client VPN de manutenção faz **SNAT** — quem chega na spoke por ele aparece
   com IP da VPC hub. Isolar *por origem* na spoke, portanto, não distingue operador de operador;
   a distinção vive na authorization rule por grupo, do lado do endpoint.
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

**Especificação da sequência de provisionamento (2026-08-27, entregue):**
`docs/superpowers/specs/2026-08-27-provisioning-sequence.md` é a sequência autoritativa deste repo,
de `00 · accounts` (pré-Terraform) a `08 · provas de isolamento`, com o dicionário companheiro de 61
recursos (`-resource-dictionary.md` + um arquivo por recurso). Cada camada traz árvore de
dependência, contrato de `outputs:`, qual state possui o recurso e o estado (aplicado / derrubado /
escrito / planejado). **Ao acrescentar camada ou recurso, atualizar os três juntos:** sequência,
índice e arquivo do recurso — o par está checado por link e não tem órfão.

O par `2026-08-20-*` ao lado é retrato histórico do monólito Crossplane da trilha corporativa,
marcado como referência. **Não é estado deste repo** — começa na VPC e mistura conceitos que aqui
são camadas separadas.

## Comparação com desenho de referência e resolução PrivateLink vs TGW

Narrativa completa em
[`docs/archived/private-access/reference-design-comparison.md`](docs/archived/private-access/reference-design-comparison.md)
(2026-08-26). Conclusões que ficam ativas:

- Desenho de referência não tem ingress centralizado (é trânsito puro, ingress distribuído por
  spoke) — não valida "entrada pública no hub"; a decisão de ingress único pelo hub foi tomada
  sabendo disso.
- **Mecanismo de isolamento que vale copiar:** TGW sem propagação automática + route table por
  tenant ⟹ spoke↔spoke não roteia por ausência de rota, não por deny. Habilitar é aditivo.
- **PrivateLink vs TGW para ingress: resolvido a favor do TGW** (custo marginal cai a zero com a
  VPN de cliente já decidida). PrivateLink continua candidato para spoke de recursos compartilhados
  (banco, mensageria).

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
- **O SNAT do Client VPN afeta as provas negativas do `4.1`/`4.2`?** Quem chega numa spoke pelo
  Client VPN de manutenção aparece com IP da **VPC hub**, não do cliente. Logo uma prova de
  isolamento baseada em "origem X não alcança spoke Y" **não distingue operador de operador** por
  endereço — a distinção vive na authorization rule por grupo, do lado do endpoint. Verificar se o
  `4.1` como escrito ainda prova o que pretende, ou se precisa de outro vetor. **Não analisado.**
- **Fase 3 (ingress) não foi revisitada à luz do SNAT.** O caminho ALB→NLB→gateway não passa pelo
  Client VPN, então provavelmente não muda nada — mas o `X-Forwarded-For`/`numTrustedProxies` já
  era ponto de atenção ali, e vale conferir junto.
- **Quantas subnets privadas o hub tem por AZ, e o custo da associação.** A AWS cobra por associação de
  target network, então associar as duas subnets privadas dobra essa parcela em troca de redundância de
  AZ. O plano assume duas; se o custo apertar, uma resolve para PoC.
- ~~**Zona privada do endpoint do EKS** não é output do `aws_eks_cluster`~~ — **RESOLVIDO no `2.4`, e
  a pergunta estava mal posta.** A zona não é *"difícil de achar"*: ela **não aparece na conta**
  (*"managed by Amazon EKS, and it doesn't appear in your account's Route 53 resources"*). E não
  precisa ser achada — com o endpoint público desligado, o DNS **público** resolve o hostname para o IP
  privado. Nem plano A nem plano B; sobrou uma regra de security group.
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
- **Cluster naming idea (not decided):** OpenStack's TripleO project uses `Undercloud` (the
  bootstrap/control cluster that deploys and manages) and `Overcloud` (the workload cluster it
  produces) — possible naming inspiration for cluster-zero (undercloud-like) vs. per-project
  Backstage clusters (overcloud-like).

## Known Broken

Itens fechados/retirados (tags de LBC
[`1.1`](docs/archived/private-access/step-1-1-lbc-tags.md), TGW em `src/network`
[`2.3`](docs/archived/private-access/step-2-3-spoke-joins-mesh.md), existência de
`up-03-connectivity`) saíram desta lista — detalhe em `docs/archived/index.md`.

1. ~~**Endpoint da API do EKS público para `0.0.0.0/0`**~~ — **RESOLVIDO 2026-08-27.** Fechado por
   default no `2.5`, e o aceite conjunto `2.4`+`2.5` **provou o caminho privado inteiro** (apply
   completo com endpoint fechado desde a criação, `dig` resolvendo IP privado, `kubectl` falhando por
   rede sem o túnel). Detalhe em
   [`docs/archived/private-access/step-2-4-2-5-apply.md`](docs/archived/private-access/step-2-4-2-5-apply.md).
2. **Break-glass documentado, controles ausentes** — *unexpected*: MFA de root não verificado, alarme
   de uso de root não existe (falta regra EventBridge), ensaio nunca executado.
3. **Management account com `AdministratorAccess` em usuário, não grupo** — *unexpected*: migrar para
   `platform-admins` (atribuir grupo antes de revogar usuário).
4. **Credencial-raiz do Crossplane é access key de longa duração** — *intentional*, só na trilha k3d
   (sem Pod Identity; no EKS o pod usa `AWS_CONTAINER_CREDENTIALS_FULL_URI`). Mitigação pendente:
   reduzir o IAM user a só `sts:AssumeRole` (hoje `PowerUserAccess` direto).
5. **`bootstrapClusterCreatorAdminPermissions` divergente** — *unexpected*: `true` na camada 2,
   `false` no cluster do chart Crossplane. Não decidido.
6. **VPC default da `cicd` de pé em toda região**, SG aberto — *unexpected*, workload real quando a
   camada 2 sobe.
7. **Link quebrado** em `docs/superpowers/plans/2026-08-07-cluster-zero-terraform.md` →
   `infra/terraform/cluster-zero/README.md` — *intentional*, artefato da trilha Azure nunca
   construído.
8. **Valores reais em docs genéricas** — *unexpected*: account id em
   `aws/docs/bootstrap/00-crossplane-iam-user.md:91`; e-mail real em `accounts/03-provisioning.md` e
   `accounts/scripts/create-account`. Pré-existente.
9. `crossplane render` não injeta defaults do XRD — *intentional*: `providerConfigName`/
   `metadata.name` explícitos no XR de teste; `providerConfigName` é obrigatório, sem fallback.
10. `enum` de `providerConfigName` inclui `wasp-nonprod` nos XRDs versionados — *intentional*,
    trade-off vs. genericização.
11. `aws/eks/apps/echo/templates/*.yaml` falham em parser YAML puro — *intentional*, Helm templates.
12. `revoke-permission-set` só exercido no caminho feliz — ramos "atribuição/permission set
    inexistente" nunca rodaram.
13. `idp/app-config.production.yaml` `guest: {}`; `idp/packages/backend/src/index.ts` `allow-all`
    policy; `googleAuthModule.ts` `dangerouslyAllowSignInWithoutUserInCatalog: true` — *intentional*
    (PoC).
14. **Asserção com um único `override_resource` prova o valor, não a ligação** — *unexpected*,
    genérico: valor fixo no código igual ao injetado passa sem haver fio. Comprovado e corrigido no
    `1.3` (dois runs, valores/tamanhos diferentes). Auditar o resto do repo.
15. **`aws/terraform/scripts/` sem `status`/`platform-status`** — *unexpected*: nenhuma forma de
    perguntar "o que está de pé e quanto custa por hora"; perigoso com o T1 que fica de pé de
    propósito na fase 2.
16. **Sob `mock_provider`, data source de provider devolve valor sintético** — *intentional*
    (limitação do framework): assertion sobre JSON computado pelo provider passa sem verificar nada.
    Regra: `jsonencode` ou `override_data` (é o que a camada 03 faz). Auditar outros usos no repo.
17. **Ordenação por referência não é testável offline** — *intentional*/limitação de framework: a
    mutação que troca `aws_acm_certificate_validation.vpn.certificate_arn` por
    `aws_acm_certificate.vpn.arn` passa verde (ARNs idênticos). Só o apply pega — sintoma é
    certificado `PENDING_VALIDATION` no endpoint.
18. `connection_log_options.enabled = false` no Client VPN — *intentional*: custo/retenção do log
    group não decidido; perde-se a trilha de quem conectou quando.
19. Portal self-service do Client VPN não configurado — *intentional*, exige segunda aplicação SAML
    no Identity Center.
20. **Attachment cross-conta com perpetual diff em `transit_gateway_default_route_table_*`** —
    *intentional*, `ignore_changes` (atributos write-only, invisíveis ao provider default `cicd`).
    State guarda `true`; a verdade está no TGW e nas associação/propagações explícitas. Conferido na
    AWS antes de ignorar.
21. **Nenhuma prova de que spoke↔spoke não roteia** — *unexpected*, propriedade central do desenho.
    Só existe uma spoke; é o `4.1`/`4.2`.

## How to Resume

**Primeiro comando — o SSO cai sozinho e leva os três profiles juntos** (`network` e `cicd` assumem
role a partir de `personal`):

```bash
for p in personal network cicd; do
  echo "=== ${p} ==="
  aws sts get-caller-identity --profile "${p}" --output json
done
```

`--query` devolve lixo nesta máquina (wrapper `rtk`, ver `CLAUDE.local.md`) — usar `--output json` e ler
o `Account`/`Arn` inteiro, nunca `--query`. Erro de profile inexistente ou ARN vazio ⟹
`! aws sso login --profile personal` (abre navegador; o agente não roda). A sessão do `az` expira
**independentemente** — conferir com `az account show`.

**Custo por hora ao fim desta sessão (2026-08-27): zero** — as duas camadas pagas foram derrubadas
depois do aceite `2.4`+`2.5`. Não confiar nisso de memória na próxima sessão — confirmar por camada,
já que a leitura da AWS CLI nesta máquina passa por wrapper:

```bash
cd wasp-idp/aws/terraform
for m in control-plane connectivity/us-east-1 dns network-foundation/us-east-1; do
  printf '%-32s %s\n' "${m}" "$( (cd "${m}" && terraform state list 2>/dev/null | grep -vc '^data\.') )"
done
# esperado: 0, 0, 3, 13
k3d cluster list                    # esperado: vazio
```

### Subir o ambiente — a sequência está no `aws/terraform/README.md`, não aqui

Os comandos completos (7 passos: `up-all` → `up-03` → exportar/importar `.ovpn` → **conectar** →
`generate-tfvars --force` → `up-04` → provar) vivem em `aws/terraform/README.md`, seção "Sequência de
provisionamento", com custo e dependência por camada. **Ler de lá, não daqui** — a duplicata é o que
faz uma das duas ficar errada, e o README ganhou nesta sessão a seção "Manter este arquivo verdadeiro"
justamente por isso.

O que é de sessão e **não** está no README:

- **Nada garante que sobrevive entre sessões/máquinas — conferir sempre, não presumir pelo handoff.**
  Achado do `2.4`+`2.5` (2026-08-27): tanto o `aws-vpn-client` quanto o `saml-metadata.xml` que a
  sessão anterior registrava como "já instalado"/"sobrevive ao destroy" **não estavam presentes** na
  sessão seguinte. Conferir `aws-vpn-client --version` e a existência do `saml-metadata.xml` antes de
  assumir qualquer um dos dois. Reinstalar client: mesma URL versionada (`.../GTK/6.0.1/...`), nunca
  `latest` (entrega 5.4.1, sem CLI). Reobter metadata: a aplicação `hub-client-vpn` no Identity Center
  não precisa ser recriada — **Applications → nome → Actions → Edit configuration** para rebaixar.
- **`~/trash/hub.ovpn` de sessões anteriores está inválido** — a DNS name do endpoint muda a cada
  recriação da 03. Reexportar sempre.

### Aceite conjunto `2.4` + `2.5` — **PASSOU** (2026-08-27)

Não é mais trabalho ativo. Narrativa completa, comandos exatos usados e o incidente de recuperação em
[`docs/archived/private-access/step-2-4-2-5-apply.md`](docs/archived/private-access/step-2-4-2-5-apply.md).
Resumo: `dig` resolveu IP privado de primeira (sem precisar ligar/desligar o endpoint público),
`kubectl` respondeu com o túnel e falhou por timeout de rede (nunca `Unauthorized`) sem ele.

**Lição operacional para a próxima vez que algo parecido rodar:** nunca deixar um `apply`/`destroy` de
vários minutos dependurado numa chamada síncrona de ferramenta (agente ou shell interativo) — usar
`nohup ... > log 2>&1 < /dev/null & disown` (ou os scripts `up-NN`, que já fazem isso sozinhos). Um
processo morto no meio não impede recuperação (`force-unlock` + `import` + `plan` sem duplicata — a
receita está no `CLAUDE.md` de `aws/terraform/`), mas custa tempo evitável.

**Derrubar no fim do dia, sempre**, mesmo com o teste inconcluso: ordem inversa, `control-plane`
antes de `connectivity`.

`control-plane/scripts/destroy` recusa se houver XR vivo no Crossplane ou se o contexto do `kubectl`
apontar para outro cluster; o `destroy` da `connectivity` recusa enquanto houver attachment de fora do
próprio state. Contar **~10 min** no destroy da 03 (cada `aws_ec2_client_vpn_network_association` leva
7–10 min, simétrico com a criação) — não é travamento.

**Preflight antes de subir qualquer coisa:**

```bash
aws-vpn-client --version                              # 6.0.1 — ausente ⟹ alguém instalou por `latest`
systemctl is-active aws-client-vpn-daemon.service
terraform -chdir=aws/terraform/control-plane init -backend-config="bucket=tfstate-o-e4r8ndteju"
```

O `init` é necessário uma vez por máquina: o nome do bucket não é versionado, entra por
`-backend-config`. Sem tty, os `up-*` salvam o plano, dizem onde está e saem com erro em vez de
assumir o sim — usar `--yes`. **Plano salvo não sobrevive à expiração de credencial**: replanejar,
não reaproveitar.

Branch corrente: `feat/private-access-phase-2`. Convenção — uma branch por fase — em **In Progress**.

Contexto de desenho, se precisar do porquê antes de executar:

```bash
code docs/superpowers/plans/2026-08-26-private-access-and-ingress/README.md
code docs/superpowers/plans/2026-08-26-private-access-and-ingress/02-private-access.md
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

Narrativa completa de cada achado em `docs/archived/` (índice em `docs/archived/index.md`). Fato +
porquê, um por linha:

**Terraform / camadas**

- Referência funcional do provisionamento EKS são as Compositions Crossplane, não o chart
  `aws/eks/chart/templates/`.
- Corte de teardown é `hub | spoke+cluster`, nunca `rede | cluster` — Terraform destrói em ordem
  reversa só dentro do mesmo state, e o corte sobrevive ao TGW (AWS recusa deletar TGW com
  attachment vivo).
- EBS CSI pertence à abstração `Cluster` (L2b), ao lado do `eks-pod-identity-agent`.
- Trust de Pod Identity exige `sts:TagSession` além de `sts:AssumeRole`.
- `authentication_mode = "API"` — sem `aws-auth` ConfigMap.
- `Network` de referência tem as 4 subnets hardcoded em `172.16.{1,2,3,4}.0/24` — não herdar.
- Race de Pod Identity do EBS CSI não existe no Terraform — o grafo já ordena addon depois da
  association.
- Nunca fixar versão de Kubernetes/chart/addon em documento de plano — `generate-tfvars` descobre.
- `curl | tr` engole a falha do `curl` (exit code é o do `tr`) — sem pipe, `--fail`, e validar
  também o formato da resposta (portal cativo devolve HTML com 200).

**Load balancer e TLS**

- Tags de papel do LBC não têm fallback (controller não examina route table) — já em `src/network`,
  com teste.
- Tag `kubernetes.io/cluster/<nome>` é opcional desde o LBC `2.1.2` (só desempata VPC
  compartilhada) — fora de `src/network` de propósito, que não conhece nome de cluster.
- `TargetGroupBinding` aceita target group criado fora do controller — Terraform pode ser dono do
  NLB sem quebrar o apply único.
- Ler IPs privados de NLB é frágil (`aws_lb` não os expõe) — fixar com
  `subnet_mapping { private_ipv4_address = cidrhost(...) }`.
- ALB só lê certificado do ACM, nunca Secret do Kubernetes, e não valida certificado de backend —
  autoassinado basta no trecho ALB→NLB→gateway.
- Wildcard cobre um nível só (`*.*.` não existe) — daí um wildcard por cluster.
- Um NLB por cluster, não por Service — fan-out por aplicação no mesh; hub escala por listener rule.
- `X-Forwarded-For` + `numTrustedProxies`: com ALB na frente, o Istio vê o IP do ALB.

**Endpoint da API do EKS**

- **A private hosted zone do endpoint privado é invisível na conta** — a AWS a cria e associa à VPC do
  cluster, mas ela não aparece nos recursos de Route 53 da conta. Qualquer desenho que dependa de
  associá-la a outra VPC está morto na origem.
- **Com o público fechado, o DNS público resolve para IP privado.** Não precisa de Resolver inbound
  endpoint, zona própria nem `dns_servers` no Client VPN. Ressalva da doc: cluster que já existia e não
  resolve privado se corrige ligando e desligando o acesso público uma vez.
- **O que a doc exige para rede conectada por TGW é `443/tcp` no security group do CLUSTER** — é ele
  que governa o endpoint privado, e `public_access_cidrs` não o afeta. Origem: o CIDR do **hub** (SNAT).
- **`public_access_cidrs` omitido, nunca vazio, quando o endpoint público está desligado** — o provider
  só faz drift detection do atributo *"when present in a configuration"*, e `[]` brigaria para sempre
  com o `0.0.0.0/0` que a EKS guarda.
- **O `depends_on` que abre o caminho no `apply` não protege o `destroy` na direção contrária.** O TGW
  attachment e a rota da spoke podem ser destruídos antes de o Terraform terminar de remover o
  `kubernetes_config_map_v1`/`helm_release` do Crossplane, cortando a rota até o endpoint no meio do
  processo (`i/o timeout`, não credencial). Fix: `depends_on` explícito nos seis recursos de rede
  apontando para os quatro consumidores da API. Só um `destroy` real prova a aresta.

**Rede / VPN**

- TGW nasce com association/propagation default ligados — desligar os dois é o que torna
  isolamento por tenant possível.
- TGW entrega roteamento IP, não resolução de nome.
- Route table por spoke não isola cliente de cliente — precisa route table por cliente.
- Client VPN com SAML exige o client da AWS; cert de servidor obrigatório em qualquer autenticação;
  `memberOf` carrega IDs de grupo, não nomes; nunca `authorize_all_groups = true`.
- Client VPN faz SNAT — tráfego chega à spoke com origem no CIDR da VPC hub, não no client CIDR.
  Não escrever rota para o client CIDR em spoke nenhuma; liberar o CIDR do hub nos SGs de destino.
  Comprovado com pacote no `2.3`.
- Attachment cross-conta de TGW tem dois portões: RAM (`aws_ram_sharing_with_organization` +
  share/associations) e depois o aceite do attachment em si (`auto_accept_shared_attachments =
  disable`) — sem o segundo, fica `pendingAcceptance` e falha com erros que não citam a causa.
- Hipótese sobre caminho de rede se confere com um pacote, não lendo route table — no `2.3` as
  tabelas estavam certas e mesmo assim não passava.
- Client da AWS VPN roda nesta máquina e desde a 6.0.1 é scriptável (Ubuntu 24.04 oficialmente
  suportado, build GTK/Electron); instala GUI + daemon + CLI `/usr/local/bin/aws-vpn-client`
  (gerencia perfil sem `sudo`).
- `latest` do client entrega 5.4.1, sem CLI — o CLI só existe na 6.0.1, que exige URL de versão
  explícita. Regressão silenciosa: instala, GUI abre, `aws-vpn-client` não existe.
- `import-profile` aceita configuração que `connect` recusa — validação do CA é só no `connect`.
- `client_cidr_block` precisa de /22 ou maior, sem sobreposição — daí `100.64.0.0/22`.
- `transit_gateway_configuration` no endpoint do Client VPN é armadilha para quem destrói a camada
  todo dia: o attachment que cria leva horas para deletar e impede deletar o TGW. Associação por
  subnet é o caminho certo.
- Subnet privada serve como target network — exigência de rota para IGW é só do tutorial de mutual
  auth. AWS acrescenta a rota local da VPC sozinha na associação.
- Aplicação SAML do Identity Center não pode ser Terraform — `CreateApplication` só cria OAuth 2.0
  customizado. Metadata XML entra por arquivo.
- Certificado do endpoint pode ser público do ACM validado por DNS (não precisa autoassinado) —
  nenhuma chave privada em state/disco, rotação automática. Nome do certificado não precisa casar
  com o hostname (`remote-cert-tls server` confere extended key usage, não nome).
- `NameID` da assertion SAML tem de ser e-mail; assertion e resposta assinadas; um IdP só por
  endpoint; sem single logout.
- Portas do handshake SAML divergem entre guias da AWS: usuário Linux diz `8096–8115`, administrador
  diz `35001` (o que vale — ACS URL usa `35001`).
- Azure VPN Gateway leva 30–45 min para provisionar; subnet tem de se chamar `GatewaySubnet`; ASN do
  lado Azure é 65515; inside CIDRs em `169.254.21.0–169.254.22.255`, `/30` cada.
- Raiz com dois providers de cloud: sem credencial do segundo, o `plan` falha mesmo para mudança que
  só toca o primeiro — guardar atrás de `local.manage_*`.

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
- [x] **Rodar o apply do `2.2`.** Aplicado, 12 recursos, 0 falhas. TGW `tgw-09a8a60996c37ad64`,
      endpoint `cvpn-endpoint-0ed2eee5abea362d4`. De pé agora, ~US$ 0,20/h.
- [x] Testar se o login SAML completa (aceite do `2.2`) e se `aws-vpn-client connect` sob SAML abre o
      navegador sozinho — **os dois sim**, confirmado por túnel real conectado.
- [x] **`2.3`** — attachment das **duas** pontas (o hub nunca esteve anexado ao próprio TGW), RAM
      + `aws_ram_sharing_with_organization` na raiz `dns/`, accepter do attachment cross-conta,
      `tgw-rt-spoke`, as duas propagações e as rotas. **Aceito com ping real:** 3/3, RTT ~140 ms
      a um nó do EKS dentro de `10.2.0.0/16`, pelo túnel.
- [x] **`2.4`** — deixou de ser DNS: regra de `443/tcp` a partir do CIDR da VPC hub no SG do cluster.
      A zona privada do EKS é invisível na conta (plano A impossível) e o DNS público resolve para IP
      privado com o endpoint fechado (plano B desnecessário). **Escrito, 111 testes offline, 6
      mutações capturadas.**
- [x] **`2.5`** — `endpoint_public_access = false` **por default**, com a lista de CIDRs omitida (não
      vazia) quando fechado. Abrir é break-glass declarado no tfvars.
- [x] **Aceite conjunto `2.4` + `2.5` executado na AWS — PASSOU (2026-08-27).** `dig` resolveu IP
      privado de primeira (sem precisar do ligar-desligar preventivo cogitado no plano); `kubectl`
      respondeu com o túnel e falhou por timeout de rede sem ele, nunca por autenticação. **Fase 2
      completa.** Narrativa em
      [`docs/archived/private-access/step-2-4-2-5-apply.md`](docs/archived/private-access/step-2-4-2-5-apply.md).
- [x] Derrubar `control-plane` (04) — **achado real no caminho**: o primeiro `destroy` morreu com
      `dial tcp ...:443: i/o timeout` (TGW attachment/rota destruídos antes do `kubernetes_config_map_v1`
      e do `helm_release` do Crossplane terminarem). Recuperado com `state rm` dos dois + reaplicar.
      **Corrigido no código**: os seis recursos de rede que cortam o caminho ganharam `depends_on`
      explícito nos quatro consumidores da API. `validate` + 21 testes offline passam; a aresta em si
      só é provada por um `destroy` real — **verificar isso na próxima vez que a camada 04 subir e
      descer de novo** (não é testável offline, mesma limitação de "ordenação por referência").
- [x] Derrubar `connectivity` (03) — 18 recursos, 0 falhas. Custo/h de volta a zero, confirmado
      (`0, 0, 3, 13`).
- [ ] Os dois critérios pendentes do `1.2` **mudaram de forma com o `2.5`**: "a API recusa de outro IP"
      deixa de fazer sentido (não há endpoint público para recusar ninguém) e "o apply do laptop segue
      funcionando" virou o próprio aceite do `2.5`, agora **com o túnel**. Verificar na forma nova, não
      na antiga. O caminho `1.2` sobrevive só como break-glass.
- [ ] Auditar asserções do repo que dependem de um único `override_resource` (Known Broken 16).
- [ ] **`3.1`–`3.2`** — NLB interno + gateway Istio; depois lado hub com cert e listener rule.
- [ ] **`4.1`–`4.2`** — as duas provas negativas. **Antes de executar, reler o desenho delas à luz
      do SNAT** (Open Questions): prova de isolamento por endereço de origem não distingue operador
      de operador quando todos chegam com IP da VPC hub.
- [ ] **Ao final da fase 4 inteira** (não antes), gerar um **diagrama da solução completa** com a
      skill `aws-architecture-diagram-skill`: hub (TGW, Client VPN, SAML), spokes (VPC, EKS,
      attachment, `tgw-rt-spoke`), RAM sharing na management account, ingress da fase 3
      (NLB + Istio) e as propagações do TGW. **Pedido explícito do usuário nesta sessão.**
- [x] Criar `aws/terraform/scripts/` — feito, com `lib` + `up-00`/`up-01`/`up-02`/`up-04`/`up-all`.
- [ ] Acrescentar `status` a `aws/terraform/scripts/` (o `platform-status` do plano): o que está de pé
      por nível e quanto custa/h. Antídoto para "esqueci ligado" e para "achei que era resíduo e
      destruí o T1".
- [ ] Acrescentar `vpn` a `aws/terraform/scripts/`: `config` exporta e importa o perfil, `status`
      confere na ordem em que quebra, `connect` chama `aws-vpn-client connect` — **scriptável**, ao
      contrário do que o plano assumia.
- [x] `up-03-connectivity` nasceu com a raiz `connectivity/`, fora do `up-all` por default.
- [ ] Abrir branch dedicada em `wasp-gitops` (`~/git/wasp-gitops`) para os manifestos do lado cluster
      (gateway Istio como `ClusterIP` + `TargetGroupBinding`); path interno decidido na implementação.
      Repo já tem `charts/httpbin` (workload de teste) e `update-istio-charts`. `wasp-idp` não ganha
      diretório de GitOps próprio.
- [ ] Atualizar a tabela de custo do T1 em `docs/superpowers/plans/.../README.md`: Client VPN cobra
      por associação de subnet, não por endpoint — o real é ~US$ 0,20/h com 2 AZs, não ~0,15/h.

### Frente E — scripts shell em inglês

- [x] Commitar os 7 scripts já convertidos em `aws/eks/scripts/` — feito em `1a6cc34`.
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
- [x] Sequência de provisionamento e dicionário de recursos deste repo — ver Completed Work.
- [ ] Ao fechar `2.4`, `2.5` e a fase 3: mover as camadas `06` e `07` da sequência de 📋 para ✅ e
      trocar `undecided` por qual raiz possui a associação da zona privada.
- [ ] Decidir e registrar como a trilha Crossplane (`aws/eks/resources/`) converge com as camadas
      Terraform para uma spoke genérica — hoje são dois caminhos paralelos, e a sequência diz
      `undecided`.

## Completed Work

Narrativa detalhada de cada entrega concluída vive em `docs/archived/<tema>/<passo>.md`, indexada em
[`docs/archived/index.md`](docs/archived/index.md). Resumo do que já está lá, do mais recente ao mais
antigo:

- **2026-08-27** — `2.4`+`2.5` escritos e **aceitos na AWS**: SG rule para o endpoint privado do EKS,
  endpoint público fechado por default, aceite conjunto PASSOU (`dig` privado de primeira, `kubectl`
  falha por rede sem o túnel). **Fase 2 completa.** Dois applies mortos por timeout de processo,
  recuperados sem duplicata (`force-unlock`+`import`+`plan`). Especificação da sequência de
  provisionamento + dicionário de 61 recursos. Duas specs registradas, não implementadas: cachear
  `saml-metadata.xml` no Secrets Manager
  (`docs/superpowers/specs/2026-08-27-saml-metadata-secrets-manager.md`) e avaliação de orquestração —
  Terragrunt (não trocar agora) + alvo de tirar agente/humano do loop via CI/CD
  (`docs/superpowers/specs/2026-08-27-terraform-orchestration-tooling.md`).
- **2026-08-26** — `2.3` (spoke entra na malha via TGW, aceito com ping real) + teardown exercitado;
  `2.2` (apply da `connectivity/` + resolução das duas perguntas do aceite + a raiz escrita); `2.1`
  (portão do client VPN); scripts de sequência (`up-*`) + camada 2 de DNS aplicada; `1.3` (raiz
  `dns/`); `1.2` (endpoint da API restrito por IP); `1.1` (tags de descoberta do LBC); plano de acesso
  privado e ingress fechado (9 decisões); port das camadas Terraform para a trilha corporativa.
- **2026-08-25/26** — camada 2 do Terraform (`control-plane`) escrita, aplicada, verificada e
  destruída.
- **2026-08-25** — camada 1 do Terraform (`network-foundation`, bucket de state).
- **2026-08-24/25** — Frente A: contas, OUs, SCPs, CloudTrail organizacional.
- **2026-08-24/26** — Frente C: domínios de `aws/docs/`, hierarquia de fontes WAF → whitepaper → SRA.
- **2026-08-17** — bootstrap do IAM user `crossplane-poc` + hub Crossplane de pé no k3d.

> Before trusting anything time-sensitive above, run `git status`, `git diff`, and `git log` against the base branch.
