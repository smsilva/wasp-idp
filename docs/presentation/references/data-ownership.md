# Nobody owns the data

- Fonte: Tharun Mathew, "Platform teams own the pipeline. Nobody owns the data", platformengineering.com, 2026-09-23. <https://platformengineering.com/features/platform-teams-own-the-pipeline-nobody-owns-the-data/>
- Relato de experiência do autor: os números vêm da implementação dele, não de pesquisa — citar como "um caso", nunca como tendência.

## Argumento

- Platform engineering resolveu o ownership de infraestrutura e runtime, mas o **dado** segue sem dono responsável.
- Falha de pipeline dispara alerta; falha de qualidade de dado acontece em silêncio dentro de um sistema "saudável".
- Saída: tratar **data contracts como infraestrutura declarativa**, aplicada pela CI/CD — não como documento de política.

## Citações (literais)

- "A service fails loudly and syntactically...A data system fails quietly and semantically."
- "No stated contract means every change is potentially breaking and none is officially breaking."
- "Kubernetes does not ask politely for resource limits...An internal data platform needs the same posture."

## Números (do caso do autor)

- Tempo mediano para achar o dono responsável por um dataset: de cerca de três dias perguntando por aí para menos de uma hora.
- Cerca de um terço dos datasets catalogados não tinha consumidor vivo; foram aposentados em dois trimestres.

## Recomendações

1. Owner nomeado em escala (rota), não caixa de e-mail do time.
2. Interfaces e schemas explícitos.
3. Consumidores conhecidos, por registro ou atribuição de consulta.
4. Caminho de deprecação com janela de migração.
5. CI/CD rejeita o pull request de pipeline incompleto: exige schema, chave de roteamento de alerta e manifesto de TTL/retenção.

## Uso na apresentação

- Estende o ownership do catálogo para além do código: Resource e API também precisam de dono, contrato e consumidores conhecidos (slides `catalog-ownership`, `entity-api`, `entity-resource`).
- "Contrato quebrado vira entidade nova" (`major-breaking`) é o mesmo princípio aplicado a dado.
- Um terço sem consumidor e aposentado = mesmo raciocínio do ambiente ocioso do Fury (`mercadolibre-fury.md`).
- Contrato aplicado pela CI/CD, não por documento: guardrail executável, como no Security Plane.
