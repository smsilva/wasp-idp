# Known Broken

Achados operacionais — itens em aberto ou limitações intencionais aceitas conscientemente.
Itens fechados/resolvidos saem desta lista (detalhe em
[`docs/archived/index.md`](../../docs/archived/index.md)); quando um item vira trabalho
rastreável, referencia a issue do GitHub em vez de duplicar a narrativa aqui.

## Em aberto ou intencional

1. **Break-glass documentado, controles ausentes** — MFA de root não verificado, alarme de uso de
   root não existe (falta regra EventBridge), ensaio nunca executado. Issues #31, #32.
2. **Management account com `AdministratorAccess` em usuário, não grupo** — migrar para
   `platform-admins` (atribuir grupo antes de revogar usuário). Issue #30.
3. **Credencial-raiz do Crossplane é access key de longa duração** — *intentional*, só na trilha
   k3d (sem Pod Identity; no EKS o pod usa `AWS_CONTAINER_CREDENTIALS_FULL_URI`). Issue #20.
4. **`bootstrapClusterCreatorAdminPermissions` divergente** — `true` na camada 2, `false` no
   cluster do chart Crossplane. Issue #17.
5. **VPC default da `cicd` de pé em toda região**, SG aberto — *unexpected*, workload real quando a
   camada 2 sobe. Issue #34.
6. **Link quebrado** em `docs/superpowers/plans/2026-08-07-cluster-zero-terraform.md` →
   `infra/terraform/cluster-zero/README.md` — *intentional*, artefato da trilha Azure nunca
   construído.
7. **Valores reais em docs genéricas** — account id em
   `aws/docs/bootstrap/00-crossplane-iam-user.md:91`; e-mail real em `accounts/03-provisioning.md`
   e `accounts/scripts/create-account`. Issue #23.
8. `crossplane render` não injeta defaults do XRD — *intentional*: `providerConfigName`/
   `metadata.name` explícitos no XR de teste; `providerConfigName` é obrigatório, sem fallback.
9. `enum` de `providerConfigName` inclui `wasp-nonprod` nos XRDs versionados — *intentional*,
   trade-off vs. genericização.
10. `aws/eks/apps/echo/templates/*.yaml` falham em parser YAML puro — *intentional*, Helm
    templates.
11. `revoke-permission-set` só exercido no caminho feliz — ramos "atribuição/permission set
    inexistente" nunca rodaram.
12. `idp/app-config.production.yaml` `guest: {}`; `idp/packages/backend/src/index.ts` `allow-all`
    policy; `googleAuthModule.ts` `dangerouslyAllowSignInWithoutUserInCatalog: true` —
    *intentional* (PoC).
13. **Asserção com um único `override_resource` prova o valor, não a ligação** — *unexpected*,
    genérico: valor fixo no código igual ao injetado passa sem haver fio. Comprovado e corrigido no
    `1.3` (dois runs, valores/tamanhos diferentes). Issue #2 (auditar o resto do repo).
14. **`aws/terraform/scripts/` sem `status`/`platform-status`** — *unexpected*: nenhuma forma de
    perguntar "o que está de pé e quanto custa por hora"; perigoso com o T1 que fica de pé de
    propósito na fase 2. Issue #11.
15. **Sob `mock_provider`, data source de provider devolve valor sintético** — *intentional*
    (limitação do framework): assertion sobre JSON computado pelo provider passa sem verificar
    nada. Regra: `jsonencode` ou `override_data` (é o que a camada 03 faz). Issue #25 (auditar
    outros usos).
16. **Ordenação por referência não é testável offline** — *intentional*/limitação de framework: a
    mutação que troca `aws_acm_certificate_validation.vpn.certificate_arn` por
    `aws_acm_certificate.vpn.arn` passa verde (ARNs idênticos). Só o apply pega — sintoma é
    certificado `PENDING_VALIDATION` no endpoint.
17. `connection_log_options.enabled = false` no Client VPN — *intentional*: custo/retenção do log
    group não decidido; perde-se a trilha de quem conectou quando.
18. Portal self-service do Client VPN não configurado — *intentional*, exige segunda aplicação
    SAML no Identity Center.
19. **Attachment cross-conta com perpetual diff em `transit_gateway_default_route_table_*`** —
    *intentional*, `ignore_changes` (atributos write-only, invisíveis ao provider default `cicd`).
    State guarda `true`; a verdade está no TGW e nas associação/propagações explícitas.
20. **Nenhuma prova de que spoke↔spoke não roteia** — *unexpected*, propriedade central do
    desenho. Só existe uma spoke. Issue #9 (`4.1`/`4.2`).
21. **ArgoCD desta célula sobe sem credencial de repositório** — *unexpected*: zero `Application`,
    nenhum secret de repo. Consequência: o lado GitOps do `3.1` foi instalado por
    `helm upgrade --install` a partir do checkout local. Caminho decidido em
    [ADR 0012](../../docs/adr/0012-argocd-github-app-auth.md). Issue #7.
22. **O `TargetGroupBinding` é instalado com o ARN passado à mão** — *unexpected*: o valor certo
    está no ConfigMap `platform-bootstrap`, mas nada no lado cluster o lê hoje. Com `name_prefix`,
    o ARN muda a cada recriação da target group. Resolver junto com o wire do ArgoCD, issue #3.
23. **Sync verde do ArgoCD não prova autenticação, nem com o repo privado** — *intentional*/
    limitação: o `repo-server` serve de cache um clone anterior. A prova exige mutação — apagar o
    secret, **reiniciar `argocd-repo-server` E redis**, exigir `authentication required`, e só
    então restaurar. Vale para qualquer verificação futura de credencial.
24. **`ingress.enabled` do chart `httpbin` é decorativo** — *unexpected*, e do repositório de
    GitOps: só o `NOTES.txt` o lê. O gate real dos dois templates de Ingress é
    `global.environment.cluster.ingress.type` (default `nginx`). Num cluster sem nginx o Ingress
    nasce, nunca ganha `status.loadBalancer`, e a `Application` fica em `Progressing` para
    sempre — falso negativo que se lê como falha de credencial.
25. **`recover-lock.yml` nunca foi executado e tem dois defeitos que o impedem de rodar** —
    *unexpected*. (a) Referencia o composite action privado direto
    (`uses: smsilva/wasp-gitops/actions/aws/setup@main`): o fix do App token tocou só
    `provision-region.yml` e `teardown-region.yml`, então este falha na resolução do action, antes
    de qualquer step. (b) Cria só o symlink de `values.auto.tfvars`, não o de `saml-metadata.xml`
    — e `module.hub` faz `file(var.saml_metadata_path)` em todo plan, então o `plan` de revisão
    falha por arquivo ausente (mesma causa da run `33512301706`, corrigida no `down-cell` pelo
    PR #58). Ele também duplica `ln`/`init` em vez de usar `scripts/lib`. Detalhe em
    [`../terraform/ci/README.md`](../terraform/ci/README.md).

Lições genéricas já corrigidas (não são mais "quebradas", mas a regra vale para qualquer camada
futura) vivem em [`lessons-learned/`](lessons-learned/) — `terraform-layers.md` e
`load-balancer-and-tls.md` têm as mais recentes, do apply do `3.2`.
