# Four golden signals

- Fonte: *Site Reliability Engineering* (Google), cap. 6 "Monitoring Distributed Systems", escrito por Rob Ewaschuk, editado por Betsy Beyer. <https://sre.google/sre-book/monitoring-distributed-systems/>

## Os quatro sinais

- "The four golden signals of monitoring are latency, traffic, errors, and saturation."
- **Latency:** "The time it takes to service a request" — separar a latência das requisições bem-sucedidas da das que falharam (um erro rápido distorce a média).
- **Traffic:** a demanda sobre o sistema, medida de forma adequada a cada tipo de sistema (ex.: requisições HTTP por segundo).
- **Errors:** "The rate of requests that fail, either explicitly (e.g., HTTP 500s), implicitly … or by policy".
- **Saturation:** o quão "cheio" o sistema está, nos recursos mais restritos.
- "If you measure all four golden signals and page a human when one signal is problematic … your service will be at least decently covered."

## Sintoma vs. causa

- Sintoma = **o que** quebrou; causa = **por quê**. Alertar por sintoma; usar causa para depurar. Reduz ruído de alerta.

## Uso na apresentação

- Contrato mínimo de observabilidade que a plataforma entrega pronto para **todo** ambiente e recurso que gera, sem o time configurar.
- No MVP 1: latência, tráfego (requisições e tokens), erros e saturação do LiteLLM proxy — liga com `token-finops`.
- São as fitness functions de runtime de um ambiente (`fitness-functions.md`).
