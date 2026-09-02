# Local SSO Profile for Cluster Access

## O que este documento resolve

`aws eks update-kubeconfig` e `kubectl` precisam de um profile no `~/.aws/config` local — não
existe um profile "cicd" genérico que sirva pra isso depois da issue #71: acesso admin ao cluster
agora vem do grupo `platform-admins` do Identity Center (`admin_group_ids`), não mais só de
`OrganizationAccountAccessRole`. Este documento cria o profile que federa nesse caminho.

Pré-requisito: o bootstrap manual do permission set já concluído — ver
[`bootstrap/01-identity-center-eks-admin.md`](../bootstrap/01-identity-center-eks-admin.md).

## Criar o profile

Acrescente ao `~/.aws/config` (reaproveita a `sso-session` que o profile `personal` já declara —
ver [`client-vpn-operations.md`](client-vpn-operations.md) para o profile `personal` em si):

```ini
[profile platform-admin]
sso_session = personal
sso_account_id = 270222614208
sso_role_name = PlatformAdmin
region = us-east-1
```

`sso_role_name` é o **nome do permission set**, não um nome de role IAM — o Identity Center expõe
o permission set como "role" no profile SSO. Se o permission set se chamar diferente do
`PlatformAdmin` (outro grupo, outro cluster), o valor aqui muda junto.

## Autenticar e usar

```bash
aws sso login --profile personal          # se a sessão SSO ainda não estiver ativa
aws sts get-caller-identity --profile platform-admin
```

Esperado: `arn:aws:sts::270222614208:assumed-role/AWSReservedSSO_PlatformAdmin_<hash>/<usuário>` —
sem precisar de um `aws sso login --profile platform-admin` separado, porque o profile reaproveita
a `sso-session personal` já autenticada (mesmo mecanismo do profile `cicd`, que usa
`source_profile = personal`).

Depois, com o [Client VPN conectado](client-vpn-operations.md):

```bash
aws eks update-kubeconfig --name <cluster-name> --region <região> --profile platform-admin
kubectl auth can-i '*' '*'   # esperado: yes
```

## Por que não `--profile cicd`

`cicd` assume `OrganizationAccountAccessRole` — acesso amplo, sem vínculo com grupo ou pessoa (ver
[`bootstrap/01-identity-center-eks-admin.md`](../bootstrap/01-identity-center-eks-admin.md), seção
"Por que é manual"). `platform-admin` federa pelo grupo `platform-admins`, é o caminho que a #71
introduziu e a #75 pretende tornar o único. O comando sugerido no summary do workflow
`provision-region.yml` já usa `platform-admin`.
