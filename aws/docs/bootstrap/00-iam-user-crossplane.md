# 00 — IAM User do Crossplane (`crossplane-poc`)

**Pilar WAF principal:** Security (SEC02 — identidade de máquina; SEC08 — proteção de
segredos).

## Pré-requisitos

- Conta Hub já criada (`../accounts/03-provisionamento-de-contas.md`) e você autenticado
  nela com uma credencial **`AdministratorAccess`** (SSO admin, não a `crossplane-poc` —
  ela ainda não existe). Sem isso os passos ③ e ⑤ abaixo falham com `AccessDenied`.
- `aws` CLI configurado (`aws sts get-caller-identity` deve retornar a conta Hub).
- `aws/eks/providers/bootstrap-iam-policy.json` já versionado neste repo (fonte de
  verdade da policy inline — não editar `<account-id>` no arquivo; substituir só no
  comando, ver ④).

## ① Criar a IAM user

```bash
aws iam create-user --user-name crossplane-poc
```

Idempotente na prática: se a user já existir, o comando falha com `EntityAlreadyExists` —
seguro re-rodar/pular.

## ② Anexar a managed policy `PowerUserAccess`

Cobre EC2/VPC/EKS e a maior parte do que o Crossplane precisa para rede e cluster, mas
via `NotAction: iam:*` **exclui todo o namespace IAM** — por isso o passo ④ é necessário.

```bash
aws iam attach-user-policy \
  --user-name crossplane-poc \
  --policy-arn arn:aws:iam::aws:policy/PowerUserAccess
```

## ③ Verificar a lacuna de IAM (opcional, mas recomendado antes de prosseguir)

Confirma que a user, com só `PowerUserAccess`, **não** consegue criar roles do cluster —
é a lacuna que a policy inline do passo ④ fecha:

```bash
aws iam simulate-principal-policy \
  --policy-source-arn arn:aws:iam::<account-id>:user/crossplane-poc \
  --action-names iam:CreateRole iam:GetRole iam:PutRolePolicy \
  --resource-arns "arn:aws:iam::<account-id>:role/poc-eks-example"
```

Esperado: `implicitDeny` nas três actions. Se já vier `allowed`, algo na conta concedeu IAM
amplo por fora — investigar antes de seguir (não é o desenho esperado).

## ④ Anexar a inline policy `CrossplaneEksRoleManagement`

Usa o JSON já versionado no repo — ele é a **fonte de verdade** do estado desejado; este
comando só a aplica. Substituir `<account-id>` pelo ID real da conta Hub (o arquivo em
disco mantém o placeholder — não editá-lo, sed só no comando ou via `--policy-document`
processado):

```bash
sed "s/<account-id>/094289743086/g" \
  aws/eks/providers/bootstrap-iam-policy.json > /tmp/bootstrap-iam-policy.rendered.json

aws iam put-user-policy \
  --user-name crossplane-poc \
  --policy-name CrossplaneEksRoleManagement \
  --policy-document file:///tmp/bootstrap-iam-policy.rendered.json

rm -f /tmp/bootstrap-iam-policy.rendered.json
```

> **Não editar o placeholder no arquivo versionado.** Ele deve continuar genérico
> (`<account-id>`) para ser reaplicável em qualquer conta — renderizar só no arquivo
> temporário do comando.

## ⑤ Gerar a access key

```bash
aws iam create-access-key --user-name crossplane-poc
```

A saída traz `AccessKeyId` e `SecretAccessKey` **uma única vez** — não é recuperável depois
(só re-gerável, criando uma nova). Não persistir em arquivo local; usar direto no comando
do passo ⑥ ou colar manualmente no `create-secret` interativo.

## ⑥ Gravar no Secrets Manager

Secret `poc-idp/crossplane-poc-credentials`, região `us-east-1`, formato JSON:

```bash
aws secretsmanager create-secret \
  --name poc-idp/crossplane-poc-credentials \
  --region us-east-1 \
  --secret-string '{"aws_access_key_id":"<access-key-id>","aws_secret_access_key":"<secret-access-key>"}'
```

Se o secret já existir (re-bootstrap após rotação de key):

```bash
aws secretsmanager put-secret-value \
  --secret-id poc-idp/crossplane-poc-credentials \
  --region us-east-1 \
  --secret-string '{"aws_access_key_id":"<access-key-id>","aws_secret_access_key":"<secret-access-key>"}'
```

> **Nunca** deixar a saída do passo ⑤ num arquivo (`/tmp/...env`, histórico de shell
> persistido) — colar direto no comando acima e descartar o terminal scroll-back se
> necessário. Ver `../../CLAUDE.md` (seção "Operação: credenciais AWS via CLI") para o
> padrão de recuperação inline usado depois, no consumo.

## ⑦ Consumir a credencial no Crossplane (k3d)

Fora do escopo deste bootstrap (que termina no Secrets Manager), mas o próximo passo natural:
recuperar inline (nunca em arquivo) e passar para
`aws/eks/scripts/configure-aws-creds`, que cria o Secret `aws-iam-credential` no
namespace `crossplane-system` e aplica o `ProviderConfig`:

```bash
set -a
source <(aws secretsmanager get-secret-value \
  --secret-id poc-idp/crossplane-poc-credentials --region us-east-1 \
  --query SecretString --output text \
  | jq -r '"AWS_ACCESS_KEY_ID=" + .aws_access_key_id, "AWS_SECRET_ACCESS_KEY=" + .aws_secret_access_key')
set +a

aws/eks/scripts/configure-aws-creds
```

## Verificação final

```bash
aws iam get-user --user-name crossplane-poc
aws iam list-attached-user-policies --user-name crossplane-poc
aws iam list-user-policies --user-name crossplane-poc
aws secretsmanager describe-secret --secret-id poc-idp/crossplane-poc-credentials --region us-east-1
```

Esperado: `PowerUserAccess` na lista de attached policies, `CrossplaneEksRoleManagement` na
lista de inline policies, secret existente na região `us-east-1`.

## Well-Architected — porquê

| Best practice | Como atende |
|---|---|
| **SEC02-BP02** credenciais temporárias | não atende ainda — access key é degrau inevitável (ver `../security/04`); mitigado por escopo e por ser substituída por Pod Identity assim que o cluster existir |
| **SEC03-BP01** menor privilégio | `PowerUserAccess` exclui IAM; a inline policy escopa o restante a `role/poc-eks-*`, nunca `"*"` |
| **SEC08-BP01** proteger segredos em repouso | Secrets Manager como única fonte de verdade da credencial, nunca arquivo em disco/repo |
| **OPS05-BP04** reaplicável em conta nova | JSON da policy versionado — o `put-user-policy` é só a aplicação de um estado declarado |

## Próximo

→ `../network/00-topologia.md`: com a automação credenciada, a próxima peça é a rede
(VPC/subnets) que hospedará o cluster.