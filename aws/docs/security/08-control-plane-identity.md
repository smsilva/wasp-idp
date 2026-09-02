# 08 — Control Plane Identity (how many, and of what type)

**Pilar WAF principal:** Security
([SEC02-BP02 — Use temporary credentials](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/sec_identities_unique.html) /
[SEC03-BP01 — Define access requirements](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/sec_permissions_define.html)).

## A pergunta

Com **control planes regionais** — cada um uma spoke privilegiada rodando EKS + Crossplane, que
provisiona as spokes de workload da sua região ([`decisions.md`](../../../decisions.md) §2) — quantas identidades
IAM existem? Uma por control plane? Uma por cluster gerenciado? Uma por instância de Crossplane?

Respostas curtas, antes do detalhe:

- **Zero IAM users.** O tipo está errado, não a quantidade.
- **Uma role de origem por control plane regional.**
- **Uma role de destino por conta-alvo** — não por região, não por cluster.
- **Zero identidades** para o EKS de workload que o control plane cria.

## Primeiro: o tipo, não a contagem

`crossplane-poc` é um IAM user com access key de longa duração no Secrets Manager. Isso contraria
[SEC02-BP02](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/sec_identities_unique.html),
que é explícito: *"we now recommend not using [IAM users] to avoid the risks in using long-term
access keys"*, e lista como anti-pattern *"using long-term access keys for machine identities when
temporary credentials could be used"*.

Com um control plane, é um segredo para rotacionar. Com N control planes regionais, são N segredos
replicados em N clusters — o problema cresce linearmente e cada cópia é uma superfície.

Substituto: **EKS Pod Identity** (ou IRSA). O pod do provider recebe credencial temporária via
token do próprio cluster; não existe segredo em lugar nenhum. Já é o alvo registrado em
[`decisions.md`](../../../decisions.md) §7, com o trust criado pelo Terraform junto com a spoke.

## A granularidade: quem detém a credencial

O eixo que define blast radius **não é o recurso gerenciado — é quem guarda a credencial.** O
control plane guarda; o EKS de workload que ele cria não guarda nada. Daí a matriz:

| Eixo | Quantas identidades | Por quê |
|---|---|---|
| **Por control plane regional** | 1 role de origem (Pod Identity) | Permite revogar/auditar uma região sem tocar nas outras; o CloudTrail atribui a ação ao control plane certo |
| **Por conta-alvo** (spoke/tenant) | 1 role de destino | A trust policy lista quais control planes legitimamente gerenciam aquela conta |
| **Por EKS de workload gerenciado** | **0** | Ele não provisiona infraestrutura; não há credencial a conceder |

A cadeia resultante é a que o repo já usa, com o primeiro elo trocado:

```text
Pod do provider (control plane us-east-1)
  └─ Pod Identity → role crossplane-cp-use1 (conta network)
       └─ sts:AssumeRole → role crossplane-<conta-alvo> (conta de workload)
            └─ cria VPC / EKS / IAM naquela conta
```

O hop cross-account é o mesmo de [`02-cross-account-roles.md`](02-cross-account-roles.md) —
invariante, como o tópico 4 já registra. Só o elo inicial muda.

## Conta não tem região — a role de destino é uma só

O erro intuitivo: supor que uma conta de workload com presença em duas regiões precisa de duas
roles, ou de duas contas. **Não.**

IAM é **global**. Uma role criada na conta de workload vale para qualquer região dela. Logo dois
control planes regionais apontando para a **mesma** role de destino é o desenho correto:

```text
crossplane-cp-use1 (network) ─┐
                              ├─→ crossplane-<conta-alvo>   (uma role, global)
crossplane-cp-euw1 (network) ─┘
```

Ver [`accounts/00-strategy.md`](../accounts/00-strategy.md), seção "Conta não tem região".

## O problema que isso cria: contenção regional

Se as duas roles de origem assumem a mesma role de destino, o control plane de `us-east-1` tem
permissão técnica para criar recursos em `eu-west-1`. Um XR com região errada, ou uma Composition
com região hardcoded, cria infra na região errada — e a única defesa passa a ser revisão de
código.

Três controles, em ordem de preferência:

### 1. SCP na OU (preferido)

`aws:RequestedRegion` restrito na OU da conta-alvo. Vale para **qualquer** principal, não só o
Crossplane — inclusive para um humano com `AdministratorAccess` naquela conta. É preventivo e não
depende de o provider suportar nada.

Já existe como guardrail baseline ([`accounts/02-scp-guardrails.md`](../accounts/02-scp-guardrails.md)), e é o eixo pelo qual as
OUs de tenant devem ser particionadas ([`tenancy/02-ou-per-geography.md`](../tenancy/02-ou-per-geography.md)). **Isto você deveria
ter de qualquer forma**, independentemente da decisão sobre roles.

### 2. Session tag na cadeia de assume

O control plane passa uma tag de sessão (`region=use1`) no `AssumeRole`, e a policy da role de
destino condiciona:

```json
"Condition": {
  "StringEquals": { "aws:RequestedRegion": "${aws:PrincipalTag/region}" }
}
```

Uma role só, contenção por região, elegante. **Não adotar sem verificar** se o provider AWS do
Crossplane propaga session tags no `assumeRoleChain` do ProviderConfig — se não propagar, a
condição nunca casa e **tudo** é negado (falha fechada, mas quebrada).

### 3. Role de destino por região de origem

`crossplane-<conta-alvo>-use1`, `-euw1`, cada uma com `aws:RequestedRegion` fixo na própria
policy. Mais roles, zero ambiguidade, nenhuma dependência de feature do provider. É a escolha
correta se (2) não funcionar.

## Nome carrega a região

`crossplane-cp-use1`, não `crossplane-cp`. Sem isso, descobrir qual control plane executou uma
ação exige correlacionar horário de log com janela de deploy — atribuição por inferência, não por
identidade. Com o nome regional, o `sts:AssumeRole` no CloudTrail já responde.

Vale a regra de renomeação já registrada em [`CLAUDE.md`](../../CLAUDE.md): **IAM não renomeia in-place** —
trocar nome de role é criar nova, validar o assume com a credencial real do consumidor, e só então
apagar a antiga.

## Trust policy: não basta listar a conta

Trust apontando para `arn:aws:iam::<network>:root` autoriza **qualquer** principal daquela conta a
assumir. Escopar:

```json
{
  "Effect": "Allow",
  "Principal": { "AWS": "arn:aws:iam::<network-account-id>:root" },
  "Action": "sts:AssumeRole",
  "Condition": {
    "StringEquals": {
      "sts:ExternalId": "<external-id>",
      "aws:PrincipalArn": "arn:aws:iam::<network-account-id>:role/crossplane-cp-<região>"
    }
  }
}
```

`ExternalId` e o raciocínio de confused deputy estão em
[`02-cross-account-roles.md`](02-cross-account-roles.md); aqui o acréscimo é o
`aws:PrincipalArn` — sem ele, qualquer role da conta `network` que alcance o assume entra na
conta-alvo.

## Refinamento opcional: uma identidade por provider

Least privilege real: uma Pod Identity association **por ServiceAccount de provider**, em vez de
uma para todo o Crossplane.

| Provider | Role recebe |
|---|---|
| `provider-aws-eks` | EKS + as actions de IAM das roles do cluster |
| `provider-aws-ec2` | VPC, subnets, route tables, TGW attachment |
| `provider-aws-route53` | só Route 53 |

Custa mais roles e mais associations. O ganho: um CRD malicioso ou uma Composition com bug num
provider não alcança o domínio de outro. Vale quando sair da PoC — hoje o `PowerUserAccess` único
já é a fronteira e é grosseira de propósito.

## O gargalo honesto: k3d não tem Pod Identity

Nada disto elimina a access key **enquanto o control plane for k3d local** — não há issuer nem
serviço de Pod Identity fora do EKS. As opções no k3d são access key (hoje) ou IAM Roles Anywhere
com PKI própria, e o tópico 4 já registra a access key como débito consciente.

Ou seja: **a aposentadoria do IAM user está bloqueada pela migração do control plane para EKS**,
não por trabalho de IAM. É argumento a favor de priorizar essa migração — ela destrava a correção
de um gap de SEC02-BP02 que nenhuma policy resolve.

Enquanto a chave existir, SEC02-BP02 lista mitigações para access key de IAM user que **devem**
valer aqui:

- Permissões altamente restritas — considerar conceder ao user **apenas `sts:AssumeRole`** para
  uma role específica, isolando a credencial de longa duração do poder real.
- Limitar redes/IPs de origem na trust policy da role.
- Monitorar uso e alertar sobre permissão não usada ou uso indevido.
- Permission boundary complementando a SCP (SCP é grosseira; boundary é fina).

A primeira é a mais valiosa e a mais barata: hoje o `crossplane-poc` tem `PowerUserAccess`
**direto**; reduzi-lo a só `sts:AssumeRole` moveria todo o privilégio para roles temporárias sem
esperar a migração para EKS.

## Well-Architected — porquê

| Best practice | Como atende |
|---|---|
| **[SEC02-BP02 — Use temporary credentials](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/sec_identities_unique.html)** | Pod Identity como alvo; enquanto houver access key, aplicar as mitigações que a própria BP lista (`sts:AssumeRole` apenas, monitoramento, boundary) |
| **[SEC03-BP01 — Define access requirements](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/sec_permissions_define.html)** | Quem/o quê precisa de acesso é definido por eixo (control plane, conta-alvo, workload), não por conveniência |
| **[SEC03 — Permissions management](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/permissions-management.html)** | Contenção regional por SCP + condição, e opcionalmente uma role por provider |
| **[SEC04 — Detection](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/detection.html)** | Nome de role com região torna o CloudTrail atribuível sem correlação por horário |

## Próximo

→ Volta ao índice: [`CLAUDE.md`](CLAUDE.md). Para o hop cross-account em si,
[`02-cross-account-roles.md`](02-cross-account-roles.md); para a trajetória do host do control
plane, [`04-workload-identity.md`](04-workload-identity.md).
