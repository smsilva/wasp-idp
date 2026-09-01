# Terraform — bootstrap da plataforma AWS

Substitui o bootstrap por k3d + Crossplane. Desenho em
`docs/superpowers/specs/2026-08-25-terraform-bootstrap-module-design.md`; decisão da raiz
regional em [ADR 0014](../../docs/adr/0014-single-regional-root-composing-hub-and-cell-modules.md).

## Manter este arquivo verdadeiro

**Este README é a sequência executável.** Quem chega sem contexto segue o que está aqui e espera que
funcione; uma linha desatualizada aqui não é doc velha, é comando que falha no meio, às vezes com
recurso já criado atrás. Já aconteceu duas vezes antes da raiz regional existir, e a razão não muda
com o desenho novo.

Atualizar junto com a mudança, no mesmo trabalho — não depois:

| Mudou isto | Atualizar aqui |
|---|---|
| Script novo ou renomeado (`up-NN`) | bloco de comandos, tabela da sequência, `## Raízes`, `## Ordem de teardown` |
| Pré-requisito novo que **não é Terraform** (console, túnel, SCP) | linha `—` própria na tabela da sequência, com o que ele custa e de quem depende |
| Passo que muda o que um `apply` **exige** para completar | o bloco de comandos, e não só a prosa: quem lê copia o bloco |
| Guarda nova num script | `### Armadilhas que os scripts pegam antes de tocar em nada` |
| Custo por hora de um módulo | tabela da sequência **e** `## Custo` (as duas divergem calado) |
| Região nova aplicada de verdade | coluna `Exercitada` em `## Raízes`, tabela de CIDR |
| **Raiz nova** (pasta com backend próprio) | linha em `## Raízes` — sem ela a raiz é indescobrível, e o README dela também: a `ci/` ficou fora da tabela e a documentação dos workflows foi escrita de novo em outro arquivo por isso |

**O que NÃO entra aqui:** o que está de pé agora, IDs de recurso, valores da conta. Isso é estado de
sessão e vive em `HANDOFF.md` — repetir aqui garante duas fontes e uma delas errada. Armadilhas de
código e de comportamento de provider vão para `CLAUDE.md`, não para este arquivo.

**Contagem de testes também não entra** — em nenhum arquivo versionado. O número muda a cada módulo
novo, envelhece sozinho e não informa decisão nenhuma: o que importa é `0 falhas`, e quem quer o
total roda o loop.

Ao fechar um passo de plano que muda a sequência, a checagem é uma pergunta só: **alguém que só leia
este README consegue subir o ambiente hoje?**

## Os dois eixos: ordem e permanência

**Ordem** é o prefixo numérico dos scripts (`00`, `01`/`02`...) — o que roda antes do quê. **Permanência**
é T0/T1/T2 — custo e ciclo de vida. São eixos independentes: não confundir "roda depois" com "custa
mais" ou "fica de pé mais tempo".

| Ordem | Camada | Permanência | Terraform? |
|---|---|---|---|
| — | Organization, contas, OUs, SCP, Identity Center | T0 | não — `aws/docs/accounts/scripts/` |
| — | *aprovar a região na SCP* | — | não |
| — | `ci/` — trust OIDC GitHub → AWS | T0 | sim |
| 00 | `up-00-state-backend` | T0 | sim |
| 01 | `up-01-dns` | T0 | sim |
| — | *aplicação SAML no Identity Center* → `variables/saml-metadata.xml` | — | não, é console |
| 02 | `up-02-region` → `module.hub` | **T1** | sim |
| — | *conectar o túnel do Client VPN* | — | não |
| 02 | `up-02-region --with-cell` → `module.cell` | **T2** | sim |
| — | providers e Compositions do Crossplane | T2 | não — GitOps |

`module.hub` e `module.cell` dividem o mesmo passo `02` (mesma raiz, `regions/<região>/`) e têm
permanências diferentes: o hub é o repouso da região (fica de pé), a célula sobe/valida/desce. A
fundação da Organization não ganha um `up-00` próprio — `up-NN` significa "raiz Terraform,
idempotente, roda sozinha", e a fundação roda uma vez na vida (e-mail de root único, app SAML por
console). Ela entra como bloco acima do `up-*`, na ordem que `aws/docs/accounts/` já estabelece.

A aplicação SAML é **uma para toda a Organization**, não uma por região — o ACS URL do Client VPN é
`http://127.0.0.1:35001` em qualquer endpoint. É o que permite a uma região nova ter Client VPN sem
um segundo passo de console, e o motivo de o metadata morar em `variables/`.

## Provisionar via GitHub Actions

O workflow `.github/workflows/provision-region.yml` roda `up-02-region --with-cell` em CI,
autenticado por OIDC.

**[`ci/README.md`](ci/README.md) é o documento único da automação**, dos dois lados: o trust
GitHub→AWS (a raiz `ci/`, aplicada uma vez por um admin), as variables e secrets do repositório com
o motivo de cada um, o GitHub App que dá acesso ao composite action privado, os três workflows e os
exemplos de execução via `gh`. Para a sequência completa do zero, incluindo esse bootstrap no lugar
certo da ordem, ver [`bootstrap-checklist.md`](bootstrap-checklist.md).

## Sequência de provisionamento

Um script por camada em `scripts/`, mais `up-all`, que roda a sequência parando na primeira falha, e
`down-cell`, o teardown noturno da célula.

```bash
cd aws/terraform

./scripts/up-all                               # 00 + dns, centavos/mês
./scripts/up-all --with-cell                   # inclui a célula (~US$ 165/mês)
```

`up-all` sempre aplica o hub (é o repouso da região, ~US$ 110/mês); a célula só entra com
`--with-cell`, e exige o túnel do Client VPN conectado primeiro — os providers `helm`/`kubernetes`
falam com o API server a partir desta máquina durante o apply.

**Roteiro completo de operação do túnel (exportar `.ovpn`, importar profile, conectar, diagnosticar):**
[`aws/docs/vpn/client-vpn-operations.md`](../docs/vpn/client-vpn-operations.md).

| # | Script | Raiz | Depende de | Custo/mês | Nível |
|---|---|---|---|---|---|
| — | — | *aprovar região na SCP* | — | zero | **pré-requisito, não é Terraform** |
| — | — | *preencher `variables/values.tfvars`* | — | zero | **pré-requisito de toda raiz, não é Terraform** |
| — | — | *aplicação SAML no Identity Center* | — | zero | **pré-requisito da célula, é console** |
| 00 | `up-00-state-backend` | `state-backend/` | — | centavos | T0 |
| 01 | `up-01-dns` | `dns/` | 00 | ~US$ 0,50 | T0 |
| 02 | `up-02-region` (hub) | `regions/<região>/` | 00, dns | ~US$ 110 | T1 |
| — | — | *conectar o túnel do Client VPN* | hub | +US$ 0,05/h | **pré-requisito da célula, não é Terraform** |
| 02 | `up-02-region --with-cell` | `regions/<região>/` | hub + túnel conectado | ~US$ 165 a mais | T2 |

**A ordem não é preferência.** `00` antes de tudo porque nenhuma outra raiz inicializa o backend sem
o bucket; `dns` antes do hub porque o certificado do endpoint da VPN valida por DNS na subzona que
ele delega; o hub antes da célula porque o caminho até a API do cluster **é** o túnel do Client VPN.

**Para CI (ou qualquer chamador não-interativo) sem túnel do Client VPN:** `--public-cidr <cidr>`
abre o endpoint público da API do EKS restrito a esse CIDR só para o apply da célula, e
`--close-public-access` fecha de novo — nenhuma infraestrutura de rede nova, é o mesmo
break-glass abaixo, só que setado por flag em vez de editar `variables/values.tfvars`. As duas só
valem com `--with-cell`, e são mutuamente exclusivas. Ver
`docs/superpowers/specs/2026-08-31-github-actions-runner-private-access-design.md` para o desenho
completo e as limitações aceitas (sem sweep de fechamento agendado; break-glass manual e de CI
compartilham o mesmo atributo — não usar os dois ao mesmo tempo).

**Desbloqueio de emergência, se o túnel não estiver disponível:** descomentar
`endpoint_public_access = true` e `public_access_cidrs = ["<ip>/32"]` em `variables/values.tfvars`
abre o endpoint público só para o CIDR declarado à mão. É break-glass declarado em arquivo, não
default — não há descoberta do IP desta máquina.

**A célula não entra no `up-all` por default e é derrubada toda noite** (`down-cell`) — T2. Não
presumir resíduo e destruir; e não esquecer ligada entre sessões de trabalho.

### Aprovar a região vem antes, e não é Terraform

```bash
aws/docs/accounts/scripts/apply-baseline-service-control-policy --regions us-east-1,us-west-2
```

Sem isso, um `apply` fora das regiões aprovadas falha no primeiro `Create*` com
`explicit deny in a service control policy`, e o erro **parece bug de código**. `--regions` vale
para a Organization inteira — não há como liberar região só numa conta por essa via.

### Armadilhas que os scripts pegam antes de tocar em nada

| Armadilha | Onde | O que o script faz |
|---|---|---|
| Bucket de state inexistente | `up-00` | **Para** e imprime o bootstrap manual (state local → apply → `init -migrate-state`). A raiz guarda o próprio state no bucket que gerencia; automatizar às cegas um passo de uma vez só esconde o problema |
| Sem tty (pipe, CI, harness de agente) | qualquer script com `--yes` opcional | O `read` volta vazio na hora e o cancelamento pareceria decisão de quem rodou. O script **salva o plano, diz onde está e sai com erro**, apontando o `--yes` |

### O encanamento comum fica em `scripts/lib`

Sourced, não executado. Log com timestamp em `<raiz>/logs/` (gitignored — a saída carrega account
id, ARN e endpoint reais), `PIPESTATUS[0]` para o `tee` não mascarar falha, confirmação antes de
qualquer apply, e descoberta do bucket a partir do id da Organization.

### Descida

```bash
cd aws/terraform/scripts
./down-cell --region <região> --yes          # rotina, todo dia — mantém o hub de pé
```

`down-cell` destrói só `module.cell` (`-target`); é o teardown de rotina. Derrubar a região inteira
(hub incluso — TGW, Client VPN, ALB) não é rotina, e não tem script próprio de propósito: a
assimetria é intencional.

**Via GitHub Actions:** `.github/workflows/teardown-region.yml` dispara `down-cell
--public-cidr <runner-egress-ip>/32` (abre o endpoint para o refresh alcançar a API) seguido de
`down-cell --close-public-access` com `if: always()`. Esse caminho não sofre da armadilha de RBAC
(item 2 abaixo): a role `github-actions-provision` é quem criou o cluster, então já tem
`AccessEntry`. Ver `ci/README.md` para o bootstrap OIDC e `bootstrap-checklist.md` para a sequência
completa do zero.

```bash
cd aws/terraform/regions/<região>
terraform init -backend-config="bucket=<state-bucket-name>"   # se a raiz não estiver inicializada
nohup terraform destroy -no-color -auto-approve > /tmp/destroy-<região>.log 2>&1 < /dev/null &
disown
```

Antes de derrubar uma região que hospeda célula, conferir que o Crossplane não tem XR vivo (ver
"Ordem de teardown" abaixo). Derrubar o hub muda o DNS name do ALB e do Client VPN — invalida o
`.ovpn` exportado e reescreve os registros alias das células no apply seguinte.

**Duas armadilhas de um `terraform destroy` da região inteira rodado por um humano, sem o túnel
do Client VPN — nenhuma delas aparece via `provision-region.yml` ou `teardown-region.yml`, que já
as evitam por desenho:**

1. **Todo `destroy` faz *refresh* antes de decidir o que apagar, e o refresh lê os recursos
   Kubernetes através do endpoint ATUAL.** Se ele estiver fechado (rotina de encerrar a sessão) e
   não houver túnel conectado, o `destroy` morre logo no início com
   `dial tcp <ip-privado>:443: i/o timeout` — mesma causa do gotcha "ordem endpoint-vs-refresh do
   `terraform plan`" do CI (`CLAUDE.md`), só que fora do `apply`. Fix: abrir o endpoint restrito ao
   IP de quem roda antes do destroy —
   `terraform apply -target=module.cell.module.cluster.aws_eks_cluster.this -var
   'endpoint_public_access=true' -var 'public_access_cidrs=["<meu-ip>/32"]'`.
2. **RBAC do cluster é de quem o criou, não de quem tem credencial AWS válida.** Um cluster
   provisionado pelo `provision-region.yml` tem `AccessEntry` só para a role
   `github-actions-provision` (mais node role e o service-linked role do EKS) —
   `authenticationMode: API`, sem `bootstrapClusterCreatorAdminPermissions` para ninguém além de
   quem criou. Uma sessão local com credencial AWS válida e rede alcançando o endpoint ainda
   recebe `Error: Unauthorized` dos dois recursos `kubernetes_*` do `destroy`. Fix, se o destroy
   é mesmo a intenção: `aws eks create-access-entry` + `aws eks associate-access-policy`
   (`AmazonEKSClusterAdminPolicy`, escopo `cluster`) para a role que está rodando o destroy —
   **temporário por natureza**: some junto com o cluster no mesmo destroy, não precisa de
   remoção própria.

## Raízes

**A coluna `Exercitada` diz se a raiz já foi aplicada na AWS ao menos uma vez e teve o resultado
verificado — não se está de pé agora.** O que está de pé neste momento é pergunta de sessão, não de
repositório: vive em `HANDOFF.md`, e a resposta confiável é `terraform state list` por raiz.

| Raiz | Contas | State key | Entrega | Exercitada |
|---|---|---|---|---|
| `state-backend/` | `network` | `state-backend/` | O bucket de state, uma vez, sem região | sim |
| `ci/` | `cicd` + `network` | `ci/` | Provider OIDC do GitHub Actions + uma role por conta. Documenta também o lado GitHub inteiro — ver [`ci/README.md`](ci/README.md) | sim — os três workflows autenticam por ela |
| `dns/` | `network` + Azure | `dns/` | Subzona `nonprod.<domínio>` no Route 53 + delegação NS na zona pai | sim |
| `regions/us-east-1/` | `network` (hub) + `cicd` (célula) | `regions/us-east-1/` | `module.hub` (VPC `10.1.0.0/16`, TGW, Client VPN, ALB público) + `module.cell` (VPC `10.2.0.0/16`, EKS, node group, Pod Identities, ESO, ArgoCD, Crossplane) | sim — apply e destroy reais dos dois módulos provados |
| `regions/us-west-2/` | `network` (hub) + `cicd` (célula) | `regions/us-west-2/` | `module.hub` (VPC `10.4.0.0/16`) + `module.cell` (VPC `10.5.0.0/16`) | sim para o `plan` da composição inteira (invariante); aplicado só o hub, por custo |
| `spikes/ipam/` | `personal` + `network` + `cicd` | **state local**, não o bucket | **Spike descartável, fora da sequência** — prova o desenho de IPAM da [ADR 0015](../../docs/adr/0015-defer-ipam-adoption.md). Não tem `up-NN` e não entra em `up-all`. Ver [`spikes/ipam/README.md`](spikes/ipam/README.md) | não — código escrito, ainda não aplicado |

### `dns/` é a única raiz sem região na state key

Hosted zone pública é recurso **global**: não cabe em `regions/<região>/`. E não pode morar junto do
hub — o hub de uma região pode ser recriado (CIDR errado, migração), e a zona recriada nasce com
**name servers novos**; mesmo com a delegação automatizada a propagação do NS não é instantânea.

Todos os valores de **identidade** — domínio, ids de conta, UUIDs de grupo, e o resource group e a
subscription do Azure que só o `dns/` usa — vivem num único `variables/values.tfvars` gitignored,
carregado por cada raiz via symlink `values.auto.tfvars` (ver `variables/README.md` e o
[ADR 0014](../../docs/adr/0014-single-regional-root-composing-hub-and-cell-modules.md)). O que está
inline nas raízes (região, CIDR, AZs) é **decisão de desenho documentada**, não identidade.

`manage_delegation = false` desliga o lado Azure: numa raiz com dois providers de cloud, a ausência
de credencial do segundo faz o `plan` falhar mesmo para mudança que só toca o primeiro. Desligado, a
subzona existe no Route 53 e ninguém a resolve — é modo de trabalho, não estado de repouso.

**`dns/` também liga o RAM sharing com a Organization** (`aws_ram_sharing_with_organization`, via
provider aliasado `aws.management`, profile `personal`). Não tem relação com DNS — é configuração
permanente da Organization inteira, e mora aqui porque `dns/` é a raiz T0 (permanente, custo quase
zero). Sem ela, qualquer attachment cross-conta de TGW falha com `OperationNotPermittedException`.

### Por que o bucket de state tem raiz própria

Ele guarda o state de **todas** as camadas e regiões. Numa raiz própria, nenhum destroy de região o
alcança — o bucket não está no state de nenhuma delas. `prevent_destroy = true` no recurso e
`force_destroy = false` (default) somam duas proteções: a AWS recusa deletar bucket não-vazio, e ele
nunca estará vazio.

### Uma raiz por região, não uma raiz com `-reconfigure`

Cada região tem diretório e state key próprios (`regions/<região>/`). A alternativa — uma raiz só,
alternando backend com `terraform init -reconfigure` — tem um footgun permanente: esquecer de trocar
o backend antes do apply mistura as regiões, e nada no Terraform pega isso. Os valores de região,
CIDR e AZs ficam **inline** em cada `main.tf` (locals) — são decisões de desenho documentadas
(`aws/docs/network/01-cidr-addressing.md`), não segredo. `module.cell` **fica** no `main.tf` de toda
região, idêntico entre elas — a diferença entre aplicar só o hub ou hub+célula é operacional
(flag do script), nunca estrutural.

### Alocação de CIDR

Supernet `10.0.0.0/12`, um `/16` por VPC. N=0 reservado à Organization.

A alocação é **por região, não por ordem de criação**: cada região ocupa um `/14` contíguo, para que
um pool regional de IPAM (que exige `locale` por região) possa ser criado sem re-endereçar nada.

| Bloco | Região | Módulo |
|---|---|---|
| `10.0.0.0/16` | — | **reservado à Organization** |
| `10.1.0.0/16` | us-east-1 (`10.0.0.0/14`) | `module.hub` |
| `10.2.0.0/16` | us-east-1 (`10.0.0.0/14`) | `module.cell` |
| `10.3.0.0/16` | us-east-1 (`10.0.0.0/14`) | livre |
| `10.4.0.0/16` | us-west-2 (`10.4.0.0/14`) | `module.hub` |
| `10.5.0.0/16` | us-west-2 (`10.4.0.0/14`) | `module.cell` |
| `10.6`–`10.7` | us-west-2 (`10.4.0.0/14`) | livres |
| `10.8`–`10.15` | — | livres, 2 regiões futuras |

**Teto de 15, e região multiplica** — ver `aws/docs/network/01-cidr-addressing.md`. É a única
decisão irreversível da cadeia.

**A VPC spoke nunca pode ser separada do state do cluster.** No teardown, o egress
*pod → subnet privada → NAT → IGW → API do ELB* precisa sobreviver até o último nó sair; o grafo
de dependências do Terraform garante isso somente dentro de um mesmo state — é por isso que
`module.hub` e `module.cell` vivem na mesma raiz, ligados por referência (output → input), não por
`terraform_remote_state`.

## Pré-requisitos

- `aws sso login --profile personal` ativo.
- Profiles locais `network` e `cicd` assumindo `OrganizationAccountAccessRole`.
- `variables/values.tfvars` preenchido (gitignored — ver `variables/README.md`).
- `state-backend/terraform.tfvars` preenchido (gitignored, `cp state-backend/terraform.tfvars.example
  state-backend/terraform.tfvars` e editar `bucket_name`) — só usado por `up-00-state-backend`, não
  faz parte de `variables/values.tfvars` porque é o único valor que a raiz `state-backend/` lê antes
  de o bucket existir.
- A conta `cicd`, dona da célula, na OU `Deployments`.

## Submódulos

| Submódulo | Equivale a | Notas |
|---|---|---|
| `src/network` | XR `Network` (L1a) | 16 recursos com NAT ligado. Subnets derivadas do CIDR com `cidrsubnet()`, não fixas — por isso serve qualquer região sem alteração |
| `src/state-backend` | — | Bucket de state endurecido, com `prevent_destroy` |
| `src/hub` | conectividade regional | VPC hub, TGW, Client VPN (SAML), ALB público de ingress com listener `:443` compartilhado. Composto por toda `regions/<região>/` |
| `src/cell` | XR `Cluster` + `ClusterBootstrap` | VPC spoke, EKS, node group, Pod Identities, ESO, ArgoCD, Crossplane — descartável por `terraform destroy -target=module.cell` |
| `src/cluster` | XR `Cluster` (L1b) | EKS `authentication_mode = "API"` (sem `aws-auth` ConfigMap), role do cluster, role compartilhada dos nós, access entries e os dois addons de base |
| `src/nodegroup` | idem | Node groups por mapa. `ignore_changes` no `desired_size` para não brigar com autoscaler futuro |
| `src/pod-identity` | trust de Pod Identity das Compositions | Molde dos três consumidores. O trust precisa de `sts:AssumeRole` **e** `sts:TagSession` — só o primeiro falha |
| `src/ingress` | NLB interno + target group | Endereços de IP privados fixos por AZ, ligados ao ALB do hub via `TargetGroupBinding` |
| `src/helm/modules/{aws-load-balancer-controller,ingress-istio,target-group-binding,httpbin,external-secrets,argo-cd,crossplane}` | XR `ClusterBootstrap` | Um chart por módulo, versão fixada. `ingress-istio` é maior: `base` + `istiod` + `gateway` numa versão só, mais o `Gateway` CR da célula |

O módulo do Load Balancer Controller nasce com escopo estreito de propósito: sem IngressClass e
sem o service mutator webhook, ele reconcilia `TargetGroupBinding` e nada mais. O NLB e a target
group são do Terraform (`src/ingress`), e um controller capaz de materializar load balancer
próprio reabriria a porta que o ADR 0004 fechou ao decidir ingress único pelo hub.

Pelo mesmo motivo o Service do gateway em `ingress-istio` é **ClusterIP**: quem materializa o load
balancer é `src/ingress`, e a ligação pods → target group é o `TargetGroupBinding`.

Três módulos trazem chart **local** (`target-group-binding`, o `Gateway` CR de `ingress-istio` e
`httpbin`), e a razão é mecânica, não estética: os três entregam CRs, não existe chart upstream para
um CR só, e `kubernetes_manifest` faria dry-run server-side no **plan** — exigindo CRDs que só
chegam naquele mesmo apply. O chart local é o que mantém o apply único.

**O nome da célula tem três pontas, em lugares diferentes, e elas têm de concordar:** o certificado
wildcard do ACM e a listener rule do ALB (conta `network`) e o `Gateway` CR do Istio (dentro do
cluster). Divergir não quebra o apply — quebra o `curl` do aceite com um 404 do `fixed-response` do
listener, que se lê como rota faltando no cluster. As três saem de `local.cell_wildcard`, e
`tests/ingress.tftest.hcl` assere que continuam saindo.

Sobre `src/pod-identity` e `src/cluster`: o trust e o `assume_role_policy` usam `jsonencode()`,
não `data "aws_iam_policy_document"`. Com `mock_provider`, o data source devolve string sintética
— a assertion sobre `sts:TagSession` passaria sem verificar nada. Com `jsonencode` é o próprio
Terraform que computa o documento, e o teste vê o valor real.

## Nova região

Duas coisas, nesta ordem. A SCP vem primeiro — sem ela o `apply` falha no `CreateVpc`, não no
código:

```bash
cd ../docs/accounts/scripts
AWS_PROFILE=personal ./apply-baseline-service-control-policy --regions us-east-1,<nova-região>
```

Isso vale para a **Organization inteira**, não só para a conta `network`. Depois, copiar a raiz de
uma região existente e trocar o que é regional:

```bash
cd ../regions
cp --recursive us-east-1 <nova-região>
rm --recursive --force <nova-região>/.terraform <nova-região>/logs \
  <nova-região>/values.auto.tfvars <nova-região>/saml-metadata.xml
ln --symbolic ../../variables/values.tfvars <nova-região>/values.auto.tfvars
ln --symbolic ../../variables/saml-metadata.xml <nova-região>/saml-metadata.xml
```

Editar em `<nova-região>/main.tf` (`locals`): `region`, `hub_vpc_cidr` e `cell_vpc_cidr` (dois `/16`
livres — conferir a tabela de alocação acima **antes** de escrever). E em `<nova-região>/versions.tf`
a `key` do backend (`regions/<nova-região>/terraform.tfstate`) — a `region` do bloco `backend "s3"`
**não muda**: é onde vive o bucket de state (`us-east-1`), não a região da infraestrutura.

`module.cell` **fica** no `main.tf` — não é opcional remover. **Um `terraform plan` verde da
composição inteira (hub + célula) é o aceite de uma região nova**, mesmo que só o hub seja aplicado:
ele prova que nenhum nome global colide (IAM roles, SAML provider) e nenhum caminho de arquivo aponta
para a região errada.

```bash
cd <nova-região>
terraform init -backend-config="bucket=<state-bucket-name>"
terraform plan -out=/tmp/<nova-região>.tfplan
terraform apply "/tmp/<nova-região>.tfplan"   # só o hub, por custo — module.cell fica pendente
```

Nenhuma linha de `src/hub`, `src/cell` ou `src/network` muda — os dois módulos foram feitos
reutilizáveis, com teste provando que a aritmética de CIDR acompanha o valor recebido.

## Ordem de teardown

Dentro de uma raiz a ordem é de graça — é o grafo de dependências do Terraform, e `module.cell`
depende de `module.hub` por referência (output → input), nunca o contrário. O que **não** é de
graça: XRs que o Crossplane tenha criado dentro do cluster depois do bootstrap. Eles não estão no
state do Terraform, e destruir o cluster primeiro deixa recurso AWS órfão sem controlador. Antes de
um `destroy` que alcance a célula:

```bash
kubectl get managed     # tem de vir vazio
kubectl get composite   # idem
```

Se não vier vazio, deletar os XRs e esperar a reconciliação terminar **antes** do `terraform
destroy`/`down-cell`.

## Testes

Sem credencial, sem chamada à AWS — `mock_provider` + `command = plan`:

```bash
for module in src/network src/state-backend src/pod-identity src/cluster src/nodegroup src/ingress \
              src/hub src/cell \
              src/helm/modules/aws-load-balancer-controller \
              src/helm/modules/ingress-istio \
              src/helm/modules/target-group-binding src/helm/modules/httpbin \
              src/helm/modules/external-secrets src/helm/modules/argo-cd \
              src/helm/modules/crossplane \
              regions/us-east-1 regions/us-west-2 dns; do
  (cd "${module}" && terraform init -backend=false && terraform test)
done
```

A volta inteira passa de 2 min — rodar em background ou por diretório, senão o teto de tempo de
uma chamada corta no meio.

Cada raiz de região testa que seus dois CIDRs **caem dentro do supernet** e **não se sobrepõem entre
si**. Um typo no CIDR é irreversível depois de aplicado.

### Duas limitações do framework que já custaram tempo

1. **`command = plan` só avalia valores conhecidos antes do apply.** ID de subnet não é um
   deles, então `aws_nat_gateway.this[0].subnet_id == aws_subnet.public[0].id` não compila.
   Saída: `override_resource` com `override_during = plan`, dando IDs conhecidos — e
   **distintos** entre pública e privada, senão a assertion passa mesmo com o NAT na privada.
2. **Alguns blocos são `set`, não `list`.** `aws_s3_bucket_server_side_encryption_configuration.this.rule[0]`
   falha com "cannot index a set value"; é preciso um `for`. E com `length(...) == 1`, porque
   `alltrue([])` é `true` e um `for` sem checar tamanho passaria com zero regras.

Assertion nova sobre propriedade que importa merece **teste de mutação**: quebre a
implementação de propósito e confirme que o teste falha.

## Custo

O hub (`module.hub`) custa **~US$ 110/mês**: TGW isolado por default (~zero até algo anexar) + Client
VPN (~US$ 146/mês por **duas** associações de target network, uma por AZ) + ALB de ingress
(~US$ 16/mês). VPC, subnets, IGW, route tables e bucket vazio não cobram por hora; NAT do hub fica
desligado de propósito — sem TGW anexado nada roteia por ele.

A célula (`module.cell`) custa **~US$ 165/mês** a mais: EKS control plane ~73 + NAT ~32 (aqui
deliberado — os nós dependem dele para chegar à API do EKS e aos registries) + 2×`t3.medium` ~60.

Por isso a célula não fica de pé entre sessões de trabalho — sobe, valida, desce (`down-cell`). O
hub fica: é o repouso da região, e derrubá-lo e recriá-lo troca o DNS name do ALB e do Client VPN,
invalidando o `.ovpn` exportado e os registros alias das células.

## Tempos aproximados

Não é custo, é quanto tempo esperar antes de considerar um `apply`/`destroy` travado. Nenhum script
imprime progresso ao vivo em toda etapa — os números abaixo são a referência de quanto é normal
demorar.

| Camada | Apply | Destroy | Gargalo |
|---|---|---|---|
| `state-backend` | segundos | — (`prevent_destroy`) | 6 recursos S3, sem espera de propagação |
| `dns` | segundos | — (`prevent_destroy`) | zona Route 53 + 1 registro NS no Azure |
| `module.hub` | **~10 min** | **~10 min** | as duas `aws_ec2_client_vpn_network_association` (uma por AZ), 7-9 min cada, em paralelo — depois o Internet Gateway, que só sai depois delas |
| `module.cell` | ordem de 15-25 min (não medido nesta sessão) | ordem de 10-15 min (não medido nesta sessão) | EKS control plane é o mais lento do grupo — no fluxo antigo equivalente (`aws/eks/scripts/provision-eks`), sozinho já levava ~15 min |

**Medido nesta sessão** (destroy real do hub `us-east-1`, 42 recursos): as duas
`aws_ec2_client_vpn_network_association` levaram 8m30s e 8m31s (paralelas), o Internet Gateway
10m11s (o passo mais longo — só libera depois que as associações do Client VPN soltam as ENIs da
VPC), o TGW attachment 2m7s, as duas `aws_ec2_client_vpn_route` 4m26s cada. O resto (VPC, subnets,
route tables, ALB, certificados, SAML provider) sai em segundos. O apply é **simétrico**: as mesmas
duas associações do Client VPN dominam o tempo, dos dois lados.

**Por isso `nohup ... & disown`, nunca uma chamada síncrona:** um `apply`/`destroy` de ~10 min
estoura qualquer teto de tempo de ferramenta de agente ou de terminal com timeout curto — ver
`CLAUDE.md`, "Endpoint da API do EKS".
