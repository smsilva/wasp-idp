# aws/eks — EKS via Crossplane (walk skeleton)

Provisiona um cluster **EKS** na AWS usando **Crossplane** rodando num **k3d** local.
Um Helm chart (`chart/`) renderiza os Managed Resources (MRs) a partir de
`chart/values.yaml`; os scripts em `scripts/` aplicam em **fases** com barreiras de
readiness (`kubectl wait`) e desmontam na ordem inversa.

A **fatia 1** (walk skeleton) provisiona o cluster e comprova `kubectl get nodes`
ponta-a-ponta (fases `10`–`60` + `70-access`). A **fatia 2** leva o cluster à paridade
com o AKS de referência; a primeira peça é a **base de EKS Pod Identity** (fase `65`
— ver [Componentes da plataforma (fatia 2)](#componentes-da-plataforma-fatia-2)).
DNS, ingress, secrets e SSO são etapas seguintes (ver o design do épico).

## Pré-requisitos

- Binários: `k3d`, `kubectl`, `helm`, `aws`.
- Credenciais de um **IAM user dedicado** do Crossplane exportadas no ambiente:
  ```bash
  export AWS_ACCESS_KEY_ID=...
  export AWS_SECRET_ACCESS_KEY=...
  ```
  A user precisa da inline policy de bootstrap `CrossplaneEksRoleManagement`
  (`providers/bootstrap-iam-policy.json`) — escopada a `role/poc-eks-*`. Ela é o
  bootstrap de admin (a user NÃO pode se auto-conceder IAM); o JSON versionado é a
  fonte de verdade. Contexto completo (conta, onde ficam as credenciais) em
  [`../CLAUDE.md`](../CLAUDE.md).
- `aws sts get-caller-identity` deve retornar sem erro (o `make check` valida).

## Uso

```bash
cd aws/eks
make check      # valida binários + credenciais AWS
make up         # k3d + Crossplane + providers + Secret/ProviderConfig das credenciais
make provision  # provisiona o EKS em fases (VPC -> ... -> NodeGroup -> Pod Identity)
make access     # AccessEntry + kubeconfig + valida kubectl get nodes
make clean CONFIRM=1   # DESTRUTIVO: remove os MRs (ordem inversa) e destrói o k3d
```

> ⚠️ **`make clean` é destrutivo e exige `CONFIRM=1`** (e o `scripts/teardown` exige
> `--yes-destroy`). O EKS leva ~28-30 min para reprovisionar, então o ambiente costuma ser
> reaproveitado entre atividades — **não** destrua por reflexo "para zerar custo". Só
> descarte quando realmente não for mais usar. Ver `CLAUDE.local.md` →
> "Ambiente AWS/EKS — NUNCA destruir sem autorização".

`make help` lista os targets. Cada target é um wrapper fino sobre um script de
`scripts/` — todos aceitam `--help` e as flags `--cluster-name` / `--cluster-id`.

### Provisionamento em fases

`scripts/provision-eks` aplica os templates `chart/templates/10-vpc` … `84-eso-config`
em ordem, esperando cada barreira de readiness antes da próxima fase (a VPC precisa
existir antes das subnets, o Cluster antes do NodeGroup, o NodeGroup antes do Pod
Identity, etc.). A fase `70-access` **não** entra aqui — depende do `callerArn` e é
papel do `make access` (`scripts/configure-access`).

### Tempos de provisionamento (medidos)

Medições reais em `us-east-1` (clusters `poc-eks-h11a`/`h11b`, 2 corridas, 2026-08).
O **control plane domina** — o restante é rápido.

| Fase | Barreira de readiness | Tempo aprox. |
|---|---|---|
| `10-vpc` | VPC Ready | < 1 min |
| `20-subnets` | 4 subnets Ready | ~3 min |
| `30-network-access` | **NAT Gateway** Ready (a barreira de rede) | ~4-5 min |
| `40-iam` | cluster/node roles Ready | < 1 min |
| `50-eks` | **control plane** Ready | **~12-15 min** ← domina |
| `60-nodegroup` | NodeGroup Ready | ~2-3 min |
| `65-pod-identity` | agent + role + association + addon EBS CSI | ~2-3 min (+ race EBS, ver abaixo) |
| `72-cluster-auth` | ClusterAuth + AccessEntry do Crossplane | ~1 min |
| `74-remote-providerconfigs` | (sem Ready — só aplica) | imediato |
| `80-eso-pod-identity` | Role + inline policy + association | ~1-2 min |
| `82-external-secrets` | `Release` do chart ESO (wait=true) | ~2 min |
| `84-eso-config` | 2 `Object` (ClusterSecretStore + ExternalSecret) | < 1 min |

**Total:** base (`10`→`65`) **~28-30 min** (control plane é o gargalo); camada ESO
(`72`→`84`) **~6-8 min**. Reusar o k3d/Crossplane já de pé (`make up` prévio) poupa só o
bootstrap local — o control plane EKS continua sendo ~12-15 min a cada provisão.

## Nome dos recursos e `.cluster-id`

Todo recurso é prefixado por **`poc-eks-<clusterId>`**. O `clusterId` é um sufixo
curto (5 chars) gerado **uma única vez** por `provision-eks` e persistido em
`aws/eks/.cluster-id` (gitignored) — reusado em re-runs para idempotência. Paridade
com o `random_string.id` da receita AKS de referência.

- Forçar um id específico: `./scripts/provision-eks --cluster-id smoke1` (grava no
  `.cluster-id`).
- `configure-access` e `teardown` leem o `.cluster-id`; `--cluster-id` sobrescreve.
- `teardown` remove o `.cluster-id` ao final **apenas** se ele bater com o id
  processado (não apaga um `.cluster-id` de outra stack passado via `--cluster-id`).

Exemplo dos nomes gerados (prefixo `poc-eks-<id>`): vpc `-vpc` · subnets
`-{public,private}-1{a,b}` · nat `-nat` · roles `-cluster-role` / `-node-role` ·
cluster `<sem sufixo>` · nodegroup `-node-group` · Pod Identity
`-addon-pod-identity-agent` / `-ebs-csi-role` / `-ebs-csi-assoc` /
`-addon-ebs-csi-driver`.

## Parâmetros (chart/values.yaml)

| Campo | Default | Observação |
|---|---|---|
| `region` | `us-east-1` | região da stack |
| `clusterName` | `poc-eks` | prefixo (compõe `poc-eks-<id>`) |
| `k8sVersion` | `1.34` | só minor (o EKS resolve o patch) |
| `cluster.endpointPublicAccess` | `true` | **spike**: control plane público (gated por IAM) |
| `cluster.publicAccessCidrs` | `[]` | vazio = `0.0.0.0/0` — **restringir em produção** |
| `vpc.cidr` | `172.16.0.0/16` | |
| `subnets.public` / `.private` | 2+2 /24 | 2 AZs (`us-east-1a/b`) |
| `nodeGroup.instanceType` | `t3.medium` | |
| `nodeGroup.desiredSize` | `3` | min 1 / max 3 |
| `providerConfigName` | `default` | ProviderConfig do Crossplane |

Override em runtime via `--set` (ex.: `--set nodeGroup.desiredSize=1`). **Segurança:**
os defaults são de spike/dev; para produção, allowlist do CIDR corporativo em
`cluster.publicAccessCidrs` **ou** `cluster.endpointPublicAccess=false` (ver o comentário
no `values.yaml`).

## ⚠️ AVISO DE CUSTO

Enquanto a stack existir, **cobra continuamente** — os maiores itens:

- **Control plane EKS** (~US$0,10/h por cluster);
- **3× `t3.medium`** (NodeGroup);
- **NAT Gateway** (hora + tráfego) + **EIP** associado.

O custo **só zera após o teardown** — um cluster esquecido de fim de semana é caro.
Mas o teardown é **destrutivo e o reprovisionamento leva ~28-30 min**: destrua quando
*decidir* descartar o ambiente, não por reflexo ao interromper uma tarefa (o cluster costuma
ser reaproveitado). **Rode `make clean CONFIRM=1`** (ou `./scripts/teardown --yes-destroy`)
quando for esse o caso. Depois confirme na AWS que não sobrou nada: `aws eks list-clusters`,
`aws ec2 describe-nat-gateways` (State != `deleted`), `aws ec2 describe-vpcs`.

> Agentes (Claude Code): **nunca** rode o teardown sem autorização explícita do usuário
> naquele momento — ver `CLAUDE.local.md`.

## Teardown

`scripts/teardown --yes-destroy [--keep-cluster]` remove os MRs na **ordem inversa** da criação
(`70-access` → `65-pod-identity` → `60-nodegroup` → `50-eks` → `40-iam` →
`30-network-access` → `20-subnets` → `10-vpc`, `sleep 5` entre fases), tolerante a erro
por fase
(`--ignore-not-found` + `|| true`), espera `kubectl wait managed --all --for=delete`
e por fim destrói o k3d — a menos que `--keep-cluster` preserve o cluster local (útil
para reaplicar sem recriar Crossplane).

Na primeira execução real contra uma stack nova, prefira rodar com `--keep-cluster`,
confirmar que `kubectl get managed` ficou vazio, e só então destruir o k3d — assim um
`kubectl wait` que estourasse o timeout com MRs ainda vivos não deixa recursos AWS
órfãos por destruir o control plane do Crossplane cedo demais.

## Pegadinhas

- **Contexto vira EKS após `update-kubeconfig`.** `configure-access` roda
  `aws eks update-kubeconfig`, que **muda o contexto kubectl ativo** para o EKS; o
  script volta sozinho para `k3d-poc-idp` ao final. Operar o Crossplane apontando
  para o EKS não funciona — sempre confirme `kubectl config current-context`.
- **Contexts órfãos no kubeconfig após o teardown.** `update-kubeconfig` deixa dois
  contexts (`poc-eks-<id>` e o ARN completo) que o `teardown` **não** remove. Limpe
  com `kubectl config delete-context <ctx>` (idem `delete-cluster` / `delete-user`).
- **`iam:ListInstanceProfilesForRole` é obrigatória para o teardown.** O provider AWS
  chama essa action ao deletar uma role (para checar instance profiles anexados). Sem
  ela, as roles ficam presas em `deletionTimestamp` com `AccessDenied` e o teardown
  trava na fase 40. Já está no `bootstrap-iam-policy.json` — descoberta exercitando o
  teardown real (a **criação** não precisava dela).
- **AccessEntry SSO usa o ARN da ROLE, não da sessão STS.** Numa sessão SSO,
  `aws sts get-caller-identity` retorna o ARN de *sessão*
  (`…:assumed-role/ROLE/SESSION`), mas o EKS exige o ARN da *role* IAM com path SSO
  (`…:role/aws-reserved/sso.amazonaws.com/…`). `configure-access` resolve isso via
  `iam get-role`.
- **`UnhealthyPackageRevision`** nos providers = versões desalinhadas
  (provider ⇄ provider-family). Ver [`../CLAUDE.md`](../CLAUDE.md).
- **VPN corporativa quebra o pull dos providers** (`x509: unknown authority` de
  `xpkg.upbound.io`). Desconectar a VPN e recriar o k3d do zero. Ver
  [`../CLAUDE.md`](../CLAUDE.md).
- **Cosmos-style "already exists"** não se aplica aqui, mas o EKS **NAT Gateway tem
  quota per-AZ** (`vpc/L-FE5A380F`) — se recriar em outra conta/região, cheque a quota
  antes.

## Componentes da plataforma (fatia 2)

A fatia 2 instala a plataforma via Crossplane, entregando um cluster **neutro e pronto
para apps** (as apps entram por helm puro, fora do Crossplane — ver o design do épico). O
primeiro componente é a **base de EKS Pod Identity** (fase `65-pod-identity.yaml`),
que espelha o padrão maduro de
`<assets-repo>` (`crossplane/providers/aws/eks`).

### Por que Pod Identity (e não IRSA/OIDC)

Pods de plataforma (external-secrets, external-dns, AWS LB Controller — histórias
seguintes) precisam assumir permissões IAM. **EKS Pod Identity** faz isso via uma
trust policy **fixa** (principal `pods.eks.amazonaws.com`), independente do **OIDC
issuer**, que é **por-cluster** e recriado a cada provisão (o da fatia 1 morreu no
teardown). IRSA/OIDC exigiria recalcular trust policies a cada recriação — fragilidade
que a fatia 1 registrou. Decisão 1 do ADR
(`docs/superpowers/specs/2026-08-12-eks-stack-aplicacao-fatia2-design.md`).

### MRs da fase 65

Todos com o prefixo `poc-eks-<id>`:

| MR | Kind (API) | Papel |
|---|---|---|
| `-addon-pod-identity-agent` | `Addon` (`eks.aws.upbound.io/v1beta1`) | Instala o **EKS Pod Identity Agent** no cluster — o DaemonSet que intercepta o `AssumeRole` dos pods. Sem ele, nenhuma `PodIdentityAssociation` resolve. Não tem role própria. |
| `-ebs-csi-role` | `Role` (`iam.aws.upbound.io/v1beta1`) | Role IAM cuja **trust policy** permite `sts:AssumeRole` + `sts:TagSession` ao principal fixo `pods.eks.amazonaws.com`. É o **molde** que ESO/external-dns/cert-manager repetem para suas roles. |
| `-ebs-csi-policy` | `RolePolicyAttachment` (`iam…`) | Anexa a managed policy AWS `AmazonEBSCSIDriverPolicy` à role (permissões de criar/anexar/deletar volumes EBS). |
| `-ebs-csi-assoc` | `PodIdentityAssociation` (`eks…v1beta1`) | Liga a role ao ServiceAccount `ebs-csi-controller-sa` (ns `kube-system`). A partir daqui os pods do driver assumem a role **via Pod Identity** — sem `serviceAccountRoleArn` (isso seria IRSA), sem OIDC. |
| `-addon-ebs-csi-driver` | `Addon` (`eks…v1beta1`) | Instala o **EBS CSI driver** (provisionamento dinâmico de volumes EBS para PVCs). A identidade vem da association acima. |

O padrão canônico **Role → RolePolicyAttachment → PodIdentityAssociation** é o que as
próximas histórias de plataforma herdam, trocando só a policy e o par ns/ServiceAccount.

### EBS CSI como consumidor-base

O **EBS CSI driver** é o primeiro consumidor de Pod Identity: permite ao cluster
provisionar volumes EBS quando um pod pede um `PersistentVolumeClaim`. Serve como
associação **real e útil** (não placeholder) para validar a base — e deixa storage
dinâmico pronto para histórias futuras (ex.: workloads com estado). É opcional:
`--set podIdentity.ebsCsi.enabled=false` instala só o agent (a base mínima), sem o
driver nem a role de exemplo.

### Race de ordering do EBS CSI — resolvida estruturalmente (fases 65 + 68)

**Histórico:** originalmente a fase `65` aplicava, num mesmo `apply`, o agent + a
Role/RPA/`PodIdentityAssociation` **e** o addon `aws-ebs-csi-driver` — sem ordem garantida.
Quando o addon subia **antes** da association resolver, os pods do `ebs-csi-controller`
nasciam sem o endpoint de credenciais e caíam em `CrashLoopBackOff` (`no EC2 IMDS role
found`), prendendo o addon em `CREATING`. O fix era um `rollout restart` manual do
controller depois que a association ficava `Ready`.

**Fix (mesmo padrão do ESO 80→82):** o addon do driver foi movido para uma fase própria
`68-ebs-csi-driver.yaml`, que o `provision-eks` só aplica **depois** de a
`PodIdentityAssociation` da fase `65` estar `Ready`. Assim os pods do controller nascem já
com `AWS_CONTAINER_CREDENTIALS_FULL_URI` injetado — sem race, sem restart manual. A fase
`65` entrega só a base de Pod Identity (agent + Role + RPA + association); a `68` entrega o
consumidor (o driver).

Se ainda assim um controller subir cedo (ex.: reaplicação parcial fora de ordem), o fix
pontual continua válido (contexto do EKS, após a association `Ready`):

```bash
eks_ctx="arn:aws:eks:<region>:<account>:cluster/${full}"   # contexto criado por 'make access'
kubectl --context "${eks_ctx}" -n kube-system rollout restart deploy/ebs-csi-controller
kubectl --context "${eks_ctx}" -n kube-system rollout status  deploy/ebs-csi-controller
```

### Validação

```bash
# clusterId gerado na provisão (prefixo dos recursos)
id="$(cat aws/eks/.cluster-id)"; full="poc-eks-${id}"

# 1. agent ACTIVE
aws eks describe-addon --cluster-name "${full}" \
  --addon-name eks-pod-identity-agent --query addon.status --output text   # ACTIVE

# 2. association listada
aws eks list-pod-identity-associations --cluster-name "${full}"

# 3. trust policy = pods.eks.amazonaws.com (sem OIDC issuer)
aws iam get-role --role-name "${full}-ebs-csi-role" \
  --query 'Role.AssumeRolePolicyDocument.Statement[0].Principal.Service' --output text

# MRs Ready no Crossplane
kubectl --context k3d-poc-idp get managed | grep -E 'addon|podidentity|ebs-csi'
```

## external-secrets (ESO) + Secrets Manager (fatia 2)

Segunda peça de plataforma: instala o **external-secrets (ESO)** no EKS e cria um
`ClusterSecretStore` provider `aws`/SecretsManager. O pod do ESO autentica no Secrets
Manager via **Pod Identity** numa Role escopada ao prefixo `poc-eks/*`. Decisão 2
do ADR (`docs/superpowers/specs/2026-08-12-eks-stack-aplicacao-fatia2-design.md`).

### A ponte Crossplane → EKS remoto

É a **primeira história que instala coisas DENTRO do cluster** — antes, o Crossplane no
k3d só criava recursos AWS (control plane). Para instalar charts e CRs no EKS, três peças
novas de plataforma (fases `72`/`74`), espelhando `<assets-repo>`:

| Fase | MRs | Papel |
|---|---|---|
| `72-cluster-auth` | `ClusterAuth` + `AccessEntry`/`AccessPolicyAssociation` do IAM user do Crossplane | `ClusterAuth` grava o Secret `<full>-kubeconfig` (token STS) em `crossplane-system`; a AccessEntry dá RBAC de cluster-admin ao **principal do Crossplane** (o `70-access` só concede ao caller SSO — são principals distintos). |
| `74-remote-providerconfigs` | `ProviderConfig` (`helm.crossplane.io`) + `ProviderConfig` (`kubernetes.crossplane.io`) | Ambos consomem o Secret kubeconfig. A partir daqui `Release` instala charts e `Object` aplica CRs no EKS. |

Requer os providers **`upbound-provider-helm`** e **`upbound-provider-kubernetes`**
(adicionados em `providers/providers-aws.yaml`; `install-providers` espera os 7 Healthy).

### MRs do ESO (fases 80/82/84)

| Fase | MR | Papel |
|---|---|---|
| `80-eso-pod-identity` | `Role` + `RolePolicy` (inline) + `PodIdentityAssociation` | Molde canônico da fase 65, trocando a managed policy por uma **inline** (`secretsmanager:GetSecretValue`+`DescribeSecret` escopada a `arn:...:secret:poc-eks/*`) e o par ns/SA para o do ESO. Trust fixa `pods.eks.amazonaws.com`. **Aplicada antes do Release** (ver pegadinha abaixo). |
| `82-external-secrets` | `Release` (`helm.crossplane.io`) | Instala o chart `external-secrets` (repo `charts.external-secrets.io`, versão 0.10.7) no ns `external-secrets`. O SA `external-secrets` é criado pelo chart e é o alvo da association da fase 80. |
| `84-eso-config` | `Object` ClusterSecretStore + `Object` ExternalSecret | CRs do ESO (`external-secrets.io/v1beta1` — o chart 0.10.7 **não** serve `v1`) aplicados via provider-kubernetes (dependem dos CRDs do `Release`). O ClusterSecretStore usa a cadeia de credenciais padrão do SDK, que no pod resolve para a Pod Identity. |

### ⚠️ Pegadinha: ordem Pod Identity → Release (elimina a race)

A validação confirmou a **mesma race da fase 65**: quando o `Release` do ESO vinha
antes da `PodIdentityAssociation`, os pods nasciam sem credencial (`AWS_CONTAINER_
CREDENTIALS_FULL_URI` ausente) e o `ClusterSecretStore` ficava `ValidationFailed`
(`NoCredentialProviders`). **Fix estrutural adotado:** a fase `80-eso-pod-identity` (a
association é recurso AWS puro, não exige namespace/SA no cluster) é aplicada **antes** da
fase `82-external-secrets` — assim o pod do ESO já nasce com a Pod Identity resolvida. Sem
`rollout restart` manual.

Se ainda assim um pod subir cedo (ex.: reaplicação parcial), o fix pontual é
`kubectl --context <eks-ctx> -n external-secrets rollout restart deploy/<release>-external-secrets`
(a `<release>` é `poc-eks-<id>`). A **fase 65 (EBS CSI)** ainda tem essa race não resolvida
estruturalmente — ver a pegadinha da seção Pod Identity acima.

### Validação (4 critérios de aceite)

```bash
id="$(cat aws/eks/.cluster-id)"; full="poc-eks-${id}"

# Pré: criar o secret de smoke no Secrets Manager (descartável)
aws secretsmanager create-secret --name poc-eks/smoke \
  --secret-string '{"token":"h11-smoke-ok"}' --region us-east-1

# 1. Release Ready + pods Running
kubectl --context k3d-poc-idp get release "${full}-external-secrets"
kubectl --context "<eks-ctx>" -n external-secrets get pods

# 2. ClusterSecretStore Valid
kubectl --context "<eks-ctx>" get clustersecretstore aws-secrets-manager \
  -o jsonpath='{.status.conditions[?(@.type=="Ready")].reason}'   # Valid

# 3. ExternalSecret materializa o Secret k8s com o valor correto
kubectl --context "<eks-ctx>" -n external-secrets get secret eso-smoke-test \
  -o jsonpath='{.data.token}' | base64 -d   # h11-smoke-ok

# 4. Isolamento: um ExternalSecret fora de poc-eks/* fica SecretSyncError (acesso negado)

# Limpeza do smoke
aws secretsmanager delete-secret --secret-id poc-eks/smoke \
  --force-delete-without-recovery --region us-east-1
```

## Ingress istio + AWS Load Balancer Controller (NLB) + cert-manager (fatia 2)

Terceira peça de plataforma: data plane de ingress via **istio ingress-gateway**, exposto
publicamente por um **NLB** que o **AWS Load Balancer Controller** materializa a partir do
`Service type LoadBalancer` do gateway, e **TLS automático** via **cert-manager** +
`ClusterIssuer` ACME Let's Encrypt (validação **DNS-01** na mesma zona Route53 compartilhada
do external-dns). Decisões 4a/4b do ADR
(`docs/superpowers/specs/2026-08-12-eks-stack-aplicacao-fatia2-design.md`).

### MRs (fases 90/92 → 94/96/98 → 100/102/104/106)

| Fase | MR | Papel |
|---|---|---|
| `90-alb-controller-pod-identity` | `Role` + `RolePolicy` (inline) + `PodIdentityAssociation` | Molde canônico (fase 65/80/86) com a policy oficial do AWS Load Balancer Controller (describe EC2/ELBv2 + criar/gerenciar NLB/ALB, target groups, listeners, regras — mutações escopadas pela tag `elbv2.k8s.aws/cluster`). Par ns/SA: `kube-system`/`aws-load-balancer-controller`. **Aplicada antes do Release** (mesma pegadinha das fases anteriores). |
| `92-alb-controller` | `Release` (`helm.crossplane.io`) | Instala `eks/aws-load-balancer-controller` (repo `aws.github.io/eks-charts`, versão 3.5.0) no ns `kube-system`. `clusterName`/`region`/`vpcId` explícitos (não depende do IMDS); subnets já carregam as tags `kubernetes.io/role/elb`/`.../internal-elb` (fase 20) para descoberta automática. |
| `94-istio-base` | `Release` | Chart `istio/base` (repo `istio-release.storage.googleapis.com/charts`, versão 1.30.3) — CRDs do istio, ns `istio-system`. |
| `96-istiod` | `Release` | Chart `istio/istiod`, mesmo ns/versão — control plane. Depende dos CRDs da fase 94. |
| `98-istio-gateway` | `Release` | Chart `istio/gateway`, ns próprio `istio-ingress` (paridade com o padrão AKS de referência). `Service type LoadBalancer` com annotations `aws-load-balancer-type: external` + `nlb-target-type: ip` + `scheme: internet-facing` → o LB Controller (fase 92) materializa um **NLB** público. |
| `100-cert-manager-pod-identity` | `Role` + `RolePolicy` (inline) + `PodIdentityAssociation` | Molde canônico, Role **própria** (não reusa a do external-dns/external-dns) escopada a `route53:ChangeResourceRecordSets` na MESMA `hostedZoneId` do external-dns + `ListHostedZones`/`ListResourceRecordSets`/`GetChange` read-only. Par ns/SA: `cert-manager`/`cert-manager`. **Aplicada antes do Release**. |
| `102-cert-manager` | `Release` | Chart `jetstack/cert-manager` (repo `charts.jetstack.io`, versão v1.21.1) no ns `cert-manager`. `crds.enabled: true` é o campo **atual** do chart (substitui o `installCRDs` legado). |
| `104-cert-manager-issuer` | `Object` (`kubernetes.crossplane.io`) | `ClusterIssuer` ACME com solver **DNS-01** via Route53 (**divergência intencional** vs. a referência AKS, que usa HTTP-01/Ingress — decisão 4b do ADR). `server` alterna staging/production por `.Values.certManager.acmeServer`. Sem bloco de credenciais explícito: resolve via Pod Identity da fase 100, igual ao `ClusterSecretStore` do ESO (fase 84). |
| `106-cert-manager-smoke` | `Object` | `Certificate` de smoke — força um ciclo ACME completo contra o `ClusterIssuer` (ver critérios de aceite abaixo). |

### ⚠️ Pegadinha: Role própria para o cert-manager, mesma zona do external-dns

O cert-manager e o external-dns miram a **mesma hosted zone Route53** compartilhada, mas
**não compartilham Role**: cada serviço tem sua própria (fase `86` vs. `100`), com trust e
escopo de policy separados. Reusar a Role do external-dns funcionaria tecnicamente (mesma
zona), mas acopla dois operadores por uma credencial comum sem necessidade — o padrão
adotado nas fases anteriores (uma Role por serviço, mesmo mirando o mesmo recurso AWS) é
mantido aqui.

### ⚠️ Pegadinha: `ReconcileError` transitório na RolePolicy/PodIdentity (resolução de referência)

Na validação, a `RolePolicy` e a `PodIdentityAssociation` do cert-manager (fase 100)
ficaram `Synced=False`/`ReconcileError` por ~3 min com `cannot resolve references: ...
referenced field was empty (referenced resource may not yet be ready)` — a `Role` do mesmo
manifesto ainda não tinha `atProvider` populado quando elas tentaram resolver a referência
(`roleRef`/`roleArnRef`). **Não é erro real:** o provider re-resolve no backoff e ambas
ficam `Ready` sozinhas assim que a Role sincroniza (mesma dinâmica observada na fase 90). O
`kubectl wait --timeout=180s` do `provision-eks` pode estourar nesse intervalo — se estourar,
**re-checar o status antes de tratar como falha** (costuma ficar Ready logo depois); sob
`set -e` num rerun, o wait que estoura mata o script, mas reexecutar retoma do ponto (as
fases são idempotentes).

### ⚠️ Pegadinha: NLB via Service annotations, não Ingress

O AWS Load Balancer Controller materializa ALB a partir de `Ingress` e NLB a partir de
`Service type LoadBalancer` com as annotations certas. Como o istio-ingressgateway expõe um
`Service` (não um `Ingress` do k8s — o roteamento L7 é feito pelos CRs `Gateway`/
`VirtualService` do istio), o NLB só nasce se as annotations (`aws-load-balancer-type`,
`nlb-target-type`, `scheme`) estiverem no chart `istio/gateway` (fase 98) — não há como
configurá-las via um `Ingress` separado.

### Validação (3 critérios de aceite)

```bash
id="$(cat aws/eks/.cluster-id)"; full="poc-eks-${id}"

# 1. AWS Load Balancer Controller Ready + NLB provisionado para o istio-ingressgateway
kubectl --context k3d-poc-idp get release "${full}-alb-controller" "${full}-istio-gateway"
kubectl --context "<eks-ctx>" -n istio-ingress get svc -o wide   # EXTERNAL-IP = DNS do NLB
aws elbv2 describe-load-balancers --region us-east-1 \
  --query "LoadBalancers[?Type=='network'].{Name:LoadBalancerName,DNS:DNSName,Scheme:Scheme}"

# 2. cert-manager + ClusterIssuer Ready (credencial Route53 resolvida via Pod Identity)
kubectl --context "<eks-ctx>" get clusterissuer letsencrypt-dns-route53 \
  -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'   # True

# 3. Certificate de smoke emitido (desafio DNS-01 resolvido -> Secret TLS Ready)
kubectl --context "<eks-ctx>" -n cert-manager get certificate cert-smoke-test \
  -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'   # True
kubectl --context "<eks-ctx>" -n cert-manager get secret cert-smoke-test-tls
```

**staging vs. production:** `.Values.certManager.acmeServer` (default `staging`) evita
rate-limit do Let's Encrypt na PoC — o certificado emitido **não é confiável no browser**
(comportamento esperado). Trocar para `production` via `--set certManager.acmeServer=production`
quando a app for exposta de verdade.

**Limpeza do smoke:** o `Certificate`/`Secret` de smoke ficam até o teardown; o registro TXT
de desafio ACME (`_acme-challenge.cert-smoke-test.<root-domain>`) na zona
compartilhada não é removido automaticamente ao deletar o `Certificate` — checar e limpar à
mão se necessário.

## Aplicações — `echo` (smoke aberto) (fatia 2)

Primeira história de **camada de aplicação**. A fronteira do ADR (decisão 5) sai aqui do
Crossplane: `echo` (httpbin) é instalado por **helm PURO, fora do Crossplane** — a plataforma
(Pod Identity → ESO → external-dns → ingress/TLS) entrega o cluster pronto e neutro; as apps são consumo dele. Os manifests vivem em
`aws/eks/apps/echo/` (chart helm) e o deploy é encapsulado em `aws/eks/apps/deploy`.

`echo` é o smoke **aberto** (sem SSO — o gate OIDC entra numa etapa posterior): exercita a plataforma-base
ponta a ponta com uma app trivial e descartável. Fluxo E2E validado:
`browser → echo.<root-domain> → Route53 (A) → NLB → istio-ingressgateway →
VirtualService → httpbin (200)`.

```bash
aws/eks/apps/deploy echo         # helm upgrade --install no contexto do EKS
aws/eks/apps/clean  echo         # helm uninstall (não toca na plataforma)
```

O script opera contra o **contexto do EKS** (`poc-eks-<id>`), não o k3d — as apps rodam no
EKS. Ele descobre em runtime, a partir do Service do ingressgateway, o que depende do cluster
corrente e injeta via `--set`:

- **`gateway.selector`** — o chart oficial `gateway` do istio-release rotula os pods do
  ingressgateway com `istio: <release-name>` = `poc-eks-<id>-istio-gateway`. **NÃO** é
  `istio: ingress` (padrão do chart AKS de referência) — usar o selector errado faz o Gateway
  não casar nenhum pod e o request morre em 503.
- **`dns.target`** — o hostname do NLB (do `.status.loadBalancer.ingress[0].hostname` do
  Service), alvo do Ingress-fantasma abaixo.

### ⚠️ Pegadinha: external-dns não vê Gateway/VirtualService → Ingress-fantasma

O external-dns da plataforma roda com `--source=service,ingress` — **não** descobre
`Gateway`/`VirtualService` istio. Para publicar o A-record, o chart cria um **Ingress
"fantasma"** (`ingressClassName: istio`, backend inexistente, path que ninguém acessa) com a
annotation `external-dns.alpha.kubernetes.io/target: <NLB>`. Esse Ingress existe **só** para o
external-dns criar o registro; o roteamento HTTP real é 100% do `Gateway`+`VirtualService`.
Mesmo truque do chart istio-gateway da referência AKS.

### ⚠️ Pegadinha: `IngressClass istio` obrigatória (webhook do LB Controller)

O AWS LB Controller roda um webhook (`vingress.elbv2.k8s.aws`) que valida **todo**
Ingress e recusa `ingressClassName` desconhecido — só existe a classe `alb` que o próprio
chart dele cria. Sem a `IngressClass istio` o deploy falha com
`invalid ingress class: IngressClass "istio" not found`. O chart cria essa IngressClass
(controller `istio.io/ingress-controller`, que **não** está ativo no istio moderno) só para o
Ingress-fantasma passar na validação — nenhum controller a processa.

### Validação (4 critérios de aceite)

```bash
id="$(cat aws/eks/.cluster-id)"; ctx="poc-eks-${id}"; host=echo.<root-domain>

# 1. pod Running (app via helm padrão) + Certificate emitido
kubectl --context "${ctx}" -n echo get pods
kubectl --context "${ctx}" -n istio-ingress get certificate echo   # READY=True

# 2. A-record + TXT de ownership (poc-eks-idp) na zona compartilhada
aws route53 list-resource-record-sets --hosted-zone-id <hosted-zone-id> \
  --query "ResourceRecordSets[?contains(Name, 'echo')]"

# 3. rota pública 200 + cadeia LE staging (cert NÃO confiável no browser é esperado)
curl -k -s -o /dev/null -w '%{http_code}\n' "https://${host}"          # 200
echo | openssl s_client -connect "${host}:443" -servername "${host}" 2>/dev/null \
  | openssl x509 -noout -issuer                                         # issuer = (STAGING) ... Let's Encrypt

# 4. acesso aberto — sem redirect de login; http→https é 302 (redirect do VirtualService)
curl -k -s -o /dev/null -w '%{http_code}\n' -L "http://${host}/status/200"   # 200
```

**Limpeza do DNS:** `clean echo` faz `helm uninstall`, mas o external-dns roda
`policy=upsert-only` e **não deleta** o A/TXT do host ao remover o Ingress-fantasma. O
registro órfão na zona compartilhada é esperado — limpar à mão só com autorização p/ mexer na
zona.

## DNS — sub-zona delegada por ambiente + wildcard (fatia 2)

Reverte o modelo de DNS da decisão 3 do ADR (zona compartilhada + registro-por-app) para
**sub-zona Route53 delegada por ambiente + wildcard** (handoff `~/trash/environment-poc-handoff.md`,
D1/D1.1). Motivação: o modelo por-app pagou dois custos estruturais do modelo compartilhado — o
**Ingress-fantasma por app** (external-dns não vê Gateway/VS) e o **DNS órfão** no teardown
(`upsert-only` não deleta). Ver o ADR-delta (2026-08-13) no design da fatia 2.

**Modelo.** A plataforma provisiona, por ambiente, via Crossplane (`provider-aws-route53`):

1. **Sub-zona** `<envid>.<root-domain>` (`Zone`), delegada da pai `aws.flow…` (que é
   Route53 desta conta — a pai `<parent-domain>` é Azure DNS, fora daqui, por isso a âncora
   é `aws.flow…` e não `flow…`).
2. **Record NS** na pai delegando a sub-zona (TTL 60).
3. **Record wildcard** `*.<envid>.aws…` A-alias → NLB do istio-ingressgateway.
4. **Certificate wildcard** `*.<envid>.aws…` (cert-manager, DNS-01 na sub-zona).

Com isso o external-dns **sai do caminho crítico das apps**: cada app precisa só de
`Gateway`+`VirtualService` (reusando o Secret do cert wildcard) — **sem Ingress-fantasma, sem
IngressClass, sem Certificate próprio**. O chart `apps/echo` ganhou o toggle `dnsMode`
(`wildcard` default | `perApp` legado); `aws/eks/apps/deploy echo --mode wildcard` monta o host
`echo.<envid>.aws…` e injeta o Secret wildcard.

### ⚠️ Pegadinha: ClusterIssuer com hostedZoneID fixo escreve o desafio na zona ERRADA

O ClusterIssuer compartilhado (`letsencrypt-dns-route53`, fase 104) tem `hostedZoneID` **fixo
na pai**. Ao emitir o cert wildcard `*.<envid>…`, o solver DNS-01 escreveu o TXT
`_acme-challenge.<envid>.aws…` **na pai** — mas quem é autoritativo por `<envid>.aws…` é a
**sub-zona**, então o Let's Encrypt não achava o TXT e o desafio ficava eterno em
`Waiting for DNS-01 challenge propagation`. **Fix:** um **ClusterIssuer por ambiente**
(`letsencrypt-dns-route53-<envid>`, fase 104 via `certManager.subZoneIssuers`) com o
`hostedZoneID` da **sub-zona** — sem tocar no issuer compartilhado (que outros certs usam). O
cert wildcard do ambiente aponta para esse issuer. A policy IAM do cert-manager (fase 100,
`certManager.extraHostedZoneIds`) precisa abranger o ARN da sub-zona, senão `AccessDenied` na
escrita do TXT.

### Validação (5 critérios — spike no `poc-eks-h11c`)

```bash
envid=h11c; sub="${envid}.<root-domain>"; ctx="poc-eks-${envid}"

# 1. delegação NS da sub-zona efetiva (a pai devolve os NS da sub-zona)
dig +short NS "${sub}" @8.8.8.8

# 2. wildcard resolve p/ o NLB — QUALQUER host, sem registro por app
dig +short A echo."${sub}" @8.8.8.8
dig +short A qualquer-coisa."${sub}" @8.8.8.8      # mesmo IP

# 3. cert wildcard Ready + cadeia LE staging
kubectl --context "${ctx}" -n istio-ingress get certificate wildcard-"${envid}"   # READY=True
echo | openssl s_client -connect echo."${sub}":443 -servername echo."${sub}" 2>/dev/null \
  | openssl x509 -noout -issuer -subject                        # CN=*.<sub>, issuer (STAGING) LE

# 4. app exposta só com Gateway+VirtualService (sem Ingress-fantasma) → 200
curl -k -s -o /dev/null -w '%{http_code}\n' https://echo."${sub}"/get

# 5. 2º host arbitrário pelo MESMO wildcard/cert (zero escrita DNS por app)
#    sobe um Gateway+VS foo.<sub> apontando ao mesmo backend → curl 200, mesmo cert,
#    e `aws route53 list-resource-record-sets ... contains(Name,'foo')` retorna []
```

**Entrega em duas etapas:** este é o **spike** (validado ao vivo no `h11c`; a sub-zona, o
wildcard, o issuer por-ambiente e o cert foram criados à mão/`kubectl` sobre o cluster de pé).
O **faseamento definitivo** no `provision-eks` (Zone/NS/wildcard/cert como fases, envid
dinâmico, IAM por-ambiente gerado, teardown ordenado — gotcha D1: Route53 não deleta zona
não-vazia) fica como história do modelo definitivo.

## Fatia 2 — próximas histórias

**SSO** (oauth2-proxy, OIDC provider externo) e deploy de `httpbin` via Helm — reusam o
padrão de exposição do `echo`, agora com o gate OIDC. Consomem a base de Pod Identity
, o ESO, o external-dns e o ingress/TLS. Ver o design do épico. O **OIDC
issuer** do cluster (não usado pela plataforma, mas disponível) sai de
`aws eks describe-cluster --query cluster.identity.oidc.issuer`.
