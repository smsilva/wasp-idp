# Step 1.1 — LBC Discovery Tags

_2026-08-26_


Branch `feat/lbc-subnet-discovery-tags`, a partir de `main`.

**O passo não era o que o plano dizia.** `Known Broken 1` e o `1.1` afirmavam que `src/network` não
aplicava `kubernetes.io/role/{elb,internal-elb}`. As duas tags estão no módulo desde `b32eb68`, o
commit inicial dele, com comentário explicando o propósito. O achado nasceu da comparação com o
desenho de referência — que trata as tags como flag explícita de spoke — e foi registrado como bug do
código sem ninguém abrir o `main.tf`. Atravessou duas sessões de handoff assim.

O que de fato faltava era o critério de aceite escrito no próprio passo: **nenhum dos dois arquivos de
teste olhava tag alguma**. Entregue `src/network/tests/tags.tftest.hcl`, 4 runs — perda da tag
pública, perda da privada, cruzamento das duas famílias, e inversão da ordem do `merge`.

**Quatro mutações rodadas, quatro capturas**, cada uma pela asserção pretendida. A quarta só passou a
valer depois de a `var.tags` do teste **colidir de propósito** com a tag de papel, e com o valor
errado: sem colisão, inverter `merge(var.tags, {papel})` para `merge({papel}, var.tags)` passava sem
ser notado. Todo `alltrue` tem contagem ao lado — `alltrue([])` é `true`.

Duas decisões fechadas, com a doc do EKS no lugar de memória: **a tag `kubernetes.io/cluster/<nome>`
fica fora** (opcional desde o LBC `2.1.2`, só desempata clusters que dividem VPC, e o módulo não
conhece nome de cluster); e **as tags de papel não têm fallback**, porque o LBC não examina route
table como o controller in-tree.

Regressão da árvore: **49 testes em 11 diretórios, 0 falhas** (eram 45). Custo: zero, nada tocou a
AWS.
