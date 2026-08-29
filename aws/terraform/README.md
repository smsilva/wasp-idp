# Terraform — bootstrap da plataforma AWS

Substitui o bootstrap por k3d + Crossplane. Desenho em
`docs/superpowers/specs/2026-08-25-terraform-bootstrap-module-design.md`; planos em
`docs/superpowers/plans/2026-08-25-terraform-network-foundation.md` (camada 1) e
`docs/superpowers/plans/2026-08-25-terraform-control-plane.md` (camada 2).

## Manter este arquivo verdadeiro

**Este README é a sequência executável.** Quem chega sem contexto segue o que está aqui e espera que
funcione; uma linha desatualizada aqui não é doc velha, é comando que falha no meio, às vezes com
recurso já criado atrás. Duas divergências desse tipo já aconteceram: a 03 ficou marcada como "não
aplicada" depois de aplicada e aceita, e o `up-all --with-control-plane` continuou documentado
depois de o passo do túnel virar obrigatório.

Atualizar junto com a mudança, no mesmo trabalho — não depois:

| Mudou isto | Atualizar aqui |
|---|---|
| Camada nova (`up-NN`) | bloco de comandos, tabela da sequência, `## Raízes`, `## Ordem de teardown` |
| Pré-requisito novo que **não é Terraform** (console, túnel, SCP) | linha `—` própria na tabela da sequência, com o que ele custa e de quem depende |
| Passo que muda o que um `apply` **exige** para completar | o bloco de comandos, e não só a prosa: quem lê copia o bloco |
| Guarda nova num script | `### Armadilhas que os scripts pegam antes de tocar em nada` |
| Custo por hora de uma camada | tabela da sequência **e** `## Custo` (as duas divergem calado) |
| Raiz aplicada de verdade pela primeira vez | coluna `Exercitada` em `## Raízes` |

**O que NÃO entra aqui:** o que está de pé agora, IDs de recurso, valores da conta. Isso é estado de
sessão e vive em `HANDOFF.md` — repetir aqui garante duas fontes e uma delas errada. Armadilhas de
código e de comportamento de provider vão para `CLAUDE.md`, não para este arquivo.

**Contagem de testes também não entra** — em nenhum arquivo versionado. O número muda a cada módulo
novo, envelhece sozinho e não informa decisão nenhuma: o que importa é `0 falhas`, e quem quer o
total roda o loop.

Ao fechar um passo de plano que muda a sequência, a checagem é uma pergunta só: **alguém que só leia
este README consegue subir o ambiente hoje?**

## Sequência de provisionamento

Um script por camada em `scripts/`, numerado pela ordem. Cada um é idempotente e roda sozinho;
`up-all` roda a sequência parando na primeira falha.

```bash
cd aws/terraform

./scripts/up-all --base-domain <domínio>     # camadas 00 → 02, centavos por mês
./scripts/up-all --with-connectivity         # inclui a 03 (~US$ 162/mês)
```

**A 04 não sobe por `up-all`, e não é questão de custo:** entre a 03 e a 04 existe um passo que
nenhum script faz por você — **conectar o túnel**. Desde o `2.5` o endpoint público da API do EKS
nasce fechado, e quem fala com o API server durante o apply são os providers `helm`/`kubernetes`, a
partir da máquina que roda o `terraform apply`. Sem túnel, o apply da 04 morre no primeiro recurso
`kubernetes`.

```bash
# entre a 03 e a 04, obrigatoriamente
endpoint="$(cd connectivity/us-east-1 && terraform output -raw client_vpn_endpoint_id)"
aws ec2 export-client-vpn-client-configuration --client-vpn-endpoint-id "${endpoint}" \
  --profile network --region us-east-1 --output text > ~/trash/hub.ovpn
aws-vpn-client import-profile --profile-name hub --config-path ~/trash/hub.ovpn
aws-vpn-client connect --profile-name hub
aws-vpn-client get-connection-status --profile-name hub    # Connected antes de seguir

./scripts/up-04-control-plane --yes          # ~US$ 165/mês
```

O `.ovpn` **nunca** se reaproveita entre applies da 03: a DNS name do endpoint muda a cada
recriação. Reexportar sempre.

| # | Script | Raiz | Depende de | Custo/mês | Nível |
|---|---|---|---|---|---|
| — | — | *aprovar região na SCP* | — | zero | **pré-requisito, não é Terraform** |
| — | — | *aplicação SAML no Identity Center* | — | zero | **pré-requisito da 03, é console** |
| 00 | `up-00-state-backend` | `state-backend/` | — | centavos | permanente |
| 01 | `up-01-network-foundation` | `network-foundation/<região>/` | 00 | **zero** | permanente |
| 02 | `up-02-dns` | `dns/` | 00 | ~US$ 0,50 | T0 |
| 03 | `up-03-connectivity` | `connectivity/<região>/` | 00, 01, 02 | ~US$ 162 | T1 |
| — | — | *conectar o túnel do Client VPN* | 03 | +US$ 0,05/h | **pré-requisito da 04, não é Terraform** |
| 04 | `up-04-control-plane` | `control-plane/` | 00, 01, **03 + túnel conectado** | ~US$ 165 | T2 |

**A ordem não é preferência.** 00 antes de tudo porque nenhuma outra raiz inicializa o backend sem
o bucket; 01 antes de 04 porque a 04 lê a VPC hub por `tag:Name`; 02 antes de 03 porque o
certificado do endpoint da VPN valida por DNS na subzona que a 02 delega; 03 antes de 04 porque o
caminho até a API do cluster **é** o túnel. Níveis de permanência em
`docs/superpowers/plans/2026-08-26-private-access-and-ingress/README.md`.

**Desbloqueio de emergência, se o túnel não estiver disponível:**
`control-plane/scripts/generate-tfvars --enable-public-endpoint --force` abre o endpoint público
só para o IP desta máquina e escreve `endpoint_public_access = true` no `tfvars`. É break-glass
declarado em arquivo, não default.

**Nem a 03 nem a 04 entram no `up-all` por default.** As três primeiras somam centavos; as duas
últimas somam ~US$ 275/mês. Incluir exige `--with-connectivity` / `--with-control-plane`, de
propósito.

**A 03 é o primeiro nível que fica de pé de propósito e é derrubado à noite** — T1. Não presumir
resíduo e destruir; e não esquecer ligada. `connectivity/us-east-1/scripts/destroy` diz em voz alta
o que se perde antes de confirmar.

### Aprovar a região vem antes, e não é Terraform

```bash
aws/docs/accounts/scripts/apply-baseline-service-control-policy --regions us-east-1,us-west-2
```

Sem isso, um `apply` fora das regiões aprovadas falha no primeiro `Create*` com
`explicit deny in a service control policy`, e o erro **parece bug de código**. `--regions` vale
para a Organization inteira — não há como liberar região só numa conta por essa via. O `up-01` faz
um `describe-vpcs` barato para antecipar o deny para antes de qualquer escrita.

### Armadilhas que os scripts pegam antes de tocar em nada

| Armadilha | Onde | O que o script faz |
|---|---|---|
| Bucket de state inexistente | `up-00` | **Para** e imprime o bootstrap manual (state local → apply → `init -migrate-state`). A raiz guarda o próprio state no bucket que gerencia; automatizar às cegas um passo de uma vez só esconde o problema |
| Região negada pela SCP | `up-01`, `up-03` | `describe-vpcs` antes do primeiro `Create*` |
| Zona pai já tem NS para o label | `up-02` | **Recusa.** Delegação antiga colide no apply, e a mensagem do Azure não diz que a causa é um record set preexistente |
| Subzona ausente ou ambígua | `up-03` | **Recusa.** Sem a camada 02 o certificado não tem onde validar; com duas subzonas `<label>.*` não se sabe para qual emitir |
| Hub sem subnet privada | `up-03` | **Recusa.** Sem associação o endpoint fica em `pending-associate` para sempre — sobe, cobra e não conecta |
| Metadata SAML ausente | `up-03` | **Para e imprime o roteiro de console.** É o passo mais fácil de esquecer justamente por não ser Terraform |
| Metadata SAML curto demais | `up-03` | **Recusa** abaixo de 1000 caracteres: o provider exige isso, e arquivo curto quase sempre é página de erro salva por engano |
| Nome de grupo no lugar do id | `up-03` | Traduz nome → UUID pelo Identity Center, e a variável do Terraform recusa o que não for UUID. Nome ali dá túnel que sobe e não alcança nada, com erro que não diz por quê |
| Attachment de fora do state no TGW | `destroy` da 03 | **Recusa.** A AWS também recusa deletar TGW com attachment vivo, mas o erro dela chega depois de o destroy ter apagado o endpoint e o certificado |

### O encanamento comum fica em `scripts/lib`

Sourced, não executado. Log com timestamp em `<raiz>/logs/` (gitignored — a saída carrega account
id, ARN e endpoint reais), `PIPESTATUS[0]` para o `tee` não mascarar falha, confirmação antes de
qualquer apply, e descoberta do bucket a partir do id da Organization. Um script por camada **não**
significa cinco cópias disso — é assim que essas coisas divergem.

Sem tty (pipe, CI, harness de agente) o `read` volta vazio na hora e o cancelamento pareceria
decisão de quem rodou. Nesse caso o script **salva o plano, diz onde está e sai com erro**,
apontando o `--yes`.

### Descida

Não há `down-*`. Derrubar é por raiz, de propósito — a assimetria é intencional: subir a sequência
inteira é rotina, derrubar nunca é. A `control-plane` tem `scripts/destroy` com guardas próprios
(Crossplane sem recurso vivo, contexto kubectl correto). `dns` e `state-backend` têm
`prevent_destroy` no que importa.

## Raízes

**A coluna `Exercitada` diz se a raiz já foi aplicada na AWS ao menos uma vez e teve o resultado
verificado — não se está de pé agora.** O que está de pé neste momento é pergunta de sessão, não de
repositório: vive em `HANDOFF.md`, e a resposta confiável é `terraform state list` por raiz.

| Raiz | Conta | State key | Entrega | Exercitada |
|---|---|---|---|---|
| `state-backend/` | `network` | `state-backend/` | O bucket de state, uma vez, sem região | sim |
| `network-foundation/us-east-1/` | `network` | `network-foundation/us-east-1/` | VPC hub `10.1.0.0/16` | sim |
| `network-foundation/us-west-2/` | `network` | `network-foundation/us-west-2/` | VPC hub `10.3.0.0/16` | sim |
| `dns/` | `network` + Azure | `dns/` | Subzona `nonprod.<domínio>` no Route 53 + delegação NS na zona pai | sim |
| `connectivity/us-east-1/` | `network` | `connectivity/us-east-1/` | TGW isolado por default + cert do ACM + Client VPN com SAML + ALB público de ingress com o listener `:443` compartilhado | sim para o TGW e a VPN — túnel conectado e pacote atravessando até a spoke; o ALB ainda **não** foi aplicado |
| `control-plane/` | `cicd` | `control-plane/` | VPC spoke `10.2.0.0/16`, EKS, NLB interno do ingress, ESO, ArgoCD, Crossplane | sim, **menos com o endpoint da API fechado** — esse é o aceite que falta |

A camada 2 aplicou 39 recursos num único `terraform apply`, sem `-target`: EKS 1.36, dois nós
`t3.medium`, três Pod Identities e os três charts. Com o `3.1` são 61 recursos — entram o NLB
interno com endereços fixos, sua target group e a quarta Pod Identity (a do Load Balancer
Controller). Desde 2026-08-29 o *chart* do controller também sai daqui — antes era instalado à mão, por `helm`, a partir de um checkout local. Prova o que estava em aberto no desenho — os
providers `kubernetes` e `helm` configurados a partir de outputs do módulo do cluster resolvem
na hora do apply. **Não** inventar apply em duas fases.

### `dns/` é a única raiz sem região na state key, e a única com valores em `tfvars`

Hosted zone pública é recurso **global**: não cabe em `network-foundation/<região>/`. E não pode
morar em `connectivity/`, que é destruído toda noite — a zona recriada nasce com **name servers
novos**, e mesmo com a delegação automatizada a propagação do NS não é instantânea.

Ela também é a única raiz que lê valores de `terraform.tfvars` em vez de tê-los inline. Nas outras,
o que está inline (região, CIDR, AZs) é **decisão de desenho documentada**; aqui, domínio, resource
group e subscription são **identidade de quem roda**, e o repo é público.

`manage_delegation = false` desliga o lado Azure: numa raiz com dois providers de cloud, a ausência
de credencial do segundo faz o `plan` falhar mesmo para mudança que só toca o primeiro. Desligado, a
subzona existe no Route 53 e ninguém a resolve — é modo de trabalho, não estado de repouso.

**`dns/` também liga o RAM sharing com a Organization** (`aws_ram_sharing_with_organization`, via
provider aliasado `aws.management`, profile `personal`). Não tem relação com DNS — é configuração
permanente da Organization inteira, e mora aqui porque `dns/` é a raiz T0 (permanente, custo quase
zero), não porque o TGW da `connectivity/` (T1) devesse possuí-la. Sem ela, qualquer attachment
cross-conta de TGW falha com `OperationNotPermittedException`.

A VPC hub entra por `data "aws_vpc"` filtrando `tag:Name` num provider `aws` aliasado com o
profile `network` — não por `terraform_remote_state`. O acoplamento é ao recurso, não ao arquivo
de state da camada 1. O filtro tem de devolver exatamente um id, senão quebra no plan;
`control-plane/scripts/generate-tfvars` confere isso antes de gerar arquivo.

### Por que o bucket de state tem raiz própria

Ele guarda o state de **todas** as camadas e regiões. Enquanto vivia junto da
`network-foundation` de `us-east-1`, um `terraform destroy` daquele hub levaria junto o mapa de
toda a infraestrutura. Numa raiz própria, nenhum destroy de região o alcança — o bucket não está
no state de nenhuma delas. Fix estrutural, não guarda por convenção.

Somam-se duas proteções: `prevent_destroy = true` no recurso, e `force_destroy = false` (default)
— a AWS recusa deletar bucket não-vazio, e ele nunca estará vazio.

### Uma raiz por região, não uma raiz com `-reconfigure`

Cada região tem diretório e state key próprios. A alternativa — uma raiz só, alternando backend
com `terraform init -reconfigure` — tem um footgun permanente: esquecer de trocar o backend antes
do apply mistura as regiões, e nada no Terraform pega isso. Os valores de região, CIDR e AZs
ficam **inline** em cada `main.tf`: são decisões de desenho documentadas
(`aws/docs/network/01-cidr-addressing.md`), não segredo.

Isolamento verificado: `terraform plan -destroy` em `us-west-2` mostra 13 recursos, zero menção
ao bucket ou ao CIDR de `us-east-1`.

### Alocação de CIDR

Supernet `10.0.0.0/12`, um `/16` por VPC. N=0 reservado à Organization, N=1 e N=3 em uso, N=2
para o `control-plane`. **Teto de 15, e região multiplica** — ver
`aws/docs/network/01-cidr-addressing.md`. É a única decisão irreversível da cadeia.

**A VPC spoke nunca pode ser separada do state do cluster.** No teardown, o egress
*pod → subnet privada → NAT → IGW → API do ELB* precisa sobreviver até o último nó sair; o grafo
de dependências do Terraform garante isso somente dentro de um mesmo state. Separar
`rede | cluster` reintroduz o bug do NLB órfão sem o mecanismo que o compensava na Composition
de referência (as ~40 `ClusterUsage`).

O corte `hub | spoke+cluster` é seguro **hoje** porque não há TGW: os nós não roteiam pelo hub.
Quando o TGW entrar, este raciocínio precisa ser revisitado.

## Pré-requisitos

- `aws sso login --profile personal` ativo.
- Profiles locais `network` e `cicd` assumindo `OrganizationAccountAccessRole`.
- `terraform.tfvars` preenchido em cada raiz (gitignored; valores em `CLAUDE.local.md`).
- Para a camada 2: a conta `cicd` na OU `Deployments`. **Já existe** — criada em 2026-08-25.

## Submódulos

| Submódulo | Equivale a | Notas |
|---|---|---|
| `src/network` | XR `Network` (L1a) | 16 recursos com NAT ligado. Subnets derivadas do CIDR com `cidrsubnet()`, não fixas — por isso serve qualquer região sem alteração |
| `src/state-backend` | — | Bucket de state endurecido, com `prevent_destroy` |
| `src/cluster` | XR `Cluster` (L1b) | EKS `authentication_mode = "API"` (sem `aws-auth` ConfigMap), role do cluster, role compartilhada dos nós, access entries e os dois addons de base |
| `src/nodegroup` | idem | Node groups por mapa. `ignore_changes` no `desired_size` para não brigar com autoscaler futuro |
| `src/pod-identity` | trust de Pod Identity das Compositions | Molde dos três consumidores. O trust precisa de `sts:AssumeRole` **e** `sts:TagSession` — só o primeiro falha |
| `src/helm/modules/{aws-load-balancer-controller,ingress-istio,target-group-binding,external-secrets,argo-cd,crossplane}` | XR `ClusterBootstrap` | Um chart por módulo, versão fixada. Duas exceções: `ingress-istio` são três releases (`base`, `istiod`, `gateway`) numa versão só, e `target-group-binding` traz um chart **local** de um CR só |

O módulo do Load Balancer Controller nasce com escopo estreito de propósito: sem IngressClass e
sem o service mutator webhook, ele reconcilia `TargetGroupBinding` e nada mais. O NLB e a target
group são do Terraform (`src/ingress`), e um controller capaz de materializar load balancer
próprio reabriria a porta que o ADR 0004 fechou ao decidir ingress único pelo hub.

Pelo mesmo motivo o Service do gateway em `ingress-istio` é **ClusterIP**: quem materializa o load
balancer é `src/ingress`, e a ligação pods → target group é o `TargetGroupBinding`.

`target-group-binding` é o único módulo com chart local, e a razão é mecânica: não existe chart
upstream para um CR só, e `kubernetes_manifest` faria dry-run server-side no **plan**, exigindo um
CRD que só chega no mesmo apply. O chart local mantém o apply único.

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

Isso vale para a **Organization inteira**, não só para a conta `network`. Depois, copiar um
diretório de região existente e ajustar região e CIDR (N livre do supernet):

```bash
cp -r network-foundation/us-west-2 network-foundation/<nova-região>
# editar main.tf (region, CIDR, AZs) e versions.tf (key do backend)
cd network-foundation/<nova-região>
terraform init -backend-config="bucket=<state-bucket-name>"
terraform plan -out=hub.tfplan
terraform apply hub.tfplan
```

Nenhuma linha de `src/network` muda — foi feito reutilizável e há teste provando que a
aritmética de CIDR acompanha o valor recebido.

## Ordem de apply

O `bucket` do backend fica fora do `versions.tf` porque é valor real; entra por
`-backend-config`. O `profile` **está** no bloco de backend de propósito: o backend é
inicializado antes de o provider ser configurado, então não herda `profile` do bloco `provider`.

A camada 2 tem três scripts em `control-plane/scripts/`, nesta ordem:

```bash
cd control-plane
./scripts/generate-tfvars                              # descobre e valida; só leitura
terraform init -backend-config="bucket=<state-bucket>"  # o bucket sai do script acima
./scripts/apply                                        # plan, confirma, aplica, guarda o log
```

O `generate-tfvars` falha **antes** de gerar arquivo se a tag da VPC hub não for univoca, se o
CIDR pedido já estiver em uso na conta, se a região não passar na SCP ou se o bucket não existir
— erros que de outro modo apareceriam no meio do apply, com recursos já criados atrás.

O `apply` lê o exit code por `PIPESTATUS[0]`: o `tee` sempre retorna 0, e sem isso um apply que
falhou passaria por sucesso. Os logs vão para `control-plane/logs/`, gitignored — a saída carrega
account id, ARN e endpoint reais.

## Ordem de teardown

**Inverso do apply: `control-plane` → `connectivity` → `network-foundation`.**

O `control-plane` antes da `connectivity` **não é convenção, é imposição da AWS**, e agora por dois
caminhos independentes. O primeiro é o TGW: o attachment da spoke vive no state da `control-plane`, e
a AWS recusa deletar um TGW com attachment vivo. O segundo é o ALB: cada célula pendura no listener
`:443` compartilhado o próprio certificado (por SNI) e a própria rule de host, também a partir do
state da `control-plane`. O `connectivity/us-east-1/scripts/destroy` antecipa os dois — recusa com
exit 1 enquanto houver attachment, certificado ou rule de fora do próprio state, e nomeia quem
destruir primeiro. Ele exclui da checagem o que é dele: o attachment do próprio hub e o certificado
default do listener. Contar **~10 min** no destroy da 03: cada
`aws_ec2_client_vpn_network_association` leva 7–10 min, simétrico com a criação. Não é travamento.

Dentro de uma camada a ordem é de graça — é o grafo de dependências do Terraform. O que **não**
é de graça: XRs que o Crossplane tenha criado dentro do cluster depois do bootstrap. Eles não
estão no state, e destruir o cluster primeiro deixa recurso AWS órfão sem controlador. Antes de
destruir a `control-plane`:

```bash
kubectl get managed     # tem de vir vazio
kubectl get composite   # idem
```

Se não vier vazio, deletar os XRs e esperar a reconciliação terminar **antes** do
`terraform destroy`.

`control-plane/scripts/destroy` faz essa checagem antes de chamar o Terraform. Ele também
confere que o contexto corrente do `kubectl` casa com o cluster do state: o contexto pode estar
apontando para o k3d `control-plane`, e um `get managed` vazio no cluster errado é pior que
nenhuma checagem.

## Testes

Sem credencial, sem chamada à AWS — `mock_provider` + `command = plan`:

```bash
for module in src/network src/state-backend src/cluster src/nodegroup src/pod-identity \
              src/ingress \
              src/helm/modules/aws-load-balancer-controller \
              src/helm/modules/ingress-istio \
              src/helm/modules/target-group-binding \
              src/helm/modules/external-secrets src/helm/modules/argo-cd \
              src/helm/modules/crossplane \
              network-foundation/us-east-1 network-foundation/us-west-2 \
              control-plane dns connectivity/us-east-1; do
  (cd "${module}" && terraform init -backend=false && terraform test)
done
```

A volta inteira passa de 2 min — rodar em background ou por diretório, senão o teto de tempo de
uma chamada corta no meio.

Cada raiz de região testa que seu CIDR **cai dentro do supernet**. Essa validação vivia na
variável `hub_vpc_cidr` da raiz única; com os valores inline ela viraria um buraco silencioso,
e um typo no CIDR é irreversível depois de aplicado.

### Duas limitações do framework que já custaram tempo

1. **`command = plan` só avalia valores conhecidos antes do apply.** ID de subnet não é um
   deles, então `aws_nat_gateway.this[0].subnet_id == aws_subnet.public[0].id` não compila.
   Saída: `override_resource` com `override_during = plan`, dando IDs conhecidos — e
   **distintos** entre pública e privada, senão a assertion passa mesmo com o NAT na privada.
2. **Alguns blocos são `set`, não `list`.** `aws_s3_bucket_server_side_encryption_configuration.this.rule[0]`
   falha com "cannot index a set value"; é preciso um `for`. E com `length(...) == 1`, porque
   `alltrue([])` é `true` e um `for` sem checar tamanho passaria com zero regras.

Assertion nova sobre propriedade que importa merece **teste de mutação**: quebre a
implementação de propósito e confirme que o teste falha. Duas das assertions atuais eram vazias
até isso ser feito.

## Custo

A camada 1 tem **custo recorrente zero**: VPC, subnets, IGW, route tables e bucket vazio não
cobram por hora, e o NAT está desligado (sem TGW, nada roteia pelo hub — ligá-lo custaria
~US$ 32/mês servindo zero tráfego). O bucket cobra armazenamento e requisições, na casa de
centavos.

A camada 2 é a que custa: **~US$ 165/mês** — EKS control plane ~73 + NAT ~32 + 2×`t3.medium` ~60.
Números anteriores de ~US$ 105 omitiam os nós. O NAT aqui é deliberado, ao contrário do hub: sem
TGW não há egress pelo hub, e os nós dependem dele para chegar à API do EKS e aos registries.

A camada 03 custa **~US$ 162/mês** (~US$ 0,22/h), mais US$ 0,05/h por conexão ativa e as LCU do
ALB. São duas parcelas: o Client VPN cobra ~US$ 146/mês por **associação de target network**, não por
endpoint — as duas subnets privadas do hub (uma por AZ) dobram essa parcela, e a redundância de AZ
foi mantida sabendo disso; o ALB de ingress soma ~US$ 16/mês. Números de ~US$ 110/mês em texto mais
antigo assumiam uma associação só e nenhum ALB.

**O ALB de ingress vive aqui, e não numa camada permanente, porque sem TGW ele não alcança spoke
nenhuma** — é um listener servindo 404. A consequência a saber antes de derrubar: o teardown noturno
desta camada leva o **ingress público de todas as células** junto, e o DNS name do ALB muda na
recriação, então os registros alias das células são reescritos pelo apply seguinte da 04. É por isso
que a 04 desce antes desta e sobe depois.

Por isso a camada 2 não fica de pé entre sessões de trabalho — sobe, valida, desce
(`control-plane/scripts/destroy`). O state fica no bucket, então subir de novo é o mesmo
`generate-tfvars` + `apply`. A 03 é a exceção declarada: fica de pé durante o dia de trabalho e é
derrubada à noite, não ao fim de cada tarefa.
