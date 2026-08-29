# State boundary follows lifecycle, not account

**Status:** Aceito

## Contexto

Um recurso pode viver, tecnicamente, em qualquer state Terraform que tenha o provider certo
configurado. A tentação natural é organizar state por conta AWS (um state por conta), o que pareceria
mais simples de raciocinar sobre permissões.

## Decisão

**A fronteira de state segue o ciclo de vida do recurso, não a conta que o possui.** Um recurso
entra no state cujo apply/destroy compartilha o mesmo ciclo de vida dele, mesmo que isso signifique
usar um provider `aws.<outra-conta>` dentro desse state.

Exemplo concreto: os componentes do `3.2` (certificado wildcard, target group, listener rule,
registro alias) do lado hub vivem no state da `control-plane` (conta `cicd`), via provider
`aws.network`, porque o ciclo de vida deles é o da célula — nascem e morrem junto com ela — não o
da conta `network`.

## Consequências

Um mesmo state Terraform passa a gerenciar recursos em mais de uma conta AWS simultaneamente — isso
é esperado e correto sob esta regra, não um cheiro de design. Quem lê o código precisa checar o
provider de cada recurso, não assumir pela pasta/state em que está. Ver também ADR 0009, que aplica
esta mesma regra à decisão de onde o ALB do hub vive.
