# Terraform Bootstrap Module — Design

## Contexto

O bootstrap da PoC AWS é feito hoje por um cluster k3d local: `install-crossplane` sobe
Crossplane, `install-providers` instala 8 providers, e o chart `aws/platform/charts/hub`
renderiza um XR `Network` que cria a VPC hub. Isso é um degrau de bootstrap consciente e
divergente do alvo — a Fase 2 de `decisions.md` §8 prescreve que a rede hub e o cluster de
plataforma venham de **Terraform**, não de Crossplane rodando num cluster descartável.

Este design define o módulo Terraform que fecha essa divergência. Não existe nenhum `.tf`
em `aws/` — é greenfield.

Referências, em ordem de autoridade:

1. **As Compositions Crossplane do repositório de referência interno — a especificação
   funcional.** A decomposição do monólito `environment-eks` em três abstrações (`Network`,
   `Cluster`, `ClusterBootstrap`) é o que o Terraform traduz. O caminho local do repo e os IDs
   dos tickets citados estão em `CLAUDE.local.md` (não versionado). Não usar as fases do chart
   `aws/eks/chart/templates/` como referência: são a mesma coisa numa forma menos decomposta e
   com bugs já corrigidos do outro lado.
2. `/home/silvios/git/azure-kubernetes/examples/cluster_argocd_ingress_istio/` — referência de
   **estrutura** apenas: raiz compõe submódulos de `src/`, flags `local.install_*`, e por addon o
   tripé *workload identity → role assignment → helm module*.
3. `decisions.md` §7 (cardinalidade × churn) e §8 (Fase 0 e Fase 2).
4. `aws/docs/compute/05-gitops.md` — ArgoCD como satélite e o padrão de connection secret.

## A decisão que bloqueava o design

**Pergunta:** no módulo de escopo fino, o ArgoCD sobe sem ingress, ou istio + cert-manager +
external-dns entram no Terraform para ele nascer com URL e TLS?

A binária estava mal-posta. Decompondo o requisito real — configurar OIDC no ArgoCD — as
dependências não são as do trio:

| Peça | Depende de | Depende de DNS/TLS? |
|---|---|---|
| Client ID | app registration no Google | não |
| Client secret em `argocd-secret` | mecanismo de entrega de secret | **não** |
| `url` em `argocd-cm` + redirect URI | endpoint estável | **sim — só esta** |

O exemplo Azure não passa o client secret pelo Terraform: `extra-objects.yaml` cria um
`ExternalSecret` que faz merge de `oidc.azuread.clientSecret` dentro do `argocd-secret`, e
`sso.yaml` referencia com `clientSecret: $oidc.azuread.clientSecret`. **O entregador do secret
é o ESO, não o Terraform** — e o ESO não depende de DNS (Pod Identity → role → Secrets
Manager). A numeração das fases já codificava isso: `80/82/84` (ESO) vêm antes de `86/88`
(external-dns) e `100/102` (cert-manager).

Quanto à URL: o único consumidor no bootstrap é humano, olhando status de sync. `port-forward`
basta, e o Google aceita `http://localhost` como exceção documentada ao HTTPS — este repo já
prova o caminho, com o Backstage usando `http://localhost:7007/api/auth/google/handler/frame`.

**Decidido:** ArgoCD sobe **sem ingress**, com `ClusterIP` + `port-forward`. **ESO entra** no
escopo do Terraform. **istio, cert-manager, external-dns e ALB controller ficam fora**, para
GitOps, quando a decisão de domínio existir.

Rejeitado: paridade total com o exemplo Azure (acopla o módulo à delegação de
`wasp.silvios.me`, que está aberta) e o padrão seed cluster / hub-of-hubs (`decisions.md` §7 —
cria dependência de disponibilidade e não elimina o Terraform, só o esconde).

## Escopo

A fronteira do escopo fino cai **exatamente na terceira abstração**. `Network` e `Cluster`
entram inteiros; da `ClusterBootstrap` entra só um pedaço da camada L4.

| Abstração | Camadas | No Terraform |
|---|---|---|
| `Network` | L1a — 16 MRs, VPC→RTA | **inteira**, duas vezes (hub e spoke) |
| `Cluster` | L1c IAM + L2 EKS/addons/ponte | **inteira**, com a ponte L2c colapsada |
| `ClusterBootstrap` | L3 Route53 + L4 Releases + L5 Objects | **só ESO da L4**, + ArgoCD e Crossplane |

**Dentro:** VPC hub (`network`) e VPC spoke (`cicd`); roles de cluster e de node com seus
attachments; EKS; node groups; addon `eks-pod-identity-agent`; role + policy + association +
addon do EBS CSI; `AccessEntry` + `AccessPolicyAssociation`; ESO (Pod Identity + inline policy +
Helm release); ArgoCD (Helm release, sem ingress); Crossplane core + Pod Identity da role de
origem; ConfigMap de contrato Terraform→GitOps.

**Fora, por GitOps:** toda a L3 (zona Route53, delegação NS, wildcard A-alias) e toda a L5
(ClusterIssuers, Certificate wildcard, Gateways). Da L4: istio, cert-manager, external-dns, ALB
controller, echo. Mais providers, functions e ProviderConfigs do Crossplane.

**Correção ao que eu disse antes:** o driver EBS CSI **não** é adição minha ao escopo. Ele é L2b
da abstração `Cluster`, ao lado do `eks-pod-identity-agent`, com role própria
(`<full>-ebs-csi-role`), `AmazonEBSCSIDriverPolicy`, association em
`kube-system/ebs-csi-controller-sa` e o addon `aws-ebs-csi-driver`. Entra por pertencer à
abstração, não por julgamento meu — desconsiderar a sugestão de cortá-lo.

**Fora, sem dono ainda:** Global Accelerator e endpoint group (Fase 1, pulada — escopo atual é
só projetos internos), TGW e attachments (Gap 2, migração aditiva futura), IPAM (Fase 0 item 3).

## Tradução da Composition para Terraform

O inventário abaixo é o que a `Cluster` cria hoje, com o equivalente Terraform. Três linhas
**colapsam** — não têm recurso correspondente porque resolvem limitações do Crossplane que o
Terraform não tem.

| Composition (`Cluster`) | Terraform |
|---|---|
| `Role` cluster-role + `RolePolicyAttachment` `AmazonEKSClusterPolicy` | `aws_iam_role` + `aws_iam_role_policy_attachment` |
| `Role` node-role + 3 attachments (`WorkerNode`, `ECRReadOnly`, `EKS_CNI`) | idem — **uma role compartilhada por todos os node groups** |
| `eks.Cluster`, `accessConfig.authenticationMode: API` | `aws_eks_cluster` com `access_config { authentication_mode = "API" }` |
| `eks.NodeGroup` (lista) | `aws_eks_node_group` com `for_each` |
| `Addon` `eks-pod-identity-agent` | `aws_eks_addon` |
| Role + policy + `PodIdentityAssociation` + `Addon` do EBS CSI | `src/pod-identity` + `aws_eks_addon` |
| `AccessEntry` + `AccessPolicyAssociation` (`AmazonEKSClusterAdminPolicy`) | `aws_eks_access_entry` + `aws_eks_access_policy_association` |
| `ClusterAuth` → Secret kubeconfig no hub | **colapsa** → providers `kubernetes`/`helm` a partir de `aws_eks_cluster_auth` |
| 2 `ProviderConfig` remotos (helm, kubernetes) | **colapsa** → mesmos providers |
| ~40 `ClusterUsage` (16 papéis de rede × N node groups + caminho de acesso × 2 PCs) | **colapsa** → grafo de dependências implícito |

### Por que as ClusterUsage desaparecem

O grafo de `ClusterUsage` existe por causa do **bug do NLB órfão no teardown**: no teardown, o alb-controller (um
pod num nó) precisa do egress *pod → subnet privada → NAT → IGW → API do ELB* para deletar o
NLB. Se a rede sair concorrente, sobra NLB órfão travando a VPC. Como `Network` e `Cluster` são
XRs distintos, o Crossplane não tem aresta de dependência entre eles — `matchControllerRef` só
casa o mesmo owner, que era o bug do desenho antigo. As usages são uma aresta construída à mão.

Terraform destrói em ordem reversa de dependência nativamente. **Mas isso só vale se a rede e o
cluster estiverem no mesmo grafo** — ou seja, no mesmo state.

**Constraint que isso impõe à camada:** a VPC spoke **nunca** pode ser separada do state do
cluster. O corte de duas camadas é seguro porque é `hub | spoke+cluster`, não
`rede | cluster`. Separar `network | cluster` reintroduziria esse bug com um mecanismo pior
(sem `ClusterUsage` para compensar). Está registrado aqui porque é o tipo de refatoração que
parece inócua depois.

O hub fica em outro state e isso é seguro **hoje** porque não há TGW: os nós não roteiam pelo
hub. Quando o TGW entrar (Gap 2), a aresta hub↔spoke passa a existir e este raciocínio precisa
ser revisitado.

### Detalhes concretos herdados da referência

- **`authentication_mode = "API"`** — sem `aws-auth` ConfigMap. Só access entries.
- **Trust de Pod Identity precisa de `sts:TagSession`**, não só `sts:AssumeRole`. A referência
  tem os dois; um trust só com `AssumeRole` falha.
- **`resolve_conflicts_on_create/update = "OVERWRITE"`** nos addons — torna a reaplicação
  idempotente quando o addon já existe de uma provisão anterior.
- **Subnets do control plane são as 4** (2 públicas + 2 privadas), mínimo 2 AZs, e a lista é
  **imutável** depois de criado o cluster. Node groups usam só as 2 privadas.
- **`public_access_cidrs` vazio significa `0.0.0.0/0`.** Default de SPIKE/dev na referência;
  restringir é hardening pendente, não default.

### Um gap da referência que não vamos herdar

A `Network` tem `vpcCidr` parametrizável mas as 4 subnets são **fixas** em
`172.16.{1,2,3,4}.0/24` — trocar o CIDR sem trocar as subnets quebra o provisionamento, e a
própria doc marca "parametrizar as subnets é follow-up". Nosso plano de CIDR é
`10.0.0.0/12` com um `/16` por spoke (`aws/docs/network/01`), então `src/network` **calcula as
subnets a partir do CIDR** com `cidrsubnet()` desde o início. Herdar o hardcode aqui custaria a
única decisão irreversível da cadeia.

## Camadas e state

Duas camadas, dois states, pelo mesmo eixo que decidiu Terraform vs Crossplane:

| Camada | Conta | Cardinalidade | Churn |
|---|---|---|---|
| `network-foundation` | `network` (`094289743086`) | 1 por região | ~zero |
| `platform-cell` | `cicd` (a criar) | 1 por região | baixo, mas > foundation |

A `platform-cell` lê o foundation por **`data` source** (tag/nome da VPC, não `terraform_
remote_state`): desacopla o state e sobrevive ao foundation ser reescrito ou migrado.
`terraform destroy` da cell não toca no hub — é a armadilha de "ordem inversa no teardown" do
§7 resolvida por construção, não por disciplina.

Rejeitado: um módulo único com providers com alias (acopla hub e cluster no mesmo state) e três
camadas com addons separados (YAGNI — os addons do escopo fino são dois e morrem com o
cluster).

### Bootstrap do state backend

A Fase 0 item 5 (bucket de state + roles OIDC) não existe. Sequência:

1. `network-foundation` roda com **state local** e cria, entre seus recursos, o bucket S3 de
   state com versionamento, BPA e SSE.
2. `terraform init -migrate-state` move o próprio state para o bucket que acabou de criar.
3. `platform-cell` já nasce com backend S3.

Bloqueio de state via `use_lockfile = true` no backend S3 — recurso do **backend** do Terraform
(estável desde 1.11), não do provider AWS. Dispensa a tabela DynamoDB dedicada do padrão
antigo.

## Pré-requisito: a conta `cicd`

O módulo põe o EKS de plataforma na conta `cicd`, OU `Deployments`. Ela **não existe na AWS** —
foi decidida e escrita nos scripts, nada aplicado. Não há atalho: mover EKS entre contas é
rebuild, não move.

**A Frente A vira pré-requisito duro da Frente B.** Antes de qualquer `terraform apply`:

```bash
cd aws/docs/accounts/scripts
./create-organizational-unit-structure
./create-account --name cicd --ou deployments --email <cicd-account-email>
```

Rejeitado: subir o control plane em `wasp-nonprod` porque já existe — contradiz a decisão de OU
e gasta o rebuild depois.

**Efeito colateral favorável:** o módulo põe na `cicd` apenas ArgoCD, Crossplane e ESO — tudo
build/validate/promote/release. Isso resolve a conflação de `decisions.md` §2 (que listava
`auth` e `discovery` na mesma spoke) na direção segura, por construção. Se `auth`/`discovery`
forem para lá depois, a conta deixa de ser `Deployments` e a decisão 6 do §11 precisa ser
reaberta.

## Layout de diretórios

```
aws/terraform/
├── src/
│   ├── network/                  # ≡ XR Network (L1a) — VPC, subnets, IGW, NAT, RTs
│   ├── state-backend/            # bucket S3 de state (só o foundation usa)
│   ├── cluster/                  # ≡ XR Cluster (L1c+L2a) — IAM roles, EKS, access entries
│   ├── nodegroup/                # ≡ XR Cluster (L2a) — for_each sobre a lista
│   ├── pod-identity/             # ≡ molde L2b — role + trust + policy + association
│   └── helm/modules/             # ≡ XR ClusterBootstrap (L4), recortado
│       ├── external-secrets/
│       ├── argo-cd/
│       └── crossplane/
├── network-foundation/           # raiz camada 1 — conta network
│   ├── main.tf  variables.tf  outputs.tf  locals.tf
└── platform-cell/                # raiz camada 2 — conta cicd
    ├── main.tf  variables.tf  outputs.tf  locals.tf
```

`src/network` é um só submódulo para hub e spoke — a diferença é CIDR e, no futuro, o
attachment de TGW. Reuso real, não coincidência de nome.

Flags em `locals.tf` da raiz, no estilo do exemplo Azure:

```hcl
locals {
  install_external_secrets = true
  install_argocd           = true
  install_crossplane       = true
  install_argocd_oidc      = false   # exige secret no Secrets Manager
  install_app_of_apps      = false   # igual ao exemplo Azure
}
```

## O tripé de identidade

O equivalente AWS de *workload identity → role assignment → helm* é **Pod Identity association
→ inline policy → Helm release**, e as fases `65`, `80/82`, `86/88`, `100/102` já estão
organizadas assim. O submódulo `src/pod-identity` encapsula o molde canônico da fase `65`:

```
entrada:  cluster_name, namespace, service_account_name,
          policy_json (inline) | managed_policy_arns (gerenciadas)
saída:    role_arn
recursos: aws_iam_role — trust em pods.eks.amazonaws.com,
          com Action = ["sts:AssumeRole", "sts:TagSession"]
          aws_iam_role_policy / aws_iam_role_policy_attachment
          aws_eks_pod_identity_association
```

`sts:TagSession` no trust não é opcional — a referência tem as duas actions, e um trust só com
`AssumeRole` falha.

O trust é **fixo** — não depende do OIDC issuer, que é por-cluster e recriado a cada provisão.
Propriedade herdada da referência e deliberada: mantém o submódulo estável entre recriações.

O submódulo aceita policy inline **ou** ARNs de policy gerenciada porque a referência usa as
duas formas: EBS CSI usa a gerenciada `AmazonEBSCSIDriverPolicy`, ESO usa inline escopada a
prefixo do Secrets Manager.

Consumidores no escopo fino:

| Consumidor | ns / ServiceAccount | Policy |
|---|---|---|
| EBS CSI | `kube-system` / `ebs-csi-controller-sa` | gerenciada `AmazonEBSCSIDriverPolicy` |
| ESO | `external-secrets` / SA do chart | inline: `secretsmanager:GetSecretValue` em prefixo |
| Crossplane | `crossplane-system` / SA do chart | inline: `sts:AssumeRole` nas roles de destino |

**A association do ESO é criada antes do Helm release** (mesmo encadeamento das fases 80→82): a
association é recurso AWS puro, não exige que namespace e ServiceAccount existam, então o pod
nasce já com credencial e a race desaparece sem rollout restart.

### O que isso aposenta

A role do Crossplane via Pod Identity **elimina a access key de longa duração** —
`Known Broken` #3 e o desvio de [SEC02-BP02](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/sec_identities_unique.html).
O bloqueio registrado era "k3d não suporta Pod Identity"; com o control plane em EKS, o
bloqueio cai. O IAM user `crossplane-poc` e o secret
`poc-idp/crossplane-poc-credentials` deixam de ser o caminho de credencial.

Granularidade, conforme `aws/docs/security/08-control-plane-identity.md`: **1 role de origem por
control plane** (Pod Identity) + **1 role de destino por conta-alvo** (IAM é global) + **zero**
para o EKS de workload gerenciado.

## Contrato Terraform → GitOps

O Terraform sabe coisas que o GitOps precisa (ARN da role do Crossplane, IDs de conta, região,
IDs de subnet) e o GitOps não pode descobrir sozinho sem chamar a AWS. O seam é um **ConfigMap**
escrito pelo Terraform no namespace `crossplane-system`:

```yaml
kind: ConfigMap
metadata:
  name: platform-bootstrap
data:
  region:                  us-east-1
  clusterName:             <nome>
  hubVpcId:                <id>
  spokeSubnetIds:          <csv>
  crossplaneRoleArn:       <arn da role de origem>
  networkAccountId:        "094289743086"
  targetAccountIds:        <csv>
```

É o mesmo padrão de contrato do connection secret em `compute/05` — produtor publica, consumidor
lê, e trocar o produtor não muda o contrato. Os `Application`s do app-of-apps que instalam
providers, functions e ProviderConfigs leem daqui.

**Por que providers e functions ficam fora do Terraform:** versão de provider é churn alto (8
providers, release frequente), e a instalação leva ~4 min por causa de pressão de patch no
apiserver. Terraform esperando isso é `apply` de 10 min que falha por timeout; ArgoCD
reconciliando é o comportamento correto para recurso que converge devagar.

## ArgoCD sem ingress

| Aspecto | Valor no bootstrap |
|---|---|
| Service | `ClusterIP` |
| Acesso | `kubectl port-forward svc/argocd-server -n argocd 8080:443` |
| `argocd-cm` `url` | `http://localhost:8080` |
| Conta `admin` local | **habilitada** — break-glass |
| OIDC | opcional (`install_argocd_oidc`), redirect `http://localhost:8080/auth/callback` |
| app-of-apps | `install_app_of_apps = false` por default |

Quando OIDC estiver ligado, o client secret vem do Secrets Manager via ESO, com merge em
`argocd-secret` — nunca por variável Terraform, que o poria no state em claro.

A conta `admin` local permanece habilitada de propósito: se a `Application` que auto-gerencia
`argocd-cm` aplicar OIDC errado, ela é o único caminho de volta. Mesmo raciocínio do break-glass
de [SEC03-BP03](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/sec_permissions_emergency_process.html)
já documentado em `aws/docs/accounts/04-cross-account-access.md`.

Quando o domínio for decidido, a migração é aditiva: GitOps instala o trio, o `url` do
`argocd-cm` é reescrito para o FQDN, e um segundo redirect URI é adicionado no Google. Nada do
módulo muda.

## Teardown

Ordem obrigatória: **cell antes de foundation**.

Dentro da cell, a ordenação é **de graça** — é o grafo de dependências do Terraform, e é por isso
que as ~40 `ClusterUsage` do teardown ordenado não têm tradução. Não recriar esse mecanismo à mão.

O que **não** é de graça: os XRs que o Crossplane criar **dentro** do cluster depois do
bootstrap. Eles não estão no state do Terraform — o Crossplane é quem os reconcilia, e destruir
o cluster primeiro deixa recurso AWS órfão sem controlador. É a armadilha "ordem inversa no
teardown" do §7, e o Terraform não a resolve porque não sabe que eles existem.

Decisão: **documentar, não automatizar.** Provisioner de destroy-time é frágil (roda com o
provider já parcialmente destruído) e a falha dele é pior que a do humano — deixa state
inconsistente. O runbook no README da raiz lista os passos; a guarda automatizada (Usage API do
Crossplane ou fitness function) fica para quando existirem XRs de verdade em produção.

Observação de escopo: como o escopo fino **não** instala istio nem ALB controller, o NLB órfão
desse bug não existe neste módulo — não há NLB. O problema volta quando a L4 completa chegar
por GitOps, e aí ele é do GitOps, não do Terraform.

## Verificação

O script determinístico de acompanhamento — equivalente ao
`azure-kubernetes/scripts/follow-creation/follow`, com `wait_until` compondo checadores
pequenos e idempotentes — **é necessário e ganha design próprio**. Este módulo só se
compromete a expor os outputs que ele consome:

```
cluster_name  region  argocd_namespace  eso_namespace  crossplane_namespace
kubeconfig_command
```

Testes do próprio módulo, em ordem de custo:

1. `terraform fmt -check` e `terraform validate` — sem credencial.
2. `terraform plan` contra as contas reais — custo zero, valida provider, permissão e
   `data` source.
3. `terraform apply` real — **só sob autorização explícita.** Custo: EKS control plane
   ~US$ 73/mês, NAT gateway ~US$ 32/mês + tráfego, mais os nodes. É o "custo alto" que o
   handoff sinaliza; hoje o custo da PoC é zero.

## Riscos e itens que continuam abertos

| Item | Efeito neste módulo |
|---|---|
| Delegação de `wasp.silvios.me` para Route53 | **nenhum** — foi o ponto da decisão. Bloqueia só as fatias DNS/ingress/TLS. |
| Teto de 15 spokes no plano de CIDR (`10.0.0.0/12`) | o módulo consome 2 `/16` (hub e spoke de plataforma). Única decisão irreversível da cadeia. |
| Session tags em `assumeRoleChain` não verificado | afeta a opção 2 de contenção regional, não o escopo fino. |
| Parametrização dos valores de `CLAUDE.local.md` | o módulo os recebe como `variables`; a origem (tfvars? SSM?) fica para depois. |
| Orquestrador `environment/` BLOCKED | irrelevante aqui — o módulo não usa XRs. |
| Rebuild do IAM user `crossplane-poc` para só `sts:AssumeRole` | fica **obsoleto** se o módulo entrar antes; é mitigação para a janela em que o k3d ainda é o control plane. |

## Próximo passo

Plano de implementação via `superpowers:writing-plans`. Nenhum código antes disso.
