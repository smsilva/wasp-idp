# Lessons learned — Network and VPN

Fato + porquê, um por linha. Narrativa completa de cada achado, quando existe, em
[`docs/archived/`](../../../docs/archived/index.md).

- TGW nasce com association/propagation default ligados — desligar os dois é o que torna
  isolamento por tenant possível.
- TGW entrega roteamento IP, não resolução de nome.
- Route table por spoke não isola cliente de cliente — precisa route table por cliente.
- Client VPN com SAML exige o client da AWS; cert de servidor obrigatório em qualquer
  autenticação; `memberOf` carrega IDs de grupo, não nomes; nunca `authorize_all_groups = true`.
- Client VPN faz SNAT — tráfego chega à spoke com origem no CIDR da VPC hub, não no client CIDR.
  Não escrever rota para o client CIDR em spoke nenhuma; liberar o CIDR do hub nos SGs de destino.
  Comprovado com pacote no `2.3`.
- Attachment cross-conta de TGW tem dois portões: RAM (`aws_ram_sharing_with_organization` +
  share/associations) e depois o aceite do attachment em si
  (`auto_accept_shared_attachments = disable`) — sem o segundo, fica `pendingAcceptance` e falha
  com erros que não citam a causa.
- Hipótese sobre caminho de rede se confere com um pacote, não lendo route table — no `2.3` as
  tabelas estavam certas e mesmo assim não passava.
- Client da AWS VPN roda nesta máquina e desde a 6.0.1 é scriptável (Ubuntu 24.04 oficialmente
  suportado, build GTK/Electron); instala GUI + daemon + CLI `/usr/local/bin/aws-vpn-client`
  (gerencia perfil sem `sudo`).
- `latest` do client entrega 5.4.1, sem CLI — o CLI só existe na 6.0.1, que exige URL de versão
  explícita. Regressão silenciosa: instala, GUI abre, `aws-vpn-client` não existe.
- `import-profile` aceita configuração que `connect` recusa — validação do CA é só no `connect`.
- `client_cidr_block` precisa de /22 ou maior, sem sobreposição — daí `100.64.0.0/22`.
- `transit_gateway_configuration` no endpoint do Client VPN é armadilha para quem destrói a camada
  todo dia: o attachment que cria leva horas para deletar e impede deletar o TGW. Associação por
  subnet é o caminho certo.
- Subnet privada serve como target network — exigência de rota para IGW é só do tutorial de mutual
  auth. AWS acrescenta a rota local da VPC sozinha na associação.
- Aplicação SAML do Identity Center não pode ser Terraform — `CreateApplication` só cria OAuth 2.0
  customizado. Metadata XML entra por arquivo.
- Certificado do endpoint pode ser público do ACM validado por DNS (não precisa autoassinado) —
  nenhuma chave privada em state/disco, rotação automática. Nome do certificado não precisa casar
  com o hostname (`remote-cert-tls server` confere extended key usage, não nome).
- `NameID` da assertion SAML tem de ser e-mail; assertion e resposta assinadas; um IdP só por
  endpoint; sem single logout.
- Portas do handshake SAML divergem entre guias da AWS: usuário Linux diz `8096–8115`,
  administrador diz `35001` (o que vale — ACS URL usa `35001`).
- Azure VPN Gateway leva 30–45 min para provisionar; subnet tem de se chamar `GatewaySubnet`; ASN
  do lado Azure é 65515; inside CIDRs em `169.254.21.0–169.254.22.255`, `/30` cada.
- Raiz com dois providers de cloud: sem credencial do segundo, o `plan` falha mesmo para mudança
  que só toca o primeiro — guardar atrás de `local.manage_*`.
