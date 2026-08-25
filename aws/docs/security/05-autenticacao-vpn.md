# 05 — Autenticação de VPN

**Pilar WAF principal:** Security ([SEC02 — Identity management](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/identity-management.html); [SEC05 — Protecting networks](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/protecting-networks.html)).

## O recorte deste tópico

`../network/04-vpn-acesso.md` cobre a **topologia** da VPN (fecha no Hub, BGP/ECMP, túneis
IPSec). Este cobre a **identidade**: quem/o quê autentica em cada tipo de VPN, e o ciclo de
vida da credencial. As duas se complementam — topologia decide por onde passa; autenticação
decide quem entra.

## Dois tipos, dois modelos de autenticação

| Tipo | Autentica | Credencial | Termina em |
|---|---|---|---|
| **Site-to-Site** | um **peer de rede** (on-prem, outro cloud) | PSK (pre-shared key) + IKE | Customer Gateway no Hub |
| **Client VPN** | um **humano** (operador/dev) | certificado mútuo e/ou SSO/SAML | Client VPN Endpoint no Hub |

A diferença central: site-to-site autentica **máquina↔máquina** (dois gateways), client VPN
autentica **pessoa** — e por isso client VPN cai na mesma disciplina de identidade humana do
tópico 0 (federar no Identity Center, não criar usuário local por túnel).

## Site-to-Site: PSK como credencial de par

- A AWS gera **1 PSK por túnel** ao criar a VPN Connection (2 túneis = 2 PSKs), ou o PSK é
  acordado externamente quando o peer o traz.
- No mundo Crossplane, o PSK gerado é escrito como **K8s Secret** (`writeConnectionSecretToRef`)
  — é o ponto de entrega para configurar o lado remoto. Proteção = controle de acesso ao
  secret (tópico 4, disciplina de Secrets Manager/RBAC).
- **Confidencialidade isolada do PSK não é o vetor crítico**: o túnel já usa IKEv2 + AES256, e
  o PSK só autentica o estabelecimento. O risco real é quem **lê o secret** — daí escopar o
  acesso, não cifrar o PSK além do que a AWS já faz.
- Sem rotação automática nesta fase (débito conhecido — `../network/04`).

## Client VPN: certificado mútuo + federação (futuro)

Quando o acesso **humano** à rede privada for necessário (hoje ainda não é — a exposição é via
APIM/Front Door), o Client VPN Endpoint fecha no Hub e autentica em duas camadas:

```text
1. Mutual TLS  — certificado do servidor (ACM) + certificado do cliente (por device/usuário)
2. Federação   — SAML/SSO (Identity Center) autoriza QUAL usuário, além de "tem um cert"
```

- **Certificado** prova *posse do device*; **SSO** prova *quem é a pessoa*. As duas juntas
  evitam que um cert vazado sozinho dê acesso.
- Autorização por grupo do IdP → regras de autorização do endpoint por CIDR/grupo (um grupo
  `network-ops` alcança o CIDR de gestão; um `dev` só o de dev).
- Revogar acesso = revogar no IdP (SSO) + CRL do certificado — sem tocar em IAM da conta.

Mesma regra do site-to-site: **fecha no Hub**, nunca no spoke, e a identidade humana vem do
Identity Center (`../accounts/04`), não de credencial local.

## Onde a auth de VPN toca os outros domínios

| Depende de | Para |
|---|---|
| `../accounts/04` (Identity Center) | federar o usuário do Client VPN — sem usuário local |
| tópico 4 (Secrets Manager/RBAC) | guardar o PSK e o material de certificado |
| `../network/04` | a topologia que essa credencial autentica (túnel, Hub, BGP) |

## Well-Architected — porquê

| Best practice | Como atende |
|---|---|
| **[SEC02-BP01 — Use strong sign-in mechanisms](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/sec_identities_enforce_mechanisms.html)** | Client VPN federa no Identity Center; sem usuário local por túnel |
| **[SEC02-BP04 — Rely on a centralized identity provider](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/sec_identities_identity_provider.html)** | mTLS (posse) + SSO (identidade) no Client VPN |
| **[SEC08-BP01 — Implement secure key management](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/sec_protect_data_rest_key_mgmt.html)** | PSK em secret com acesso escopado (RBAC/Secrets Manager) |
| **[SEC05-BP01 — Create network layers](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/sec_network_protection_create_layers.html)** | toda VPN autentica e termina no Hub |

## Próximo

→ [`06-deteccao-e-auditoria.md`](06-deteccao-e-auditoria.md): quando um controle falha, como
o perímetro vira sinal.
