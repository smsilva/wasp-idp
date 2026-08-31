# Checklist de bootstrap — do zero ao primeiro `workflow_dispatch`

Sequência completa, uma vez por Organization. Cada item diz **quem executa** e **onde** o
detalhe vive — sem duplicar conteúdo.

- [ ] **1. Organization, contas, OUs, Identity Center** — admin humano, console + scripts.
      Detalhe: `aws/docs/accounts/`.
- [ ] **2. Aprovar a região na SCP** — admin humano, console.
      Detalhe: `aws/docs/accounts/` (política de regiões habilitadas).
- [ ] **3. `up-00-state-backend`** — admin humano, `terraform apply` local com profile `network`.
      Detalhe: `aws/terraform/README.md`, seção "Ordem e permanência".
- [ ] **4. `up-01-dns`** — admin humano, `terraform apply` local.
      Detalhe: `aws/terraform/README.md`.
- [ ] **5. Aplicação SAML no Identity Center** — admin humano, console (não é Terraform:
      `CreateApplication` só cria OAuth 2.0 customizado). Salvar o metadata baixado em
      `variables/saml-metadata.xml`.
      Detalhe: `aws/terraform/README.md`, seção "Os dois eixos".
- [x] **6. `terraform apply` da raiz `ci/`** (OIDC provider + as duas roles) — admin humano,
      local, profiles `cicd`/`network`. Aplicado em 2026-08-31 (8 added, 0 changed, 0 destroyed).
      Detalhe: `aws/terraform/ci/README.md`.
- [x] **7. Configurar variáveis e secret no repositório GitHub** — admin humano, console do
      GitHub (Settings → Secrets and variables → Actions): `CICD_ROLE_ARN`, `NETWORK_ROLE_ARN`,
      `STATE_BUCKET` (variables) e `SAML_METADATA_XML` (secret). Configurado em 2026-08-31 via
      `gh variable set`/`gh secret set`.
      Detalhe: `aws/terraform/ci/README.md`, passo 4-5.
- [ ] **8. Primeiro `workflow_dispatch` de `provision-region.yml`** — CI, gatilho manual.
      Detalhe: `.github/workflows/provision-region.yml`.

O valor deste checklist é ordenação e completude, não profundidade — o atrito real desta frente
foi descobrir, uma peça de cada vez, que faltava `values.tfvars`, faltava o metadata SAML,
faltava o symlink. Um item pulado custa um `apply` que morre no meio, longe da causa.
