# Local SSO Profile for Cluster Access

Pré-requisito: bootstrap do permission set já feito — [`bootstrap/01-identity-center-eks-admin.md`](../bootstrap/01-identity-center-eks-admin.md).

## Passos

Acrescente ao `~/.aws/config`:

```ini
[profile platform-admin]
sso_session = personal
sso_account_id = 270222614208
sso_role_name = PlatformAdmin
region = us-east-1
```

```bash
aws sso login --profile personal          # se a sessão SSO ainda não estiver ativa
aws sts get-caller-identity --profile platform-admin
```

Esperado: `arn:aws:sts::270222614208:assumed-role/AWSReservedSSO_PlatformAdmin_<hash>/<usuário>`.

Com o [Client VPN conectado](client-vpn-operations.md), descubra o nome do cluster na região atual e escreva o kubeconfig (`--alias`/`--user-alias` evitam contexto com o ARN inteiro como nome):

```bash
CLUSTER_NAME="$(aws eks list-clusters --profile platform-admin --query 'clusters[0]' --output text)"
aws eks update-kubeconfig --name "${CLUSTER_NAME}" --profile platform-admin --alias "${CLUSTER_NAME}" --user-alias platform-admin
kubectl auth can-i '*' '*'   # esperado: yes
```

## Informações relevantes

- `sso_role_name` é o **nome do permission set**, não uma role IAM — muda junto se o permission set for outro (outro grupo, outro cluster).
- `platform-admin` reaproveita a `sso-session personal` já autenticada — não precisa de `aws sso login --profile platform-admin` separado (mesmo mecanismo do profile `cicd`, via `source_profile = personal`).
- `platform-admin` federa pelo grupo `platform-admins` do Identity Center (`admin_group_ids`, issue #71); o caminho antigo (`--profile cicd`, via `OrganizationAccountAccessRole`) ainda funciona até a issue #75 aposentá-lo.

## Onde buscar mais

- [`client-vpn-operations.md`](client-vpn-operations.md) — profile `personal`, conexão do Client VPN, tabela de profiles envolvidos.
- [`bootstrap/01-identity-center-eks-admin.md`](../bootstrap/01-identity-center-eks-admin.md) — por que o permission set é manual, o que ele concede e o que a access entry do Terraform concede.
- [`eks-access-entries.md`](eks-access-entries.md) — como o EKS decide quem tem acesso via access entries.
