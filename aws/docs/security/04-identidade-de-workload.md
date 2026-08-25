# 04 — Identidade de Workload

**Pilar WAF principal:** Security ([SEC02 — Identity management](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/identity-management.html); [SEC08 — Protecting data at rest](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/protecting-data-at-rest.html)).

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
para começar — ver bootstrap abaixo. Mas "fora da AWS" **não** obriga access key: uma máquina
externa ainda emite STS temporária via Roles Anywhere ou OIDC federation (próxima seção) — o
access key é o último degrau, só quando não há nem PKI nem um issuer OIDC utilizável.

## Máquina FORA da AWS: STS sem access key (Roles Anywhere e OIDC federation)

Um control plane que roda **fora** da AWS (Crossplane num k3d, num AKS, on-prem, num CI/CD)
não tem role de instância a assumir — mas ainda pode obter credencial **temporária**, sem
access key de longa duração, por um de dois mecanismos. A escolha depende de **o que a
plataforma-hospedeira já oferece**:

| Mecanismo | Prova de identidade | Quando é o encaixe |
|---|---|---|
| **IAM Roles Anywhere** | certificado **X.509** de uma PKI (trust anchor via ACM PCA ou CA própria) | há PKI, mas **não** há um issuer OIDC público utilizável (VM bare-metal, on-prem, k3d local sem URL pública) |
| **OIDC federation** (`sts:AssumeRoleWithWebIdentity`) | **JWT** de uma ServiceAccount, assinado por um **issuer OIDC público** | a plataforma expõe um issuer OIDC alcançável pela AWS (AKS, GKE, EKS) |

Nos dois, o fluxo é o mesmo em espírito: a máquina apresenta uma prova forte (cert ou JWT),
a AWS valida contra um **trust anchor / OIDC provider** registrado, e o STS devolve credencial
temporária (`ASIA...`). **Nenhum segredo de longa duração** cruza a fronteira.

**OIDC federation replica o IRSA cross-cloud.** Um AKS liga um issuer público
(`--enable-oidc-issuer`); registra-se esse issuer como **IAM OIDC identity provider** na conta
AWS, e a role federa a ServiceAccount pela mesma convenção do IRSA:

```json
"Action": "sts:AssumeRoleWithWebIdentity",
"Condition": { "StringEquals": {
  "<issuer>:sub": "system:serviceaccount:<ns>:<sa>",
  "<issuer>:aud": "sts.amazonaws.com" }}
```

> **Gotcha do aud (AKS→AWS):** o token projetado precisa ter `aud: sts.amazonaws.com`; o token
> default do AKS vem com outro audience. Instalar o `amazon-eks-pod-identity-webhook` no AKS
> (injeta `AWS_ROLE_ARN`/`AWS_WEB_IDENTITY_TOKEN_FILE` e projeta o token com o aud certo) — o
> mesmo webhook do IRSA, rodando fora do EKS.

## Trajetória do control plane: k3d → AKS → EKS

**Onde o Crossplane roda decide a credencial-raiz** — e só ela. O hop cross-account
(`sts:AssumeRole` → role da conta spoke, tópico 2) é **invariante**: não importa como a raiz
autentica, o salto Hub→spoke não muda. Só troca o primeiro elo da cadeia.

| Host do control plane | Mecanismo-raiz WAF-aligned | Access key de longa duração? |
|---|---|---|
| **k3d local** (PoC hoje) | sem issuer público → Roles Anywhere (PKI) **ou** access key de bootstrap | sim — degrau de PoC |
| **AKS** (undercloud/cluster-zero) | **OIDC federation** (`AssumeRoleWithWebIdentity`) via issuer do AKS | ❌ nenhuma |
| **EKS** (se o control plane fosse AWS) | **IRSA/Pod Identity** nativo (nem OIDC provider manual) | ❌ nenhuma |

Ou seja, o cenário "control plane no AKS provisionando EKS numa spoke" é
`role federada OIDC no AKS` → assume `crossplane-<spoke>` na conta spoke → cria a VPC/EKS. É a
evolução **aditiva** do bootstrap atual: quando o control plane sair do k3d para um AKS/EKS, a
credencial-raiz de longa duração **deixa de existir** sem tocar no hop cross-account.

> **Decisão registrada (PoC):** para a PoC, a credencial-raiz por **access key** do
> `crossplane-poc` (k3d fora da AWS) é aceita como **débito consciente** — mesma categoria do
> bootstrap galinha-e-ovo (abaixo). Resolve-se ao migrar o control plane para AKS (OIDC
> federation) ou EKS (IRSA), não antes. Roles Anywhere seria o plano B se quiséssemos eliminar
> o access key **ainda no k3d**, ao custo de manter PKI/trust anchor.

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
| **[SEC02-BP02 — Use temporary credentials](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/sec_identities_unique.html)** | Pod Identity/IRSA (dentro do EKS) e Roles Anywhere/OIDC federation (fora da AWS) emitem STS; access key só no bootstrap inevitável |
| **[SEC02-BP05 — Audit and rotate credentials periodically](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/sec_identities_audit.html)** | access key de bootstrap é efêmera (substituída por Pod Identity) |
| **[SEC08-BP01 — Implement secure key management](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/sec_protect_data_rest_key_mgmt.html)** | Secrets Manager como fonte de verdade, escopado por prefixo de ARN |
| **[SEC03-BP01 — Define access requirements](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/sec_permissions_define.html)** | role de Pod Identity escopada ao próprio prefixo de secret |

## Próximo

→ [`05-autenticacao-vpn.md`](05-autenticacao-vpn.md): identidade e credencial no acesso via
VPN.
