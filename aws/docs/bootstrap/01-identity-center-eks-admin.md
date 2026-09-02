# 01 — Identity Center: admin do EKS por grupo (`platform-admins`)

**Pilar WAF principal:** Security ([SEC02 — Identity management](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/identity-management.html) — identidade federada em vez de role compartilhada; [SEC03 — Permissions management](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/permissions-management.html) — escopo do que o permission set concede).

Hoje o admin do cluster vem de `OrganizationAccountAccessRole` (ver [`vpn/eks-access-entries.md`](../vpn/eks-access-entries.md)), assumível por qualquer principal com acesso à management account, sem vínculo com grupo ou pessoa — o CloudTrail registra "alguém da management", não quem.
Este roteiro **adiciona** um caminho de admin por grupo do Identity Center; as duas fontes (`admin_principal_arns` e `admin_group_ids`) coexistem por ora — aposentar a `OrganizationAccountAccessRole` é a [issue #75](https://github.com/smsilva/wasp-idp/issues/75).

## Objetivo

Sair de "o grupo `platform-admins` existe no Identity Center da management account, sem nenhum account assignment na conta `cicd`" para "existe uma role `AWSReservedSSO_PlatformAdmin_<hash>` provisionada na conta `cicd`, que o Terraform resolve sozinho via data source".

## Por que é manual

Este repositório **não gerencia o Identity Center**: não há nenhum recurso `aws_ssoadmin_*` nem `aws_identitystore_*` no Terraform. O provider `aws_ssoadmin_*` só consegue gerenciar um permission set depois de ele já existir, e criar/atribuir permission sets é justamente o passo que falta — por isso é uma sequência imperativa, como o bootstrap da [`crossplane-poc`](00-crossplane-iam-user.md).
Hoje, `list-permission-sets-provisioned-to-account` na conta `cicd` retorna vazio — não existe nenhum account assignment do Identity Center ali. É esse vazio que este roteiro preenche.

## Pré-requisitos

- Acesso admin ao Identity Center na **management account** (`221047292361`) — é lá que o Identity Center vive, mesmo quando o account assignment é feito para a conta `cicd`.
- O grupo `platform-admins` já existente no Identity Center, GroupId `3418c4d8-f051-7051-668e-da8de656357f`.
- `aws sso login` funcionando (profile com sessão SSO ativa na management account).
- Confirmar a conta antes de qualquer passo:

```bash
aws sts get-caller-identity
```

`Account` deve ser `221047292361`.

## ① Criar o permission set

No console do Identity Center (management account) → **Permission sets** → **Create permission set**.

O **nome importa**: ele vira, ao mesmo tempo, a chave de `admin_group_ids` no Terraform e o prefixo do nome da role provisionada (`AWSReservedSSO_<nome>_<hash>`) — ver a `name_regex` em [`regions/us-east-1/main.tf`](../../terraform/regions/us-east-1/main.tf).
Convenção deste repo: um permission set por grupo que precisa de admin.

- `PlatformAdmin` — para o cluster de control plane (é o caso deste roteiro).
- Clusters de workload podem ter outros, por exemplo `UserDiscoveryDevOps`, `CloudOpsOperations`.

**Policy a anexar:** o permission set precisa dar à role poder de **falar com o EKS**, não poder **dentro** do cluster. Na prática, o mínimo é `eks:DescribeCluster` (o que `aws eks update-kubeconfig` chama); uma managed policy como `AmazonEKSReadOnlyAccess` também cobre isso e é uma opção razoável de começo.

**Não confundir com o poder dentro do cluster.** Essa é a separação que mais gera confusão:

| Camada | Concede o quê | Onde vive |
|---|---|---|
| Permission set (Identity Center) | Poder de **alcançar** a API do EKS na conta (`eks:DescribeCluster` etc.) | Console do Identity Center, manual (este passo) |
| Access entry (Terraform) | Poder **dentro** do cluster (`AmazonEKSClusterAdminPolicy`, equivalente a `system:masters`) | `admin_group_access_entries` em [`regions/us-east-1/main.tf`](../../terraform/regions/us-east-1/main.tf), declarativo |

Sem a access entry, a role provisionada consegue rodar `aws eks update-kubeconfig` mas o `kubectl` resulta em acesso negado pela API do EKS — os dois passos são necessários, nenhum substitui o outro.

## ② Criar o account assignment

Ainda no console do Identity Center: **AWS accounts** → selecionar a conta `cicd` (`270222614208`) → **Assign users or groups** → grupo `platform-admins` → permission set `PlatformAdmin`.

## ③ Verificar que a role foi provisionada

```bash
aws iam list-roles \
  --profile cicd \
  --path-prefix /aws-reserved/sso.amazonaws.com/ \
  --query 'Roles[].RoleName'
```

Esperado: algo como `AWSReservedSSO_PlatformAdmin_a1b2c3d4e5f6g7h8`.

O `<hash>` no fim do nome é **imprevisível** — não é derivável do GroupId nem do nome do permission set antes do provisionamento. É exatamente por isso que o Terraform não digita o ARN à mão: ele resolve a role por data source (`aws_iam_roles`, com `path_prefix` + `name_regex` sobre o nome do permission set), em [`regions/us-east-1/main.tf`](../../terraform/regions/us-east-1/main.tf).

## ④ Ligar no Terraform

Em `aws/terraform/variables/values.tfvars` (gitignored, valores reais desta conta):

```hcl
admin_group_ids = {
  PlatformAdmin = "3418c4d8-f051-7051-668e-da8de656357f"
}
```

O shape (chave = nome do permission set, valor = GroupId em UUID) está documentado em [`values.tfvars.example`](../../terraform/variables/values.tfvars.example).

## ⑤ Verificação fim-a-fim

Só funciona **depois** do `terraform apply` que cria a access entry correspondente (ver a tabela do passo ①) — antes disso, `aws eks update-kubeconfig` autentica mas `kubectl` é negado pela API do EKS.

```bash
aws sso login --profile <profile-do-permission-set-PlatformAdmin>
aws eks update-kubeconfig --profile <profile-do-permission-set-PlatformAdmin> --region us-east-1 --name <cluster-name>
kubectl auth can-i '*' '*'
```

Esperado: `yes`.

## Armadilhas

- **`terraform plan` falha com "esperada exatamente 1 role para o permission set ... encontradas 0"**: é o postcondition do data source `aws_iam_roles.admin_group` acusando que o permission set ainda não tem account assignment na conta `cicd` — ou seja, os passos ① a ③ acima não foram feitos (ou o nome do permission set não bate com a chave de `admin_group_ids`). Não é bug do Terraform.
- **Não remover o path `/aws-reserved/sso.amazonaws.com/` do ARN da role.** A documentação do provider AWS sugere tirar o path de roles SSO, mas essa recomendação vale para o `aws-auth` ConfigMap legado; a documentação de EKS access entries diz textualmente que o ARN de role *pode* incluir path. Este cluster usa `authenticationMode = API` (ver [`vpn/eks-access-entries.md`](../vpn/eks-access-entries.md)), não o ConfigMap — o path fica.
- **Renomear o permission set provisiona uma role NOVA** (nome e hash diferentes) e deixa a access entry antiga órfã, apontando para uma role que não existe mais. Trate o nome do permission set como imutável: renomear é destruir-e-recriar a access entry, não um "editar" inofensivo.

## Próximo

→ [Issue #75](https://github.com/smsilva/wasp-idp/issues/75): aposentar `OrganizationAccountAccessRole` como caminho de admin, uma vez que o caminho por grupo estiver validado em uso.
