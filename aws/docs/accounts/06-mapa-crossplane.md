# 06 — Mapa para Crossplane

**Ponte entre a arquitetura de contas (tópicos 0–5) e o código.** Diferente do domínio
`../network/`, boa parte deste domínio **não é** (e não deveria ser) provisionada pela mesma
instância de Crossplane que gerencia as spokes — motivo abaixo.

## Por que "bootstrap de conta" é uma camada diferente de "provisionar dentro da conta"

O Crossplane hospedado no hub k3d desta PoC (`../../CLAUDE.md`, `../../eks/`) autentica com
credenciais de **uma** conta AWS (`crossplane-poc`). Ele pode gerenciar recursos
**dentro** dessa conta (e, com roles cross-account assumíveis, dentro de outras já
existentes) — mas ele **não pode criar a própria conta em que vai rodar**, nem a
Organization que a contém. É um problema de ordem: a credencial que gerenciaria o
`create-account` teria que existir antes da conta existir.

**Divisão de responsabilidade:**

| Camada | Quem faz | Por quê |
|---|---|---|
| Organization, OUs, SCPs, `create-account` | **Bootstrap manual/script, fora do Crossplane** (AWS CLI direto, ou um provider Crossplane `provider-aws-organizations` rodando numa conta de **gerência** já estabelecida) | É meta-infraestrutura — precisa existir antes de qualquer Crossplane ter onde rodar |
| IAM Identity Center, permission sets | Bootstrap manual (raramente muda) | Configuração de identidade humana, não workload |
| Dentro de uma conta já criada (VPC, TGW, EKS, RAM share) | **Crossplane** (é o que `../network/07-mapa-crossplane.md` já cobre) | Aqui sim há credencial válida (a role/user daquela conta) para reconciliar |

Isso não é uma limitação temporária — é a mesma distinção que ferramentas como AWS Control
Tower fazem (Control Tower cria a Landing Zone; o que roda **dentro** das contas é gerenciado
por outra coisa, Terraform/Crossplane/CloudFormation).

## O que É automatizável (uma vez que a Organization existe)

Se uma conta de gerência **já** tem Organizations habilitado, um provider
`provider-aws-organizations` do Crossplane (rodando com credenciais **dessa** conta de
gerência) pode reconciliar:

- `Account` (MR) — criação de conta por projeto como um recurso declarativo, análogo ao que
  `Network`/`Cluster` fazem hoje para rede/EKS.
- `OrganizationalUnit`, `Policy` (SCP) — versionar guardrails como código.

**Não confundir com o Crossplane do hub k3d desta PoC** — seria uma instância/provider
**separado**, rodando com credenciais da conta de gerência, não da `crossplane-poc`
(que vive dentro de uma conta-membro, não na gerência).

## Estado atual do PoC vs. alvo

| Peça | Estado no PoC | Alvo |
|---|---|---|
| Organization própria | ❌ não existe — conta única, sem Organizations habilitado | Organization com `feature-set ALL` |
| OUs / SCPs | ❌ não existem | Security + Infrastructure + Workloads (mínimo), guardrails de região/root/IMDSv2 |
| Conta Hub dedicada | ❌ não existe — a conta única acumula tudo | Conta própria, só recursos de `../network/` do Hub |
| Conta por projeto | ❌ não existe — o PoC roda tudo numa conta compartilhada com outros sistemas (`<account-id>`, ver `../../CLAUDE.md`) | 1 conta por projeto |
| IAM Identity Center | não documentado nesta PoC (uso de SSO já existe no dia a dia, mas fora do escopo do repo) | Permission sets nomeados por função, atribuídos por conta |
| `provider-aws-organizations` no Crossplane | ❌ não instalado em lugar nenhum | Instância separada, rodando na conta de gerência |

## Ordem de adoção sugerida (quando sair do design para a prática)

1. Decidir se a Organization nasce numa conta **nova** (recomendado, ver
   `00-estrategia-de-contas.md` — "conta com residentes não deve virar gerência") ou se a
   conta atual do PoC se torna a gerência depois de migrar seus recursos residentes para uma
   conta-membro própria.
2. `create-organization --feature-set ALL` (tópico 1).
3. Criar OUs Security/Infrastructure/Workloads (tópico 1) + SCPs baseline (tópico 2).
4. `create-account` para a conta network (tópico 3) → mover para OU Infrastructure.
5. Configurar IAM Identity Center + permission sets (tópico 4).
6. Dentro da conta network: instalar o Crossplane/hub k3d **desta** PoC (ou uma instância
   equivalente) e seguir `../network/07-mapa-crossplane.md` para provisionar TGW/VPN.
7. Por projeto: `create-account` → mover para OU Workloads → provisionar spoke
   (`../network/`).
