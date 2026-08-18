# CLAUDE.md — aws/ (poc-cloud-idp)

Contexto AWS do PoC EKS via Crossplane (ver plano em
`docs/superpowers/plans/2026-08-10-aws-eks-crossplane-walk-skeleton.md`).

> **Arquitetura de referência hub-and-spoke** (objetivo evoluído da PoC): documentação
> evolutiva em `aws/docs/` — `aws/docs/CLAUDE.md` é o índice mestre, cada domínio é uma
> subpasta com seu próprio `CLAUDE.md`. Convenção: corpo genérico com placeholders
> (`<supernet>`, `<hub-asn>`); valores reais da conta que executa a PoC não são versionados.
> Primeiro domínio pronto: `network/`.

> **Convenção de genericização:** valores por-conta/segredos (account id, zone ids, domínio,
> e-mail) usam placeholders `<...>`; identificadores estruturais que precisam ser YAML/Crossplane
> válido (API groups como `platform.example.com`, nomes `poc-eks`) usam valores genéricos
> concretos — **nunca** `<...>` em campo executável. Valores reais desta conta ficam em
> `CLAUDE.local.md` na raiz do repo (gitignored).

## Conta AWS

- Conta `<account-id>` (pode **não ser isolada** — assumir que já hospeda infra de outros
  sistemas: RDS, IAM users provisionados via Terraform etc.). Não assumir que é uma conta
  dedicada ao poc-idp; só os recursos com prefixo `poc-idp/` ou `crossplane-poc` são nossos.

## IAM user dedicada (Crossplane)

- `crossplane-poc` — IAM user dedicada criada manualmente via `aws iam create-user`
  (não reusar credenciais de outros ambientes/tenants, ex. `<iac-spike>`). Policies:
  - **`PowerUserAccess`** (managed) — cobre EC2/VPC/EKS etc., mas via `NotAction: iam:*`
    **exclui todo o namespace IAM**. Basta para a rede, mas a fase 40-iam
    (criar Roles do cluster) falha com `AccessDenied` em `iam:GetRole`/`CreateRole`.
  - **`CrossplaneEksRoleManagement`** (inline) — complementa a lacuna de IAM, escopada a
    `arn:aws:iam::<account-id>:role/poc-eks-*` (só as Roles do nosso cluster; não alcança
    roles de outros times). Documento versionado: `aws/eks/providers/bootstrap-iam-policy.json`.

  **Bootstrap (galinha-e-ovo):** a própria user NÃO consegue se auto-conceder IAM — tem
  `implicitDeny` em `iam:PutUserPolicy`/`iam:CreateRole` (confirmado via
  `aws iam simulate-principal-policy`). Logo o grant de IAM é **bootstrap manual de admin**
  (mesma categoria de criar a user), não um MR do Crossplane. Reaplicar em máquina/conta
  nova:
  ```bash
  aws iam put-user-policy --user-name crossplane-poc \
    --policy-name CrossplaneEksRoleManagement \
    --policy-document file://aws/eks/providers/bootstrap-iam-policy.json
  ```
  O JSON versionado é a fonte de verdade do estado desejado; o `put-user-policy` é o
  passo de bootstrap (feito por quem tem `AdministratorAccess`).

  **`iam:ListInstanceProfilesForRole` é obrigatória só no teardown** (não na criação): o
  provider AWS chama essa action ao **deletar** uma Role para checar instance profiles
  anexados. Sem ela, as Roles travam em `deletionTimestamp` com `AccessDenied` e o teardown
  paralisa na fase 40. Já está no `bootstrap-iam-policy.json` — **não remover** ao revisar
  a policy só testando a criação.
- Credenciais (access key) guardadas no **Secrets Manager** desta conta, região
  `us-east-1`, secret `poc-idp/crossplane-poc-credentials` (JSON
  `{"aws_access_key_id": "...", "aws_secret_access_key": "..."}`). Recuperar sempre inline,
  nunca persistir em arquivo — ver seção "Operação: credenciais AWS via CLI" abaixo.
- **Nunca** commitar essas credenciais em texto plano no repo; o Secrets Manager é a
  fonte de verdade, não arquivos locais como `/tmp/.crossplane-poc-env`.
- **Fatia 2 — DNS fixado:** external-dns e cert-manager (DNS-01) usam a hosted zone
  Route53 **pública existente** `<root-domain>` (id `<hosted-zone-id>`,
  `us-east-1`). Zona compartilhada com outros times → external-dns SEMPRE com
  `--txt-owner-id=poc-eks-idp`, `--domain-filter=<root-domain>` e
  `--zone-id-filter=<hosted-zone-id>`. Secrets da fatia 2 no prefixo `poc-eks/*`.
- Nomenclatura: o Secret de auth do Crossplane chama-se `aws-iam-credential` (não
  `aws-sp-credential` — "SP"/Service Principal é termo Azure, não existe em AWS; a
  credencial vem de um IAM user).

## Fluxo de bootstrap do hub (k3d) — ordem dos scripts

O hub Crossplane sobe em 4 passos idempotentes (`aws/eks/scripts/`), nesta ordem:

1. **`install-crossplane`** — cria o cluster k3d `poc-idp` (3 servers) + instala o Crossplane.
2. **`install-providers`** — aplica os 8 Providers (`providers/providers-aws.yaml`) e espera `Healthy`.
3. **`install-functions`** — aplica as 4 Composition Functions (`providers/functions.yaml`:
   patch-and-transform, environment-configs, auto-ready, kcl) e espera `Healthy`. **Pré-requisito
   de qualquer Composition em `resources/`** — todas rodam `mode: Pipeline` e falham sem elas.
   Só `patch-and-transform` é exigida pela `Network`; as outras 3 são de cluster/environment.
4. **`configure-aws-creds`** — cria o Secret `aws-iam-credential` (a partir de
   `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` no env) + aplica o `ProviderConfig` default.

Só depois destes 4 é que faz sentido aplicar XRD/Composition/claim (ex.: `resources/network/`
+ `examples/current/01-network.yaml`) — esse passo cria recursos AWS reais (VPC + NAT = custo).

## Gotcha: VPN corporativa quebra o pull dos pacotes do Crossplane

- Com a VPN da organização ativa, o k3d/Crossplane falha ao baixar os pacotes de
  `xpkg.upbound.io` de duas formas distintas e cumulativas: (1) `x509: certificate
  signed by unknown authority` na resolução de manifest/digest (a VPN intercepta TLS
  com a CA corporativa, que não está no trust store do node nem no do pod do
  Crossplane) e (2) mesmo depois de corrigir o TLS, `read: connection reset by peer`
  durante o pull das camadas da imagem (rede da VPN reseta transferências maiores).
- **Fix real: desconectar a VPN e recriar o cluster do zero** (`k3d cluster delete` +
  `install-crossplane` + `install-providers`) — sem VPN, os 5 providers instalam e
  ficam `Healthy` sem nenhum patch manual de CA cert ou DNS. Não tente contornar via
  patch de CA/resolv.conf enquanto a VPN estiver ativa; é retrabalho descartável.

## Gotcha (RESOLVIDA): race de Pod Identity do EBS CSI — fases 65 + 68

- **Era:** a fase `65-pod-identity` aplicava addon + role + association + **driver EBS** num
  mesmo apply, sem ordem garantida. Se o addon `aws-ebs-csi-driver` subia antes da
  `PodIdentityAssociation` resolver, os pods do `ebs-csi-controller` nasciam sem credencial,
  caíam em `CrashLoopBackOff` (`no EC2 IMDS role found`) e o addon travava em `CREATING`.
  Isso também **matava o `provision-eks`** (o `kubectl wait` do addon estourava sob `set -e`,
  antes das fases 72+ — confirmado 2× na a validação).
- **Fix (mesmo padrão do ESO 80→82):** o addon do driver foi movido para a fase própria
  `68-ebs-csi-driver.yaml`, aplicada pelo `provision-eks` só **depois** de a association da
  fase `65` estar `Ready`. Os pods do controller nascem já com
  `AWS_CONTAINER_CREDENTIALS_FULL_URI` — sem race, sem restart manual. A fase 65 entrega só
  a base (agent + Role + RPA + association); a 68 entrega o consumidor.
- **Fix pontual (se ainda ocorrer por reaplicação fora de ordem):** com a association
  `Ready`, `kubectl rollout restart deploy/ebs-csi-controller` no contexto do EKS. Comandos
  no `aws/eks/README.md`.

## Gotcha: `provision-eks` longo excede o timeout de uma chamada Bash

- `make provision` leva 20-30 min (NAT ~3 + control plane ~15 + nodegroup ~5 + Pod
  Identity ~3). Rodar tudo numa única chamada de shell com teto de ~10 min mata o
  processo no meio do `kubectl wait` do control plane — o Crossplane no k3d **continua**
  reconciliando (é ele quem cria, não o script), mas as fases seguintes (nodegroup, Pod
  Identity) nunca são aplicadas. Sintoma: nenhum processo `provision-eks`/`kubectl wait`
  vivo, porém MRs `SYNCED=True` e control plane `CREATING`/`ACTIVE`.
- **Fix:** `provision-eks` é idempotente — reexecutar retoma (fases prontas passam como
  `unchanged`/`condition met`) e avança. Rodar em background ou em janelas por fase para
  não reesbarrar no teto. Com a ponte Crossplane→EKS a corrida ficou mais longa (+ ClusterAuth + Release do
  ESO + config); o mesmo cuidado vale.

## Secrets Manager — prefixo `poc-eks/*` (fatia 2)

- Os secrets consumidos pela plataforma/apps da fatia 2 vivem no prefixo **`poc-eks/*`**
  (região `us-east-1`). A Role Pod Identity do ESO (`<full>-eso-role`) tem inline policy
  escopada a `arn:aws:secretsmanager:us-east-1:*:secret:poc-eks/*` — ler fora do prefixo
  é negado (isolamento). Não confundir com `poc-idp/crossplane-poc-credentials` (as
  creds do IAM user do Crossplane, prefixo `poc-idp/`).
- Secret de smoke do ESO (`poc-eks/smoke`) é descartável: criar antes de validar, apagar
  com `delete-secret --force-delete-without-recovery` depois (ver `aws/eks/README.md`).
- **IAM de bootstrap já cobre o ESO:** a inline policy da Role do ESO é anexada via
  `iam:PutRolePolicy` (+ `GetRolePolicy`/`DeleteRolePolicy`/`ListRolePolicies`), todas já
  presentes no `CrossplaneEksRoleManagement` (escopo `role/poc-eks-*`). **Nenhum grant de
  IAM novo** foi necessário — confirmado no `bootstrap-iam-policy.json`. Se um apply real
  acusar `AccessDenied` em alguma action de secrets/IAM não listada, documentar aqui e
  re-`put-user-policy` (bootstrap de admin).

## Ponte Crossplane → EKS remoto (fatia 2)

- A partir do ESO o Crossplane (no k3d) passa a gerenciar recursos **dentro** do EKS via
  os providers `provider-helm` e `provider-kubernetes`, autenticando pelo Secret
  `<full>-kubeconfig` que o MR `ClusterAuth` grava em `crossplane-system`. Para esse
  kubeconfig ter RBAC, o IAM user do Crossplane (`crossplane-poc`) ganha uma
  `AccessEntry`/`AccessPolicyAssociation` de cluster-admin (fase `72`) — principal
  distinto do caller SSO do `70-access`. O `crossplaneArn` é derivado em runtime por
  `provision-eks` via `aws sts get-caller-identity` (as creds exportadas SÃO do user do
  Crossplane, então o ARN vem direto, sem o rodeio de sessão SSO do `configure-access`).
- **Creator NÃO ganha admin automático:** o cluster nasce com `authenticationMode: API`
  **sem** `bootstrapClusterCreatorAdminPermissions`, então o `crossplane-poc` (que
  criou o cluster) NÃO tem RBAC até a fase `72` aplicar sua `AccessEntry`. `aws eks
  update-kubeconfig` + qualquer `kubectl` contra o EKS falha com "the server has asked for
  the client to provide credentials" antes da fase 72 estar `Ready`. Se precisar de acesso
  ao EKS cedo (ex.: race da fase 65 destravar addon), aplicar a fase 72 manualmente antes.

## Gotcha (benigno): `Responsive=False`/`WatchCircuitOpen` durante provisionamento de XR

- Durante o provisionamento de um XR com muitos MRs (ex.: `Network`, 16 MRs), a condition
  `Responsive` pode ir a `False` com reason `WatchCircuitOpen` e mensagem "Too many watch
  events from Subnet/... Allowing events periodically". É **throttling interno do Crossplane
  v2** (proteção contra volume de watch events), **não falha** — resolve sozinho para
  `Responsive=True`/`WatchCircuitClosed` quando o XR fica `Ready`. Não tratar como erro;
  olhar `Synced`/`Ready`, não `Responsive`.

## Gotcha: chart external-dns — `zoneIdFilters` não é value first-class

- O chart `external-dns/external-dns` v1.15.2 **não tem** `zoneIdFilters` como value
  de topo (fica vazio em silêncio, sem erro) — o filtro de zone-id só existe via
  `extraArgs: ["--zone-id-filter=<id>"]`. `domainFilters` já é value nativo, mas
  `zoneIdFilters` não. Confirmar sempre nos logs do pod (`ZoneIDFilter:[<id>]`), não
  só no manifest aplicado.
- Route53 não suporta resource-level scoping nas actions de leitura
  (`ListHostedZones`, `ListResourceRecordSets`, `ListTagsForResources`) — exigem
  `Resource: "*"` na inline policy. Só `ChangeResourceRecordSets` aceita
  `Resource: arn:aws:route53:::hostedzone/<id>`. Isolamento real vem do
  `--zone-id-filter` + `--txt-owner-id`, não da IAM policy de leitura.
- `policy: upsert-only` faz o external-dns **nunca** deletar registros
  automaticamente — nem quando o Service/Ingress que os gerou é removido. Limpeza de
  registros de teste/smoke exige `aws route53 change-resource-record-sets` manual com
  `Action: DELETE`.

## Operação: credenciais AWS via CLI (evitar bloqueio do classifier)

- **NUNCA persistir as creds do Crossplane em arquivo** (`/tmp/...env`) nem extrair o Secret
  `aws-iam-credential` do k3d para o shell — o auto-mode classifier bloqueia (Credential
  Materialization/Exploration) e o próprio repo proíbe. Recuperar sempre **inline** e só na
  memória do processo, no mesmo comando que usa a AWS CLI:
  ```bash
  set -a
  source <(aws secretsmanager get-secret-value \
    --secret-id poc-idp/crossplane-poc-credentials --region us-east-1 \
    --query SecretString --output text \
    | jq -r '"AWS_ACCESS_KEY_ID=" + .aws_access_key_id, "AWS_SECRET_ACCESS_KEY=" + .aws_secret_access_key')
  export AWS_DEFAULT_REGION=us-east-1; unset AWS_PROFILE AWS_SESSION_TOKEN
  set +a
  ```
  Pré-requisito: SSO admin ativo (`aws sso login`) para o `get-secret-value` do bootstrap.
- **Nunca imprimir tokens**, nem truncados: `aws eks get-token ... | head -c N` é bloqueado.
- `provision-eks`/`teardown` longos: rodar em **background** com as creds carregadas inline
  no mesmo shell (as exportações não persistem entre chamadas Bash separadas).

## Camada de aplicação (helm puro) — `aws/eks/apps/` (fatia 2+)

- Apps (echo/httpbin) são **helm puro FORA do Crossplane** (ADR decisão 5). Scripts
  `deploy`/`clean` operam contra o **contexto do EKS** (`poc-eks-<id>`), não o k3d.
- **Gateway selector** = `istio: <clusterName>-<clusterId>-istio-gateway` (o chart oficial
  `gateway` do istio-release rotula os pods pelo nome do Release), **NÃO** `istio: ingress`
  (padrão do chart AKS de referência). Selector errado → Gateway não casa pod → 503.
- Kinds istio no cluster são `networking.istio.io/v1` (não `v1alpha3`).

## Gotcha: external-dns não vê Gateway/VirtualService istio

- external-dns roda `--source=service,ingress` (config imutável da plataforma) e **não**
  descobre `Gateway`/`VirtualService`. No modo por-app (legado): um **Ingress-fantasma**
  (`ingressClassName: istio`, backend inexistente + annotation
  `external-dns.alpha.kubernetes.io/target`) publica o A-record. O webhook do AWS LB
  Controller recusa Ingress sem IngressClass conhecida → o chart cria a `IngressClass istio`
  (controller `istio.io/ingress-controller`, inativo) só p/ o Ingress passar na validação.
- Modelo preferido: sub-zona wildcard elimina o Ingress-fantasma — app só precisa de
  Gateway+VirtualService.

## DNS: sub-zona delegada por ambiente + wildcard (fatia 2)

- Âncora sob `<root-domain>` (Route53 desta conta), **não** `<parent-domain>`
  (Azure DNS, fora da conta — delegar lá exigiria console Azure por ambiente, não self-service).
- Sub-zona `<envid>.<root-domain>` via `provider-aws-route53` (Kinds `Zone`
  `route53.aws.upbound.io/v1beta1`, `Record` `v1beta2`; Route53 é global — `Zone` **não** tem
  campo `region`). NS delegado da pai (TTL 60) + wildcard `*.<envid>` A-alias → NLB
  (canonical ELB zone `us-east-1` = `Z26RNL4JYFTOTI`).
- **Gotcha do ClusterIssuer com hostedZoneID fixo:** o issuer compartilhado
  `letsencrypt-dns-route53` aponta para a pai — o solver DNS-01 do cert wildcard escreve o TXT
  de desafio na PAI, mas a SUB-ZONA é autoritativa → LE não acha o TXT, desafio eterno em
  `Waiting for DNS-01 challenge propagation`. **Fix:** ClusterIssuer **por-ambiente**
  (`letsencrypt-dns-route53-<envid>`, `certManager.subZoneIssuers`) com hostedZoneID da
  sub-zona; a policy IAM do cert-manager (fase 100, `certManager.extraHostedZoneIds`) precisa
  incluir o ARN da sub-zona. **Nunca** editar o ClusterIssuer compartilhado (classifier bloqueia
  e outros certs dependem dele).
- **DNS wildcard/cert NÃO cobrem o apex:** `*.h11c…` cobre `foo.h11c…` mas não `h11c…`; o SAN
  `*.h11c…` idem. Para roteamento por path no apex (`h11c.aws…/health`): Record A do apex +
  cert com o apex no SAN + Gateway/VS no host apex.

## Gotcha: `network/composition.yaml` tem VPC CIDR HARDCODED (bloqueia hub-and-spoke)

- Toda instância de `Network` nasce com `cidrBlock: 172.16.0.0/16` fixo — incompatível com
  hub-and-spoke (VPCs sobrepostas). Decisão de migração, gap e base de CIDR alvo:
  `aws/docs/network/07-mapa-crossplane.md` (Gap 1) e `01-enderecamento-cidr.md`.
