# Real-Run Validation of `provision-region.yml` (Issue #41, Third Slice)

A raiz `ci/` foi aplicada na AWS em 2026-08-31 (8 IAM resources, contas `270222614208`/
`094289743086`, ver `aws/terraform/bootstrap-checklist.md` itens 6-7), e as 4 variáveis/secret
foram configuradas no repositório GitHub. Restava só o item 8: um `workflow_dispatch` real de
`provision-region.yml`. Levou 8 execuções, cada uma diagnosticada a partir de logs/CloudTrail —
registrado aqui porque cada causa raiz é reaproveitável em qualquer workflow futuro que assuma
role via OIDC do GitHub ou fale com a API de um EKS por endpoint público temporário.

## Run 1 — `AccessDenied` em `sts:AssumeRoleWithWebIdentity`

CloudTrail mostrou o `sub` real emitido pelo GitHub:
`repo:smsilva@287870/wasp-idp@522972834:ref:refs/heads/main` — formato qualificado por ID
(`owner@owner_id/repo@repo_id`), não `repo:<owner>/<repo>:...`. O dono ou o repositório já foi
renomeado, e o GitHub passa a emitir o claim `sub` sempre com os IDs numéricos imutáveis depois
disso, mesmo tendo voltado ao nome atual. Fix: trust da role `cicd` com o formato qualificado —
ver `aws/terraform/ci/main.tf` e `ci/README.md`.

## Run 2 — SAML "Could not parse metadata"

`printf '%s' "${{ secrets.SAML_METADATA_XML }}"` quebra: a interpolação `${{ }}` do GitHub
Actions processa o conteúdo antes do shell rodar, e o XML do metadata SAML tem aspas duplas que
colidem com a sintaxe do YAML do workflow. Fix: passar o secret por `env:` em vez de
interpolação direta — `printf '%s' "${SAML_METADATA_XML}"` lendo de variável de ambiente, imune
a esse parsing.

## Runs 3-5 — três lacunas sucessivas de leitura IAM

`iam:ListRolePolicies`, depois `iam:ListAttachedRolePolicies`, depois
`iam:ListInstanceProfilesForRole` — o provider AWS chama essas actions ao ler/atualizar/deletar
uma role existente, e faltavam na policy inline de `aws/terraform/ci/main.tf`. A terceira já
estava documentada em `aws/CLAUDE.md` para o `bootstrap-iam-policy.json` do `crossplane-poc`
(mesmo gotcha, contexto diferente) — não foi generalizada de propósito, cada raiz declara sua
própria policy.

## Run 6 — `ExpiredTokenException` depois de ~5 min

O token OIDC do GitHub vive ~5 minutos (confirmado no CloudTrail: job às 22:08:44, `exp` do
token às 22:13:46). A primeira versão do workflow escrevia `web_identity_token_file` apontando
para o JWT bruto salvo em disco, deixando o SDK reautenticar a partir dele a cada renovação de
sessão — mas o apply de uma região leva 20-30 min, e o JWT morreu muito antes disso. Fix imediato
(que depois foi revisto no run 7, ver abaixo): `aws sts assume-role-with-web-identity` uma vez no
início do job, gravando o resultado em `~/.aws/credentials`. O token nunca mais é lido.

## Run 6 (mesma execução) — `ResourceInUseException: Addon already exists`

O addon `aws-ebs-csi-driver` tinha sido criado por uma tentativa anterior que morreu no meio,
ficando fora do state. `terraform import` de
`module.cell.module.cluster.aws_eks_addon.this["aws-ebs-csi-driver"]` resolveu — o plan seguinte
mostrou o recurso "atualizado in-place", provando a adoção sem duplicata.

## Run 7 — a expiração "resolvida" no run 6 era só adiada (issue #47)

Trocar o JWT por credenciais estáticas de 1h (o default do
`assume-role-with-web-identity`) só empurrou o problema: quando a hora termina, não há como
renovar — o JWT de 5 min já não existe. A issue #47 tinha aceitado esse teto de 1h como
limitação conhecida (role chaining trava a sessão em 1h, *"regardless of the maximum session
duration setting"*). Só que **isso vale para role chaining, não para
`AssumeRoleWithWebIdentity`**: o `DurationSeconds` dessa API vai de 900s até o
`MaxSessionDuration` **da role**, que aceita de 1h a 12h (doc da STS). Fix real, não paliativo:
`max_session_duration = 21600` (6h, teto de um job em runner hospedado pelo GitHub) na role
`cicd` + `--duration-seconds 21600` na troca. A sessão da `network` continua capada em 1h (essa
sim é role chaining de verdade, via `source_profile`), mas deixou de ser fatal — o SDK a
re-deriva sozinho a partir da `cicd`, que agora sobrevive ao job inteiro. Fecha a #47 pela causa
raiz, não pela aceitação do limite. Detalhe completo em `aws/terraform/ci/README.md`, seção
"Credenciais que sobrevivem ao `apply`".

## Run 7 (mesma execução) — timeout no *refresh*, não no apply

Com a expiração resolvida, o job ainda morreu — mas antes de qualquer `Modifying`, direto no
`terraform plan`: `dial tcp <ip-privado>:443: i/o timeout` em
`kubernetes_config_map_v1.platform_bootstrap` e `kubernetes_namespace_v1.gateway`. Causa: todo
`terraform plan` faz *refresh* do state antes de calcular o diff, e esse refresh lê os recursos
Kubernetes já existentes através do endpoint ATUAL do cluster — que estava fechado, porque o
`--close-public-access` do run anterior já tinha rodado, e a variável que abriria o endpoint
neste run só teria efeito depois que o apply (que ainda não começou) rodasse. Um runner do
GitHub Actions não tem VPN para o caminho privado. Fix:
`aws/terraform/scripts/up-02-region` agora abre o endpoint com um `apply -target` isolado
(`module.cell.module.cluster.aws_eks_cluster.this`) *antes* do plan completo, só quando
`--public-cidr` é passado — o único caminho que abre a partir de fechado.

## Run 8 — verde de ponta a ponta

Todos os 9 passos com sucesso: OIDC, SAML, egress IP, os 6 helm releases de `module.cell`
(`argo_cd`, `aws_load_balancer_controller`, `crossplane`, `external_secrets`,
`ingress_istio` base + `istiod`), e o fechamento do endpoint público no `if: always()`. Fecha o
item 8 do `bootstrap-checklist.md` e, com ele, a issue #41.
