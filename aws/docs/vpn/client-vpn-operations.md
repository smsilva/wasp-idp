# Client VPN — operação diária

O Client VPN é o caminho de manutenção para o cluster EKS. O endpoint público da API fica
**fechado** por padrão; todo acesso administrativo (`kubectl`, `helm`, providers Terraform
`kubernetes`/`helm` locais) passa pelo túnel.

Este documento cobre a **operação**. O desenho e as decisões de arquitetura estão em
[ADR 0006](../../../docs/adr/0006-client-vpn-saml-for-maintenance-access.md).

## Pré-requisitos

- `aws-vpn-client` 6.0.1 — **não** instalar por `latest`, que entrega 5.4.1 sem CLI.
  Conferir: `aws-vpn-client --version`
- `saml-metadata.xml` no lugar — symlink `regions/<região>/saml-metadata.xml → ../../variables/saml-metadata.xml`
- SSO ativo: `aws sts get-caller-identity --profile personal`

## Profile do Client VPN

O profile é separado do `~/.aws/config` — vive no keychain do sistema, gerenciado pelo
`aws-vpn-client`. O nome `hub` é fixo (não por região — cada região tem o próprio endpoint,
mas o profile local chama-se `hub` porque o endpoint vive na VPC hub).

### Criar/recriar

O `.ovpn` **nunca** se reaproveita entre applies do hub: a DNS name do endpoint muda a cada
recriação. Reexportar sempre.

```bash
endpoint="$(cd regions/us-east-1 && terraform output -raw client_vpn_endpoint_id)"
aws ec2 export-client-vpn-client-configuration --client-vpn-endpoint-id "${endpoint}" \
  --profile network --region us-east-1 --output text > ~/trash/hub.ovpn
aws-vpn-client import-profile --profile-name hub --config-path ~/trash/hub.ovpn
```

### Conectar

```bash
aws-vpn-client connect --profile-name hub        # abre navegador para autenticar
aws-vpn-client get-connection-status --profile-name hub   # tem de dizer "Connected"
```

### Desconectar

```bash
aws-vpn-client disconnect --profile-name hub
```

## Autenticação

Usuário: **`silvios`** (e-mail `smsilva@gmail.com`) — mesmo do SSO. O Client VPN autentica
contra a aplicação SAML do Identity Center; o grupo `platform-admins`
(`3418c4d8-f051-7051-668e-da8de656357f`) tem authorization rule configurada em
`operator_group_ids` (`variables/values.tfvars`).

## Depois de conectado

```bash
# kubeconfig — uma vez por região
aws eks update-kubeconfig --name control-plane-us-east-1 --region us-east-1 --profile cicd
kubectl get nodes
```

A role usada para o `kubectl` é a mesma do profile `cicd`: `OrganizationAccountAccessRole` na
conta `270222614208`. Ela tem access entry de cluster-admin provisionada pelo Terraform via
`admin_principal_arns` em `variables/values.tfvars` (issue #56).

## Problemas comuns

| Sintoma | Causa provável | Ação |
|---|---|---|
| `connect` falha com `connection failed` | `.ovpn` é de um endpoint antigo (DNS name mudou) | Reexportar o `.ovpn` do endpoint atual |
| `connect` abre navegador e falha na autenticação | `saml-metadata.xml` expirado ou ausente | Conferir o symlink; reexportar o XML do Identity Center |
| `connect` não abre navegador | `aws-vpn-client` < 6.0 (versão sem CLI) | Instalar 6.0.1, não `latest` |
| `Connected` mas `kubectl` falha com `the server has asked for the client to provide credentials` | Access entry não provisionada | Conferir `admin_principal_arns` em `variables/values.tfvars` |
| `kubectl` timeout (`dial tcp <ip>:443: i/o timeout`) | Túnel desconectado ou rota do supernet ausente | `get-connection-status` primeiro; se `Connected`, conferir propagações do TGW |
| Daemon do Client VPN não está rodando | `systemctl is-active aws-client-vpn-daemon.service` | `systemctl --user start aws-client-vpn-daemon.service` |

## Perfis AWS envolvidos

| Profile | Conta | Role | Para quê |
|---|---|---|---|
| `personal` | `221047292361` (management) | SSO direto | Identity Center, Organizations |
| `hub` (VPN) | `094289743086` (network) | `OrganizationAccountAccessRole` | Túnel — **é profile do `aws-vpn-client`, não do `~/.aws/config`** |
| `network` | `094289743086` (network) | `OrganizationAccountAccessRole` | `export-client-vpn-client-configuration` + recursos da VPC hub |
| `cicd` | `270222614208` (cicd) | `OrganizationAccountAccessRole` | `eks update-kubeconfig` + recursos da célula |

## Custo

O Client VPN cobra por **associação de endpoint** (~US$ 0,10/h por AZ = ~US$ 0,20/h com duas AZs)
+ **conexão ativa** (~US$ 0,05/h). Sem conexão ativa, ~US$ 146/mês parado.

## Ver também

- [ADR 0006: Client VPN with SAML for maintenance access](../../../docs/adr/0006-client-vpn-saml-for-maintenance-access.md)
- [README do aws/terraform/](../../terraform/README.md) — sequência de provisionamento
- [HANDOFF.md](../../../HANDOFF.md) — estado atual (o que está de pé, custo, how to resume)