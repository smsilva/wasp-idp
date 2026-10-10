# AGENTS.md

Contexto declarado ao lado do código para agentes, no mesmo papel que o `catalog-info.yaml` cumpre para humanos e portal. Cobre o `AGENTS.md` (padrão aberto), o `CLAUDE.md` (equivalente do Claude Code) e as Agent Skills (padrão aberto de capacidades empacotadas), mais os estudos que medem o efeito desses arquivos.

## Fontes

Todas lidas em 2026-10-07.

- Site oficial do padrão: <https://agents.md/> (mantido pela Agentic AI Foundation; origem OpenAI e outros vendors).
- Linux Foundation, press release de 2025-12-09: <https://www.linuxfoundation.org/press/linux-foundation-announces-the-formation-of-the-agentic-ai-foundation> (fundação neutra).
- Anthropic, doc oficial do Claude Code "How Claude remembers your project": <https://code.claude.com/docs/en/memory> (vendor: Anthropic).
- Agent Skills, site do padrão: <https://agentskills.io/> (originado pela Anthropic).
- Anthropic, engineering blog "Equipping agents for the real world with Agent Skills", 2025-10-16, com nota de atualização de 2025-12-18: <https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills> (vendor: Anthropic).
- Anthropic, "Introducing Agent Skills", 2025-10-16: <https://claude.com/blog/skills> (vendor: Anthropic).
- Gloaguen et al. (ETH Zurich / LogicStar.ai), arXiv:2602.11988, v1 2026-02-12, v3 2026-09-29: <https://arxiv.org/abs/2602.11988> (acadêmico, independente de vendor).
- Lulla et al., arXiv:2601.20404, v1 2026-01-28, v2 2026-03-30: <https://arxiv.org/abs/2601.20404> (acadêmico).
- Khatri, arXiv:2607.27250, 2026-07-28: <https://arxiv.org/abs/2607.27250> (acadêmico, autor único).
- Post da OpenAI sobre a AAIF (<https://openai.com/index/agentic-ai-foundation/>): **não lido**, 403.

## AGENTS.md: o que é

- Definição literal: "a simple, open format for guiding coding agents", "a dedicated, predictable place to provide the context and instructions to help AI coding agents work on your project" (<https://agents.md/>).
- Na voz da Linux Foundation: "a simple, universal standard that gives AI coding agents a consistent source of project-specific guidance needed to operate reliably across different repositories and toolchains" (press release da LF).
- Origem: lançado pela OpenAI em agosto de 2025 (press release da LF). O site credita a criação conjunta a OpenAI Codex, Amp, Jules (Google), Cursor e Factory.
- Governança: "AGENTS.md is now stewarded by the Agentic AI Foundation under the Linux Foundation" (<https://agents.md/>). A AAIF foi anunciada em 2025-12-09 com três projetos fundadores: MCP (Anthropic), goose (Block) e AGENTS.md (OpenAI) (press release da LF).
- Adoção: "used by over 60k open-source projects" (<https://agents.md/>); a LF diz "more than 60,000 open source projects and agent frameworks" (dezembro de 2025). O site lista mais de 25 ferramentas compatíveis, entre elas GitHub Copilot, VS Code, Cursor, Zed, Jules, Gemini CLI, Codex, Aider, Devin, Junie e Warp.
- Mesmo guarda-chuva do MCP: o press release descreve o MCP como "the universal standard protocol for connecting AI models to tools, data and applications", com mais de 10.000 servers publicados. AGENTS.md (contexto estático no repo) e MCP (contexto dinâmico via tools) estão sob a mesma fundação.

## AGENTS.md: estrutura recomendada

- Seções sugeridas pelo site: project overview, build and test commands, code style guidelines, testing instructions, security considerations, commit message or pull request guidelines (<https://agents.md/>).
- Monorepo: "For large monorepos, use nested AGENTS.md files for subprojects. Agents automatically read the nearest file in the directory tree, so the closest one takes precedence." O exemplo citado é o repositório da OpenAI, com 88 arquivos `AGENTS.md` (<https://agents.md/>).
- É Markdown livre, sem schema: diferente do `catalog-info.yaml`, não existe campo obrigatório nem validação.

## CLAUDE.md (Claude Code)

- Definição: "CLAUDE.md files are markdown files that give Claude persistent instructions for a project, your personal workflow, or your entire organization." (<https://code.claude.com/docs/en/memory>).
- Hierarquia, da mais ampla para a mais específica: **Managed policy** (`/etc/claude-code/CLAUDE.md` no Linux; "Organization-wide instructions managed by IT/DevOps"), **User** (`~/.claude/CLAUDE.md`), **Project** (`./CLAUDE.md` ou `./.claude/CLAUDE.md`; "Team-shared instructions for the project", compartilhado via source control) e **Local** (`./CLAUDE.local.md`, pessoal, no `.gitignore`).
- Carga: arquivos nos diretórios acima do working directory carregam no início; os de subdiretórios carregam sob demanda. "All discovered files are concatenated into context rather than overriding each other." Diferente da regra "nearest wins" do AGENTS.md.
- Compatibilidade com AGENTS.md: "Claude Code can read `AGENTS.md` as your project instructions, so a repository already set up for other coding agents works without adding a `CLAUDE.md`". Se houver os dois, por default lê só o `CLAUDE.md`; o `CLAUDE.md` pode importar o `AGENTS.md` com `@AGENTS.md`.
- Orientação de tamanho: "target under 200 lines per CLAUDE.md file. Longer files consume more context and reduce adherence."
- Não é enforcement: "Claude treats them as context, not enforced configuration. To block an action regardless of what Claude decides, use a PreToolUse hook instead."
- O que entra: "Treat CLAUDE.md as the place you write down what you'd otherwise re-explain"; procedimentos de vários passos vão para skill ou rule com escopo de path.

## Agent Skills

- Definição do padrão: "Agent Skills are a lightweight, open format for extending AI agent capabilities with specialized knowledge and workflows." "At its core, a skill is a folder containing a `SKILL.md` file", com metadados (`name` e `description`, no mínimo), instruções e, opcionalmente, `scripts/`, `references/` e `assets/` (<https://agentskills.io/>).
- Definição da Anthropic: "Organized folders of instructions, scripts, and resources that agents can discover and load dynamically to perform better at specific tasks" (engineering blog, 2025-10-16).
- Progressive disclosure em três estágios: discovery (só nome e descrição na inicialização), activation (lê o `SKILL.md` quando a tarefa casa com a descrição), execution (scripts e arquivos sob demanda). "Full instructions load only when a task calls for them, so agents can keep many skills on hand with only a small context footprint." (<https://agentskills.io/>).
- Datas: lançadas pela Anthropic em 2025-10-16; publicadas como padrão aberto em 2025-12-18 ("We've published Agent Skills as an open standard for cross-platform portability. (December 18, 2025)", nota no engineering blog). O site do padrão diz: "originally developed by Anthropic, released as an open standard".
- Argumento de plataforma: skills empacotam "procedural knowledge and company-, team-, and user-specific context into portable, version-controlled folders" (<https://agentskills.io/>). A vitrine de clients lista, entre outros, Claude Code, ChatGPT & Codex, GitHub Copilot, VS Code, Cursor, Gemini CLI, Junie, Kiro, Goose e Pulumi Neo.
- Diferente da AGENTS.md, as Agent Skills **não** aparecem como projeto da AAIF nas fontes lidas.

## Efeito na qualidade do agente (estudos)

Três papers no arXiv, com conclusões que não batem entre si. Nenhum mostra aumento de taxa de sucesso.

- **Gloaguen et al., arXiv:2602.11988** (SWE-bench com context files gerados por LLM e um dataset novo, AGENTbench, com context files escritos por devs): "providing context files does not generally improve task success rates, while increasing inference cost by over 20% on average". Os agentes seguem as instruções, mas "repository overviews", embora amplamente recomendadas, não ajudaram. Conclusão dos autores: context files servem para práticas de código fora do padrão; qualquer tentativa de ganho deve ser avaliada antes de ir para produção.
- **Lulla et al., arXiv:2601.20404** (Codex, 10 repositórios, 124 PRs, com e sem AGENTS.md): "the presence of AGENTS.md is associated with a lower median runtime (Δ28.64%) and reduced output token consumption (Δ16.58%), while maintaining a comparable task completion behavior". Mede eficiência, não acerto.
- **Khatri, arXiv:2607.27250** (Claude Code e Codex, 17 tarefas, 3 repositórios, 288 runs): "Context strategy does not measurably move correctness on either agent (bounded to <=10-15pp via equivalence testing)". Os agentes falham por "implementation skill" (design, escolha de padrão, ligação exata), não por "missing repository knowledge that a context file could supply". Amostra pequena, um autor só.
- Leitura conjunta: o arquivo **muda o comportamento** (o agente segue as instruções) e pode reduzir custo/tempo, mas não substitui capacidade. Vale para convenção não óbvia e comandos do projeto, não para overview genérico. Isso combina com a orientação da Anthropic de manter o `CLAUDE.md` curto.

## Não verificado

- Data exata de lançamento do AGENTS.md (a LF diz só "August 2025").
- Contagem atual de adoção além dos "over 60k" do site, que não traz data. Não há fonte primária para número mais recente.
- Texto do post da OpenAI sobre a AAIF (403).
- Que o v1 de 2602.11988 dizia que context files "tend to reduce" a taxa de sucesso: veio de resumo de busca, não do texto do v1. Citar só o abstract atual (v3).
- Que o desenho do 2602.11988 é enviesado para Python: crítica de um blog secundário (ArXivIQ), não dos autores.
- Entrada do A2A (Google) na AAIF em agosto de 2026 e contagem de membros da AAIF: só fontes secundárias (Forbes e outros).
- Se Agent Skills foram doadas a alguma fundação: nada nas fontes lidas.

## Uso na apresentação

- Paralelo direto com o slide `declare-next-to-code` (`catalog-info.yaml`): o mesmo repo declara **o que a app é** para humanos e portal (`catalog-info.yaml`) e **como trabalhar nela** para agentes (`AGENTS.md`/`CLAUDE.md`). Ambos são versionados e revisados em PR junto do código. Diferença a citar: o catálogo tem schema e o portal valida; o `AGENTS.md` é Markdown livre.
- Golden path gera o contexto do agente: o template que cria o repo já cria `catalog-info.yaml` **e** `AGENTS.md` com comandos de build/test, convenções e guardrails da plataforma. As skills da plataforma (ex.: "provisionar Environment", "registrar rota") são distribuídas como Agent Skills, no papel dos templates do portal.
- A hierarquia do `CLAUDE.md` mapeia na divisão de responsabilidade: managed policy = plataforma/segurança, project = time dono da app, local = dev. A plataforma é dona da camada org-wide.
- "Catálogo como contexto": o arquivo é estático; o MCP (mesma fundação, AAIF) é o canal dinâmico pelo qual o agente consulta o catálogo, o ownership e o estado vivo. Arquivo diz *como*, MCP responde *o quê, agora*.
- Ressalva honesta para a nota do slide: os estudos não mostram ganho de acerto (Gloaguen: custo +20%; Khatri: sem efeito mensurável); o ganho medido é de eficiência (Lulla: -28,64% de runtime mediano). Mensagem: conteúdo curto e específico (comandos, convenções não óbvias), não overview do repo. Isso reforça gerar pelo golden path em vez de deixar cada time escrever um texto longo.
