# HANDOFF

Visão geral e estado do repo. Progresso de qualquer tarefa em andamento (parado em, próximo passo, ambiente local) vive em `HANDOFF.local.md` (gitignored) de quem está trabalhando — ver `CLAUDE.md`.

## Why

Exercitar a PoC AWS EKS-via-Crossplane (arquitetura de referência hub-and-spoke) na conta AWS
pessoal do Silvio, genérica, antes de qualquer ambiente corporativo. `aws/` foi genericizada a
partir de um exemplo interno (placeholders `<...>` para valores por-conta/segredos; valores
genéricos concretos como `platform.example.com`/`poc-eks` onde o token é YAML/Crossplane
executável). Valores reais ficam em `CLAUDE.local.md` (gitignored); os valores de identidade das camadas
Terraform vivem em `aws/terraform/variables/values.tfvars` gitignored, carregado por cada raiz via
symlink `values.auto.tfvars` (ver `aws/terraform/variables/README.md` e o
[ADR 0014](docs/adr/0014-single-regional-root-composing-hub-and-cell-modules.md), que escolheu o
formato tfvars no lugar do `values.yaml` previsto no [ADR 0013](docs/adr/0013-consolidate-local-values-yaml.md)).

Decisões de arquitetura que orientam esta frente (sequência de provisionamento, escopo fino do
Terraform, alocação de CIDR, ingress centralizado, etc.) vivem em [`docs/adr/`](docs/adr/README.md)
— ler antes de propor mudança de rumo, não rederivar do zero.

### VPN

O desenho assume `Site-to-Site VPN` por cliente ([ADR 0005](docs/adr/0005-site-to-site-vpn-per-client.md)).

## Vocabulário (ler antes de qualquer coisa)

"hub" cobria três eixos independentes e a ambiguidade custou tempo. Dois foram renomeados; só o
topológico mantém o termo:

| Eixo | Nome correto | Nome antigo |
|---|---|---|
| **Conta AWS** de conectividade | `network` — Connectivity Account, OU `Infrastructure` | "conta hub", profile `hub`, ProviderConfig `hub` |
| **Papel topológico** de rede | `hub` — único uso legítimo. Par de `spoke`; chart `platform/charts/hub`, VPC hub, TGW | (inalterado) |
| **Control plane** Crossplane (k3d) | **Control Plane** / `control-plane` | "hub k3d", `poc-eks-hub-config` |
| **Conta** do Control Plane | `cicd`, na OU `Deployments` | `platform` |

`network` é canônico no whitepaper *Organizing Your AWS Environment Using Multiple Accounts*, no
AWS SRA e no Landing Zone Accelerator. A AWS **não** nomeia contas como "Hub".

O chart `platform/charts/hub` **não** foi renomeado de propósito: ali "hub" é topologia, e
`network` colidiria com o XR `Network` que ele renderiza.

O prefixo `poc-idp/` no Secrets Manager (`poc-idp/crossplane-poc-credentials`) é o nome real de um
secret na AWS, não apelido do cluster — **não renomear**.

**Hierarquia de fontes AWS:** **WAF** diz *por quê* isolar por conta e **nomeia zero contas e
zero OUs**; o **whitepaper** nomeia OUs (`Security`, `Infrastructure`, `Workloads`, `Sandbox`,
`Deployments`, …); o **SRA** nomeia contas (`Shared Services`, `Network`, …). Tabela em
`aws/docs/accounts/01-organizations-and-ous.md`.

## Estado atual

Não presumir o que está de pé pelo handoff — conferir sempre (comando em **Operação**).

**AWS: `regions/us-east-1` e `regions/us-west-2` vazias desde 2026-09-04** (nem hub nem célula). Custo da Organization abaixo de US$ 1/mês (hosted zone, bucket de state, CloudTrail no `log-archive`, Secrets Manager). Raízes: `state-backend`, `dns`, `regions/<região>` (compõe `src/hub` + `src/cell`), `ci`; sequência, custo e ordem em `aws/terraform/README.md` — fonte de verdade.

**Decomposição do custo do resting state**, medida no Cost Explorer e útil para a frente do Client
VPN (abaixo). O que o hub custava parado:

| Item | Cobrança | Mês |
|---|---|---|
| Client VPN — **2 subnet associations** | US$ 0,10/h **cada** | **~US$ 146** (73% do total) |
| TGW — attachment do hub | US$ 0,05/h | ~US$ 37 |
| ALB do hub | ~US$ 0,0225/h + LCU | ~US$ 18 |

A cobrança do Client VPN é **por associação, não por endpoint** — endpoint parado custa zero. Esse
detalhe é o que abre a opção cirúrgica descrita em Open Questions. A célula, quando de pé, soma
~US$ 165/mês por cima.

**IPAM: adiado** ([ADR 0015](docs/adr/0015-defer-ipam-adoption.md)); achados medidos em `aws/docs/network/08-ipam.md`. Alocação de CIDR por região em `/14` contíguos (`us-west-2` em `10.4`/`10.5`).

Números que valem para qualquer trabalho futuro com IPAM: VPC alocada por pool leva **~4 min para
criar e 18–27 min para destruir**; todo o resto (IPAM, pools, RAM, delegação) sai em **~1 min**. O
provider espera a **desalocação assíncrona**: a VPC some da AWS muito antes, e a alocação fica
retida no pool apontando para a VPC morta — logo **CIDR alocado por IPAM não é estável entre
recriações**. Ao diagnosticar um destroy que parece travado, conferir `pgrep -af terraform` **sem
truncar** — um `| head -3` já escondeu o processo vivo e levou a um diagnóstico errado.

**Documentação do CI consolidada:** `aws/terraform/ci/README.md` é o documento único da automação
(trust OIDC, variables/secrets com o motivo de cada um, GitHub App, composite action `aws/setup`,
os três workflows, exemplos de `gh`). A raiz `ci/` foi acrescentada à tabela `## Raízes` do
`aws/terraform/README.md` — ela não estava lá, e é por isso que o README dela era indescobrível.

**IDP:** Backstage em `idp/` (1.55.3, roda só local via `yarn start`), integrado à org GitHub `wasp-foundry` pelo App `wasp-foundry-backstage`. Template `python-service` cria app (repo + PR em `wasp-foundry/gitops`); CI das apps publica no GHCR e faz bump pelo App `wasp-foundry-ci`. Exemplo vivo: `wasp-foundry/hello-alpha`. Clusters k3d são locais a cada máquina — não fazem parte do estado compartilhado. Operação em `docs/idp/CLAUDE.md`.

## Frentes

| Frente | Estado |
|---|---|
| IDP: criação de app por time (#100, #101) | Entregue em 2026-10-01 |
| IDP: Bookinfo no catalog + clusters `development`/`production` (#105) | Em andamento — spec `docs/superpowers/specs/2026-10-01-bookinfo-catalog-multi-cluster-design.md` |
| Teardown: aresta de grafo (#92) e retry (#94 achado 1) | Mergeados, **não exercitados na AWS** (exigem célula de pé) |
| Teardown: agendar, notificar falha, subcomando de recuperação (#94 achados 3/4/5) | Aberto — achado 4 é o de maior retorno |
| Efemeridade do Client VPN | Não iniciada — decisão pendente (Open Questions) |
| SEC-EDGE (#84–#89) | #84 (WAF no ALB do hub) mergeado e **não aplicado**; próxima #85 (access logs do ALB para S3), da qual #86 depende |

Backlog e priorização: GitHub Project #6 — https://github.com/users/smsilva/projects/6 (`gh project item-list 6 --owner smsilva --limit 100 --format json`; sem `--limit 100` o default de 30 omite itens).

## Referências (ler sob demanda, não de uma vez)

| Precisa de... | Vá para |
|---|---|
| Por que uma decisão de arquitetura foi tomada | [`docs/adr/`](docs/adr/README.md) |
| Achado/limitação ainda válida, ainda não resolvida | [`aws/docs/known-broken.md`](aws/docs/known-broken.md) |
| Pergunta em aberto, sem decisão | [`aws/docs/open-questions.md`](aws/docs/open-questions.md) |
| Lição já corrigida, mas que vale para camada futura | [`aws/docs/lessons-learned/`](aws/docs/lessons-learned/) |
| Narrativa de entrega concluída | [`docs/archived/index.md`](docs/archived/index.md) |
| O que falta fazer, priorizado | GitHub Project #6 (link acima) |
| Sequência de provisionamento e dicionário de recursos | `docs/superpowers/specs/2026-08-27-provisioning-sequence.md` |

## Operação

Conferir estado e credenciais antes de qualquer coisa na AWS:

```bash
cd aws/terraform
for m in state-backend dns regions/us-east-1 regions/us-west-2; do
  printf '%-24s %s\n' "${m}" "$( (cd "${m}" && terraform state list 2>/dev/null | grep -vc '^data\.') )"
done
for p in personal network cicd; do aws sts get-caller-identity --profile "${p}" --output json; done
```

Esperado em 2026-09-04: `regions/*` em **0**. Qualquer coisa diferente de zero ali significa que
alguém subiu a região — checar o custo antes de continuar.

O guard de grafo roda sem credencial válida e é o preflight barato de qualquer mexida em
`depends_on`:

```bash
cd aws/terraform && ./scripts/check-graph          # us-east-1 por default
```

**O SSO cai sozinho, e nem sempre leva os três profiles juntos.** `network` e `cicd` assumem role a
partir de `personal`, mas as sessões de role assumida ficam em cache e sobrevivem à expiração do
token de origem — já aconteceu de `personal` estar morto e os outros dois respondendo. Sintoma quando
falta só o `personal`: qualquer coisa que use o provider da management falha com
`InvalidGrantException ... refresh cached SSO token failed`. Recuperação: `! aws sso login --profile
personal`.

`--query` devolve lixo nesta máquina (wrapper `rtk`, ver `CLAUDE.local.md`) — usar `--output json`
e ler o `Account`/`Arn` inteiro. Erro de profile inexistente ou ARN vazio ⟹
`! aws sso login --profile personal` (abre navegador; o agente não roda). A sessão do `az` expira
**independentemente** — conferir com `az account show`.

**`us-east-1` está vazia desde 2026-09-04 — nem hub nem célula.** Subir a região por CI é o caminho
provado e não exige túnel. Atenção ao custo: o hub sozinho volta a ~US$ 200/mês, dos quais ~US$ 146
são as duas subnet associations do Client VPN:

```bash
gh workflow run provision-region.yml --ref main -f region=us-east-1
gh workflow run teardown-region.yml  --ref main -f region=us-east-1
```

`--ref main` é obrigatório: o trust policy da role `cicd` restringe o claim `sub` a
`ref:refs/heads/main`, e disparar de um branch falha no `AssumeRoleWithWebIdentity` com mensagem que
não menciona branch nenhum. **Não há caminho de teste em branch.** Provisionamento leva 20-30 min,
teardown ~8 min; sondar com `sleep 285` (sleep de 10 min é morto pelo harness). Detalhes e mais
exemplos de `gh` em `aws/terraform/ci/README.md`.

Localmente (exige túnel conectado):

```bash
cd aws/terraform/scripts && ./up-02-region --region us-east-1 --yes
```

**Derrubar (rotina, todo dia, quando a célula estiver de pé):**

```bash
cd aws/terraform/scripts && ./down-cell --region us-east-1 --yes
```

`down-cell` destrói só `module.cell` (`-target`), mantendo o hub de pé. Derrubar a região inteira
(hub incluso) é `terraform destroy` sem `-target` na raiz `regions/<região>/` — não é rotina, sem
script próprio de propósito. Se o destroy morrer com `dial tcp <ip-privado>:443: i/o timeout`, a
aresta de `depends_on` está errada, não é falha de credencial — recuperação: `terraform state rm`
dos objetos Kubernetes presos + reaplicar o `destroy`.

**Se o destroy travar num `helm uninstall`** (sintoma: `context deadline exceeded`, e não o timeout
de rede acima), a receita que funcionou em 04/09 está em `aws/terraform/CLAUDE.md`, seção State:
`state pull` para backup, `state rm` de **todos** os `helm_release`/`kubernetes_*` de uma vez, e o
destroy vira 100% API da AWS — dispensa túnel e endpoint público aberto, que é o que trava a
recuperação depois de o cleanup do workflow ter fechado o endpoint. Auditar órfão depois é parte da
receita, não zelo.

**Continuar com as camadas de pé exige o túnel conectado** (a API do cluster só existe por ele):

```bash
aws-vpn-client get-connection-status --profile-name hub   # tem de dizer "Connected"
! aws-vpn-client connect --profile-name hub               # abre navegador; precisa ser o usuário
```

**Nada garante que sobrevive entre sessões/máquinas** — `aws-vpn-client --version` (6.0.1 esperado;
`latest` entrega 5.4.1 sem CLI) e a existência de `saml-metadata.xml` precisam ser conferidos
sempre, nunca presumidos. `~/trash/hub.ovpn` de sessões anteriores está sempre inválido (DNS name
muda a cada recriação da 03) — reexportar sempre.

**Subir o ambiente** — a sequência completa (preencher `variables/values.tfvars` → `up-all` →
exportar/importar `.ovpn` → conectar → `up-all --with-cell` → provar; sem passo de geração de
tfvars), com custo e dependência por camada, vive em `aws/terraform/README.md`. **Ler de lá, não
daqui.**

**Verificar a célula ponta a ponta.** Desde 2026-08-29 (branch `feat/terraform-cluster-addons`)
**nenhum `helm` manual é necessário** — `up-02-region --with-cell` entrega a célula inteira, e o checkout de
`wasp-gitops` deixou de estar no caminho:

| Chart | Onde vive |
|---|---|
| `aws-load-balancer-controller` | `src/helm/modules/aws-load-balancer-controller` |
| `base`, `istiod`, `gateway` (ClusterIP) + o `Gateway` CR | `src/helm/modules/ingress-istio`, Istio 1.30.4 upstream |
| `TargetGroupBinding` | `src/helm/modules/target-group-binding`, chart local |
| `httpbin` + `VirtualService` | `src/helm/modules/httpbin`, chart local, `go-httpbin` 2.21.0 |

**Ainda não exercitado na AWS** — os quatro módulos passam offline e o apply real é o aceite que
falta. Ordem em que quebra, e o que cada ponto significa:

```bash
terraform -chdir=aws/terraform/regions/us-east-1 output cell_services_url   # https://services.<célula>.<subzona>/
```

`dig` no host → certificado no listener → os dois target groups (spoke e hub) `healthy` → `curl`
público sem `-k`.

**O host é `services.`, não `app.`** — qualquer outro nome sob o wildcard cai no `fixed-response`
404 do listener do ALB, e o sintoma é indistinguível de rota faltando no cluster.

**Regressão offline** (~3-4 min, rodar em background):

```bash
cd aws/terraform
for m in src/network src/state-backend src/pod-identity src/cluster src/nodegroup src/ingress \
         src/hub src/cell \
         src/helm/modules/aws-load-balancer-controller \
         src/helm/modules/external-secrets src/helm/modules/argo-cd src/helm/modules/crossplane \
         regions/us-east-1 regions/us-west-2 dns; do
  (cd "${m}" && terraform init -backend=false >/dev/null && terraform test)
done
```

**Preflight antes de subir qualquer coisa:**

```bash
aws-vpn-client --version                              # 6.0.1 — ausente ⟹ alguém instalou por `latest`
systemctl is-active aws-client-vpn-daemon.service
terraform -chdir=aws/terraform/regions/us-east-1 init -backend-config="bucket=tfstate-o-e4r8ndteju"
```

`terraform apply`/`destroy` rodam por `! <comando>` — o classifier de auto-mode bloqueia para o
agente; `apply` sem tty falha de propósito, usar `--yes` quando não houver terminal. Plano salvo
não sobrevive à expiração de credencial — replanejar, não reaproveitar.

**Reproduzir o Control Plane k3d, se necessário:**

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
`x509` e depois `connection reset`) e SSO admin ativo.

**Lição operacional:** nunca deixar um `apply`/`destroy` de vários minutos dependurado numa chamada
síncrona de ferramenta — usar `nohup ... > log 2>&1 < /dev/null & disown` (os scripts `up-NN` já
fazem isso). Um processo morto no meio não impede recuperação, mas custa tempo evitável.

## Open Questions

- **O que deve virar efêmero no hub, para o Client VPN parar de custar ~US$ 146/mês parado?** Esta é
  a frente pedida e não iniciada — o brainstorming foi interrompido antes da decisão. Três opções já
  levantadas, com o trade-off apurado; **não rederivar**:

  | Opção | Custo parado | `.ovpn` entre sessões | Ressalva |
  |---|---|---|---|
  | Só as 2 `aws_ec2_client_vpn_network_association` (+ as 2 rotas) | ~US$ 55 | **estável** — o `dns_name` do endpoint não muda | endpoint, certificado ACM, SAML provider e authorization rules sobrevivem |
  | O Client VPN inteiro | ~US$ 55 | reexportar sempre | certificado revalida por DNS a cada subida |
  | O hub inteiro | US$ 0 | reexportar sempre | inverte a premissa do [ADR 0014](docs/adr/0014-single-regional-root-composing-hub-and-cell-modules.md) de que o hub é o resting state |

  A opção cirúrgica existe porque **a cobrança é por associação, não por endpoint**. Ela também
  derruba a nota de `aws/terraform/CLAUDE.md` de que "o `.ovpn` nunca se reaproveita entre applies do
  hub" — isso vale quando o endpoint é recriado, não quando só as associações vão e voltam.
  **Armadilha já documentada, não tentar:** `transit_gateway_configuration` no endpoint parece o
  caminho mais direto e não é — o attachment que ele cria leva *"several hours"* para deletar, o
  provider não espera, e isso **impede deletar o TGW**.
- **Um retry de teardown é suficiente, ou o caminho é `state rm` automático?** O retry de #94 cobre
  erro transitório. Não cobre finalizer preso por controller sem credencial — nesse caso a segunda
  tentativa falha igual. Com a aresta de #92 o cenário deixa de acontecer por essa causa, mas a
  pergunta continua de pé para outras.
- **Vale abrir exceção na SCP baseline para limpar as VPCs default das 15 regiões negadas?**
  Continua em aberto, mas **deixou de ser o único caminho**: a issue **#69** propõe neutralizá-las com
  *declarative policy* de EC2 (VPC Block Public Access), sem tocar na SCP. O item bloqueante lá é
  medir se a policy dá para restringir por região — aplicada larga, ela mata o ALB público da célula.
- **#40** segue investigação em aberto, sem trabalho iniciado — ver o corpo da issue para os
  ângulos já mapeados.
- **A `gp2` in-tree (`kubernetes.io/aws-ebs`) ainda provisiona volume em Kubernetes 1.36, via CSI
  migration?** Muda se a #62 é gap de qualidade (classe legada, `gp2` mais caro por IOPS que `gp3`)
  ou bug latente (classe que não funciona mais). Conferir na doc da AWS **antes** de escrever
  código — a regra existe porque o passo `2.4` custou ~US$ 180/mês por não fazer isso.
- **Um cluster recém-criado não tem admin além da role de CI**, cuja trust OIDC é restrita a
  `refs/heads/main`. `aws eks update-kubeconfig` + `kubectl` falham com "the server has asked for the
  client to provide credentials". Para depurar de dentro, ou resolver a #56, ou criar uma access
  entry fora do Terraform (`aws eks create-access-entry` + `associate-access-policy`; não gera drift
  porque `var.access_entries` está vazio, então o `for_each` não gerencia nada).

## Known Broken

Lista completa e canônica em [`aws/docs/known-broken.md`](aws/docs/known-broken.md). Itens com contexto que vale ter à mão:

- **Teardown não é agendado nem notifica** — *unexpected*, #94 achados 3 e 4. `down-cell` se diz
  "nightly" e o `README.md` diz "todo dia", mas os três workflows são `workflow_dispatch` puro. E
  falha de teardown não avisa ninguém: o run de 02/09 ficou `failure` em silêncio por 2 dias. É o
  único modo de falha do repo que **gasta dinheiro continuamente**.
- **#92 e #94 não foram exercitados na AWS** — *intentional*. Ambos validados só offline; exigem uma
  célula de pé, e a região foi destruída de propósito. O caminho de retry só aparece numa falha real.

- **`recover-lock.yml` nunca foi executado e não roda** — *unexpected*, item 25. Dois defeitos:
  referencia o composite action do repositório privado direto (a correção do App token tocou só os
  outros dois workflows), e cria apenas o symlink de `values.auto.tfvars`, sem o de
  `saml-metadata.xml` que `module.hub` lê em todo plan. **Não corrigido de propósito:** a correção
  precisa de uma execução real para ser dada por boa, e é a lição que a #52 inteira ensinou.
- **Endpoint público do EKS fica aberto se o job morrer antes do passo de fechamento** —
  *intentional*, issue #49. O `if: always()` cobre falha de step, não cancelamento nem morte do
  runner.
- **`terraform validate` em `src/cell` acusa "Provider configuration not present"** — *intentional*,
  pré-existente (confirmado por `git stash` + reexecução): resíduo de estado de teste com o provider
  aliasado `aws.network`. A checagem que vale é o `plan` na raiz regional.
- **`aws_iam_saml_provider.client_vpn` tem drift** entre o XML local e o que está na AWS —
  *unexpected*, não aplicado de propósito, para não mexer em config compartilhada do Client VPN.

## Completed Work

Narrativa detalhada de cada entrega concluída vive em `docs/archived/<tema>/<passo>.md`, indexada
em [`docs/archived/index.md`](docs/archived/index.md).

- **2026-10-01 — #101, criação de aplicação por time na org `wasp-foundry`.** Template Backstage `python-service` cria o repo, CI publica no GHCR e o ApplicationSet `foundry-apps` faz o deploy no k3d do cluster-zero; aceitação ponta a ponta com `hello-alpha` (mantido como exemplo vivo). PR #103. Spec e planos em `docs/superpowers/{specs,plans}/2026-09-30-foundry-app-scaffolding*`.
- **2026-09-30 — #100, Backstage 1.49.0 → 1.55.3** (PR #102). Exigiu fixar `@yarnpkg/core` em
  `4.9.1` (a `4.9.2` saiu quebrada), `yarn dedupe` de `@internationalized/date` e `nav.take` de
  `page:user-settings`/`page:notifications` no `Sidebar.tsx`. Login guest e Google validados.

- **2026-09-04 — região `us-east-1` destruída por inteiro e custo zerado.** Investigação de custo
  achou hub e célula de pé por falha silenciosa de teardown; 76 recursos removidos, órfãos auditados,
  Organization abaixo de US$ 1/mês.
- **2026-09-04 — #92, aresta faltando entre os consumidores da API do Kubernetes e `module.cluster`.**
  Causa raiz do teardown que falhou. Inclui o guard `scripts/check-graph`, que assere grafo offline —
  classe de bug que antes só um apply+destroy real pegava.
- **2026-09-04 — #94 achado 1, retry no `teardown-region.yml`.** Segundo step antes do fechamento do
  endpoint, com `continue-on-error` no primeiro para o job não reportar falha quando o retry funciona.
- **2026-09-01 — #67, VPCs default removidas da Organization** (`feat/67-remove-default-vpcs`,
  `33e61f5`). Eram **8**, não 6: a `log-archive` também tinha as duas, e a
  `OrganizationAccountAccessRole` a alcança sem profile local. `scripts/remove-default-vpcs` é
  idempotente, recusa VPC com ENI (provado em `--dry-run` e em modo `DELETE` com ENI descartável) e
  é chamado pelo `create-account`. **Não existe forma nativa de impedir a criação** — só Control
  Tower/AFT apagam, e o AFT não cobre as contas que ele provisiona; fontes e limites em
  `aws/docs/accounts/03-provisioning.md`.

- **2026-09-01 — #15, IPAM avaliado: adiar** (ADR 0015). Spike aplicado em `us-east-1` (brownfield: alocação dentro da VPC existente) e `us-west-2` (greenfield: sem sobreposição); `us-west-2` realocada para `10.4`/`10.5`. Abriu #66 e #67.
- **2026-09-01 — #52, `provision-region.yml` e `teardown-region.yml` provados do zero** (78 recursos num apply; 78 destruídos, zero recriados). Cinco bugs corrigidos no caminho, entre eles a race de Pod Identity do EBS CSI (addon agora com `depends_on` na association).
- **2026-08-31 — #41, workflow de CI provisiona hub e célula** (run 8 verde ponta a ponta); #47 fechada pela causa raiz.
- **2026-08-30 — fase 4 da raiz regional única** (ADR 0014): raízes antigas apagadas, `regions/us-west-2/` criada, scripts renumerados `up-00`/`up-01`/`up-02`, clone limpo aplica seguindo só o README (#37).

> Before trusting anything time-sensitive above, run `git status`, `git diff`, and `git log` against the base branch.
