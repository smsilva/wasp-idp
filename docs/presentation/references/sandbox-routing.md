# Sandbox routing

Verificar mudanças (sobretudo as feitas por agents) **antes do PR**, contra o sistema real, com sandboxes leves por requisição num cluster compartilhado. Origem: consolidação de uma conversa com o claude.ai (2026-10-06); artigo e docs conferidos em 2026-10-07.

## Fontes

- Arjun Iyer (CEO da Signadot), "Agents have made CI the bottleneck. Faster pipelines are the wrong fix.", The New Stack, 2026-10-04. <https://thenewstack.io/ci-bottleneck-agent-verification/> — **post patrocinado pela Signadot** (tag `sponsored`), que vende exatamente essa solução.
- Istio: request routing <https://istio.io/latest/docs/tasks/traffic-management/request-routing/>; versões suportadas <https://istio.io/latest/docs/releases/supported-releases/> (em 2026-10: 1.31 atual, EOL ~fev/2027; 1.30 EOL ~dez/2026; 1.29 EOL 2026-10-12 — reconferir perto da apresentação).
- OpenTelemetry Baggage: <https://opentelemetry.io/docs/concepts/signals/baggage/>

## Tese do artigo

1. **Agents viraram a CI do avesso:** "Agents pushed CI job volume up 25x at Anthropic." No Linear, a suíte de testes "has nearly quadrupled since January, and agents now write most of their tests".
2. **Posição errada:** a CI roda depois do PR; o agent que espera minutos por um check vermelho perdeu o contexto.
3. **Verde ≠ funciona:** um repo é um serviço entre dezenas, e os testes mockam o resto; as falhas reais vivem nas fronteiras (campo renomeado, timeout com retry em cascata, migração que trava tabela). "Making the gate faster does not change what it checks." O DORA associa mais adoção de IA a mais throughput **e** mais instabilidade.
4. **Verificar contra o sistema, antes do PR:** num cluster compartilhado só o serviço alterado sobe; "every other hop resolves to the shared stable versions". "A test environment costs roughly the price of one pod, and it comes up in seconds. Fifty agents working in parallel share one stable environment instead of cloning it fifty times."
5. **Verificação governada pela plataforma:** "the platform team writes those steps once, as a sequence of approved actions that exercises a change against the live system and records what happened. Agents invoke them through the skills and hooks that Claude Code, Cursor, and similar tools already support". O registro vira evidência para review e merge gates; a CI vira confirmação.

## Mecânica: request-level isolation

- Padrão usado por Lyft, Uber e Signadot (segundo a conversa; não conferido nas fontes de Lyft/Uber).
- A versão em teste sobe **ao lado** da estável com label próprio; `DestinationRule` define os subsets e `VirtualService` manda para o subset de teste só as requisições com o header de sandbox; o resto vai para o estável.

```yaml
apiVersion: networking.istio.io/v1
kind: VirtualService
metadata:
  name: orders
spec:
  hosts: [orders]
  http:
  - match:
    - headers:
        baggage:
          regex: ".*sandbox=pr123.*"
    route:
    - destination: {host: orders, subset: test-pr123}
  - route:
    - destination: {host: orders, subset: stable}
```

- **Propagação de contexto é o ponto crítico:** o Envoy não liga a requisição de entrada à de saída, então cada serviço precisa repassar o header. Com **OpenTelemetry Baggage** (`baggage: sandbox=pr123`) os SDKs instrumentados propagam junto com o `traceparent`. Basta **um** serviço não propagar para o roteamento quebrar em silêncio dali em diante → candidato a fitness function / requisito de "good citizen" da plataforma (`fitness-functions.md`).

## Cuidados e limites

| Tema | Cuidado |
|---|---|
| Ambient mode | roteamento L7 por header exige **waypoint** para o serviço em teste; só ztunnel não basta |
| Mensageria (Kafka/SQS) | o mesh não ajuda: levar o baggage no header da mensagem e filtrar no consumer, ou tópico/consumer group por sandbox |
| Dados | a versão em teste escreve nos mesmos bancos; mudança de schema ou efeito colateral pede banco/schema isolado |
| Entrada | o gateway injeta ou valida o header, para tráfego externo não cair num sandbox |
| Traffic mirroring | `mirror:` copia tráfego real e descarta a resposta; validação passiva, segura só sem escrita |

## Ambiente completo × sandbox por requisição

- Ambiente efêmero completo (o `Environment` do MVP 1 é um cluster EKS inteiro): isolamento total, caro, ~28-30 min para subir; continua necessário para mudanças de infra e da própria plataforma.
- Sandbox por requisição: ~um pod, sobe em segundos, testa as fronteiras reais; exige propagação de contexto e cuidado com dados e mensageria.
- A plataforma deveria oferecer os dois, não só "ambiente por PR".

## Relação com outras referências

- State of AI Vol. 2 (`state-of-ai-in-platform-engineering.md`): só 17% rodam validation loops automatizados e 35% validam só por leitura humana (p. 26); validation loop e **sandboxed environments** estão entre os quatro pré-requisitos do Level 3 (p. 10, p. 50).
- Rollout progressivo em produção baseado em métricas é a continuação natural do mesmo roteamento (golden signals como critério — `golden-signals.md`).
- Build vs. buy: Signadot (comercial, autora do artigo) × Istio + OTel próprio. Não decidido.

## Perguntas em aberto (da conversa)

- Os serviços já têm OpenTelemetry? Em quais linguagens?
- Mesh em sidecar ou ambient?
- Quais serviços usam mensageria, e qual broker?
- Estratégia de dados do sandbox: banco compartilhado, schema por sandbox ou dados sintéticos?
- Construir com Istio + OTel ou avaliar Signadot e alternativas?
- Quais agents os times usam (define o formato das skills e hooks)?
