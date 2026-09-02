# `security/` — Domain: Security & IAM

Índice de leitura. Convenções e regras ficam em [`CLAUDE.md`](CLAUDE.md).

## O que este domínio entrega

O **perímetro de identidade** de toda a arquitetura: quem pode agir, com qual privilégio, em
qual conta, e como isso é detectado. Enquanto [`accounts/`](../accounts/) decide **onde** as identidades
vivem (SSO na management account, contas por projeto) e [`network/`](../network/) decide **por onde** o
tráfego passa, este domínio decide **o que cada identidade pode fazer** — humano ou máquina,
dentro de uma conta ou cross-account — e como uma violação vira sinal auditável.

Não repete SSO/permission sets (isso é [`accounts/04-cross-account-access.md`](../accounts/04-cross-account-access.md)); parte dali
e aprofunda: policies escopadas, roles cross-account, perímetro de dados/RAM, identidade de
workload (Pod Identity/IRSA), autenticação de VPN e detecção.

## Tópicos

| # | Arquivo | Assunto | Pilar WAF principal |
|---|---|---|---|
| 0 | [`00-identity-model.md`](00-identity-model.md) | Humano vs. máquina; as 3 perguntas do perímetro (quem/o quê/onde); credenciais temporárias por padrão | Security ([SEC02 — Identity management](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/identity-management.html)) |
| 1 | [`01-least-privilege-and-policies.md`](01-least-privilege-and-policies.md) | Menor privilégio; policies escopadas por ARN; permission boundaries; SCP como teto | Security ([SEC03 — Permissions management](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/permissions-management.html)) |
| 2 | [`02-cross-account-roles.md`](02-cross-account-roles.md) | `sts:AssumeRole`, trust policies, `ExternalId`, confused deputy; sem IAM user duplicado por conta | Security ([SEC02 — Identity management](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/identity-management.html)/[SEC03 — Permissions management](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/permissions-management.html)) |
| 3 | [`03-data-perimeter-and-ram.md`](03-data-perimeter-and-ram.md) | Resource-based policies; RAM com escopo por Organization; `allowExternalPrincipals=false` | Security ([SEC03 — Permissions management](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/permissions-management.html)) |
| 4 | [`04-workload-identity.md`](04-workload-identity.md) | Automação (Crossplane) sem SSO; IAM user escopado; Pod Identity/IRSA; máquina fora da AWS (Roles Anywhere vs OIDC federation); trajetória k3d→AKS→EKS; segredos no Secrets Manager | Security ([SEC02 — Identity management](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/identity-management.html)/[SEC08 — Protecting data at rest](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/protecting-data-at-rest.html)) |
| 5 | [`05-vpn-authentication.md`](05-vpn-authentication.md) | Client VPN (cert/SSO) e site-to-site (PSK); ciclo de vida da credencial; ponte com [`network/04-vpn-access.md`](../network/04-vpn-access.md) | Security ([SEC02 — Identity management](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/identity-management.html)/[SEC05 — Protecting networks](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/protecting-networks.html)) |
| 6 | [`06-detection-and-audit.md`](06-detection-and-audit.md) | CloudTrail, IAM Access Analyzer, GuardDuty, credential report; achar privilégio excessivo | Security ([SEC04 — Detection](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/detection.html)) |
| 7 | [`07-crossplane-map.md`](07-crossplane-map.md) | O que de IAM é (e não é) provisionável via Crossplane; estado do PoC vs. alvo; bootstrap galinha-e-ovo | — |
| 8 | [`08-control-plane-identity.md`](08-control-plane-identity.md) | Quantas identidades para N control planes regionais; role origem vs. role destino; contenção de região; aposentar o IAM user | Security ([SEC02-BP02 — Use temporary credentials](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/sec_identities_unique.html)) |
