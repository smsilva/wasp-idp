# Agent evals and validation loops

Fundamento para a afirmação do *State of AI in Platform Engineering Vol. 2* (p. 29-30) de que, em paths probabilísticos, "Evals become the test suite", e para a recomendação de validation loops e gates determinísticos em efeitos irreversíveis (ver `state-of-ai-in-platform-engineering.md`).

- Fonte (todas lidas em 2026-10-07):
  - Anthropic (vendor), "Demystifying evals for AI agents", 2026-01-09: <https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents>
  - Anthropic (vendor), "Building effective agents", 2024-12-19: <https://www.anthropic.com/engineering/building-effective-agents>
  - Anthropic (vendor), "Writing effective tools for agents — with agents", 2025-09-11: <https://www.anthropic.com/engineering/writing-tools-for-agents>
  - Anthropic (vendor), doc do Claude Code, "Best practices" (sem data na página): <https://code.claude.com/docs/en/best-practices>
  - OpenAI (vendor), "A practical guide to building agents" (PDF, abril de 2025): <https://cdn.openai.com/business-guides-and-resources/a-practical-guide-to-building-agents.pdf>
  - SWE-bench (benchmark acadêmico, Princeton): <https://www.swebench.com/original.html>; paper <https://arxiv.org/abs/2310.06770>
  - HashiCorp (vendor, doc oficial), `terraform plan`: <https://developer.hashicorp.com/terraform/cli/commands/plan>
  - Kubernetes (doc oficial), "API Concepts": <https://kubernetes.io/docs/reference/using-api/api-concepts/>
  - Crossplane (doc oficial), CLI command reference: <https://docs.crossplane.io/latest/cli/command-reference/>
  - Open Policy Agent (doc oficial), "Terraform": <https://www.openpolicyagent.org/docs/terraform>
  - Kyverno (doc oficial), "Validate Rules": <https://kyverno.io/docs/policy-types/cluster-policy/validate/>

## (a) Evals como suíte de teste de agentes

- Evals dão regressão de graça: "Once evals exist, you get baselines and regression tests for free: latency, token usage, cost per task, and error rates can be tracked on a static bank of tasks." (<https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents>)
- Regression eval é suíte de regressão no sentido clássico: "Regression evals ask, “Does the agent still handle all the tasks it used to?” and should have a nearly 100% pass rate. They protect against backsliding, as a decline in score signals that something is broken and needs to be improved." (mesma URL)
- Capability eval vira regression suite: "After an agent is launched and optimized, capability evals with high pass rates can “graduate” to become a regression suite that is run continuously to catch any drift." (mesma URL)
- O que se avalia é o estado final, não a fala do agente: "A flight-booking agent might say “Your flight has been booked” at the end of the transcript, but the outcome is whether a reservation exists in the environment’s SQL database." (mesma URL) — análogo direto de infra: o agente dizer "cluster criado" não vale; vale o recurso existir e o echo responder 200.
- Grader determinístico para agente de código: "Deterministic graders are natural for coding agents because software is generally straightforward to evaluate: does the code run and do the tests pass? Two widely used coding agent benchmarks, SWE-bench Verified and Terminal-Bench, follow this approach." (mesma URL)
- Cada tarefa de eval precisa de verificação: "Each evaluation prompt should be paired with a verifiable response or outcome." (<https://www.anthropic.com/engineering/writing-tools-for-agents>)
- OpenAI põe evals como primeiro princípio para escolher modelo: "Set up evals to establish a performance baseline" (PDF da OpenAI, seção sobre seleção de modelos).

### SWE-bench: testes reais como verificação

- Definição do benchmark original: "Without the Pull Request's changes, a number of test(s) fail. After the Pull Request is merged, the same set of test(s) pass. These "Fail-to-Pass" tests are the primary signal for evaluation." (<https://www.swebench.com/original.html>)
- Como roda: "Per task instance, an AI system is given the issue text. The AI system should then modify the codebase in order to resolve the described issues. When the AI system is finished, we run the aforementioned Fail-to-Pass tests to check if the issue was successfully resolved." (mesma URL)
- Versão Verified, descrita pela Anthropic: "SWE-bench Verified gives agents GitHub issues from popular Python repositories and grades solutions by running the test suite; a solution passes only if it fixes the failing tests without breaking existing ones." (<https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents>)

## (b) Validation loop: feedback determinístico devolvido ao agente

- Ground truth a cada passo: "During execution, it's crucial for the agents to gain “ground truth” from the environment at each step (such as tool call results or code execution) to assess its progress." (<https://www.anthropic.com/engineering/building-effective-agents>)
- Por que agentes de código funcionam: "Code solutions are verifiable through automated tests; Agents can iterate on solutions using test results as feedback; The problem space is well-defined and structured; and Output quality can be measured objectively." (mesma URL)
- O loop fechado, nas palavras da doc do Claude Code: "Claude stops when the work looks done. Without a check it can run, "looks done" is the only signal available, and you become the verification loop: every mistake waits for you to notice it. Give Claude something that produces a pass or fail, and the loop closes on its own. Claude does the work, runs the check, reads the result, and iterates until the check passes." (<https://code.claude.com/docs/en/best-practices>)
- O que conta como check: "The check is anything that returns a signal Claude can read in the conversation: a test suite, a build exit code, a linter, a script that diffs output against a fixture, or a browser screenshot compared against a design." (mesma URL)
- A falha tem de voltar com o motivo, não como código opaco: "if a tool call raises an error (for example, during input validation), you can prompt-engineer your error responses to clearly communicate specific and actionable improvements, rather than opaque error codes or tracebacks." (<https://www.anthropic.com/engineering/writing-tools-for-agents>) — é exatamente o "a falha volta ao agente com o motivo" do relatório.
- Limite do loop: "it's also common to include stopping conditions (such as a maximum number of iterations) to maintain control." (<https://www.anthropic.com/engineering/building-effective-agents>); a OpenAI chama de "Exceeding failure thresholds: Set limits on agent retries or actions. If the agent exceeds these limits (e.g., fails to understand customer intent after multiple attempts), escalate to human intervention." (PDF da OpenAI)

### Checks determinísticos de plataforma/IaC que servem de feedback

- Kubernetes rejeita campo desconhecido com mensagem que lista o erro: "`Strict`: The API server rejects the request with a 400 Bad Request error when it detects any unknown or duplicate fields. The response message from the API server specifies all the unknown or duplicate fields that the API server has detected." E: "The default validation setting for kubectl is `--validate=true`, which means strict server-side field validation." (<https://kubernetes.io/docs/reference/using-api/api-concepts/>)
- Dry-run no servidor roda toda a validação sem persistir: "When you set `?dryRun=All`, any relevant admission controllers are run, validating admission controllers check the request post-mutation, merge is performed on `PATCH`, fields are defaulted, and schema validation occurs. The changes are not persisted to the underlying storage, but the final object which would have been persisted is still returned to the user, along with the normal status code." (mesma URL)
- Crossplane valida offline contra XRDs: "The resource validate command validates the provided Crossplane resources against the schemas of the provided extensions (XRDs, CRDs, Providers, Functions, and Configurations)." e "All validation happens offline using the Kubernetes API server’s validation library, without requiring a Crossplane instance or control plane." (<https://docs.crossplane.io/latest/cli/command-reference/>, comando beta)
- Crossplane mostra o que a Composition faria antes de aplicar: o `composition render` "runs the Crossplane render engine (either in a Docker container or via a local binary) to produce high-fidelity output that matches what the real reconciler would produce." (mesma URL)
- Kyverno como gate de admissão: com `failureAction: Enforce`, "resource creation or updates are blocked when the resource does not comply"; com `Audit`, a violação é registrada "but the resource creation or update is allowed." (<https://kyverno.io/docs/policy-types/cluster-policy/validate/>)

## (c) Guardrails determinísticos em ações irreversíveis

- OpenAI, risco por tool (inclui reversibilidade): "Assess the risk of each tool available to your agent by assigning a rating—low, medium, or high—based on factors like read-only vs. write access, reversibility, required account permissions, and financial impact. Use these risk ratings to trigger automated actions, such as pausing for guardrail checks before executing high-risk functions or escalating to a human if needed." (PDF da OpenAI, "Tool safeguards")
- OpenAI, humano em ação irreversível: "High-risk actions: Actions that are sensitive, irreversible, or have high stakes should trigger human oversight until confidence in the agent’s reliability grows. Examples include canceling user orders, authorizing large refunds, or making payments." (PDF da OpenAI)
- OpenAI, guardrail em camadas e regras determinísticas: "Think of guardrails as a layered defense mechanism. While a single one is unlikely to provide sufficient protection, using multiple, specialized guardrails together creates more resilient agents." e "Rules-based protections: Simple deterministic measures (blocklists, input length limits, regex filters) to prevent known threats like prohibited terms or SQL injections." (PDF da OpenAI)
- Anthropic: "We recommend extensive testing in sandboxed environments, along with the appropriate guardrails." (<https://www.anthropic.com/engineering/building-effective-agents>)
- Terraform plan como preview antes do apply: "The `terraform plan` command creates an execution plan, which lets you preview the changes that Terraform plans to make to your infrastructure." O `-detailed-exitcode` dá sinal binário para automação: "0 = Succeeded with empty diff (no changes)", "1 = Error", "2 = Succeeded with non-empty diff (changes present)". (<https://developer.hashicorp.com/terraform/cli/commands/plan>, conferido via renderização da página)
- OPA sobre o plan: "OPA makes it possible to write policies that check the changes Terraform is about to make before it makes them." Exemplo de regra da doc: "Authorization holds if score for the plan is acceptable and no changes are made to IAM". Benefício citado: "Giving individual developers a first pass review of their Terraform changes". (<https://www.openpolicyagent.org/docs/terraform>)

## Não verificado

- O número exato da página das citações do PDF da OpenAI (o texto foi extraído com `pdftotext`; "Tool safeguards" e "Rules-based protections" aparecem na p. 25-26, "High-risk actions" no fim do documento). Conferir no PDF antes de pôr página na tela.
- OpenAI "Evals guide" da plataforma (<https://platform.openai.com/docs/guides/evals>) não foi lido nesta sessão.
- A frase "Evals become the test suite" é do relatório da platformengineering.org (ver `state-of-ai-in-platform-engineering.md`); nenhuma fonte primária de vendor usa essa frase literal. Anthropic diz o equivalente ("regression suite", "regression tests for free").
- Nenhuma fonte primária lida trata especificamente de **mudança gerada por agente** passando por Terraform plan/OPA/Kyverno; a ligação "gate de IaC = gate de agente" é inferência nossa a partir de docs que tratam de mudança em geral.
- Não foi verificada a frase literal "The `plan` command alone does not actually carry out the proposed changes" (resumo do WebFetch, não confirmada no texto bruto).
- Posts do Medium/blogs secundários não foram consultados (403 e fora do critério de fonte primária).

## Uso na apresentação

- Slide de paths deterministic / probabilistic / hybrid: no path probabilístico, a eval é a suíte de teste (Anthropic: regression evals "should have a nearly 100% pass rate"); no hybrid, o agente gera e o gate determinístico decide.
- Exemplo da PoC, gate determinístico: o XRD do Crossplane rejeita campo desconhecido (`unknown field`) — o claim com o `domain.parentZoneId` removido falha alto no API server. É o `Strict` field validation do Kubernetes aplicado ao XRD, e a mensagem de erro que lista o campo é o feedback que volta ao agente no validation loop.
- Exemplo da PoC, gate em efeito irreversível: `aws/eks/scripts/decommission-environment` exige `--yes-destroy` (e oferece `--dry-run`, análogo ao `terraform plan`). Corresponde ao "High-risk actions ... should trigger human oversight" da OpenAI; a flag é a confirmação explícita, não o agente decidindo sozinho.
- Ligação com `fitness-functions.md`: a fitness function é o check determinístico que devolve pass/fail; dentro do validation loop ela vira o feedback que o agente lê até passar ("iterates until the check passes"). O echo HTTP 200 nos dois IPs do NLB é o "outcome" no sentido da Anthropic (o estado final no ambiente, não o que o agente diz).
- Mensagem de uma linha para o slide: "Agente propõe, check determinístico decide; irreversível pede confirmação."
