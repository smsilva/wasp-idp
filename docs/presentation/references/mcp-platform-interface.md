# MCP as platform interface

Tese testada: o catálogo da plataforma (Backstage: Domain/System/Component/API/Resource, ownership, dependências) serve de contexto para agentes de IA via MCP — o mesmo catálogo serve ao portal (humano) e ao MCP (agente). Resultado: **confirmada por fonte primária** no Backstage upstream (o `catalog-backend` registra actions de leitura do catálogo que o `mcp-actions-backend` expõe como MCP tools) e, como vendor, em Port, Spotify Portal e Red Hat Developer Hub.

- Fonte (todas lidas em 2026-10-07):
  - Spec MCP, revisão corrente `2026-07-28` — overview: <https://modelcontextprotocol.io/specification/latest>
  - Spec MCP — versioning: <https://modelcontextprotocol.io/specification/versioning>
  - Spec MCP — Tools: <https://modelcontextprotocol.io/specification/2026-07-28/server/tools>
  - Spec MCP — Resources: <https://modelcontextprotocol.io/specification/2026-07-28/server/resources>
  - Spec MCP — Prompts: <https://modelcontextprotocol.io/specification/2026-07-28/server/prompts>
  - Spec MCP — Authorization: <https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization>
  - Spec MCP — Security Best Practices: <https://modelcontextprotocol.io/specification/2026-07-28/basic/security_best_practices>
  - Docs MCP — Local Server Security (tutorial oficial, não normativo): <https://modelcontextprotocol.io/docs/2026-07-28/tutorials/security/local-server-security>
  - Blog oficial do MCP, "MCP joins the Agentic AI Foundation" (2025-12-09): <https://blog.modelcontextprotocol.io/posts/2025-12-09-mcp-joins-agentic-ai-foundation/>
  - Press release da Linux Foundation sobre a AAIF: <https://www.linuxfoundation.org/press/linux-foundation-announces-the-formation-of-the-agentic-ai-foundation>
  - Anúncio da Anthropic (doação): <https://www.anthropic.com/news/donating-the-model-context-protocol-and-establishing-of-the-agentic-ai-foundation>
  - Backstage — MCP Actions Backend: <https://backstage.io/docs/ai/mcp-actions/>
  - Backstage — Actions Registry (alpha): <https://backstage.io/docs/backend-system/core-services/actions-registry/>
  - Backstage — release notes v1.40.0 (tag publicada em 2025-06-17): <https://backstage.io/docs/releases/v1.40.0/>
  - Backstage — código-fonte das actions do catálogo (repo da organização Backstage/CNCF): <https://github.com/backstage/backstage/tree/master/plugins/catalog-backend/src/actions>
  - **Vendor** — Spotify Portal for Backstage, MCP: <https://backstage.spotify.com/docs/portal/core-features-and-plugins/mcp/overview>
  - **Vendor** — Red Hat Developer Hub 1.8, MCP (artigo Red Hat Developer, 2025-11-10): <https://developers.redhat.com/articles/2025/11/10/mcp-red-hat-developer-hub-chat-your-catalog>
  - **Vendor** — Port MCP Server: <https://docs.port.io/agent-management/port-mcp-server/overview/>
  - **Vendor** — Humanitec MCP knowledge server: <https://developer.humanitec.com/platform-orchestrator/docs/integrations/mcp-knowledge-server/>
  - **Vendor** — Upbound Crossplane, Intelligent Control Planes: <https://docs.upbound.io/manuals/uxp/features/intelligent-control-planes>
  - **Projeto da comunidade Argo** — `argoproj-labs/mcp-for-argocd` (v0.9.0, 2026-08-11): <https://github.com/argoproj-labs/mcp-for-argocd>

## O que é o MCP (spec)

- Definição literal: "Model Context Protocol (MCP) is an open protocol that enables seamless integration between LLM applications and external data sources and tools." — <https://modelcontextprotocol.io/specification/latest>
- Arquitetura: "The protocol uses JSON-RPC 2.0 messages to establish communication between: Hosts: LLM applications that initiate connections; Clients: Connectors within the host application; Servers: Services that provide context and capabilities." — mesma URL.
- Analogia oficial com LSP: "In a similar way, MCP standardizes how to integrate additional context and tools into the ecosystem of AI applications." — mesma URL. Útil para a fala: assim como o LSP desacoplou editor de linguagem, o MCP desacopla agente de sistema.
- Versão: "The **current** protocol version is **2026-07-28**." Formato `YYYY-MM-DD`, "to indicate the last date backwards incompatible changes were made." — <https://modelcontextprotocol.io/specification/versioning>
- A revisão `2026-07-28` declara o protocolo stateless: "Stateless, self-contained requests" e "Per-request capability negotiation"; a negociação por handshake vale só para "`2025-11-25` and earlier". — overview e versioning acima.

## Primitivas do server: quem controla cada uma

- Lista literal: "Resources: Context and data, for the user or the AI model to use"; "Prompts: Templated messages and workflows for users"; "Tools: Functions for the AI model to execute". Do client para o server: "Elicitation: Server-initiated requests for additional information from users". — <https://modelcontextprotocol.io/specification/latest>
- Tools são "**model-controlled**, meaning that the language model can discover and invoke tools automatically based on its contextual understanding and the user's prompts." — <https://modelcontextprotocol.io/specification/2026-07-28/server/tools>
- Resources são "**application-driven**, with host applications determining how to incorporate context based on their needs" e servem para "share data that provides context to language models, such as files, database schemas, or application-specific information." — <https://modelcontextprotocol.io/specification/2026-07-28/server/resources>
- Prompts são "**user-controlled**, meaning they are exposed from servers to clients with the intention of the user being able to explicitly select them for use." — <https://modelcontextprotocol.io/specification/2026-07-28/server/prompts>
- Extensões opcionais na revisão corrente: Tasks ("Asynchronous execution of long-running operations"), Skills over MCP e MCP Apps ("Interactive UI elements ... rendered inline within conversations"). — <https://modelcontextprotocol.io/specification/latest>
- Leitura para a apresentação: o catálogo cabe naturalmente em **resources** (contexto, leitura) e as ações da plataforma em **tools** (execução). No Backstage, porém, *tudo* sai como tool (ver abaixo), inclusive leitura do catálogo.

## Governança: Linux Foundation / Agentic AI Foundation

- "Anthropic is donating MCP to the Agentic AI Foundation, a directed fund under the Linux Foundation." — blog oficial do MCP, 2025-12-09: <https://blog.modelcontextprotocol.io/posts/2025-12-09-mcp-joins-agentic-ai-foundation/>
- Governança técnica inalterada: "The people making decisions about the protocol are still the maintainers who have been stewarding it, guided by community input through our SEP process." — mesma URL.
- A AAIF nasceu com três projetos fundadores: MCP (Anthropic), goose (Block) e AGENTS.md (OpenAI). — <https://www.linuxfoundation.org/press/linux-foundation-announces-the-formation-of-the-agentic-ai-foundation>

## Backstage: catálogo exposto como MCP (upstream, não vendor)

- Mecanismo em duas peças. Actions Registry: "The Actions Registry Service is a core service designed to provide a distributed registry for actions that can be executed within Backstage backend plugins." Status **(alpha)**. — <https://backstage.io/docs/backend-system/core-services/actions-registry/>
- MCP Actions Backend: "The MCP Actions Backend exposes actions registered with the Actions Registry as MCP tools." Pacote `@backstage/plugin-mcp-actions-backend`; endpoint Streamable HTTP padrão `http://localhost:7007/api/mcp-actions/v1`; plugins expostos via `backend.actions.pluginSources` (ex.: `'catalog'`). — <https://backstage.io/docs/ai/mcp-actions/>
- Entrou na **v1.40.0** (tag de 2025-06-17): "A new `mcp-actions` backend plugin, which will surface these actions as tools as an MCP server. This can be used to expose plugin Actions with your favourite AI tools, such as Cursor, Claude or ChatGPT." Com o aviso: "it's currently highly experimental and could be subject to breaking changes in future releases." — <https://backstage.io/docs/releases/v1.40.0/>
- Actions que o próprio `catalog-backend` registra (código-fonte na `master`, conferido em 2026-10-07; última release Backstage v1.55.3, 2026-09-29): `get-catalog-entity`, `query-catalog-entities`, `get-catalog-model-description`, `register-entity`, `unregister-entity`, `refresh-catalog-entity`, `validate-entity`. — <https://github.com/backstage/backstage/tree/master/plugins/catalog-backend/src/actions>
  - `get-catalog-entity`: "This allows you to get a single entity from the software catalog. ... Each entity is identified by a unique entity reference, which is a string of the form "kind:namespace/name"." Atributos `readOnly: true`, `destructive: false`, `idempotent: true`.
  - `query-catalog-entities` documenta para o LLM consultas por relação de ownership: "Querying relations - find all entities owned by a specific group: `{ query: { "relations.ownedby": "group:default/team-alpha" } }`". **É a prova direta da tese**: ownership e relações do catálogo chegam ao agente como filtro de tool.
  - `get-catalog-model-description`: comentário no código — "Lets users fetch a markdown formatted description of the catalog model. This is useful for informing LLMs how to properly work with it." Descrição da tool: "Returns a markdown formatted description of the current catalog model, including all registered entity kinds, annotations, labels, tags, and relations."
- Controles: atributos `destructive`/`readOnly`/`idempotent` por action, e `visibilityPermission` que filtra a action da listagem e devolve 404 na invocação para quem não tem permissão — reaproveita o permission framework do portal. — <https://backstage.io/docs/backend-system/core-services/actions-registry/>
- Auth do MCP no Backstage: static token ("temporary workaround"), **CIMD** (recomendado, alinhado à spec) e DCR (deprecated). — <https://backstage.io/docs/ai/mcp-actions/>

## Outros produtos de plataforma com MCP (vendor)

- **Spotify Portal (vendor):** "Portal exposes its plugin capabilities as MCP (Model Context Protocol) tools that any compatible AI agent can discover and use." Plugins no diagrama: Catalog, Soundcheck, Scaffolder. — <https://backstage.spotify.com/docs/portal/core-features-and-plugins/mcp/overview>
- **Red Hat Developer Hub (vendor, distro Backstage):** "Starting in version 1.8, you can install plug-ins from the Extensions Marketplace that provide an MCP server in Developer Hub". Tools: `software-catalog-mcp-tool` e `techdocs-mcp-tool`. — <https://developers.redhat.com/articles/2025/11/10/mcp-red-hat-developer-hub-chat-your-catalog>
- **Port (vendor):** "The Port Model Context Protocol (MCP) Server acts as a bridge, enabling Large Language Models (LLMs) - like those powering Claude, Cursor, or GitHub Copilot - to interact directly with your Port.io developer portal." — <https://docs.port.io/agent-management/port-mcp-server/overview/>
- **Humanitec (vendor):** o MCP é de **conhecimento de produto**, não da plataforma do cliente — o assistente "does not have access to any data within your Orchestrator organization". Contraexemplo útil: nem todo "MCP de plataforma" expõe o estado da plataforma. — <https://developer.humanitec.com/platform-orchestrator/docs/integrations/mcp-knowledge-server/>
- **Upbound Crossplane (vendor):** "MCP servers, packaged as Add-Ons...install on your control plane. They deliver tools that the language model can use." Intelligent Control Planes "bring LLM-driven logic into your control plane's reconcile loop." Atenção: na doc da Upbound "MCP" também significa *managed control plane*. — <https://docs.upbound.io/manuals/uxp/features/intelligent-control-planes>
- **Argo CD (projeto `argoproj-labs`, comunidade Argo, doado pela Akuity):** "An implementation of Model Context Protocol (MCP) server for Argo CD." Tem modo `MCP_READ_ONLY` que desliga create/update/delete/sync. — <https://github.com/argoproj-labs/mcp-for-argocd>

## Riscos e auth (spec)

- Princípio de Tool Safety: "Tools represent arbitrary code execution and must be treated with appropriate caution." e "descriptions of tool behavior such as annotations should be considered untrusted, unless obtained from a trusted server." e "Hosts must obtain explicit user consent before invoking any tool". O protocolo admite o limite: "MCP itself cannot enforce these security principles at the protocol level". — <https://modelcontextprotocol.io/specification/latest>
- Human in the loop: "For trust & safety and security, there **SHOULD** always be a human in the loop with the ability to deny tool invocations." Servers "**MUST**: Validate all tool inputs; Implement proper access controls; Rate limit tool invocations; Sanitize tool outputs". — <https://modelcontextprotocol.io/specification/2026-07-28/server/tools>
- Tool poisoning, prompt injection e rug pull (tutorial oficial, não normativo): "Tool names and descriptions are instructions your model reads. A server can hide directives in them that steer the agent — including how it uses *other* servers' tools — without the poisoned tool ever being invoked (often called tool poisoning, or tool shadowing when it targets another server's tools)." e "a server can quietly change them after you approved it (a rug pull)". Também: "Prompt injection in untrusted content can steer an honest server into the same overreach". E o princípio: "no check proves what a server will do." — <https://modelcontextprotocol.io/docs/2026-07-28/tutorials/security/local-server-security>
- Auth na spec: "Authorization is **OPTIONAL** for MCP implementations." Quando existe, é baseada em "OAuth 2.1 IETF DRAFT (draft-ietf-oauth-v2-1-13)" + RFC 8414, RFC 7591, RFC 8707, RFC 9728, RFC 9207, CIMD. "A protected *MCP server* acts as an OAuth 2.1 resource server". "MCP servers **MUST** implement OAuth 2.0 Protected Resource Metadata (RFC9728)." DCR "is deprecated" em favor de Client ID Metadata Documents. — <https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization>
- Audience binding: "MCP servers **MUST** validate that access tokens were issued specifically for them as the intended audience" e "MCP servers **MUST NOT** accept or transit any other tokens." — mesma URL.
- Security Best Practices lista: Confused Deputy, Token Passthrough ("explicitly forbidden"), SSRF, State Handle Hijacking, Local MCP Server Compromise, OAuth Authorization URL Validation, stdio em proxy, Mix-Up, Localhost Redirect URI Impersonation, CIMD Trust Policies, Scope Minimization ("Poor scope design increases token compromise impact, elevates user friction, and obscures audit trails."). A página normativa **não** trata prompt injection/tool poisoning — esses ficam no tutorial de local server. — <https://modelcontextprotocol.io/specification/2026-07-28/basic/security_best_practices>

## Não verificado

- Números de adoção do MCP no primeiro ano (ex.: "97 million monthly SDK downloads", "10,000 active servers") apareceram em resumo de busca atribuído ao anúncio da AAIF; a frase literal não foi conferida na página da Linux Foundation/Anthropic. Não usar no slide sem reler.
- Membros apoiadores da AAIF além dos três fundadores (Google, Microsoft, AWS, Cloudflare, Bloomberg) — só via resumo de busca.
- Status de maturidade atual do `mcp-actions-backend` (o "highly experimental" é da v1.40.0; o pacote segue em `0.x`, `0.2.3-next.1` no `package.json` da `master`). Não foi localizada declaração de GA.
- Spotify Portal: status beta/GA do MCP não declarado na página.
- Red Hat Developer Hub: se os plugins MCP são Tech/Developer Preview — o artigo não diz; a doc de produto da Red Hat não foi lida.
- Port: lista exata de tools e o modelo de permissões ("runs with the signed-in user's permissions") vieram de resumo de busca; a página lida não traz o texto literal.
- Kubernetes MCP: existe `containers/kubernetes-mcp-server` ("Model Context Protocol (MCP) server for Kubernetes and OpenShift"), mas não foi localizada doc oficial do projeto Kubernetes adotando um MCP server; não citar como "oficial do Kubernetes".
- Crossplane upstream (não Upbound): não foi localizada doc oficial de MCP server no crossplane.io.

## Uso na apresentação

- slide candidato `catalog-as-context` (catálogo → portal para humano, MCP para agente): a prova é o `query-catalog-entities` do Backstage upstream filtrando por `relations.ownedby`, mais o `get-catalog-model-description` feito explicitamente "for informing LLMs". Mensagem: um catálogo, dois consumidores; o permission framework do portal (`visibilityPermission`) é o mesmo que filtra as tools do agente.
- ligação com `many-clients` (CLI + MCP já citado via formae): a CLI do Backstage (`catalog` module) e o MCP consomem as mesmas actions do Actions Registry — mesma superfície, clientes diferentes.
- ligação com `agent-identity` (auth do MCP): MCP server = OAuth 2.1 resource server, audience binding obrigatório, token passthrough proibido, CIMD no lugar de DCR — o Backstage já segue (CIMD recomendado, DCR deprecated).
- nota de risco para o slide (frase nas notas, não na tela): descrição de tool é instrução que o modelo lê — tool poisoning/rug pull; por isso o catálogo exposto deve ser read-only por padrão (`readOnly: true`) e ações destrutivas passam por human in the loop.
- contraexemplo opcional: Humanitec expõe MCP só de documentação — "ter MCP" não implica expor o estado da plataforma.
