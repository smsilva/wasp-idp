# Fitness functions

Fundamento para dizer que a plataforma **e** cada ambiente gerado por ela (com seus recursos) têm fitness functions que respondem "o estado atual é o desejado?".

## Fontes

- Mark Richards e Neal Ford, *Fundamentals of Software Architecture* (O'Reilly, 2020; 2ª ed. 2025). <https://fundamentalsofsoftwarearchitecture.com/>
- Neal Ford, Rebecca Parsons, Patrick Kua (e Pramod Sadalage na 2ª ed.), *Building Evolutionary Architectures* (O'Reilly, 2017; 2ª ed. 2023). Cap. 2, "Fitness Functions": <https://www.oreilly.com/library/view/building-evolutionary-architectures/9781491986356/ch02.html>. Katas dos autores: <https://evolutionaryarchitecture.com/ffkatas/>
- Thoughtworks Technology Radar, "Architectural fitness function" (Trial → Adopt): <https://www.thoughtworks.com/radar/techniques/architectural-fitness-function>
- Livros não lidos nesta sessão: os trechos abaixo vêm do resumo do usuário, das páginas oficiais e de resumos secundários. Conferir o texto e a página do livro antes de pôr citação na tela.

## Como os dois livros se dividem (enquadramento do usuário)

- *Fundamentals* dá o **vocabulário e a taxonomia** — descritivo e estático, o "o quê": architecture characteristics (operational, structural, cross-cutting), como escolhê-las, trade-offs explícitos ("least worst architecture"), ADRs, estilos arquiteturais.
- *Building Evolutionary Architectures* dá o **mecanismo de governança** — operacional e dinâmico, o "como manter ao longo do tempo": fitness functions, cadência, guarded evolution.

## Fundamentals: characteristics

- Três grupos: **operational** (ex.: scalability, performance, availability), **structural** (ex.: configurability, extensibility, maintainability, portability), **cross-cutting** (ex.: security, accessibility, legality).
- Escolher **o mínimo** de characteristics: cada uma adiciona complexidade e afeta as outras. Na identificação com stakeholders, pedir que escolham **as três mais importantes** (em qualquer ordem), em vez de ranquear a lista inteira. O próprio livro avisa para não obcecar com o número; o objetivo é manter o design simples. (O resumo do usuário chama de regra dos "less than three"; o texto do livro fala em "top three".)
- Trade-off explícito: não existe a melhor arquitetura, só a "least worst"; a decisão vira ADR.

## Building Evolutionary Architectures: fitness functions

- Definição (1ª ed., cap. 2): "An architectural fitness function provides an objective integrity assessment of some architectural characteristic(s)." A 2ª ed. aparece citada como "any mechanism that provides an objective integrity assessment…" (InfoQ). Conferir a edição antes de citar.
- O termo vem da computação evolutiva: mede o quão perto uma solução está do objetivo.
- Qualquer verificação objetiva e repetível conta: testes, métricas, monitores, alertas, regras de arquitetura, experimentos de caos.
- Dimensões citadas do cap. 2 (via resumos): atomic vs. holistic, triggered vs. continual, static vs. dynamic, automated vs. manual, temporal.
- Guarded evolution: a arquitetura pode mudar à vontade **desde que** as fitness functions continuem passando.

## Aplicação à plataforma (tese do usuário)

A plataforma e cada `Environment` declaram o estado desejado; fitness functions verificam continuamente se o real bate com ele. Exemplos que já existem na PoC:

| Fitness function | Tipo | O que garante |
|---|---|---|
| Condições `Ready`/`Synced` do XR e dos MRs do Crossplane | continual, automated | o recurso real converge para o declarado |
| Echo HTTP 200 em **todos** os IPs do NLB | holistic, triggered | o ambiente está disponível de ponta a ponta |
| Emissor ACME de staging em ambiente de teste | static | não queima cota compartilhada |

Candidatas: os golden signals (`golden-signals.md`) por ambiente como fitness functions de runtime; DORA (`dora-metrics.md`) como fitness function da entrega; ambiente ocioso (`mercadolibre-fury.md`) como fitness function de custo.
