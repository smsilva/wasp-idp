# Archive

Histórico de itens removidos do `HANDOFF.md` na raiz após conclusão.

## Bootstrap IAM user `crossplane-poc` na conta `hub` (2026-08-17)

Executado o bootstrap manual descrito em `aws/docs/bootstrap/00-crossplane-iam-user.md`
contra a conta `hub` real (`094289743086`), usando `AWS_PROFILE=hub` (novo profile local
que assume `OrganizationAccountAccessRole` a partir do profile `personal`).

Resultado:

- IAM user `crossplane-poc` criada.
- Policy gerenciada `PowerUserAccess` anexada.
- Confirmado `implicitDeny` em `iam:CreateRole`/`GetRole`/`PutRolePolicy` só com
  `PowerUserAccess` (gap esperado, documentado no passo ③).
- Policy inline `CrossplaneEksRoleManagement` aplicada (renderizada de
  `aws/eks/providers/bootstrap-iam-policy.json` com `<account-id>` → `094289743086`,
  descartada após uso — o arquivo versionado permanece genérico).
- Access key gerada e gravada em `poc-idp/crossplane-poc-credentials` (Secrets Manager,
  `us-east-1`) — nunca persistida em arquivo local.
- Verificação final (`get-user`, `list-attached-user-policies`, `list-user-policies`,
  `describe-secret`) confere com o esperado no doc.

Não coberto ainda: passo ⑦ (consumir a credencial no Crossplane via
`aws/eks/scripts/configure-aws-creds`) — depende do k3d/Crossplane estarem instalados
(próximo item do `HANDOFF.md`).

## Hub Crossplane de pé no k3d + credencial consumida (2026-08-17)

Fluxo de bootstrap do hub concluído nos 4 passos (`aws/eks/scripts/`), tudo local no k3d
`poc-idp` (sem VPN → pull de `xpkg.*` limpo):

1. **`install-crossplane`** — cluster k3d `poc-idp` (3 servers Ready, k3s v1.31.5) +
   Crossplane 2.3.1 (deployments 1/1).
2. **`install-providers`** — 8 providers `Healthy` (5 AWS v2.5.1 + family + helm +
   kubernetes). `provider-aws-ec2`/`eks` levaram ~7 min sob pressão de apiserver (esperado
   no host de 8 cores); um `ServiceUnavailable` transitório no `providerrevision` no meio,
   benigno.
3. **`install-functions`** — 4 Composition Functions `Healthy` em ~28s (patch-and-transform
   v0.10.8, environment-configs v0.7.3, auto-ready v0.7.0, kcl v0.12.2).
4. **`configure-aws-creds`** — Secret `aws-iam-credential` + `ProviderConfig/default`
   criados; credencial recuperada inline do Secrets Manager autentica como
   `arn:aws:iam::094289743086:user/crossplane-poc` (validado com `sts get-caller-identity`).

Lacuna fechada nesta sessão: o passo 3 não existia. `install-providers` só aplicava os
`kind: Provider`; nenhum manifesto/script tratava das Composition Functions que TODAS as
Compositions em `aws/eks/resources/` exigem (`mode: Pipeline`). Criados
`aws/eks/providers/functions.yaml` (as 4 Functions, versões fixadas) e
`aws/eks/scripts/install-functions` (espelha `install-providers`). Fluxo documentado em
`aws/CLAUDE.md` (seção "Fluxo de bootstrap do hub").

Não coberto ainda: aplicar XRD/Composition/claim da `Network` — cria VPC + NAT reais
(custo), adiado pelo usuário.

## Especificação da sequência de provisionamento e dicionário de recursos (2026-08-27)

Duas entregas, nenhuma toca AWS.

**Portada da trilha corporativa:** o par que descreve o monólito `environment-eks` — árvore de
dependência por camada em YAML mais um dicionário com um arquivo por recurso (34 arquivos).
Traduzido para inglês (nome, título e corpo) e limpo de toda referência que não pode aparecer em repo
público: o API group virou `platform.example.com` e a atribuição de origem não cita caminho interno.

**Escrita para este repo:** a sequência autoritativa (`00 · accounts` → `08 · provas`) e o dicionário
de 61 recursos, um arquivo cada. Levantada por inventário do código real, não de memória — as três
raízes Terraform, `aws/docs/accounts/` e o plano da Frente D.

**As invariantes que o inventário confirmou** e que agora estão registradas no documento:

- Leitura entre camadas é **sempre data source com filtro de tag**, nunca `terraform_remote_state` —
  o lado que lê sobrevive a troca de backend ou de chave no lado que escreve. O filtro tem de
  devolver exatamente um id, e `generate-tfvars` confere antes.
- A **fronteira de state segue o ciclo de vida, não a conta**: recurso da conta do hub cuja vida é a
  de um spoke mora no state do spoke, via provider aliasado.
- **Attachment cross-account tem dois portões** — RAM organization-wide (camada `03`, one-off) e o
  `..._accepter` explícito do lado do hub (camada `05`).
- **Pod Identity tem ordenação real aqui**, ao contrário do monólito: a association precisa existir
  antes do Helm release que a consome, ou o pod entra em CrashLoop com `AccessDenied`.
- As **duas propagações de TGW não são simétricas** — trocar os argumentos quebra o roteamento em
  silêncio.
- A camada `00` **não é Terraform e não pode ser**. Região fora da lista aprovada da SCP aparece como
  deny explícito no primeiro `Create*` de qualquer camada posterior, e parece bug de código.

**Onde cada camada in-cluster realmente existe** (levantado nesta sessão, registrado em
`aws/CLAUDE.md`): o XR `Environment` está bloqueado e superado — o `README.md` dele ainda diz
"walk skeleton COMPLETE", que é resíduo. As Compositions param no equivalente às fases 72/74; tudo de
76 em diante (sub-zona, ESO, external-dns, LBC, Istio, cert-manager, app de validação) existe só no
chart faseado. `ArgoCDInstance` tem só a etapa 1.

**Duas armadilhas de higiene de repo público:**

- A chave do Jira da trilha corporativa tinha sobrado numa linha versionada deste arquivo. Removida.
  **Continua alcançável pelo histórico do git** — decidido não reescrever, porque chave de projeto
  sozinha não identifica empresa nem cliente. Ela entrou na lista de tokens em `CLAUDE.local.md`.
- Um dos tokens proibidos **é também palavra inglesa comum**, e casa em frase legítima de doc em
  inglês, virando falso positivo eterno na varredura. Reescrever a frase (`walkthrough`, `sequence`).
  Qual token e quais frases: `CLAUDE.local.md`. **Não repetir o token aqui** — este arquivo é
  versionado, e documentar a armadilha citando-a reintroduz o problema.

## `2.3` — a spoke entra na malha, e três coisas que só um pacote revelou (2026-08-26)

Aceito com ping real: **3/3 pacotes, 0% de perda, RTT ~140 ms** a um nó do EKS dentro de
`10.2.0.0/16`, pelo túnel. Commits `895e242` (escrita) e `a39430c` (as correções do apply).
Regressão: **104 testes em 13 diretórios, 0 falhas** (eram 86).

**O passo era maior do que o plano dizia — faltava metade.** O texto original descrevia só o lado
da spoke; a exploração achou que **o hub nunca tinha sido anexado ao próprio TGW**. A
`connectivity` criava o TGW e `tgw-rt-hub` e deixava os dois órfãos, sem attachment nenhum — sem
isso o tráfego que chega pelo túnel na subnet privada do hub não tem para onde ir.

**Três achados que nenhuma leitura de tabela de rota daria, todos vindos do apply real:**

- **RAM tem dois portões, não um.** Primeiro `aws_ram_sharing_with_organization` (organization-wide,
  só pela management account) — sem ele, `AssociateResourceShare` é recusado com
  `OperationNotPermittedException`. Ele mora na raiz **`dns/`** (T0, permanente), não em
  `connectivity/` (T1, destruída toda noite): é config da Organization inteira, e um destroy
  noturno não pode desligá-la e religá-la todo dia. Depois, o **aceite do attachment em si** —
  o TGW tem `auto_accept_shared_attachments = disable` de propósito, então o attachment fica em
  `pendingAcceptance` mesmo com RAM resolvido, e associação/propagação/rota falham com
  `IncorrectState`/`InvalidTransitGatewayID.NotFound`, erros que não citam o aceite pendente.
- **O Client VPN faz SNAT.** O tráfego chega à spoke com origem no CIDR da **VPC hub**
  (`10.1.x.x`), não no client CIDR (`100.64.x.x`): liberando só `100.64.0.0/22` no SG do cluster
  o ping não passava; liberando `10.1.0.0/16`, passou. **Duas rotas para o client CIDR chegaram a
  ser escritas** perseguindo a hipótese contrária e foram removidas depois do teste — o retorno
  vai para `10.1.x.x`, já coberto pela rota do supernet. A doc do cenário *"Access a peered VPC"*
  dizia o mesmo por outro caminho: libere o **security group do endpoint** no destino.
  **As tabelas de rota estavam todas certas e mesmo assim não passava** — vale como método:
  hipótese sobre caminho de rede se confere com um pacote, não com leitura de config.
- **Attachment cross-conta tem perpetual diff estrutural** em
  `transit_gateway_default_route_table_{association,propagation}`: write-only, ausentes da API, e
  o provider os deriva das route tables do TGW — que são da conta `network` e invisíveis ao
  provider default (`cicd`). Todo refresh lê `true`, todo plan propõe `true -> false`, para
  sempre. Resolvido com `ignore_changes`, depois de conferir na AWS que o attachment propaga só
  para `tgw-rt-hub`.

**A `authorization rule` por spoke que o plano previa não entrou:** a `2.2` já cobre o supernet
inteiro por grupo. Rota é topologia (cresce aqui, uma vez); authorization rule é política.

**Um `terraform apply` morreu no meio** (o processo caiu; a AWS seguiu provisionando), deixando o
cluster EKS e o NAT criados **fora do state** e um lock órfão. Recuperação: `force-unlock` +
`terraform import` dos dois + plan limpo confirmando zero duplicata. Vale saber que é recuperável
sem destruir nada.

O `connectivity/scripts/destroy` foi corrigido junto: o guard de "attachment de fora" contava o
attachment do **próprio hub** como estranho e teria recusado um destroy legítimo. Agora o exclui
via o output novo `transit_gateway_attachment_id`.

### O teardown, exercitado na mesma sessão — e o que ele provou

Derrubado na ordem inversa: **`control-plane` 46 recursos, `connectivity` 18, 0 falhas nos dois**,
custo por hora de volta a zero (verificado na API: nenhum TGW, endpoint, EKS ou NAT vivo).

- **O guard de precedência foi provado nas três posições**, rodando o `destroy` da connectivity
  fora de ordem de propósito: recusou acusando 2 attachments, recusou acusando 1 depois do fix, e
  passou com 0 depois da control-plane sair. Precedência executável, não parágrafo de README.
- **Armadilha que quase passou batido: fix em script que depende de output novo só funciona
  depois de o output existir no STATE.** O `transit_gateway_attachment_id` tinha sido escrito no
  `outputs.tf` mas nunca aplicado, então `terraform output -raw` devolvia vazio, o guard não
  excluía nada, e a mensagem acusava 2 em vez de 1 — código certo, comportamento errado. Um
  `apply` de **zero recursos** (só materializa o output) resolveu. Vale para qualquer script deste
  repo que leia `terraform output`.
- **O corte de state cross-conta se sustentou no teardown**, que é onde ele seria testado de
  verdade: `tgw-rt-spoke` é recurso da conta `network` mas vive no state do spoke — e **saiu junto
  com o spoke**, sem órfão. É a decisão "fronteira de state segue o ciclo de vida, não a conta"
  funcionando na direção que importa.
- **Tempos, para reconhecer o padrão:** attachment do hub 1m16s, `tgw-rt-hub` 55s, rotas do Client
  VPN ~3m30s cada, **network associations ~7–10 min cada** (simétrico com a criação), registro de
  validação 32s, certificado ACM 1s. O teardown inteiro da connectivity passa de 10 min por causa
  das associations — não é travamento.
- Zero `Service` do tipo LoadBalancer no cluster, conferido **antes** de destruir: o bug do NLB
  órfão (o ticket da trilha corporativa) não tinha como ocorrer aqui. Vale manter a checagem no roteiro.

## `2.2` — apply na AWS, e as duas perguntas do aceite resolvidas (2026-08-26)

`up-03-connectivity --yes` aplicou os 12 recursos planejados, 0 falhas, ~10 min — a maior parte do
tempo em `aws_ec2_client_vpn_network_association` (~6m40s cada associação) e
`aws_ec2_client_vpn_route` (~1m40s/~4m55s). Nada surpreendeu no apply em si; a região no console tem
de ser `us-east-1`, não a região default do último workspace usado (achado colateral: **um `acm:List
Certificates` em `us-east-2` bate na SCP `DenyOutsideApprovedRegions` mesmo sendo leitura** — mesmo
mecanismo já comprovado para `ec2:DescribeVpcs`, agora confirmado também para ACM).

**As duas perguntas que só um apply real respondia, resolvidas:**

- **`aws-vpn-client connect` sob SAML abre o navegador sozinho.** Sim — sem intervenção manual além do
  login na página. A hipótese de que dependeria da GUI não se confirmou.
- **Em que porta o handshake SAML acontece.** `127.0.0.1:35001` — bate com o **guia do administrador**
  do Client VPN, não com o `8096–8115` do guia do usuário Linux (as duas páginas da AWS divergiam
  nisso, e não havia como saber qual valia sem testar).

Túnel `Connected`, verificado por `ip addr`/`ip route`: `100.64.0.2/27` (dentro do `client_cidr_block`
`100.64.0.0/22`) e rotas `10.0.0.0/12` + `10.1.0.0/16` via `tun0` — supernet inteiro e VPC hub
alcançáveis pelo túnel, confirmando a authorization rule e as duas rotas de subnet.

**Perfil exportado para `~/trash/hub.ovpn`**, não `/tmp` — sobrevive a reboot. A DNS name do endpoint
(`*.cvpn-endpoint-0ed2eee5abea362d4.prod.clientvpn.us-east-1.amazonaws.com`) muda a cada recriação da
camada; o `.ovpn` nunca deve ser reaproveitado entre applies, só reexportado.

Camada de pé: ~US$ 0,20/h. Derrubar à noite com `connectivity/us-east-1/scripts/destroy` — regra já
registrada, sem exceção nova.

## `2.2` — a raiz `connectivity/` escrita, e três desvios que a execução impôs (2026-08-26)

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

## `2.1` — o portão do client passou, e derrubou uma premissa do plano (2026-08-26)

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

## Sequência de provisionamento em scripts, e a camada 2 de DNS aplicada (2026-08-26)

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

## `1.3` — raiz `dns/` escrita, e o que um `override_resource` não prova (2026-08-26)

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

## `1.2` — endpoint da API restrito ao IP de quem aplica (2026-08-26)

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

## `1.1` — tags de descoberta do LBC, e a lição sobre achado não conferido (2026-08-26)

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

## Desenho de acesso privado e ingress — plano fechado (2026-08-26)

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

## Port das camadas Terraform para a trilha corporativa (2026-08-26)

Árvore `aws/terraform/` levada para lá numa branch própria: 8 módulos de `src/` sem alteração, três
raízes, scripts, testes, mais README, CLAUDE.md e spec de desenho adaptados. Todo vocabulário local
trocado por `PLACEHOLDER-*`; zero account id, zero nome de bucket, zero nome de conta daqui.
Regressão offline verificada **lá**: 43 testes em 10 diretórios, 0 falhas. As duas lacunas (TGW e tags
de LBC) foram deixadas documentadas como ponto de entrada, não implementadas às cegas.

## Camada 2 do Terraform — escrita, aplicada, verificada e destruída (2026-08-25/26)

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
carrega account id ou VPC id hardcoded.

**Quatro correções ao plano exigidas pelos próprios testes:** `jsonencode` no lugar de
`data.aws_iam_policy_document` (sob `mock_provider` o data source devolve valor sintético e o provider
rejeita); a asserção das Pod Identities passou a verificar `role_name` em vez de `role_arn`, que é
ineliminavelmente *unknown* no plan; `kubernetes_config_map` → `kubernetes_config_map_v1`; e a
cláusula morta `cidrsubnet("10.0.0.0/12", 4, 0) != null` saiu da validação de `vpc_cidr`.

**Versões conferidas nos repositórios, não herdadas:** ESO `2.9.0`, argo-cd `7.7.7` → **`10.4.0`**
(atravessa um major), crossplane `2.3.1` → **`2.4.0`** do canal `stable`.

## Camada 1 do Terraform (2026-08-25)

Bucket de state em raiz própria com `prevent_destroy`, desacoplado de qualquer região; uma raiz por
região com state key própria. Reuso do módulo entre regiões provado com um segundo hub em `us-west-2`
sem alterar uma linha de `src/network`. Isolamento verificado: `plan -destroy` de uma região não
alcança a outra nem o bucket.

## Frente A — contas (2026-08-24/25)

Vocabulário do whitepaper aplicado em doc, scripts e na Organization real. CloudTrail organizacional +
conta `log-archive` + bucket de auditoria. SCPs baseline em Root/Security/Infrastructure/Workloads/
Deployments. Permission set de rotina da `log-archive` em `ReadOnlyAccess`. Break-glass documentado.
OU `Deployments` + conta `cicd` criadas e movidas, com deny de região comprovado na prática.

## Frente C — documentação (2026-08-24/26)

Domínio `tenancy/` a partir da SaaS Lens; `security/08-control-plane-identity.md`; correções na
família conta × região × papel; nomes de arquivo e H1 em inglês; hierarquia de fontes WAF →
whitepaper → SRA. Nesta sessão, os `CLAUDE.md` de `network/`, `dns/` e `terraform/` ganharam as
armadilhas descobertas no desenho.

A SaaS Lens confirma por escrito o que `decisions.md` §3 já havia derivado: mesmo com recursos
dedicados, um silo *"still relies on a shared identity, onboarding, and operational experience"* — é
isso que separa SaaS de *managed service*.

## Comparação com desenho de referência, e resolução PrivateLink vs TGW (2026-08-26)

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

**Ingress: PrivateLink vs TGW — resolvido.** O spec
`docs/superpowers/specs/2026-08-25-private-ingress-via-privatelink.md` continua **válido na
fundamentação** (a citação do whitepaper que separa PrivateLink de TGW por tipo de conectividade), mas
a escolha foi **reaberta e resolvida a favor do TGW** para o caminho hub→spoke: com VPN de cliente
decidida, o TGW entra de qualquer forma e o custo marginal de usá-lo também no ingress cai a zero.

**PrivateLink não morre.** Volta como candidato natural na fatia de **spoke de recursos
compartilhados** (banco, mensageria), onde CIDR sobreposto e autorização por principal de conta valem
dinheiro — ao contrário do caso de ingress, onde não usamos nenhum dos dois.

O que continua válido do spec: o NLB fica na **spoke** (o PrivateLink exige NLB no lado provedor, a
AWS não aceita ALB ali); provar conectividade de dentro antes de expor; e o hub não tem compute

## `2.4` + `2.5` — o passo de DNS que não era de DNS (2026-08-27)

Nada tocou a AWS. Regressão: **111 testes em 13 diretórios, 0 falhas** (eram 104), com **6 mutações
rodadas e 6 capturadas** no root e 1 no módulo.

**O `2.4` foi escrito no plano com uma premissa dupla, e a doc do EKS desfez as duas metades.** O
passo pedia associar a private hosted zone do endpoint do EKS à VPC hub, com plano B de Resolver
inbound endpoint se o lookup se mostrasse frágil.

- **Plano A é impossível, não frágil.** *"Amazon EKS creates a Route 53 private hosted zone on your
  behalf (…) This private hosted zone is managed by Amazon EKS, and it doesn't appear in your
  account's Route 53 resources."* Não há `zone_id` para ler, e não se autoriza associação de zona que
  não é sua. O risco registrado no plano (*"o lookup por hostname é frágil"*) subestimava: não havia
  o que procurar.
- **Plano B é desnecessário, o que é melhor motivo ainda para não construir.** Com o endpoint público
  desligado, *"the cluster's API server endpoint is resolved by public DNS servers to a private IP
  address from the VPC"*. Custaria ~US$ 0,25/h — **mais que o control plane do EKS** — para resolver
  um problema que a AWS já resolve.

**Sobrou o que a doc prescreve para "connected network":** *"your Amazon EKS control plane security
group contains rules to allow ingress traffic on port 443 from your connected network"*. Um recurso,
custo zero, no state da spoke — e a origem é o CIDR da **VPC hub**, não o client CIDR, pelo SNAT já
provado com pacote no `2.3`.

**O `2.5` veio junto porque só junto é verificável** (com o endpoint público ligado, o DNS devolve IP
público e `kubectl` pelo túnel não prova nada), e ficou mais forte do que o plano previa: o endpoint
público fecha **por default**. O `1.2` tinha posto o falha-fechado na variável (*"sem default, quem
aplica é obrigado a declarar o `/32`"*); agora está no flag — **não existe valor de tfvars que
exponha a API ao mundo**, e abrir é break-glass com `generate-tfvars --enable-public-endpoint`, que
só nesse caso descobre o IP da máquina.

Quatro coisas aprendidas na execução, registradas em `aws/terraform/CLAUDE.md`: `public_access_cidrs`
tem de ser omitido, não vazio, com o endpoint fechado (drift detection só corre *"when present in a
configuration"*); consumir atributo de data source num campo validado obriga a overridar esse data
source em todo arquivo de teste da raiz; `local.*` do módulo é alcançável na asserção do teste, não só
`output` e recurso; e asserção entre dois computados não avalia offline.

**Docs atualizadas juntas, como a regra do spec exige:** a camada `06` da sequência de provisionamento
passou de "private DNS" a **dissolvida na `05`** (não sobrou recurso próprio, logo não há raiz nova
nem fronteira de state nova), o índice do dicionário ganhou
`aws_vpc_security_group_ingress_rule` e os dois recursos de Route 53 viraram **`Rejected`** — mantidos
como registro de desenho, com o motivo de cada um (um impossível, o outro desnecessário), não
apagados.

**Falta o `apply`** que prova o caminho privado inteiro (aceite conjunto `2.4`+`2.5`); enquanto ele
não roda, o que existe é código e teste, não comportamento observado.
nenhum hoje.