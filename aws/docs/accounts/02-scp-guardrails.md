# 02 — Guardrails via Service Control Policies

**Pilar WAF principal:** Security ([SEC01-BP03 — Identify and validate control objectives](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/sec_securely_operate_control_objectives.html) / [SEC01-BP04 — Stay up to date with security threats and recommendations](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/sec_securely_operate_updated_threats.html)).

## SCP em uma frase

Um **Service Control Policy** é um teto de permissões aplicado a uma OU ou conta — não
concede nada (não substitui IAM), só **restringe** o que qualquer identidade (mesmo
`AdministratorAccess`) pode fazer naquela conta. É a diferença entre "detectar depois" e
"impedir na hora".

## Por que SCP e não só IAM por conta

IAM roda **dentro** de cada conta — um admin de conta pode, por engano ou má-fé, alterar suas
próprias policies. SCP roda **na Organization**, fora do alcance de qualquer identidade da
conta-membro. É a camada que garante que um guardrail vale **mesmo se alguém tiver
AdministratorAccess** na conta afetada.

## Pré-requisito: habilitar o policy type (pegadinha)

Ter `feature-set ALL` (tópico 1) **não** basta — uma Organization nasce com o policy type
`SERVICE_CONTROL_POLICY` **desabilitado**. Qualquer `attach-policy` antes de habilitar falha
com `PolicyTypeNotEnabledException`. Habilitar é um passo à parte, feito **uma vez** na Root:

```bash
root_id="$(aws organizations list-roots --query 'Roots[0].Id' --output text)"

aws organizations enable-policy-type \
  --root-id "${root_id}" --policy-type SERVICE_CONTROL_POLICY
```

A habilitação é **assíncrona** (fica `PENDING_ENABLE` por alguns segundos antes de `ENABLED`).
Confirmar antes de anexar qualquer policy:

```bash
aws organizations list-roots \
  --query "Roots[0].PolicyTypes[?Type=='SERVICE_CONTROL_POLICY'].Status | [0]" --output text
# → ENABLED
```

> O script `scripts/apply-baseline-service-control-policy` já faz isso automaticamente
> (função `enable_scp_policy_type`, idempotente com espera pela ativação) — este bloco
> documenta o passo para quem executar à mão.

## Guardrails recomendados nesta referência

| Guardrail | Aplicado em | Efeito |
|---|---|---|
| **Restringir região** | Todas as OUs de workload | Nega ações fora das regiões aprovadas (`<approved-regions>`) — evita recursos esquecidos em região não monitorada. **A lista de regiões é propriedade da OU, não da conta** — ver nota abaixo |
| **Impedir sair da Organization** | Root (toda a Organization) | Nega `organizations:LeaveOrganization` — uma conta-membro não pode se desvincular sozinha |
| **Proteger a Organization e o CloudTrail** | Root | Nega deletar/desabilitar o CloudTrail e as roles de auditoria |
| **Exigir IMDSv2** | OU Workloads | Nega `ec2:RunInstances` sem `HttpTokens=required` — mitiga SSRF contra o metadata service |
| **Negar acesso root** | Todas exceto Management | Nega ações feitas pelo usuário root da conta-membro (uso de root deve ser só emergencial) |

> **A restrição de região é um eixo de particionamento da árvore, não um parâmetro por conta.**
> Como SCP atacha em OU, qualquer guardrail que precise **variar** entre contas obriga a criar uma
> OU por variação. Enquanto todas as contas de workload compartilham a mesma lista de regiões
> aprovadas, uma SCP única resolve. Quando houver clientes com exigências de jurisdição
> diferentes, a lista deixa de ser global e as OUs de workload precisam ser particionadas por
> **perfil de residência de dados** — desenho em `../tenancy/02-ou-per-geography.md`.
>
> Essa mesma SCP é também a **primeira linha de contenção regional** para a automação: um control
> plane regional que receba um XR com a região errada é barrado pela SCP da OU da conta-alvo,
> antes de qualquer condição na role (`../security/08-control-plane-identity.md`).

## Exemplo de SCP — restringir região

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "DenyOutsideApprovedRegions",
      "Effect": "Deny",
      "NotAction": ["<global-service-actions-exempt>"],
      "Resource": "*",
      "Condition": {
        "StringNotEquals": {
          "aws:RequestedRegion": ["<approved-region-1>", "<approved-region-2>"]
        }
      }
    }
  ]
}
```

`NotAction` deve isentar ações inerentemente globais (IAM, Organizations, Route53, CloudFront,
Support) — sem a isenção, a policy quebra a própria administração da conta.

## Criar e anexar (comandos)

Com o policy type já habilitado (pré-requisito acima):

```bash
# 1. Criar a policy (retorna um Id p-xxxx)
policy_id="$(aws organizations create-policy \
  --name DenyOutsideApprovedRegions \
  --description "Restringe a regiões aprovadas" \
  --type SERVICE_CONTROL_POLICY \
  --content file://scp-deny-regions.json \
  --query Policy.PolicySummary.Id --output text)"

# 2. Anexar a policy a um target (Root, OU ou conta)
aws organizations attach-policy --policy-id "${policy_id}" --target-id <target-id>

# Atualizar conteúdo depois (idempotência): update-policy --policy-id ... --content ...
# Ver anexos de um target: list-policies-for-target --target-id ... --filter SERVICE_CONTROL_POLICY
```

## Onde aplicar

- **Root da Organization**: guardrails que valem para TODAS as contas, sem exceção (proteção
  de auditoria, impedir saída da Organization).
- **OU Infrastructure**: guardrails mais restritivos que Workloads — menos serviços habilitados, sem
  necessidade de rodar workloads arbitrários.
- **OU Workloads**: guardrails de baseline (região, IMDSv2) — o piso comum de todo projeto.
- **Management Account**: SCPs praticamente não se aplicam a ela mesma por padrão (a Root
  Organizational Unit as aplica às contas-membro, não à management account) — reforça por
  que ela não deve rodar workload (tópico 0): não há guardrail de SCP a proteger o que roda ali.

## Estado aplicado nesta Organization

Baseline aplicada por `scripts/apply-baseline-service-control-policy` (idempotente —
reexecutar é a forma de conferir). Regiões aprovadas: **`us-east-1`**.

| Target | SCPs anexadas |
|---|---|
| Root | `DenyLeaveOrganization`, `ProtectCloudTrail` |
| OU `Infrastructure` | `DenyOutsideApprovedRegions`, `RequireImdsv2`, `DenyRootUser` |
| OU `Workloads` | `DenyOutsideApprovedRegions`, `RequireImdsv2`, `DenyRootUser` |
| OU `Security` | `DenyOutsideApprovedRegions`, `RequireImdsv2`, `DenyRootUser` |

`FullAWSAccess` (AWS-managed) permanece anexada em todos os targets — sem ela, o modelo
deny-list do SCP negaria tudo.

Sub-OUs herdam: `Workloads/NonProd` e `Workloads/Production` recebem os guardrails de
`Workloads` sem attach próprio.

**`DenyRootUser` vs. trocar o e-mail de root de uma conta:** o e-mail do root só muda pelo
fluxo de root no console da própria conta. Se o guardrail bloquear esse fluxo, destacar a
policy do target, fazer a troca e reanexar — não remover a policy em definitivo.

## Well-Architected — porquê

| Best practice | Como atende |
|---|---|
| **[SEC01-BP03 — Identify and validate control objectives](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/sec_securely_operate_control_objectives.html)** | SCP nega na API, antes da ação acontecer |
| **[SEC01-BP04 — Stay up to date with security threats and recommendations](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/sec_securely_operate_updated_threats.html)** | Guardrail dedicado negando ações do usuário root |
| **REL/OPS** contenção de erro humano | Restrição de região evita "esqueci um recurso rodando em `sa-east-1`" |

## Próximo

→ [`03-provisioning.md`](03-provisioning.md): como criar as contas
de fato.