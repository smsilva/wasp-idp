# 03 — Account Provisioning

**Pilar WAF principal:** Operational Excellence (repetibilidade — criar conta é uma operação
de rotina, não um evento especial).

## Criar uma conta programaticamente

```bash
aws organizations create-account \
  --email "<account-alias>+aws@<root-domain>" \
  --account-name "<account-alias>"
```

- `create-account` é **assíncrono** — retorna um `CreateAccountRequestId`; a conta leva de
  segundos a poucos minutos para ficar `SUCCEEDED`. Poll com:
  ```bash
  aws organizations describe-create-account-status \
    --create-account-request-id <request-id>
  ```
- **O e-mail precisa ser único em toda a AWS** (não só na sua Organization) — nenhuma conta
  AWS, de ninguém, pode já ter usado aquele e-mail. E precisa ser **válido e controlado por
  você**: ele vira o usuário **root** da conta, e é para onde a AWS manda verificação e reset
  de senha. Um domínio fictício (`example.com`) cria a conta mas te deixa **sem acesso ao
  root** — evite fora de testes descartáveis.

### Dois modos de plus-addressing (o script `scripts/create-account` cobre ambos)

O truque do "+" gera e-mails únicos por conta a partir de uma única caixa: a AWS trata
`caixa+tag@dominio` como endereço distinto, mas o provedor entrega tudo na mesma caixa,
**ignorando o que vem depois do `+`**. Como o nome da conta entra na composição muda entre
os dois modos:

- **Domínio corporativo com catch-all** (ex.: `<email-domain>`): o nome da conta vira a *base* e
  `aws` é o tag fixo → `<name>+aws@<domain>`, ex.: `network+aws@<email-domain>`. Funciona porque o
  catch-all do domínio roteia qualquer base para a caixa certa. É o **default** do script
  (sem `--email-user`).

- **Caixa pessoal Gmail/Workspace** (ex.: `smsilva@gmail.com`): você **não** controla o
  domínio, então a base tem de ser a sua caixa e o nome da conta vira o *tag* →
  `<email-user>+<name>@<domain>`, ex.: `smsilva+network@gmail.com`. Passe `--email-user smsilva`.
  ⚠️ Não use `<name>+aws@gmail.com` aqui: o Gmail entregaria em `<name>@gmail.com` (uma caixa
  que não é a sua) — nunca chega em você. Validado em execução real: com
  `--email-user smsilva`, o e-mail "Your Amazon Web Services Account is Ready" chegou em
  `smsilva@gmail.com` endereçado a `smsilva+hub` — a prova de que o root da conta é acessível.

```bash
# catch-all corporativo (default):
scripts/create-account --name network --email-domain <email-domain> --ou infrastructure
#   -> network+aws@<email-domain>

# Gmail/Workspace pessoal:
scripts/create-account --name network --email-user smsilva --email-domain gmail.com --ou infrastructure
#   -> smsilva+network@gmail.com
```

## Mover a conta para a OU correta

`create-account` cria a conta sob a **Root** da Organization — mover para a OU explicitamente:

```bash
aws organizations move-account \
  --account-id <account-id> \
  --source-parent-id <root-id> \
  --destination-parent-id <ou-id>
```

conta network → OU Infrastructure. Conta de projeto → OU Workloads (tópico 1).

> **Gotcha (descoberto em execução real):** `create-account` cria a conta sob a **Root**, então
> o `move-account` tem de mirar a **OU de destino**, nunca a própria Root. Mover a conta da Root
> para a Root retorna `DuplicateAccountException` ("already present at the specified
> destination"). Para o Hub isso significa buscar o ID da OU **Infrastructure** (filha da Root) —
> `--query "OrganizationalUnits[?Name=='Infrastructure'].Id"` — e não reusar `root_id` como atalho.
> Como o `move-account` roda **depois** de a conta já ter sido criada, o script é **idempotente**:
> re-executar detecta a conta ACTIVE existente e só refaz o move para a OU correta.

## O papel do root da conta-membro nova

Toda conta criada via `create-account` nasce com um usuário **root** próprio (a senha não é
definida automaticamente — requer fluxo de "esqueci a senha" se for necessário logar como
root). Na prática, **você nunca deveria precisar logar como root** numa conta-membro: o
acesso do dia a dia é via **IAM Identity Center / SSO** (tópico 4), que já provê uma role
administrativa sem precisar do root.

**Quando o root é inevitável:** certas ações só o root pode fazer (ex.: fechar a conta,
alterar o e-mail raiz, sair de suporte enterprise). São raras e conhecidas — não bloqueiam o
fluxo normal de provisionamento.

## Bootstrap de acesso administrativo na conta nova

Toda conta criada dentro de uma Organization com `feature-set ALL` automaticamente ganha uma
role `OrganizationAccountAccessRole` (assumível a partir da management account) — é o gancho
inicial para configurar o SSO (tópico 4) sem precisar do root.

```bash
aws sts assume-role \
  --role-arn arn:aws:iam::<new-account-id>:role/OrganizationAccountAccessRole \
  --role-session-name bootstrap
```

> Para uso recorrente na CLI (não só uma verificação avulsa), prefira encapsular esse
> assume-role num **named profile** (`role_arn` + `source_profile`) em vez de exportar as
> credenciais STS à mão — a SDK renova a sessão sozinha. Padrão em
> [`04-cross-account-access.md`](04-cross-account-access.md#acesso-admin-à-conta-membro-antes-de-o-sso-estar-propagado).
> É o caminho de acesso admin à conta-membro **enquanto** o permission set SSO dela não foi
> criado (passo ⑤).

## A VPC default: toda conta nova nasce com uma por região, todas no mesmo CIDR

Toda conta AWS nasce com uma **VPC default por região habilitada**, e todas usam `172.31.0.0/16`. Não é uma escolha de quem cria: é o comportamento da AWS. A consequência é que as contas de uma Organization já se sobrepõem entre si antes de qualquer decisão de endereçamento — nada a ver com o supernet `10.0.0.0/12` do [ADR 0003](../../../docs/adr/0003-supernet-cidr-allocation.md). Além da sobreposição, ela vem com subnet pública em todas as AZs, `map_public_ip_on_launch` ligado, IGW anexado, security group default permissivo e NACL allow-all.

**Não existe forma nativa de impedir a criação.** `organizations create-account` não tem flag, não há atributo de conta, e SCP não alcança (a VPC é criada pela própria AWS, não por um principal da conta). A doc do AFT afirma literalmente que *"New AWS accounts are created with a VPC set up in each AWS Region, by default"*. Os únicos caminhos automáticos que a AWS oferece são de **remoção depois**, e ambos exigem Control Tower:

| Caminho | O que faz | Limite |
|---|---|---|
| [Control Tower Account Factory](https://docs.aws.amazon.com/controltower/latest/userguide/vpc-concepts.html) | Ao provisionar a conta numa região suportada, *"automatically deletes the default AWS VPC"* e cria a `aws-controltower-VPC` no lugar | Exige Control Tower; aqui `list-landing-zones` devolve vazio |
| [AFT `aft_feature_delete_default_vpcs_enabled`](https://docs.aws.amazon.com/controltower/latest/userguide/aft-feature-options.html) | Apaga as default em todas as regiões — **só na AFT management account** | A própria doc avisa: *"AFT doesn't delete AWS default VPCs automatically for any AWS Control Tower accounts that AFT provisions"* |

**Terraform também não resolve.** `aws_default_vpc` com `force_destroy` parece a resposta e é o oposto dela: a doc do provider é explícita que, se não existir VPC default, o Terraform **cria** uma. Aplicar numa conta já limpa recria o que se quer eliminar — Terraform não expressa ausência de recurso que ele não criou.

Por isso o caminho aqui é imperativo e idempotente: `scripts/remove-default-vpcs`. O `create-account` o chama **só depois de criar** uma conta — nunca para uma conta que já existia, porque ele não apaga o que não criou. Limpar conta pré-existente é rodar `remove-default-vpcs` direto, que é explicitamente destrutivo e pede confirmação. Ele apaga na ordem **subnets → internet gateway (detach + delete) → VPC**, que é a ordem que a AWS exige — `delete-vpc` direto falha com `DependencyViolation`. Uma conta sem VPC default é no-op silencioso, e o script **recusa** apagar VPC que tenha qualquer ENI: interface de rede significa que alguém está usando aquilo, e aí a remoção não é segura.

Rodar a partir da management account, que assume `OrganizationAccountAccessRole` em cada conta-membro (para si mesma usa a credencial ambiente, porque uma conta não assume essa role nela própria):

```bash
scripts/remove-default-vpcs --dry-run          # o que seria apagado, sem apagar
scripts/remove-default-vpcs --yes              # Organization inteira, regiões aprovadas
scripts/remove-default-vpcs --account <nome> --regions us-east-1 --yes
```

**As regiões negadas pela SCP ficam de fora, e continuam com a VPC default.** `describe-vpcs` nelas falha com `UnauthorizedOperation ... explicit deny in a service control policy` — a VPC existe e é inalcançável. O risco residual é baixo (região negada não cria nada), e alcançá-las exigiria abrir exceção na SCP baseline, que é decisão de guardrail. O caminho que neutraliza sem mexer na SCP — declarative policy de EC2 com VPC Block Public Access — está na issue #69.

## Checklist de uma conta nova, do zero ao "pronta para workload"

```text
① create-account (com e-mail único)
② poll até SUCCEEDED
③ move-account para a OU correta (Security, Infrastructure ou Workloads)
④ remove-default-vpcs na conta nova (o script create-account já chama)
⑤ assume-role OrganizationAccountAccessRole (verificação de acesso)
⑥ Configurar permission set do SSO para a conta (tópico 4)
⑦ SCPs da OU já se aplicam automaticamente (herdadas — tópico 2, nada a fazer aqui)
⑧ Conta pronta — segue para `../network/` provisionar a spoke, se for conta de projeto
```

## Well-Architected — porquê

| Best practice | Como atende |
|---|---|
| **OPS** repetibilidade | Sequência é a mesma para toda conta nova — script, não ritual manual |
| **[SEC01 — Security foundations](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/security.html)** | `OrganizationAccountAccessRole` + SSO evitam qualquer necessidade de login root |

## Próximo

→ [`04-cross-account-access.md`](04-cross-account-access.md): como o time acessa múltiplas
contas sem multiplicar usuários IAM.