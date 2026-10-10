# Score

Fonte: <https://docs.score.dev/docs/score-specification/score-spec-reference/> (`apiVersion: score.dev/v1b1`).

Workload spec independente de plataforma e de ambiente: o dev descreve **o que** a app precisa; a plataforma decide **como e onde**.

| Seção | O que diz | Ponto da narrativa |
|---|---|---|
| `metadata` | nome do workload | liga ao Component do catálogo (`greeting-api`) |
| `containers` | imagem e variáveis | `image: .` = a imagem que a CI buildou; versão injetada na entrega |
| `service` | portas expostas | nada de ingress, LB ou certificado |
| `resources` | dependências por **tipo** (`postgres`, `dns`, `route`) | nunca o serviço de nuvem; mesmo princípio dos Resources do catálogo |
| `${resources.<id>.<output>}` | referência resolvida no deploy | o mesmo arquivo serve para todo ambiente |

## Na apresentação

- Logo depois do slide que introduz Score (`workload-spec`), um quadro de código no estilo IDE (fundo escuro, números de linha, syntax highlight).
- Arquivo: `snippets/app-spec.yaml` (exemplo `greeting-api`).
- Mostrado por partes: arquivo inteiro → `containers` → `service` → `resources` → placeholders, cada parte em destaque com o resto esmaecido. Fecha com "nenhuma linha diz onde, em qual nuvem, nem com qual tool" → gancho para o orquestrador.
- Na fase visual: o mesmo efeito vira slides duplicados com as linhas fora de foco esmaecidas (progressive build).
