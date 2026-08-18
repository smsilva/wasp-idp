# CLAUDE.md — `aws/docs/` (Arquitetura de Referência: Hub-and-Spoke na AWS)

> **Índice mestre.** Esta pasta é a documentação **evolutiva** de como montar, do zero,
> um ambiente AWS completo seguindo o **Well-Architected Framework** — organizada em
> subpastas por domínio, cada uma com seu próprio índice (`CLAUDE.md`). Comece por aqui,
> depois desça para o domínio de interesse.

---

## Objetivo

Descrever, passo a passo, como sair de uma **conta AWS totalmente vazia** e chegar a uma
topologia **hub-and-spoke** oficial e segura, na qual:

1. Uma **conta AWS dedicada ao Hub** (Connectivity Account) concentra os recursos
   compartilhados de rede — Transit Gateway, VPNs de acesso, roteamento central.
2. Cada **projeto ganha sua própria conta AWS** (isolamento de blast radius e billing).
3. Cada **cluster entra como uma nova spoke** — uma VPC attachada ao TGW do Hub, com
   route table dedicada e isolamento por tenant.
4. **VPNs de acesso** (site-to-site / client) seguem boas práticas de segurança e fecham
   sempre no Hub, nunca no spoke.

O ponto de chegada é uma **arquitetura de referência**: reproduzível em qualquer conta,
por qualquer time.

## Princípios (não-negociáveis)

| Princípio | O que significa aqui |
|---|---|
| **Well-Architected** | Cada decisão é justificada contra os pilares AWS WAF (com foco em Security, Reliability, Operational Excellence e Cost). Referências REL/SEC/OPS citadas nos tópicos. |
| **Composable by design** | Cada peça é uma abstração componível (Crossplane XR): Network, Cluster, DnsZone. Um recurso de alto nível compõe os de baixo; nada é monolítico. (Pilar 5 do "Platform Engineering 2.0".) |
| **Agnóstico ao ambiente** | O corpo da doc usa **placeholders** (`<hub-cidr>`, `<root-domain>`, `<asn>`) — ninguém precisa dos valores reais de uma organização específica para reusar a referência. |
| **Nunca alterar config compartilhada** | Só ADICIONAR recursos isolados. Regra herdada do PoC (ver `../../CLAUDE.md`). |

## Como esta documentação é organizada

- **Uma subpasta por domínio.** Cada uma tem um `CLAUDE.md` que indexa seus tópicos.
- **Tópicos são arquivos curtos e focados** — um assunto por arquivo, evoluível de forma
  independente.
- **Referência + mapa para Crossplane.** Cada domínio explica primeiro o *quê/porquê*
  (arquitetura Well-Architected), depois o *como* (que XRD/Composition materializa a peça,
  o que já existe no repo e o gap até o alvo).
- **Placeholders no corpo.** Convenção: `<algo-entre-angle-brackets>` é um valor que o
  adotante preenche com os dados da sua própria conta.

## Domínios

| # | Domínio | Índice | Estado |
|---|---|---|---|
| 0 | **Bootstrap** — conta hub vazia → IAM user da automação com credencial | [`bootstrap/CLAUDE.md`](bootstrap/CLAUDE.md) | ✅ completo |
| 1 | **Network** — hub-and-spoke, VPC/subnets, TGW, VPN, DNS, CIDR | [`network/CLAUDE.md`](network/CLAUDE.md) | ✅ completo |
| 2 | **Accounts & Organizations** — conta vazia → hub → contas por projeto | [`accounts/CLAUDE.md`](accounts/CLAUDE.md) | ✅ completo |
| 3 | **Security & IAM** — perímetro de identidade, menor privilégio, roles cross-account, RAM, Pod Identity, VPN auth, detecção | [`security/CLAUDE.md`](security/CLAUDE.md) | ✅ completo |
| 4 | **DNS** — zonas públicas/privadas, delegação, alias/apex/wildcard, resolução cross-account, external-dns + TLS | [`dns/CLAUDE.md`](dns/CLAUDE.md) | ✅ completo |
| 5 | **Compute** — EKS como spoke, node groups, add-ons + Pod Identity, RBAC, ingress, GitOps | [`compute/CLAUDE.md`](compute/CLAUDE.md) | ✅ completo |
| 6 | **Observability** — logs, métricas, alertas de conectividade, custo como sinal | [`observability/CLAUDE.md`](observability/CLAUDE.md) | ✅ completo |

> A ordem de construção segue a dependência real: **bootstrap primeiro** (dá à automação a
> credencial que ela usa em todos os domínios seguintes), depois **network** (a fundação
> sobre a qual contas, clusters e VPNs se apoiam). Os **7 domínios estão completos** — o
> próximo passo do projeto é retomar o schema detalhado e a spec de implementação (ver
> `../../HANDOFF.md`).

## Relação com o resto do repo

- **Código Crossplane** (o que materializa esta arquitetura): `../eks/resources/`
  (`network/`, `cluster/`, `argocd/`) e o chart faseado em `../eks/chart/`.
- **Contexto operacional AWS** (conta, IAM user do Crossplane, credenciais): `../CLAUDE.md`.
- **Design/brainstorm da decomposição** (Environment → Network + Cluster): `../../docs/superpowers/`.

## Fontes externas de referência

Trabalho de rede hub-and-spoke maduro (KCL/Crossplane), usado como base:

- Design consolidado AWS↔Azure: `<hub-repo>/docs/superpowers/specs/2026-05-26-hub-spoke-design.md`
- Landing Zone (visão de arquitetura): `<hub-repo>/docs/02-arquitetura/aws-landing-zone.md`
- Templates KCL: `<assets-repo>/crossplane/providers/aws/{hub_network,spoke_network,tgw,vpn_connection}/`
- AWS Well-Architected Framework — pilares e best practices (REL02, SEC05, etc.).

## Explorações paralelas (em andamento, nenhuma final)

Materiais do próprio autor que exploram a **mesma visão em outras fatias/maturidades** —
referência para pensamento e decisão, não especificação a copiar. Nenhum é versão final;
fazem parte do processo de aprendizado. **Cuidado com o vocabulário:** "hub" significa
coisas diferentes em cada um (ver a distinção abaixo).

| Material | Fatia que explora | O que "hub" significa lá |
|---|---|---|
| `~/trash/arquitetura-cell-based-multi-region.md` | **Raio de impacto / tenancy** (camada app/dados): células como unidade de falha, pooled vs. dedicado, multi-region + cell router | Hub de **rede por região** (VPC + TGW), mais próximo do desta doc |
| `~/git/aws-saas-platform` | **Identidade + ingress + isolamento pooled** (camada app/auth): Cognito federando IdPs, ALB→WAF→Istio, namespace+claim+`AuthorizationPolicy`, roadmap de fases 1→2→3 | Hub de **identidade** (Cognito) + hub de **ingress** (Global Accelerator) — **NÃO** é hub de rede/conta; é single-account, sem TGW |

**Como se encaixam:** três lentes de uma plataforma-alvo, ainda não unificadas —
cell-based (raio de impacto), esta doc (conectividade privada hub-spoke de **rede/conta**),
e aws-saas-platform (identidade/ingress/isolamento **pooled** por namespace). São
complementares, mas os dois "hubs" (rede vs. identidade) são camadas distintas — não
confundir. O roadmap de fases do aws-saas-platform (single cluster → platform/customer
split → regional) é uma escada de maturidade útil para enquadrar decisões desta doc (ex.:
"o TGW é uma decisão de qual fase?"). Aprofundar/unificar é trabalho futuro, não decidido.