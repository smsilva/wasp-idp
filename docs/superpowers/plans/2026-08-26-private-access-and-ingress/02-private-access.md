# Phase 2 — Private access

O que destrava fechar a API do EKS. Vem antes do ingress porque **quem fala com o API server é a
máquina que roda `terraform apply`** — sem caminho privado, fechar o endpoint quebra o
provisionamento (ver `README.md`).

| # | Passo | Nível | Custo | Aceite |
|---|---|---|---|---|
| `2.1` | **PORTÃO:** verificar o client da AWS VPN nesta distro | — | zero | **FEITO** — instala, daemon sobe, GUI abre, CLI gerencia perfil SAML |
| `2.2` | `connectivity/`: TGW + cert de servidor no ACM + SAML provider + Client VPN + associação + rota do supernet | T1 | ~US$ 0,15/h | túnel sobe com identidade do Identity Center; IP de `100.64.0.0/22`; target network `associated`; **e o login SAML completa** |
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

## `2.2` — nova raiz `aws/terraform/connectivity/us-east-1/`

Separada de `network-foundation/` de propósito: aquela raiz é **deliberadamente de custo zero**, e
isso é propriedade de segurança (pode ser deixada ligada sem pensar). Lê as subnets do hub por `data`
com filtro de tag, como a camada 2 já faz — não `terraform_remote_state`.

Conteúdo: TGW com `default_route_table_association` e `default_route_table_propagation`
**desabilitados** (é o que torna o isolamento por tenant possível), `tgw-rt-hub`, cert de servidor no
ACM, `aws_iam_saml_provider`, Client VPN endpoint com `split_tunnel = true` e `client_cidr_block`
**fora do supernet** (proposta `100.64.0.0/22` — mínimo /22, sem sobreposição com `10.0.0.0/12` nem
com CIDR de cliente), associação a uma subnet privada do hub, rota para `10.0.0.0/12`, authorization
rules por grupo. O ALB da fase 3 também nasce aqui quando estabilizar.

### Detalhes de SAML que já custaram tempo em outros lugares

- **Mapeamento de atributos:** o Client VPN espera `NameID` com o usuário e `memberOf` com os grupos,
  e `memberOf` tem de carregar os **IDs** dos grupos do Identity Center, não os nomes. Errar dá túnel
  que sobe e não alcança nada, com erro pouco informativo.
- **Cert de servidor é obrigatório em qualquer tipo de autenticação.** Autoassinado (`easy-rsa`)
  importado no ACM — cert público exigiria o domínio, que só chega no `1.3`.
- **Portal self-service exige uma segunda aplicação SAML.** Vale para a demo: a pessoa entra com o
  próprio SSO e baixa a configuração, sem arquivo por e-mail.
- **Nunca `authorize_all_groups = true`** — perde-se CIDR-por-grupo, que é metade do valor de ter
  escolhido SAML.

### Scripts da raiz

`aws/terraform/connectivity/us-east-1/scripts/`:

| Script | O que faz |
|---|---|
| `generate-tfvars` | descobre VPC/subnets do hub por tag, valida que `client_cidr_block` não colide com o supernet nem com rota existente, confere região aprovada na SCP |
| `apply` | `plan` → confirma → aplica → log |
| `destroy` | **recusa** se houver attachment no TGW fora deste state; diz o que se perde antes de confirmar |

## `2.3` — o spoke entra na malha

Attachment da VPC spoke (conta `cicd`), `tgw-rt-<spoke>` na conta do hub mas no state do spoke,
associação, propagação, e as rotas remotas nas route tables da VPC. Mais a authorization rule do
grupo de operadores para `10.2.0.0/16`, do lado do Client VPN.

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
