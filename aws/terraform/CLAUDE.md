# CLAUDE.md — aws/terraform/

Camada Terraform do bootstrap. Estrutura, ordem de apply e as duas limitações do framework de
teste estão no `README.md` desta pasta — ler antes de mexer. Aqui ficam só as armadilhas que
custaram tempo e não são visíveis no código.

## Fronteira: o que é Terraform e o que não é

Terraform entrega o que se cria uma vez por região e revisa com cuidado; GitOps entrega o que
muda toda semana (`../../decisions.md` §7, cardinalidade × churn). O escopo fino está fechado em
`docs/superpowers/specs/2026-08-25-terraform-bootstrap-module-design.md` — **não ampliar sem
revisitar aquela decisão.**

A **especificação funcional do provisionamento EKS são as Compositions Crossplane** do repo de
referência interno (caminho em `CLAUDE.local.md`), não as fases do chart `aws/eks/chart/templates/`.
As fases são a mesma coisa menos decomposta e com bugs já corrigidos do outro lado.

## State

- **Nunca pôr o bucket de state no state de uma região.** Ele guarda o mapa de tudo; destruir a
  região levaria o mapa junto. Raiz própria em `state-backend/`, com `prevent_destroy`.
- **`profile` precisa estar DENTRO do bloco `backend "s3"`.** O backend é inicializado antes de o
  provider ser configurado, então não herda `profile` do bloco `provider`. Omitir dá erro de
  credencial no `init`, não no `apply`.
- **`bucket` fica fora do `versions.tf`** (valor real) e entra por `-backend-config`. A `key`
  fica no arquivo, porque carrega a região e é o que separa os states.
- Migração de state entre raízes: blocos declarativos, não `state rm` na unha. `removed` com
  `lifecycle { destroy = false }` solta sem destruir; `import` adota do outro lado. Plan limpo é
  o critério de parada de cada passo.
- Trocar a `key` de um state existente: copiar o objeto no S3 para a nova key, `init` na nova
  raiz, conferir `state list` e `plan -detailed-exitcode` = 0, e só então apagar a key antiga.
- **`apply` que morre no meio deixa recurso criado FORA do state, e um lock órfão — e é
  recuperável sem destruir nada.** A AWS continua provisionando depois de o processo morrer.
  Receita: `terraform force-unlock -force <id>` (confirmar antes que não há processo `terraform`
  vivo), `terraform import` de cada recurso órfão, e então um `plan` — que tem de vir **sem
  duplicata**, provando a adoção. Aconteceu com o cluster EKS e o NAT Gateway; os dois voltaram
  ao state sem recriar nada.

## Testes

- **Premissa sobre comportamento de serviço da AWS se confere na doc da AWS ANTES de escrever
  código** — mesma disciplina de "achado sobre módulo do repo se confere no módulo". O passo `2.4`
  inteiro (associação de zona privada, com Resolver inbound endpoint de plano B) caiu em duas frases
  de uma página do EKS: o plano A era impossível e o plano B desnecessário. Custo de não conferir:
  ~US$ 180/mês de recurso que não precisava existir.
- **A regressão offline completa (13 diretórios) passa de 2 min** — rodar em background ou por
  diretório, senão o teto de tempo de uma chamada corta no meio. E usar `-no-color`: os códigos ANSI
  quebram qualquer `grep` na linha `Success!`/`Failure!`.

- `terraform test` com `mock_provider` + `command = plan` roda **sem credencial e sem tocar a
  AWS**. É o ciclo red-green padrão aqui; usar antes de qualquer `apply`.
- **`terraform init -backend=false` num diretório só com `tests/` falha** com `unknown provider`.
  Criar o `versions.tf` primeiro; o teste continua vermelho pelo motivo certo.
- **Assertion nova sobre propriedade que importa exige teste de mutação:** quebrar a
  implementação de propósito e confirmar que o teste falha. Duas assertions desta base eram
  vazias até isso ser feito — uma comparava dois valores desconhecidos, outra usava
  `alltrue([])`, que é `true`.
- Validação que vive numa `variable` some quando os valores viram inline. Ao mover valores para
  dentro do `main.tf`, transformar a validação em assertion de teste — senão vira buraco
  silencioso. Foi o que aconteceu com a checagem de supernet do CIDR.
- **Mutar `validation` exige ENFRAQUECER a condição, não removê-la.** Trocar por `condition = true`
  não deixa o teste vermelho: o Terraform recusa condição que não referencia a própria variável, a
  configuração fica inválida e **nenhum run executa** — o que se lê como "mutação não detectada".
  Enfraquecer (`length(...) >= 0`, `for x in ... : x != ""`) mantém a referência e produz o vermelho
  de verdade.
- **`can(cidrhost(c, 0))` valida CIDR sem regex:** aceita `203.0.113.10/32`, recusa sem prefixo,
  `/33` e octeto acima de 255. Verificado no `terraform console`.
- **Validação em duas camadas tem fronteira:** a **semântica do provider** (ex.: `public_access_cidrs`
  vazio é `0.0.0.0/0` para a AWS) mora no módulo, onde vale para qualquer chamador; a **política da
  célula** (ex.: esta camada não expõe a API ao mundo nem explicitamente) mora na raiz, onde mudá-la
  aparece em diff. Misturar as duas põe decisão de projeto em módulo genérico.
- **Variável sem default é a forma de falhar fechado.** Ela invalida o `terraform.tfvars` já gerado, e
  isso é o mecanismo: quem for aplicar tem de regenerar em vez de herdar um valor perigoso.
- **Um `override_resource` prova o VALOR; dois provam a LIGAÇÃO.** Para asserção sobre atributo que só
  existe depois do apply (`name_servers`, id de subnet), um override sozinho passa mesmo se o
  consumidor tiver o valor **fixo no código** igual ao injetado — comprovado: a mutação que colava
  name servers à mão passou verde. Usar dois runs com valores **e tamanhos** diferentes; nenhuma lista
  fixa satisfaz os dois.
- **`setequal` não existe.** Há `setunion`/`setintersection`/`setsubtract`; igualdade é `==` entre
  dois `toset()`. E comparar atributo `list(string)` com literal `["a","b"]` (que é *tuple*) falha com
  *"LHS and RHS values are of different types"* em vez de comparar — `toset()` nos dois lados resolve.
- **Bloco repetível do provider costuma ser SET, não lista — `[0]` não compila.** `Cannot index a set
  value: set elements do not have addressable keys`. Para bloco que existe uma vez só (
  `authentication_options` do Client VPN), o acesso é **`one(...)`**; para vários, `for` com `if`.
- **`override_resource` substitui os atributos computados POR INTEIRO.** Omitir um atributo que a
  configuração indexa transforma-o em coleção vazia, e o erro (`the collection has no elements`)
  parece bug do código, não artefato do teste. Ao sobrescrever `aws_acm_certificate`, incluir
  `domain_validation_options` junto do `arn`.
- **Validação de schema do provider roda sob `mock_provider`.** Ela é client-side: o
  `aws_iam_saml_provider` recusa `saml_metadata_document` fora de 1000..10.000.000 caracteres **no
  plan**, sem tocar a AWS. Fixture de teste tem de ser realista em TAMANHO, não só em forma.
- **Validações de uma variável são todas avaliadas, não param na primeira que falha.** Se uma chama
  `cidrhost` e outra também, um valor malformado faz a segunda lançar *"Call to function cidrhost
  failed"* e essa é a mensagem que o usuário lê — não a que explica o problema. Cadeia de validação
  precisa de guarda: `!can(cidrhost(var.x, 0)) || <condição real>`.
- **`local.*` do módulo em teste é alcançável na asserção** — não só `output` e recurso. É a saída
  quando o atributo do recurso é *unknown* no plan: `public_access_cidrs` omitido fica "known after
  apply" e nenhuma asserção sobre ele avalia, mas o `local` que decide a omissão é legível.
- **Asserção entre dois computados é impossível offline.** Comparar
  `aws_vpc_security_group_ingress_rule.x.security_group_id` com
  `module.cluster.cluster_security_group_id` dá *"Unknown condition value"* — os dois lados só
  existem depois do apply. Não vale materializar com `override_resource` do `aws_eks_cluster`: o
  override substitui os computados por inteiro e leva `vpc_config` junto. Escrever a ausência da
  asserção e por quê.
- **Passar a consumir atributo de data source num campo VALIDADO obriga a overridar aquele data
  source em TODO arquivo de teste da raiz, não só no novo.** A regra de `443` passou a ler
  `data.aws_vpc.hub.cidr_block`; sob mock o valor é sintético (`oz8pk32m`), a validação client-side
  de `cidr_ipv4` recusa, e o plan morre — derrubando `composition` e `spoke-attachment`, que nada
  tinham a ver com a mudança. Sintoma que parece regressão alheia.
- **Ordenação é aresta do grafo, e `terraform test` não assere grafo.** Se `A` referencia
  `B.attr` só para nascer depois de `B`, e `B.attr` tem o mesmo valor de `C.attr`, nenhuma asserção de
  valor distingue as duas referências — a mutação passa verde. Comprovado com
  `aws_acm_certificate_validation` vs `aws_acm_certificate`. Escrever isso no teste em vez de
  esconder atrás de asserção que passaria de qualquer jeito.

## Scripts de subida

- **A sequência das camadas é executável, não só documentada:** `scripts/up-NN-<camada>` na ordem de
  dependência, mais `up-all`. Ordem, custos e dependências no `README.md`. Mexer numa camada nova
  significa acrescentar um `up-NN`, não instruções soltas.
- **`scripts/lib` é sourced, não executado.** Log com timestamp, `PIPESTATUS[0]`, confirmação e
  descoberta do bucket vivem lá uma vez só.
- **Contar mudanças de um plano SALVO não tem `-detailed-exitcode`** (a flag é do `plan`, não do
  `show`). O caminho é `terraform show -no-color <plano> | grep --count '^  # '`, que é o que permite
  dizer "nada a mudar" em vez de pedir confirmação para um apply vazio.
- **`init -reconfigure` é obrigatório aqui:** a mesma árvore serve várias raízes, e um `.terraform`
  herdado de outra state key faz o Terraform reclamar em vez de reinicializar.
- **Raiz com dois providers de cloud é testável offline** mockando os dois (`mock_provider "aws"` +
  `mock_provider "azurerm"`); o `subscription_id` obrigatório do azurerm não é exigido sob mock.
- **Todo script/comando de apply longo precisa emitir progresso, não só o log salvo em arquivo.**
  Um `terraform apply` de vários minutos rodado via `! <comando>` (fora do agente) sem `tee`/eco
  no terminal deixa quem está acompanhando sem nenhum sinal de que algo está de fato em execução
  — indistinguível de travado. `scripts/lib` já grava log com timestamp; o que falta em applies
  soltos (fora dos scripts `up-NN`) é garantir que a saída também aparece ao vivo no terminal.
- **Guard de script que lê `terraform output` só funciona depois de o output existir no STATE.**
  O `transit_gateway_attachment_id` foi escrito no `outputs.tf` e o `destroy` da camada 03 passou a
  consumi-lo — mas como nenhum `apply` tinha rodado desde então, `terraform output -raw` devolvia
  vazio e o guard acusava 2 attachments de fora em vez de 1. **Código certo, comportamento errado,
  e nada no plan aponta isso.** Um `apply` de zero recursos materializa o output. Vale para
  qualquer script deste repo que leia `terraform output`.
- **Todo `terraform apply`/`destroy` rodado fora dos scripts `up-NN` precisa de `-no-color`.**
  `scripts/lib` já usa; um `apply`/`destroy` improvisado com `| tee arquivo.log` sem essa flag
  salva o log cheio de códigos ANSI, ilegível fora de um terminal que os interpreta.

## Providers `kubernetes` e `helm`

- **Configurar os providers a partir de outputs do módulo do cluster e aplicar tudo num
  `terraform apply` único funciona** — a configuração do provider só precisa estar resolvida
  na hora de configurá-lo, já no apply. Não inventar apply em duas fases com `-target`.
- O que quebra é **data source** desses providers durante o plan. Manter o que for
  Kubernetes como `resource`.
- **`-target` volta a ser necessário noutro caso:** um data source que fica "known after
  apply" cascateia para os providers e faz o Terraform propor recriar **todos** os
  `helm_release`. Sintoma: plan propondo substituir releases sem motivo.
- **O `helm_release` do ArgoCD deixa CRDs para trás no destroy**, com aviso
  *"These resources were kept due to the resource policy"* (`applications`, `applicationsets`,
  `appprojects.argoproj.io`). Inócuo quando o cluster inteiro vai junto; **importa se um dia só o
  release for removido** de um cluster que fica de pé — os CRDs sobrevivem e um reinstall encontra
  schema antigo.
- No **provider `helm` 3.x o `kubernetes` virou atributo**, não bloco: `kubernetes = { ... }`
  com `exec = { ... }` dentro. Exemplo vivo da composição inteira (AKS + ArgoCD + Istio) em
  `examples/cluster_argocd_ingress_istio` do repo `azure-kubernetes` (caminho em
  `CLAUDE.local.md`).

## Versões de chart

- **Conferir no repositório, nunca herdar** do repo interno de referência nem dos scripts de
  `aws/eks/scripts/` — ambos ficaram para trás.
- **O ArtifactHub indexa o canal `master` do Crossplane**, que publica release candidates.
  Para o `stable`, ler `https://charts.crossplane.io/stable/index.yaml` direto.
- ESO 2.9.0 **não serve mais** `external-secrets.io/v1beta1` nem `v1alpha1`. Manifestos
  `ExternalSecret` têm que ser `v1`.

## Endpoint da API do EKS: o que é DNS e o que é rede

- **A private hosted zone do endpoint privado do EKS é INVISÍVEL na conta.** Doc do EKS: a AWS a cria
  e associa à VPC do cluster, mas ela *"is managed by Amazon EKS, and it doesn't appear in your
  account's Route 53 resources"*. Não há `zone_id` para `data "aws_route53_zone"` e não se autoriza
  associação de zona que não é sua — qualquer desenho que dependa de associá-la a outra VPC está
  morto na origem, não frágil.
- **Com o endpoint público desligado, o hostname resolve para IP privado pelo DNS PÚBLICO** — *"the
  cluster's API server endpoint is resolved by public DNS servers to a private IP address from the
  VPC"*. Não precisa de Resolver inbound endpoint (~US$ 0,25/h, mais que o control plane do EKS), nem
  de zona própria, nem de `dns_servers` no Client VPN. Ressalva da doc: para cluster que já existia e
  não resolve privado, ligar e desligar o acesso público uma vez resolve para sempre — criar o
  cluster já fechado, ou ligar-e-desligar, satisfaz isso.
- **O que a doc exige para rede conectada por TGW é UMA regra de security group:** `443/tcp` a partir
  do CIDR da rede conectada, **no security group do cluster** (é ele que governa o endpoint privado;
  `public_access_cidrs` não o afeta — *"the public access CIDRs don't affect the private endpoint"*).
  E a origem é o CIDR da **VPC hub**, não o client CIDR: o Client VPN faz SNAT.
- **`public_access_cidrs` tem de ser OMITIDO, não vazio, quando o endpoint público está desligado.**
  A doc do provider: o valor vale *"when enabled"* e o Terraform *"will only perform drift detection
  of its value when present in a configuration"*. Presente-e-vazio com o endpoint fechado é perpetual
  diff — a EKS guarda `0.0.0.0/0` como default e todo plan proporia `[]`. Mesma família do perpetual
  diff do attachment cross-conta, e a solução aqui é `null`, não `ignore_changes`.
- **A regra de `443` precisa de `depends_on` explícito nos módulos de helm e no ConfigMap.** Com o
  endpoint público fechado, é ela que abre o caminho por onde os providers `helm`/`kubernetes` falam
  com o API server, e nada na configuração do provider cria essa aresta. Sem ela, o sintoma é timeout
  no primeiro release — longe da causa.

## Load balancer: quem é dono do quê

- **`src/network` aplica as tags de descoberta do AWS Load Balancer Controller** desde o commit
  inicial do módulo: `kubernetes.io/role/elb` nas públicas, `kubernetes.io/role/internal-elb` nas
  privadas, cobertas por `tests/tags.tftest.hcl`. Um handoff chegou a registrar a ausência delas como
  bug latente — era leitura do desenho de referência, não do código. **Conferir o módulo antes de
  confiar em achado sobre ele.**
- **O LBC não examina route table** para deduzir se a subnet é pública ou privada — o controller
  in-tree examina, o LBC não ([doc do
  EKS](https://docs.aws.amazon.com/eks/latest/userguide/network-load-balancing.html)). Logo as tags
  de papel não têm fallback: sem elas não há descoberta, e o sintoma aparece longe da causa.
- **A tag `kubernetes.io/cluster/<nome>` fica de fora de propósito.** É opcional a partir do LBC
  `2.1.2` (obrigatória só até `2.1.1`) e serve para escolher entre clusters que **compartilham a
  VPC**. Aqui é um cluster por VPC spoke, e `src/network` não conhece nome de cluster — acrescentá-la
  criaria dependência network → cluster por um ganho inexistente. **Inverte** se um dia mais de um
  cluster dividir a mesma VPC.
- **`TargetGroupBinding` aceita target group criado fora do controller** — verificado na doc do LBC,
  que descreve provisionar o load balancer *"completely outside of Kubernetes"* e ainda gerenciar os
  targets pelo Service. Campos: `targetGroupARN`, `targetType: ip`, `serviceRef`, `vpcID` e
  `networking.ingress` (é este que faz o controller cuidar das regras de SG para targets IP).
  Consequência: **Terraform pode ser dono do NLB/target group sem quebrar o apply único** — o
  workload entra depois só registrando pods. Ressalva: o CR pode referenciar qualquer target group,
  então em cenário multi-tenant exige RBAC.

## Rede

- **TGW nasce com `default_route_table_association` e `default_route_table_propagation` LIGADOS.**
  Desligar os dois é o que torna isolamento por tenant possível — com eles ligados todo attachment
  aprende todo mundo.
- **Ler IPs privados de um NLB é frágil** (`aws_lb` não os expõe; o caminho usual é caçar ENI por
  descrição). **Fixar** com `subnet_mapping { private_ipv4_address = cidrhost(<cidr>, N) }`:
  determinístico, conhecido em tempo de plan, e estável entre recriações.
- **`client_cidr_block` do Client VPN precisa de /22 ou maior e não pode sobrepor VPC nem rota.**
  Carvar fora do supernet.
- **O Client VPN cobra por associação de target network, não por endpoint.** Duas subnets
  privadas (uma por AZ) dobram essa parcela do custo — a estimativa de ~US$ 0,15/h do T1
  assumia uma associação. Decidido manter duas (redundância de AZ) mesmo com o custo maior
  (~US$ 0,20/h ≈ US$ 146/mês parado); reduzir para uma é mudança de `for_each` na raiz.
- **`transit_gateway_configuration` no endpoint do Client VPN é uma armadilha para quem destrói a
  camada todo dia.** O bloco existe e pareceria mais direto que associar subnet, mas a doc do provider
  avisa: o attachment que ele cria leva *"several hours"* para deletar, o provider **não espera**, e
  isso **impede deletar o TGW**. Associação por subnet (`aws_ec2_client_vpn_network_association`) é o
  caminho — e é também o que põe as ENIs na VPC hub, de onde o resolver da VPC é alcançável.
- **Subnet privada serve como target network.** O requisito de rota para o IGW aparece nos
  *Prerequisites* do tutorial de mutual auth, onde o túnel É o caminho de internet; a página de
  requisitos de target network pede só `/27` com 20 IPs livres, sem sobreposição com o client CIDR, e
  uma subnet por AZ.
- **A AWS acrescenta sozinha a rota local da VPC** ao associar a target network. A rota que se escreve
  é a do supernet; as duas convivem por prefixo mais longo.
- **Aplicação SAML do Identity Center NÃO é Terraform.** *"The `CreateApplication` API only supports
  custom OAuth 2.0 applications. Creation of 3rd party SAML or OAuth 2.0 applications require setup to
  be done through the associated app service or AWS console."* O metadata XML entra por arquivo, e o
  `generate-tfvars` da camada 03 imprime o roteiro de console quando ele falta.
- **O TGW nunca ficava anexado à própria VPC hub.** `connectivity/` criava o TGW e `tgw-rt-hub`,
  mas nenhum attachment ligava a VPC hub a eles — órfãos até o `2.3`. Sem esse attachment, o
  tráfego que chega pelo túnel numa subnet privada do hub não tem como sair para o TGW rumo a
  uma spoke. O texto original do plano descrevia `2.3` só como "o lado da spoke"; o lado do hub
  também faltava, e sem ele nada roteia nas duas pontas.
- **Attachment cross-conta exige RAM antes de existir, e RAM exige "sharing with AWS
  Organizations" ligado antes de qualquer share.** Comprovado no primeiro apply do `2.3`: a AWS
  recusou `AssociateResourceShare` com `OperationNotPermittedException` até esse toggle
  organization-wide ser ligado. É `aws_ram_sharing_with_organization` — só roda sob a management
  account (provider aliasado, profile `personal`) e **não tem argumento nenhum** além de `id`
  computado; a própria existência do recurso é o "ligado". Fica em `dns/` (T0, permanente), não
  em `connectivity/` (T1, destruída toda noite) — é configuração da Organization inteira, e um
  destroy noturno da connectivity não pode desligá-la e religá-la todo dia por um recurso que não
  é seu. Com ele ligado, o attachment cross-conta nasce já associado, sem convite — não há
  `aws_ram_resource_share_accepter` do lado da spoke.
- **RAM resolve o convite de compartilhamento; o aceite do ATTACHMENT em si é outro mecanismo.**
  Comprovado no primeiro apply real do `2.3`: com `auto_accept_shared_attachments = "disable"` no
  TGW (o padrão, e o que esta camada define de propósito), o attachment cross-conta nasce em
  `pendingAcceptance` mesmo com RAM habilitado — e associação, propagação e rota falham com
  `IncorrectState`/`InvalidTransitGatewayID.NotFound`, mensagens que não dizem que a causa é o
  aceite pendente. Fix: `aws_ec2_transit_gateway_vpc_attachment_accepter`, criado com o provider
  `aws.network` (dono do TGW), com `depends_on` explícito nas três peças que dependem do
  attachment estar `available`.
- **Uma spoke recém-provisionada não tem alvo natural para teste de alcance.** O security group do
  cluster EKS nasce só com a regra auto-referenciada (tráfego EFA); nada de fora entra, e não há
  workload. Provar conectividade exige uma regra **temporária** (ICMP a partir do CIDR da VPC hub
  — ver SNAT abaixo) e removê-la depois. Não deixar a regra: ela é drift manual num SG gerenciado
  pelo EKS, some no próximo recreate do cluster e ninguém sabe por que o teste parou de funcionar.
- **O Client VPN faz SNAT: o tráfego chega à spoke com origem no CIDR da VPC HUB, não no client
  CIDR.** Comprovado no aceite do `2.3`: com o security group do cluster liberando só
  `100.64.0.0/22` (o client CIDR), o ping não passava; liberando `10.1.0.0/16` (a VPC hub),
  passou — 3/3, RTT ~140 ms. A doc do cenário *"Access a peered VPC"* diz o mesmo por outro
  caminho: manda liberar o **security group do endpoint** nos recursos de destino, não o client
  CIDR. **Consequência:** não existe (nem precisa existir) rota para `100.64.0.0/22` na spoke —
  o retorno vai para `10.1.x.x`, já coberto pela rota do supernet. Duas rotas para o client CIDR
  chegaram a ser escritas perseguindo a hipótese contrária e foram removidas depois do teste
  real. **Regra: hipótese sobre caminho de rede se confere com um pacote, não com raciocínio
  sobre tabela de rotas** — as tabelas estavam todas certas e mesmo assim não passava.
- **Attachment cross-conta tem perpetual diff em `transit_gateway_default_route_table_*`.** Os
  dois atributos são write-only (só valem na criação, não existem na API do attachment) e o
  provider os deriva inspecionando as route tables do TGW — que pertencem à conta `network`. O
  recurso é lido pelo provider default (`cicd`), que não as enxerga, então o refresh devolve o
  default `true` e o plan propõe `true -> false` **para sempre**. Fix: `ignore_changes` nos dois,
  com o comentário explicando que a verdade sobre isolamento está no TGW e nas
  associação/propagações explícitas, não ali. Verificado na AWS antes de ignorar: o attachment
  propaga só para `tgw-rt-hub`, nada em default.
- **A authorization rule por spoke já não era necessária.** O texto do `2.3` previa uma rule para
  `10.2.0.0/16`; a `2.2` já cobre o supernet inteiro (`10.0.0.0/12`) por grupo, que inclui
  qualquer spoke futura. Rota é topologia (uma só, para sempre); authorization rule é política —
  a política já estava lá.
- **As duas propagações do TGW não podem ser trocadas entre si.** `spoke_to_hub` propaga o
  attachment da SPOKE para a route table do HUB (para o hub aprender a rota de volta);
  `hub_to_spoke` propaga o attachment do HUB para a route table da SPOKE (para a spoke aprender
  a rota para o hub e, atrás dela, para o cliente VPN). Mesmo tipo de armadilha já documentada
  para `aws_acm_certificate_validation`: duas referências do mesmo formato, fácil inverter sem
  que uma asserção de valor perceba — coberto por teste de mutação específico.
- **Certificado do endpoint: público do ACM validado por DNS, não autoassinado importado.** Ficou
  possível quando a camada 02 entregou a subzona delegada, e compra duas coisas: nenhuma chave privada
  em state nem em disco, e rotação automática que o Client VPN acompanha (*"whether through ACM
  auto-rotation..."*). O nome do certificado **não** precisa casar com o hostname do endpoint — o
  client usa `remote-cert-tls server`, que confere extended key usage, não nome.

## Raiz com dois providers de cloud

Sem credencial do segundo provider, o `plan` falha mesmo para mudança que só toca o primeiro. Manter
o recurso da outra cloud atrás de um `local.manage_*` para poder desligar sem editar o resto.

## Custo

- **`enable_nat_gateway = false` nos hubs é deliberado**, não esquecimento: sem TGW nada roteia
  pelo hub, e cada NAT custaria ~US$ 32/mês servindo zero tráfego. Há teste cobrindo a ausência
  do EIP. Ligar só quando o TGW entrar.
- Antes de qualquer `apply`, conferir no plan que não aparecem `aws_nat_gateway` nem `aws_eip`
  onde não deveriam. VPC, subnets, IGW, route tables e bucket vazio não cobram por hora.

## Regiões

- Uma raiz por região (`network-foundation/<região>/`), com `key` de backend própria. **Não**
  usar uma raiz só alternando backend com `init -reconfigure`: esquecer de trocar mistura as
  regiões e nada no Terraform pega isso.
- Região, CIDR e AZs ficam **inline** em cada `main.tf` — são decisões de desenho documentadas em
  `../docs/network/01-cidr-addressing.md`, não segredo.
- **Aprovar a região na SCP antes do `apply`** (`../docs/accounts/CLAUDE.md`). Sem isso o erro
  aparece no `Create*`, parecendo bug de código.
- CIDR é a **única decisão irreversível da cadeia**. Supernet `10.0.0.0/12`, um `/16` por VPC,
  teto de 15, e região multiplica.
