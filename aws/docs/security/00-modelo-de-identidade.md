# 00 — Modelo de Identidade

**Pilar WAF principal:** Security (SEC02 — gerenciamento de identidades).

## Duas classes de identidade, dois padrões

Toda ação na AWS parte de uma identidade. Nesta referência há **exatamente duas classes**, e
confundi-las é a origem da maioria dos antipadrões de segurança:

| Classe | Quem é | Como autentica | Credencial |
|---|---|---|---|
| **Humana** | operador, dev, auditor | IAM Identity Center (SSO), federado de um IdP | STS temporário por sessão (`aws sso login`) |
| **Máquina** | Crossplane, CI/CD, pod no cluster | role assumida / Pod Identity / IAM user escopado | temporária (role) ou access key só quando inevitável |

Regra-mãe: **humano nunca usa access key de longa duração; máquina nunca usa SSO.** SSO
pressupõe um navegador e uma sessão interativa — automação não tem nem um nem outro. Access
key de longa duração para humano é uma credencial permanente a vazar — SSO existe para
eliminá-la.

## As 3 perguntas do perímetro

Todo acesso se decide respondendo três coisas, nesta ordem:

```text
1. QUEM   — a identidade está autenticada? (SSO para humano, role/Pod Identity para máquina)
2. O QUÊ  — a policy permite esta ação neste recurso? (menor privilégio — tópico 1)
3. ONDE   — a conta/OU permite via SCP? (teto preventivo — ../accounts/02)
```

As três são camadas **AND**: a ação só passa se autenticada **e** permitida pela policy **e**
não negada por SCP. Um `Deny` em qualquer camada barra — é o que torna o perímetro robusto a
erro numa camada só (um IAM permissivo demais ainda esbarra no SCP; ver `../accounts/02`).

## Credenciais temporárias por padrão

O padrão-ouro é **nenhuma credencial de longa duração** em lugar nenhum:

- **Humano** → SSO emite STS que expira (default 1h, configurável).
- **Máquina no cluster** → Pod Identity/IRSA: o pod assume uma role e recebe credencial
  temporária rotacionada pela AWS, sem nada montado em disco (tópico 4).
- **Máquina cross-account** → `sts:AssumeRole`: credencial temporária da conta de destino,
  sem IAM user duplicado lá (tópico 2).

O único caso legítimo de access key de longa duração nesta PoC é a automação de bootstrap
(`crossplane-poc`) enquanto o cluster que rodaria o Pod Identity **ainda não existe** —
um degrau, não o destino (tópico 4 e 7).

## Onde cada peça é decidida

Este domínio não redefine SSO nem permission sets — isso é `../accounts/04-acesso-cross-account.md`.
Aqui a divisão é:

| Pergunta | Domínio/arquivo |
|---|---|
| Onde as identidades humanas vivem (SSO, permission sets) | `../accounts/04` |
| Que teto de conta/OU limita todas elas (SCP) | `../accounts/02` |
| **O que exatamente cada policy permite (menor privilégio)** | **este domínio, tópico 1** |
| **Como uma conta age em outra (role cross-account)** | **tópico 2** |
| **Como um workload no cluster tem identidade** | **tópico 4** |

## Well-Architected — porquê

| Best practice | Como atende |
|---|---|
| **SEC02-BP01** identidade centralizada | SSO para humano, role/Pod Identity para máquina — sem IAM user solto por conta |
| **SEC02-BP02** credenciais temporárias | STS/Pod Identity como padrão; access key só no bootstrap inevitável |
| **SEC02-BP04** confiar em identidade forte | separação explícita humano/máquina evita reuso de credencial entre classes |

## Próximo

→ [`01-menor-privilegio-e-policies.md`](01-menor-privilegio-e-policies.md): como escrever a
policy que responde a pergunta "o quê".
