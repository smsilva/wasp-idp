# Provider de cloud account (AWS)

Atende a capacidade `cloud-account` (ADR 0029): verifica, para cada `CloudAccount` do namespace `platform-system`, se a plataforma assume a role da conta a partir da credencial base, e só com o ExternalId gerado pela Platform API.

Roda **dentro do cluster**, como Deployment `aws-account-provider` em `platform-system`. O `platform init --target local --aws-profile <profile>` grava a credencial do profile no Secret `aws-base-credential` e instala o provider; sem credencial guardada, o provider não é instalado.

## Credencial base

- Vem de `aws configure export-credentials --profile <profile> --format process` e chega ao pod como variáveis de ambiente (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` e, se temporária, `AWS_SESSION_TOKEN`). Uma credencial nova reinicia o pod (anotação com o hash dela).
- Em cada passada, o provider chama `GetCallerIdentity` e publica o ARN e a conta no ConfigMap `aws-base-identity`. A Platform API usa esse ARN como principal da trust policy e, sem o ConfigMap, responde que a capacidade não tem provider.
- Se a credencial deixa de funcionar (SSO expirado), o provider apaga o ConfigMap: o registro de contas passa a responder `409` até um novo `init`.
- O recomendado é um IAM user dedicado, com permissão só para `sts:AssumeRole` e `sts:GetCallerIdentity`. Ele assume toda role que confia nele: é a peça mais sensível do target local.

## Verificação

1. `AssumeRole` com o ExternalId. `AccessDenied` → `Ready=False, reason=TrustNotEstablished`, o estado normal até o dono aplicar a trust policy.
2. `GetCallerIdentity` com a credencial assumida. Conta diferente da do `roleArn` → `AccountMismatch`.
3. `AssumeRole` **sem** o ExternalId. Se funcionar → `ExternalIdNotEnforced`: sem a condição `sts:ExternalId`, a AWS aceita qualquer ExternalId, e a prova de posse não vale.
4. Tudo certo → `Ready=True, reason=Verified`, com `accountId`, `callerArn` e `lastValidated`.

Qualquer outro erro da AWS vira `VerificationFailed`, com a mensagem.

## Quando verifica

- Quando a anotação `platform.wasp.silvios.me/verify-requested-at` (gravada por `platform cloud account verify`) difere de `status.observedVerifyRequest`. O provider copia a anotação para o status ao responder, e o `verify --wait` espera por isso.
- A cada 6 horas para contas `ready`.
- Para contas que não estão `ready`, com intervalos que dobram de 30 s até 15 min.

Watch mais uma passada completa a cada 30 s (`--resync-seconds`).

## Testes

`uv run pytest`: os quatro desfechos e os erros com `botocore.stub.Stubber`, sem acessar a AWS.

## Depurar

```bash
kubectl --context k3d-platform-local --namespace platform-system logs deploy/aws-account-provider
kubectl --context k3d-platform-local --namespace platform-system get cloudaccounts
kubectl --context k3d-platform-local --namespace platform-system get configmap aws-base-identity --output yaml
```
