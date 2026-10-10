# The platform engineering illusion

- Fonte: David Iyanu Jonathan, "The Platform Engineering Illusion: Why Most Internal Developer Platforms Fail Before Developers Ever Use Them", platformengineering.com, 2026-07-31. <https://platformengineering.com/features/the-platform-engineering-illusion-why-most-internal-developer-platforms-fail-before-developers-ever-use-them/>
- platformengineering.**com** é do Techstrong Group (o mesmo do "Nobody owns the data", `data-ownership.md`); não confundir com platformengineering.**org** (comunidade ligada à Humanitec, fonte do `empathy-gap.md`).
- **Artigo de opinião, sem dado com fonte.** Os números (14 meses, adoção abaixo de 20%, 43 serviços com 12 desatualizados, três times desfeitos em 18 meses) são observação pessoal do autor: citar como "um relato", nunca como tendência, e nunca na tela.

## Tese

IDPs falham porque a organização trata platform engineering como **iniciativa de ferramentas**, quando ela é, estruturalmente, uma **disciplina de produto**, com os mecanismos de prestação de contas que produto tem (pesquisa com usuário, retenção, churn) e que a maioria dos times de plataforma nunca instala.

## Citações (literais)

- "the team built a platform the way you build a bridge, and developers experienced it the way you experience a toll booth."
- "the platform was correct and nobody wanted it."
- "Why would a developer, mid-deadline, exhausted, half paying attention, choose your paved road over the goat trail they already know?"
- "A technology platform is infrastructure with an API. A developer platform is a product with users, and users have preferences, workarounds, trust thresholds, and memory of every time the tool embarrassed them in front of their team."
- Sobre a pilha Backstage + Kubernetes + Terraform + Crossplane + Argo CD: "Every one of those tools is legitimate. None of them, combined, constitutes a platform, any more than a stack of good ingredients constitutes a meal."
- "you build it, you run it, you secure it, you monitor it, you cost-optimize it, and you keep current on eleven CVE feeds."
- "reduce unnecessary complexity while preserving necessary complexity — not to eliminate complexity, which is impossible, and not to hide it so thoroughly that debugging becomes archaeology."
- "Developers don't experience your architecture. They experience the fifteen minutes." (fila de CI de 15 minutos que ninguém do time de plataforma assumia)
- "mandated usage generates resentment rather than advocacy, and resentment metastasizes into shadow infrastructure"
- "A platform that adds security friction after launch teaches developers that the platform is where good ideas go to get slower"
- "the best platform teams I've worked with measure themselves partly by what they refuse to expose to developers"
- "every manual step in a 'self-service' system is really just a support queue wearing a costume."
- "infrastructure outputs are the platform team congratulating itself."
- Sobre IA: "adoption was never a tooling problem to begin with — it was a trust and design problem, and trust doesn't move faster because the tool generating the config got smarter." E sobre Kubernetes e a complexidade de operação: "It didn't. It relocated it."

## Cinco modos de falha

1. **Construir para a infraestrutura, não para o dev:** mede uptime e velocidade de provisionamento; nunca acompanha um deploy real.
2. **Sem mentalidade de produto:** sem dono, o roadmap vira "a list of things a VP saw at KubeCon".
3. **Métricas erradas:** número de clusters, deployment frequency isolada, CPU.
4. **Adoção por mandato, não por confiança conquistada:** o uso sobe, e com ele a shadow infrastructure.
5. **Governança chega depois da festa:** segurança entra no fim, vira obstrução e é remendada piorando a experiência.

## Métricas que o autor propõe

- Time-to-first-deploy de quem acabou de chegar.
- Carga cognitiva autodeclarada (pesquisa com o dev).
- Razão entre deploys pelo golden path e pelo escape hatch.
- **Taxa de bypass:** quantas vezes o dev contorna a plataforma — "the platform's real adoption curve", quase nunca no dashboard mostrado à liderança.
- Resultado de negócio: lead time, taxa de incidentes, velocidade de onboarding.

## O que as plataformas que sobrevivem têm em comum

- Produto com **dono nomeado que pode dizer não**.
- Foco em **reduzir carga cognitiva**, não em adicionar capacidade.
- **Golden paths opinativos com escape hatch**, não configurabilidade infinita ("a tax paid in decision fatigue").
- **Self-service de verdade:** sem mensagem no Slack e espera.
- Feedback contínuo, com a mudança **visível** para quem reclamou.
- Documentação **antes** do lançamento.
- Segurança **na fase de design**, não na de auditoria: policy-as-code, segurança no template, guardrail que previne em vez de só detectar.
- Começar pela **menor plataforma que resolve um problema real e nomeado**; automatizar o fluxo repetitivo que gera ticket, não o que rende palestra.

## Uso na apresentação

Reforça teses que já estão no deck com uma segunda voz, e acrescenta três ideias novas: **taxa de bypass**, **pilha de ferramentas ≠ plataforma** (a pilha citada é a nossa) e **segurança no design**.

| Slide | Uso |
|---|---|
| `empathy-gap` | Segunda voz da mesma tese: "the platform was correct and nobody wanted it"; ponte vs. pedágio |
| `cognitive-load` | Expansão do "you build it, you run it"; absorver a complexidade **desnecessária** e preservar a necessária |
| `platform-as-product` | "infrastructure with an API" vs. "product with users"; o passo manual como "support queue wearing a costume" |
| `golden-paths` | A pergunta do dev cansado no meio do prazo (paved road vs. goat trail); mandato gera shadow infrastructure (fonte independente da Syntasso) |
| `catalog-ownership` | 43 serviços, 12 desatualizados: catálogo sem dono vira lista morta (relato) |
| `score-what-not` | Bons times se medem pelo que **se recusam** a expor ao dev |
| `platform-amplifier` | IA não resolve adoção: o problema é confiança e design |
| `platform-as-product-signals` | **Taxa de bypass** como item novo; feedback com mudança visível |
| `guardrails` | Segurança na fase de design |
| `reference-architecture` | Ressalva: a pilha desenhada (Backstage, Crossplane, Argo CD) é ingrediente, não plataforma |
| `mvp1` | Menor plataforma que resolve um problema real e nomeado (Claude Code com custo sob gestão) |
| `ask` | Times piloto e adoção conquistada, não mandato |
