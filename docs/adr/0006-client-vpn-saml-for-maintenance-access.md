# Client VPN with SAML for maintenance access

**Status:** Aceito

## Contexto

Acesso de manutenção (operador humano precisando alcançar um endpoint privado, como a API do EKS)
precisa de autenticação e de concessão/revogação por pessoa. Duas alternativas na mesa: certificado
mútuo (mTLS) ou AWS Client VPN com SAML via Identity Center.

## Decisão

**AWS Client VPN no hub, autenticação SAML** pelo Identity Center. Escolhido sobre certificado
mútuo porque **conceder e revogar acesso a uma pessoa é a demonstração** que o desenho precisa
provar, e porque `access_group_id` dá **CIDR por grupo** — com certificado, todo portador alcança
tudo que estiver autorizado, sem diferenciação por identidade.

O preço original desta escolha — client desktop, `connect` não scriptável — **deixou de existir**:
a versão 6.0.1 do client da AWS trouxe CLI, então a automação continua possível.

## Consequências

O Client VPN faz **SNAT**: quem chega numa spoke por ele aparece com o IP da VPC hub, não do
cliente/operador. Isso significa que uma prova de isolamento baseada em "endereço de origem" não
distingue operador de operador — a distinção vive na authorization rule por grupo, do lado do
endpoint. Essa ressalva afeta diretamente o desenho das provas negativas de isolamento (`4.1`/`4.2`).

Também exige que a aplicação SAML no Identity Center seja mantida por console (a AWS não permite
`CreateApplication` de SAML customizado via API/Terraform) — passo manual documentado em
`docs/superpowers/plans/2026-08-26-private-access-and-ingress/02-private-access.md`.
