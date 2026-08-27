# Step 2.2 — Connectivity Apply

_2026-08-26_


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
