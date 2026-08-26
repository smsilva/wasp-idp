# Phase 2 — Private access

O que destrava fechar a API do EKS. Vem antes do ingress porque **quem fala com o API server é a
máquina que roda `terraform apply`** — sem caminho privado, fechar o endpoint quebra o
provisionamento (ver `README.md`).

| # | Passo | Nível | Custo | Aceite |
|---|---|---|---|---|
| `2.1` | **PORTÃO:** verificar o client da AWS VPN nesta distro | — | zero | **FEITO** — instala, daemon sobe, GUI abre, CLI gerencia perfil SAML |
| `2.2` | `connectivity/`: TGW + cert do ACM + SAML provider + Client VPN + associação + rota do supernet | T1 | ~US$ 0,15/h | **escrita** (22 testes, 13/14 mutações). Falta o apply: túnel sobe com identidade do Identity Center; IP de `100.64.0.0/22`; target network `associated`; **e o login SAML completa** |
| `2.3` | Attachment da spoke + `tgw-rt-<spoke>` + rotas + authorization rule do grupo para `10.2.0.0/16` | T2 | +US$ 0,05/h | pelo túnel, alcança IP privado dentro da spoke |
| `2.4` | DNS: zona privada do cluster associada à VPC hub + `dns_servers` | T2 | zero | `dig` devolve IP privado; `kubectl get nodes` pelo túnel |
| `2.5` | `endpointPublicAccess = false` | — | zero | **`terraform apply` completo com VPN conectada**; de fora, recusa |

## `2.1` — o portão — **PASSOU** (2026-08-26)

O maior risco do caminho de acesso não estava na AWS, estava no client na máquina: endpoint com
autenticação **SAML exige o client da AWS**, que no Linux é aplicação desktop empacotada para versões
específicas de Ubuntu. Verificado **antes** de criar recurso que cobra por hora — e o risco que
motivou o portão não existe mais.

**Ubuntu 24.04 LTS (AMD64) é oficialmente suportado** — a doc lista 22.04, 24.04 e 26.04. O client
hoje é build GTK/Electron (o caminho de download é `/GTK/`), não o Mono/WPF que exigia distro antiga.

| Verificação | Resultado |
|---|---|
| Instalação | `dpkg --install` exit 0, `apt-get check` limpo |
| Dependências | as 9 satisfeitas — `libgtk-3-0` e `libasound2` **não existem** com esse nome no noble e vêm por `Provides` de `libgtk-3-0t64`/`libasound2t64` |
| Daemon | `aws-client-vpn-daemon.service` `enabled` + `active`, como root |
| GUI | abre e renderiza ("No profiles available") sob GNOME/X11 |
| CLI | `aws-vpn-client 6.0.1`, 12 comandos |
| Perfil SAML | `import-profile`/`list-profiles`/`get-config`/`delete-profile` funcionam **sem `sudo`**, e o client classifica `auth-type: saml` a partir de `auth-federate` |
| Portas 8096–8115 | livres; não reservadas em repouso |

### `connect` É scriptável a partir da 6.0.1 — a premissa mudou

A versão **6.0.1 (2026-08-12)** instala `/usr/local/bin/aws-vpn-client`, com `connect`, `disconnect`,
`import-profile`, `get-config`, `get-connection-status`, `list-connections`, `put-preference`. Some o
"preço" registrado na decisão 3 (*"o client é desktop, então `connect` não é scriptável"*), e o script
`vpn` do `README.md` deixa de ser só `config`/`status`.

**Duas ressalvas, as duas honestas:**

1. **`latest` não entrega a 6.0.1.** `https://.../GTK/latest/awsvpnclient_amd64.deb` e o repo apt da
   doc entregam **5.4.1** (25/08/2026), que **não tem CLI** — a AWS mantém o 5.x como linha default
   enquanto o 6.0.x é major mais novo e não promovido. **Instalar pela URL da versão**, conferindo o
   sha256 das release notes. Instalar por `latest` é regressão silenciosa de capacidade.
2. **Se `connect` sob SAML abre o navegador sozinho, o `2.2` diz.** O `--auth-user-pass` do CLI é para
   usuário/senha, não SAML. Tentar contra endpoint sintético não respondeu a pergunta: o `connect`
   recusou com `Invalid configuration file` **antes** de tentar o túnel.

**E daí uma armadilha para o script `vpn`:** `import-profile` aceita configuração que `connect` depois
recusa — a validação do CA é no `connect`, não no import. Import bem-sucedido **não** é prova de
configuração boa.

### Saídas se falhar — não usadas, mantidas para o caso de a distro mudar

1. Rodar o client numa VM/contêiner com distro suportada só para conectar.
2. Abordagem comunitária que dirige `openvpn` puro capturando a resposta SAML num listener local —
   **de terceiros, não verificada**; se for tentar, é aqui. (`openvpn 2.6.19` está nesta máquina.)
3. Cair para certificado mútuo temporariamente, **sabendo que se perde a demo de conceder/revogar** —
   é desbloqueio, não alternativa. Com certificado, todo portador alcança todo CIDR autorizado; não
   existe "o Fulano só chega na spoke dele".

## `2.2` — nova raiz `aws/terraform/connectivity/us-east-1/` — **ESCRITA** (2026-08-26)

Separada de `network-foundation/` de propósito: aquela raiz é **deliberadamente de custo zero**, e
isso é propriedade de segurança (pode ser deixada ligada sem pensar). Lê VPC e subnets do hub por
`data` com filtro de tag, como a camada 4 já faz — não `terraform_remote_state`.

Conteúdo, como ficou: TGW com `default_route_table_association` e `default_route_table_propagation`
**desabilitados**, `tgw-rt-hub`, certificado do ACM validado por DNS, `aws_iam_saml_provider`, Client
VPN endpoint com `split_tunnel = true` e `client_cidr_block` `100.64.0.0/22`, associação a **cada**
subnet privada do hub (uma por AZ), rota para `10.0.0.0/12` por subnet, authorization rule por grupo.
O ALB da fase 3 também nasce aqui quando estabilizar.

**22 testes offline, 14 mutações, 13 capturadas.** A que sobreviveu está documentada no próprio teste
e é irreparável por asserção — ver abaixo.

### Três desvios do esboço, todos por achado da execução

**1. O certificado passou a ser público do ACM, validado por DNS** — não autoassinado importado. O
esboço descartava a opção porque *"cert público exigiria o domínio, que só chega no `1.3`"*, e o `1.3`
chegou. O que se compra: **nenhuma chave privada em state nem em disco**, e rotação automática que o
Client VPN acompanha (*"whether through ACM auto-rotation..."* na doc de federated authentication). O
nome (`vpn.<subzona>`) **não** precisa casar com o hostname do endpoint — o client usa
`remote-cert-tls server`, que confere extended key usage, não nome.

Isso reabre a classificação de nível: o certificado era T0 pelo argumento *"o material de client não
muda entre recriações"*. Com CA pública o argumento se cumpre melhor — o que o `.ovpn` embute é a
cadeia da Amazon, estável entre emissões — então o certificado pode viver no state T1 e ser reemitido
todo dia. Preço: alguns minutos de espera de validação em cada apply da manhã.

**2. `transit_gateway_configuration` está FORA de propósito**, apesar de existir no provider e
parecer mais direto que associar subnet. A doc avisa que o attachment que aquele bloco cria leva
*"several hours"* para deletar, que o provider **não espera** por ele, e que isso **impede deletar o
TGW** — incompatível com destruir esta camada toda noite. E o `2.4` depende de as ENIs viverem na VPC
hub.

**3. Subnet privada confirmada como target network.** O requisito de rota para o IGW aparece nos
*Prerequisites* do tutorial de mutual auth, onde o túnel É o caminho de internet. A página de
requisitos de target network pede `/27` com 20 IPs livres e uma subnet por AZ — as `/20` do hub
passam folgado. A AWS acrescenta sozinha a rota local da VPC na associação; a rota que se escreve é a
do supernet, e as duas convivem por prefixo mais longo.

### O passo de console, clique a clique

**A aplicação SAML no Identity Center não pode ser Terraform.** A doc do provider é explícita: *"The
`CreateApplication` API only supports custom OAuth 2.0 applications. Creation of 3rd party SAML or
OAuth 2.0 applications require setup to be done through the associated app service or AWS console."*

**Onde:** o Identity Center vive na **management account** (`221047292361`, profile `personal`, que já
tem `AdministratorAccess`) — não na conta `network`. Isso é de propósito e vale saber: a aplicação
SAML fica na management, e o `aws_iam_saml_provider` que a consome é criado pelo Terraform na conta
`network`, que é onde o endpoint vive (a doc exige que o provider IAM esteja na mesma conta do
endpoint). O XML baixado é o que atravessa essa fronteira.

Console: **https://console.aws.amazon.com/singlesignon** — confirme a região no canto superior
direito antes de começar; a instância é regional.

#### 1. Criar a aplicação

1. Menu à esquerda → **Applications**
2. Aba **Customer managed** (não *AWS managed* — a aplicação é nossa)
3. Botão **Add application**
4. Página *Select application type* → em **Setup preference**, marcar
   **I have an application I want to set up**
5. Em **Application type**, marcar **SAML 2.0**
6. **Next**

#### 2. Nomear e baixar o metadata

7. O campo vem preenchido com `Custom SAML 2.0 application`, que é o default do console. Trocar.

   | Campo | Valor |
   |---|---|
   | **Display name** | `hub-client-vpn` |
   | **Description** | `Acesso de manutencao a rede privada do hub via Client VPN` |

   O Display name **não é consumido por nada** — o Terraform lê apenas o XML —, então o único
   critério é rastreabilidade humana. O `aws_iam_saml_provider` que o Terraform cria do lado da conta
   `network` chama-se `poc-hub-client-vpn` (`${local.name}-client-vpn`, com `local.name = "poc-hub"`);
   a divergência de prefixo é inofensiva, e o par continua óbvio de reconhecer.

8. Na seção **IAM Identity Center metadata** há duas abas: **Default (IPv4 only)** e **Dual-stack**.
   Ficar na **Default (IPv4 only)** — o endpoint nasce com `endpoint_ip_address_type` no default
   `ipv4`.

   Em **IAM Identity Center SAML metadata file**, clicar **Download**.

   **É este arquivo.** Salvar como:

   ```
   aws/terraform/connectivity/us-east-1/saml-metadata.xml
   ```

   (gitignored — identifica a instância de Identity Center). O certificado ao lado, em *IAM Identity
   Center certificate*, **não** é necessário: ele já vem embutido no XML. As URLs de *sign-in* e
   *sign-out* logo abaixo também não — o Client VPN as lê do próprio metadata.

#### 3. Os dois valores que o Client VPN exige

9. Descer até **Application metadata** → escolher **Manually type your metadata values**
   (o default tenta importar um arquivo do service provider, que não existe aqui)
10. Preencher exatamente:

| Campo | Valor |
|---|---|
| **Application ACS URL** | `http://127.0.0.1:35001` |
| **Application SAML audience** | `urn:amazon:webservices:clientvpn` |

Os dois estão na doc do Client VPN em *Service provider information for creating an app*. O ACS é
`127.0.0.1` porque quem recebe a assertion é o **client na máquina do operador**, não um servidor —
daí a porta reservada localmente.

11. **Submit**. Você cai na página de detalhes da aplicação.

#### 4. Mapeamento de atributos — onde erra quem erra

12. Na página de detalhes → botão **Actions** (canto superior direito) → **Edit attribute mappings**
13. Deixar assim, e conferir letra por letra:

| User attribute in the application | Maps to this string value or user attribute in IAM Identity Center | Format |
|---|---|---|
| `Subject` | `${user:email}` | `emailAddress` |
| `memberOf` | `${user:groups}` | `unspecified` |

- **`Subject` tem de ser e-mail.** *"For the SAML assertion, you must use an email address format for
  the `NameID` attribute."* Outro formato dá conexão recusada.
- **`memberOf` é case-sensitive** e a doc diz que tem de ser escrito exatamente assim —
  `memberof` ou `MemberOf` não funcionam, e a falha não diz por quê.
- **`${user:groups}` devolve IDs de grupo, não nomes**, e é isso que as authorization rules casam. O
  `generate-tfvars` traduz nome → UUID do lado do Terraform, e a variável recusa o que não for UUID —
  as duas pontas falam UUID.

14. **Save changes**

#### 5. Atribuir os grupos

15. Ainda na página da aplicação → aba **Assigned users and groups** → **Assign users and groups**
16. Aba **Groups** → marcar `platform-admins` → **Assign users**

Sem isso o login SAML completa e a assertion vem **sem** `memberOf` populado — o túnel sobe e não
alcança nada. É o sintoma mais confuso deste caminho inteiro, porque tudo parece ter dado certo.

#### 6. Voltar para o Terraform

```bash
cd aws/terraform
./scripts/up-03-connectivity
```

O `generate-tfvars` confere que o arquivo existe e tem pelo menos 1000 caracteres (o provider exige, e
arquivo curto quase sempre é página de erro salva por engano), traduz `platform-admins` para UUID, e
só então escreve o `terraform.tfvars`.

#### Fora por ora

- **Portal self-service exige uma segunda aplicação SAML**, com ACS URL
  `https://self-service.clientvpn.amazonaws.com/api/auth/sso/saml` e um segundo
  `aws_iam_saml_provider`. Vale para a demo — a pessoa baixa a própria configuração em vez de receber
  arquivo por e-mail. Fica para depois de o túnel subir.
- **Nunca `authorize_all_groups = true`** — perde-se CIDR-por-grupo, que é metade do valor de ter
  escolhido SAML. Há teste cobrindo.

### Scripts

| Script | O que faz |
|---|---|
| `scripts/up-03-connectivity` (transversal) | orquestra: gera tfvars, `init`, `plan` → confirma → aplica → log. **Fora do `up-all` por default** (`--with-connectivity`), como a 04 |
| `connectivity/us-east-1/scripts/generate-tfvars` | **só leitura.** Descobre `base_domain` da subzona aplicada e traduz nome de grupo → UUID; recusa subzona ausente ou ambígua, hub sem subnet privada, região negada por SCP, e metadata SAML ausente ou curto demais |
| `connectivity/us-east-1/scripts/destroy` | **recusa** se houver attachment no TGW fora deste state, e diz o que se perde antes de confirmar — incluindo que o DNS do endpoint **muda** |

Não há `apply` de raiz: o `up-03` já é isso. A camada 4 tem os dois por ser mais antiga que a
convenção `up-NN`.

### O que os testes não conseguem provar, e por que está escrito lá

O endpoint referencia `aws_acm_certificate_validation.vpn.certificate_arn` **para nascer depois** da
validação. Mas esse ARN é idêntico ao de `aws_acm_certificate.vpn.arn`: nenhuma asserção de valor
distingue as duas referências, e a mutação que troca uma pela outra **passa verde** — verificada.
Ordenação é aresta do grafo, e `terraform test` não assere grafo. Ficou escrito no teste em vez de
mascarado numa asserção que passaria de qualquer jeito.

## `2.3` — o spoke entra na malha

Duas pontas, não uma: a exploração desta sessão achou que o hub nunca tinha sido anexado ao
próprio TGW — `connectivity/` criava o TGW e `tgw-rt-hub`, mas ambos ficavam órfãos, sem
attachment nenhum. Sem o lado do hub, o tráfego que chega pelo túnel na subnet privada não tem
como sair para o TGW, e o lado da spoke sozinho não fecharia o circuito.

**Lado do hub** (`connectivity/us-east-1/`, conta `network`):

- RAM: `aws_ram_resource_share` do TGW (`allow_external_principals = false`) +
  `aws_ram_resource_association` + uma `aws_ram_principal_association` por conta em
  `var.spoke_account_ids` — pré-requisito de qualquer attachment cross-conta.
- Attachment da própria VPC hub, associado a `tgw-rt-hub` (que existia órfã desde o `2.2`).
- Uma rota só, para o supernet inteiro, na route table privada do hub (lida por tag) — mesma
  lógica de "rota é topologia, não cresce por spoke" já usada para a rota do Client VPN.

**Pré-requisito de conta, fora de qualquer camada TGW:** "sharing with AWS Organizations" tem
de estar ligado — sem isso a AWS recusa `AssociateResourceShare` com
`OperationNotPermittedException`. É `aws_ram_sharing_with_organization` (só roda pela management
account), e mora em `dns/` — T0, permanente — não em `connectivity/` (T1, destruída toda noite):
é configuração da Organization inteira, não do ciclo de vida do TGW. Aplicado uma vez, descoberto
na prática ao tentar o primeiro apply do `2.3` (a AWS recusou com a mensagem exata).

Com ele ligado, o attachment cross-conta nasce **já associado**, sem convite — não há
`aws_ram_resource_share_accepter` do lado da spoke.

**Lado da spoke** (`control-plane/`, conta `cicd`):

- Attachment da VPC spoke — criado com o provider **default** (`cicd`, dono da VPC).
- `tgw-rt-<spoke>` — pertence à conta do TGW (`network`) mas o ciclo de vida é da spoke, então
  mora no state dela via o provider `aws.network` já existente (fronteira de state por ciclo de
  vida, decisão 5 do `README.md`).
- Duas propagações, e elas não podem ser trocadas entre si: `spoke_to_hub` (attachment da spoke
  → `tgw-rt-hub`, para o hub aprender a rota de volta) e `hub_to_spoke` (attachment do hub →
  `tgw-rt-spoke`, para a spoke aprender a rota para o hub e, atrás dela, para o cliente VPN).
- Uma rota, no lado da spoke, para o supernet inteiro — espelho da rota do hub.

**Não entrou:** a authorization rule por `10.2.0.0/16` que o esboço original previa. A `2.2` já
cobre o supernet inteiro por grupo, o que já inclui qualquer spoke — rota é topologia (cresce
aqui, uma vez), authorization rule é política (já estava coberta).

Aceite deliberadamente fraco: alcançar um **IP** privado dentro da spoke. Nome ainda não resolve —
isso é o `2.4`.

## `2.4` — DNS, e o risco conhecido

TGW entrega **roteamento IP, não resolução de nome**. O endpoint privado da API do EKS resolve por
uma private hosted zone que a AWS cria e associa à VPC do cluster; de dentro do hub, `kubectl` falha
porque o hostname não resolve ali.

Caminho: associar a zona privada do cluster à **VPC do hub** — par `CreateVPCAssociationAuthorization`
na conta do cluster + `AssociateVPCWithHostedZone` na do hub — e empurrar o resolver da VPC hub
(`10.1.0.2`) como `dns_servers` do Client VPN. As ENIs do endpoint vivem na VPC hub, então esse
resolver é local a elas.

**Risco:** a zona privada **não é output do `aws_eks_cluster`** — achá-la exige `data
"aws_route53_zone"` casando pelo hostname do endpoint, o que é frágil, e ela é **recriada a cada
provisão do cluster**. Plano B: **Route 53 Resolver inbound endpoint na spoke** com `dns_servers`
apontando para os IPs dele — robusto e generaliza para N spokes, mas custa ~US$ 0,25/h em 2 AZs.
Começar pela associação (grátis) e cair para o Resolver se travar.

## `2.5` — fechar

`endpointPublicAccess = false`. O aceite é o único do plano que exige **um apply inteiro**: se
`terraform apply` completar com a VPN conectada, a plataforma é operável privada. Enquanto não
passar, fechar é regressão de operabilidade, não ganho de segurança.

A partir daqui, subir a camada 2 do zero **exige VPN conectada antes do apply** — é o que torna
TGW + Client VPN camada mais permanente que o cluster.
