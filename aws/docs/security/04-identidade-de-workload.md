# 04 — Identidade de Workload

**Pilar WAF principal:** Security (SEC02 — identidade de máquina; SEC08 — proteção de segredos).

## O problema: dar identidade a código, não a pessoas

Automação (Crossplane), pipelines e pods no cluster precisam agir na AWS sem um humano no
loop. A pergunta é como dar a eles uma identidade **sem** espalhar access key de longa
duração — que não expira, não rotaciona sozinha e vaza em log/imagem/variável de ambiente.
Há três padrões, do pior ao melhor, e a escolha depende de **o que já existe**.

## Os três padrões (e quando cada um é inevitável)

| Padrão | Credencial | Quando usar |
|---|---|---|
| **IAM user + access key** | longa duração | último recurso — só quando ainda não há nada que emita STS |
| **AssumeRole** (tópico 2) | STS temporária | automação que já roda com alguma identidade (ex.: numa conta, agindo em outra) |
| **Pod Identity / IRSA** | STS temporária, rotacionada | workloads **dentro** do EKS |

Regra: subir a escada sempre que possível. O IAM user existe nesta PoC só porque o Crossplane
roda num k3d **fora** da AWS (sem role de instância a assumir) e precisa de *alguma* credencial
para começar — ver bootstrap abaixo.

## Pod Identity e IRSA — identidade nativa do pod

Para workloads **dentro** do EKS, a AWS emite credencial temporária diretamente ao pod, sem
nada montado em disco:

- **IRSA** (IAM Roles for Service Accounts) — o mais antigo; associa uma role a uma
  ServiceAccount via OIDC provider do cluster; anotação na SA.
- **Pod Identity** — o mais novo e simples; um addon (`eks-pod-identity-agent`) + uma
  `PodIdentityAssociation` (ServiceAccount ↔ role), sem gerir OIDC provider. **Preferido**
  nesta referência.

O pod assume a role, recebe STS rotacionada pela AWS, e a role carrega uma policy **escopada**
(tópico 1). Exemplo real da PoC — a role do External Secrets Operator só lê o prefixo dela:

```text
PodIdentityAssociation:  ServiceAccount external-secrets  ↔  role poc-eks-*-eso-role
Role policy (inline, escopada):
  Allow secretsmanager:GetSecretValue  on  arn:aws:secretsmanager:us-east-1:*:secret:poc-eks/*
```

Ler fora de `poc-eks/*` é negado — o workload tem identidade **e** menor privilégio, sem
access key. É o alvo para todo pod que fala com a AWS.

## Segredos: Secrets Manager como fonte de verdade

Credencial que **precise** existir (a access key de bootstrap, PSK de VPN, connection secrets)
vive no **Secrets Manager**, nunca em arquivo no repo ou disco:

- Recuperar **inline** no momento do uso, sem persistir (`get-secret-value` → export → uso).
- Acesso escopado por prefixo de ARN (`poc-eks/*` para a fatia EKS; `poc-idp/*` para as
  creds do Crossplane) — um consumidor não lê o segredo de outro.
- Rotação: fora de escopo desta fase para PSK; para a access key de bootstrap, a mitigação é
  torná-la **efêmera** (some quando o Pod Identity assume o papel — abaixo).

## O bootstrap galinha-e-ovo (por que existe access key aqui)

A automação **não pode se auto-conceder IAM**: `crossplane-poc` tem `implicitDeny` em
`iam:PutUserPolicy`/`iam:CreateRole` (confirmado via `simulate-principal-policy`). Logo:

```text
Para o Crossplane criar as roles do cluster (Pod Identity etc.)
  → precisa de permissão de IAM
     → que ele não pode dar a si mesmo
        → alguém com AdministratorAccess concede UMA vez (bootstrap manual de admin)
```

Esse grant inicial (`put-user-policy` com `CrossplaneEksRoleManagement`) é **da mesma
categoria** de criar o IAM user — um passo de admin humano, não um MR do Crossplane. A access
key existe porque, no bootstrap, **ainda não há cluster** para hospedar o Pod Identity que a
substituiria. É um degrau: uma vez o cluster de pé, os workloads usam Pod Identity, e a access
key fica restrita ao Crossplane externo. O JSON versionado
(`../../eks/providers/bootstrap-iam-policy.json`) é a fonte de verdade do estado desejado;
o `put-user-policy` é o ato de bootstrap.

> **Não remover ações "só de teardown":** `iam:ListInstanceProfilesForRole` é usada pelo
> provider ao **deletar** roles; sem ela o teardown trava em `AccessDenied`. Está no
> `bootstrap-iam-policy.json` de propósito — revisar a policy testando só a criação a
> removeria por engano.

## Well-Architected — porquê

| Best practice | Como atende |
|---|---|
| **SEC02-BP02** credenciais temporárias | Pod Identity/IRSA emitem STS rotacionada; access key só no bootstrap inevitável |
| **SEC02-BP05** auditar/rotacionar credenciais | access key de bootstrap é efêmera (substituída por Pod Identity) |
| **SEC08-BP01** proteger segredos em repouso | Secrets Manager como fonte de verdade, escopado por prefixo de ARN |
| **SEC03-BP01** menor privilégio | role de Pod Identity escopada ao próprio prefixo de secret |

## Próximo

→ [`05-autenticacao-vpn.md`](05-autenticacao-vpn.md): identidade e credencial no acesso via
VPN.
