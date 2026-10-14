# Provider de environment em cloud account (AWS, Crossplane)

Atende a capacidade `environment` para os `Environment` com `spec.cloudAccount` (ADR 0032: um método só, o Crossplane, como provider da plataforma). Os environments sem conta continuam com o `local_vcluster`.

Roda **dentro do cluster**, como Deployment `crossplane-aws-provider` em `platform-system`, com os labels do ADR 0039 (`provider=crossplane_aws`, `capabilities=environment`, `vendor=aws`). O `platform init --target local --with-crossplane` instala o Crossplane `2.3.1` (`HelmChart` do k3s, em `crossplane-system`), o `provider-aws-ec2` `v2.5.1` (as mesmas versões do EKS) e este provider. Ele exige a credencial base do `--aws-profile`, e os `init` seguintes lembram da instalação.

## Credencial

- O `init` copia o Secret `aws-base-credential` de `platform-system` para `crossplane-system`, com o mesmo nome e no formato INI (chave `creds`) que o Crossplane lê. Cada `init` renova a cópia.
- Por `CloudAccount` `Ready`, o provider escreve um `ProviderConfig` com o nome da conta: a credencial base, depois o `assumeRoleChain` com o `roleARN` e o `externalID` da conta (ADR 0029). Uma conta que deixa de estar `Ready` mantém o `ProviderConfig`, e uma conta apagada o perde (o Crossplane o segura enquanto houver recurso usando).
- O provider não lê credencial nenhuma: quem chama a AWS é o Crossplane.

## Environment

1. Finalizer `platform.wasp.silvios.me/crossplane-aws`.
2. A VPC `env-<name>` (`ec2.aws.upbound.io/v1beta1`, escopo de cluster), `10.0.0.0/16`, na primeira região da conta, com a tag `platform.wasp.silvios.me/environment`.
3. `Synced=False` da VPC → `ProvisioningFailed` com a mensagem do Crossplane; `Ready=True` com id → `Ready=True`, `CloudReady`; senão `Provisioning`. `status.cloud` guarda `vendor`, `region` e `vpcId`.
4. Delete: apaga a VPC, espera ela sumir e só então tira o finalizer. A expiração (`expiresAt`) é cobrada pelo `local_vcluster` para todo environment: aqui é só um delete.

## Guardas

- **Só a conta autorizada:** a API grava o uid da conta na anotação `platform.wasp.silvios.me/cloud-account-uid` do `Environment` depois do `can_use`; sem ela igual ao uid da conta atual, a VPC não é criada (`ProvisioningFailed`). Isso barra um `Environment` escrito por fora da API e uma conta apagada e registrada de novo com o mesmo nome.
- **Só o que é seu:** nomes de conta e de environment vêm de usuários. O provider só altera ou apaga `ProviderConfig` e VPC com o label `app.kubernetes.io/managed-by=crossplane-aws-provider` (e, na VPC, o label do environment).

## Testes

`uv run pytest`: o reconciler com stores falsos, sem cluster nem AWS. A validação contra a AWS é manual (`cli/docs/walkthrough/cloud-accounts/aws/environment.md`); o `scripts/demo/cli-smoke` nunca chama a AWS.

## Depurar

```bash
kubectl --context k3d-platform-local --namespace platform-system logs deploy/crossplane-aws-provider
kubectl --context k3d-platform-local get providerconfigs.aws.upbound.io,vpcs.ec2.aws.upbound.io
kubectl --context k3d-platform-local describe vpcs.ec2.aws.upbound.io env-<name>
```
