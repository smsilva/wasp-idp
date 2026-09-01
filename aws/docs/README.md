# `aws/docs/` — Reference Architecture: Hub-and-Spoke on AWS

Índice de leitura. Convenções de escrita e regras de manutenção ficam em
[`CLAUDE.md`](CLAUDE.md); isto aqui é só "o que existe e onde".

## Domínios

| # | Domínio | Índice | Estado |
|---|---|---|---|
| 0 | **Bootstrap** — conta `network` vazia → IAM user da automação com credencial | [`bootstrap/README.md`](bootstrap/README.md) | ✅ completo |
| 1 | **Network** — hub-and-spoke, VPC/subnets, TGW, VPN, DNS, CIDR | [`network/README.md`](network/README.md) | ✅ completo |
| 2 | **Accounts & Organizations** — conta vazia → `network` → contas por projeto | [`accounts/README.md`](accounts/README.md) | ✅ completo |
| 3 | **Security & IAM** — perímetro de identidade, menor privilégio, roles cross-account, RAM, Pod Identity, VPN auth, detecção | [`security/README.md`](security/README.md) | ✅ completo |
| 4 | **DNS** — zonas públicas/privadas, delegação, alias/apex/wildcard, resolução cross-account, external-dns + TLS | [`dns/README.md`](dns/README.md) | ✅ completo |
| 5 | **Compute** — EKS como spoke, node groups, add-ons + Pod Identity, RBAC, ingress, GitOps | [`compute/README.md`](compute/README.md) | ✅ completo |
| 6 | **Observability** — logs, métricas, alertas de conectividade, custo como sinal | [`observability/README.md`](observability/README.md) | ✅ completo |
| 7 | **Tenancy & SaaS** — SaaS Lens (silo/pool/bridge), conta por tenant, OU por geografia, CIDR × tenant | [`tenancy/README.md`](tenancy/README.md) | 🟡 desenho (nada aplicado) |

> A ordem de construção segue a dependência real: **bootstrap primeiro** (dá à automação a
> credencial que ela usa em todos os domínios seguintes), depois **network** (a fundação
> sobre a qual contas, clusters e VPNs se apoiam). Os domínios **0–6 estão completos**; o
> **7 (tenancy)** é o único puramente prospectivo — desenho sem nada aplicado numa conta real.
>
> **Tenancy decide antes de `accounts/` executar.** Quando houver cliente externo, os tiers e os
> perfis de residência (`tenancy/`) precisam estar definidos **antes** de criar contas de tenant —
> definir depois vira reorganização da árvore de OUs, com janela sem SCP durante o move. Para a
> topologia interna atual (projetos próprios, sem tenant externo), `accounts/` basta.
>
> A visão de plataforma correspondente — sequência de provisionamento por fases, células,
> roteamento global — vive em `../../decisions.md`. Onde os dois divergirem, **a doc de domínio
> ganha** (regra registrada em `decisions.md` §8).
