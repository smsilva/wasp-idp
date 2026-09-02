# CLAUDE.md — `aws/docs/` (Reference Architecture: Hub-and-Spoke on AWS)

> **Regras deste domínio.** Esta pasta é a documentação **evolutiva** de como montar, do zero,
> um ambiente AWS completo seguindo o **Well-Architected Framework** — organizada em
> subpastas por domínio, cada uma com seu próprio índice (`README.md`). O índice desta pasta
> é [`README.md`](README.md); comece por lá, depois desça para o domínio de interesse.

---

## Objetivo

Descrever, passo a passo, como sair de uma **conta AWS totalmente vazia** e chegar a uma
topologia **hub-and-spoke** oficial e segura, na qual:

1. Uma **conta AWS dedicada**, chamada **`network`** (Connectivity Account), concentra os
   recursos compartilhados de rede — Transit Gateway, VPNs de acesso, roteamento central.
   Ela hospeda o **Hub** da topologia.
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
| **Well-Architected** | Cada decisão é justificada contra os pilares AWS WAF (com foco em Security, Reliability, Operational Excellence e Cost). Referências REL/SEC/OPS citadas nos tópicos. **Conferir o ID contra a página oficial antes de citar** — nunca de memória: numeração e títulos mudam entre revisões do framework, e IDs errados já passaram batido em três tabelas. **O WAF nomeia zero contas e zero OUs** — nome de conta vem do AWS SRA, nome de OU vem do whitepaper *Organizing Your AWS Environment*; ver a tabela de hierarquia de fontes em `accounts/01-organizations-and-ous.md`. |
| **Composable by design** | Cada peça é uma abstração componível (Crossplane XR): Network, Cluster, DnsZone. Um recurso de alto nível compõe os de baixo; nada é monolítico. (Pilar 5 do "Platform Engineering 2.0".) |
| **Agnóstico ao ambiente** | O corpo da doc usa **placeholders** (`<hub-cidr>`, `<root-domain>`, `<asn>`) — ninguém precisa dos valores reais de uma organização específica para reusar a referência. |
| **Nunca alterar config compartilhada** | Só ADICIONAR recursos isolados. Regra herdada do PoC (ver [`CLAUDE.md`](../../CLAUDE.md)). |

## Vocabulário: "Hub" é topologia; `network` é conta

Distinção deliberada, e a fonte de confusão mais cara desta doc:

| Termo | O que é | Nunca é |
|---|---|---|
| **Hub** | Papel **topológico** — a VPC/TGW que concentra o tráfego. Par de *spoke*. Pode haver um Hub por região | Nome de conta |
| **`network`** | Nome da **conta AWS** (Connectivity Account), na OU `Infrastructure`. Hospeda o(s) Hub(s) | Nome de topologia |

`network` é o nome canônico em todas as referências AWS: o whitepaper *Organizing Your AWS
Environment Using Multiple Accounts* ("Network account"), o AWS SRA, e o Landing Zone
Accelerator (conta literalmente `Network`). A AWS **não** nomeia contas como "Hub".

Nos artefatos: `providerConfigName` = nome da **conta** (`network`, `wasp-nonprod`); nome de chart
Helm = **papel topológico** (`hub`, `spoke`). O chart `hub` provisiona na conta `network`.

## Como esta documentação é organizada

- **Uma subpasta por domínio.** Cada uma tem um `README.md` que indexa seus tópicos.
- **Tópicos são arquivos curtos e focados** — um assunto por arquivo, evoluível de forma
  independente.
- **Referência + mapa para Crossplane.** Cada domínio explica primeiro o *quê/porquê*
  (arquitetura Well-Architected), depois o *como* (que XRD/Composition materializa a peça,
  o que já existe no repo e o gap até o alvo).
- **Placeholders no corpo.** Convenção: `<algo-entre-angle-brackets>` é um valor que o
  adotante preenche com os dados da sua própria conta.
- **Nome de arquivo e H1 em inglês**; headings `##` e corpo na língua do projeto (pt-BR). Não
  repetir o nome da pasta no arquivo (`dns/05-security.md`, não `dns/05-dns-security.md`).

### Ao renomear um arquivo desta pasta

Varrer **todos os arquivos versionados**, não só `*.md`. Referências a caminhos de doc vivem
também em: texto de `--help` dos scripts em `accounts/scripts/`, comentários de YAML em
[`eks/resources/`](../eks/resources/), e campos `description` de XRD. Uma varredura restrita a `*.md` deixa esses
apontando para arquivo inexistente — já aconteceu, com 13 referências quebradas em 10 arquivos.

```bash
git ls-files | xargs grep -l '<nome-antigo>.md'   # sem filtro de extensão
```

Depois de qualquer `sed` amplo, conferir `git status` por arquivos tocados que ficaram **fora do
stage** — `git add` por caminho explícito já perdeu uma correção silenciosamente.

### Ao verificar uma citação nas docs da AWS

As páginas de whitepaper do `docs.aws.amazon.com` nem sempre têm um slug por seção: a OU
`Deployments`, por exemplo, mora em `advanced-ous.html`, não em `deployments-ou.html` (esse
retorna vazio). Descobrir o slug real pelo índice em vez de adivinhar:

```bash
curl -s https://docs.aws.amazon.com/whitepapers/latest/<guia>/toc-contents.json \
  | grep -oE '"[a-z0-9_-]+\.html"' | sort -u
```

## Relação com o resto do repo

- **Código Crossplane** (o que materializa esta arquitetura): [`eks/resources/`](../eks/resources/)
  (`network/`, `cluster/`, `argocd/`) e o chart faseado em [`eks/chart/`](../eks/chart/).
- **Contexto operacional AWS** (conta, IAM user do Crossplane, credenciais): [`CLAUDE.md`](../CLAUDE.md).
- **Design/brainstorm da decomposição** (Environment → Network + Cluster): [`docs/superpowers/`](../../docs/superpowers/).

## Fontes externas de referência

Trabalho de rede hub-and-spoke maduro (KCL/Crossplane), usado como base:

- Design consolidado AWS↔Azure: `<hub-repo>/docs/superpowers/specs/2026-05-26-hub-spoke-design.md`
- Landing Zone (visão de arquitetura): `<hub-repo>/docs/02-arquitetura/aws-landing-zone.md`
- Templates KCL: `<assets-repo>/crossplane/providers/aws/{hub_network,spoke_network,tgw,vpn_connection}/`
- AWS Well-Architected Framework — pilares e best practices ([REL02 — Plan your network topology](https://docs.aws.amazon.com/wellarchitected/latest/reliability-pillar/plan-your-network-topology.html), [SEC05 — Protecting networks](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/protecting-networks.html), etc.).
- **[SaaS Lens](https://docs.aws.amazon.com/wellarchitected/latest/saas-lens/saas-lens.html)** —
  lens oficial do Well-Architected para workloads SaaS multi-tenant (pub. 2023-04-04). Fonte
  primária do domínio `tenancy/`; complementa os pilares em vez de substituí-los.

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