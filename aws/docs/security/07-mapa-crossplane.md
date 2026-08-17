# 07 — Mapa para Crossplane

> Como cada peça deste domínio vira (ou não vira) XRD/Composition, o que já roda no PoC e o
> gap até o alvo. Fecha o domínio ligando a referência Well-Architected ao código real.

## O que é provisionável via Crossplane — e o que não é

IAM tem uma fronteira dura de automação, imposta pelo **bootstrap galinha-e-ovo** (tópico 4):

| Peça | Provisionável via Crossplane? | Por quê |
|---|---|---|
| Roles do cluster (Pod Identity, node, EBS CSI, ESO) | ✅ sim | `provider-aws-iam` cria `Role`/`RolePolicy` como MR, escopadas a `poc-eks-*` |
| `PodIdentityAssociation` | ✅ sim | MR do provider EKS, liga ServiceAccount ↔ role |
| RAM share do TGW (cross-account) | ✅ sim (alvo) | `ResourceShare`/`Association` como MR — hoje suprimido (conta única) |
| Roles cross-account Hub↔projeto | ✅ sim (alvo) | `Role` + trust policy como MR, quando houver 2 contas |
| **Grant de IAM à própria automação** | ❌ **não** | a automação tem `implicitDeny` em `iam:PutUserPolicy` — não pode se auto-conceder |
| SCP / OU / Organization | ⚠️ conta de gerência | `provider-aws-organizations` numa **instância separada** (`../accounts/06`) |
| Access Analyzer / GuardDuty / CloudTrail | ⚠️ possível, não no escopo | habilitação de conta, barata, ainda manual no PoC |

A linha vermelha: **o Crossplane provisiona o IAM do que ele gerencia, mas não o IAM que o
autoriza a gerenciar.** Esse último é sempre um passo de admin humano.

## O bootstrap manual (o que fica fora do declarativo)

O grant que habilita a automação é aplicado **uma vez**, por quem tem `AdministratorAccess`:

```bash
aws iam put-user-policy --user-name crossplane-poc \
  --policy-name CrossplaneEksRoleManagement \
  --policy-document file://aws/eks/providers/bootstrap-iam-policy.json
```

O JSON versionado (`../../eks/providers/bootstrap-iam-policy.json`) **é a fonte de verdade** do
estado desejado — o `put-user-policy` só o aplica. Ele escopa duas coisas:

- `CrossplaneEksRoleManagement` → todas as ações de role restritas a
  `arn:aws:iam::<account>:role/poc-eks-*` (as roles do nosso cluster, não as de outros times).
- `EksNodegroupServiceLinkedRoleRead` → `iam:GetRole` na service-linked role do EKS Nodegroup
  (leitura pontual que o provider exige).

Versionar o JSON dá o benefício declarativo (revisão, diff, reaplicar em conta nova) mesmo
sendo um passo imperativo — o mesmo espírito da "referência + mapa" dos outros domínios.

## Padrão de policy nas Compositions

Toda `Role`/`RolePolicy` que uma Composition materializa segue os tópicos 1 e 4:

- **`Resource` escopado por prefixo** — nunca `"*"`; sempre `poc-eks-*` / `poc-eks/*`.
- **Inline policy 1:1 com a role** — morre com ela (sem policy órfã).
- **Trust policy mínima** — Pod Identity confia no serviço `pods.eks.amazonaws.com`; role
  cross-account confia no principal específico da outra conta (tópico 2), não no `root`.

Exemplo materializado hoje: a role do ESO (`poc-eks-*-eso-role`) com inline escopada a
`secretsmanager:GetSecretValue` sobre `arn:aws:secretsmanager:us-east-1:*:secret:poc-eks/*` —
menor privilégio como código.

## Estado atual do PoC vs. alvo

| Peça | Estado no PoC | Alvo |
|---|---|---|
| IAM user da automação | ✅ `crossplane-poc`, `PowerUserAccess` + inline escopada | customer-managed escopada (enxugar `PowerUserAccess` via tópico 6) |
| Roles do cluster (Pod Identity/ESO/EBS/node) | ✅ criadas por MR, escopadas `poc-eks-*` | idem |
| Permission boundary | ❌ não existe | boundary por conta exigida em `iam:CreateRole` (tópico 1) |
| Roles cross-account | ❌ conta única, suprimidas | Hub↔projeto quando `../accounts/` separar contas |
| RAM share (perímetro) | ❌ suprimido (conta única) | `allowExternalPrincipals=false` por tenant (tópico 3) |
| Access Analyzer / GuardDuty | ❌ não habilitados | ligados por Organization (detecção sempre on) |
| Grant de IAM à automação | ✅ bootstrap manual documentado | permanece manual (galinha-e-ovo é intrínseco) |

## Ordem de adoção sugerida

1. Manter o bootstrap manual do IAM user (não é automatizável — aceitar).
2. Migrar workloads do cluster para **Pod Identity** com roles escopadas (já em curso — ESO).
3. Adicionar **permission boundary** por conta e exigi-la em `iam:CreateRole` (tópico 1).
4. Habilitar **Access Analyzer + GuardDuty** por Organization (barato, sem workload).
5. Usar CloudTrail/Access Analyzer para **enxugar `PowerUserAccess`** numa policy escopada.
6. Quando `../accounts/` separar Hub e projeto: introduzir **roles cross-account** e **RAM**
   escopado à Organization (tópicos 2 e 3), removendo a supressão de conta única.
