# Step 1.2 — EKS API Endpoint Restricted

_2026-08-26_


Branch `feat/lbc-subnet-discovery-tags` (o `1.2` seguiu na mesma).

**A fronteira foi a decisão do passo**, e ela se dividiu em duas por natureza do que se protege:

| Onde | O que | Natureza |
|---|---|---|
| `src/cluster` | recusa lista vazia **se** o endpoint público está ligado; recusa CIDR sem prefixo | **semântica da AWS** — vazio é `0.0.0.0/0`, e a armadilha vale para qualquer chamador |
| `control-plane` | variável **sem default**; recusa `0.0.0.0/0` mesmo explícito | **política da célula** — abrir exige editar a validação, ato visível em diff |
| `generate-tfvars` | descobre o IP em `checkip.amazonaws.com`, escreve o `/32`; `--public-access-cidr` (repetível) desliga a descoberta | o script já existia para descobrir antes de gerar arquivo |

Sem default é o que fecha o `Known Broken 3`: omitir a variável era o caminho silencioso para o
mundo, e agora é erro de validação antes de qualquer chamada à AWS. Custo do fechamento: o
`terraform.tfvars` local precisa ser regenerado.

**Seis mutações rodadas, seis capturadas.** Duas ensinaram algo:

- **Condição de `validation` tem de referenciar a própria variável.** Trocar por `true` para testar
  não deixa o teste vermelho — deixa a configuração inválida, e **nenhum run executa**. Mutação de
  validação precisa **enfraquecer** (`length(...) >= 0`), não remover. Duas tentativas foram
  perdidas nisso.
- **A invariante do módulo torna o fio do root impossível de cortar calado:** apagar o
  `public_access_cidrs = var.public_access_cidrs` deixa a lista vazia e o módulo derruba o plan no
  primeiro run. Só a mutação que passa um CIDR **válido mas errado** isola a asserção do root — e é
  ela que a justifica.

**O que NÃO foi verificado:** os outros dois critérios de aceite do passo (*o apply do laptop segue
funcionando*, *a API recusa de outro IP*) exigem a camada 2 de pé, ~US$ 165/mês. Ficam para a próxima
vez que ela subir.

Regressão: **55 testes em 11 diretórios, 0 falhas** (eram 49). Nada tocou a AWS além de um GET em
`checkip.amazonaws.com`.
