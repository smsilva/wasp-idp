# Bring-Up Scripts And DNS Layer Applied

_2026-08-26_


**Fase 1 do plano completa.** A preocupação que motivou o trabalho era a sequência: a ordem das
camadas existia só na cabeça de quem já tinha rodado.

`aws/terraform/scripts/` — um script por camada, numerado pela ordem de dependência, mais `up-all`
que roda a sequência parando na primeira falha. `scripts/lib` é sourced e concentra o encanamento
(log com timestamp, `PIPESTATUS[0]`, confirmação, descoberta do bucket pelo id da Organization) —
"um script por camada" não podia significar cinco cópias disso.

A ordem, e por quê: 00 `state-backend` antes de tudo porque nenhuma outra raiz inicializa o backend
sem o bucket; 01 `network-foundation` antes de 04 porque a 04 lê a VPC hub por `tag:Name`; 02 `dns` é
independente das outras, mas pré-requisito de certificado e ingress; 03 `connectivity` ainda não
existe e o `up-all` a pula avisando; 04 `control-plane` **não entra por default** (~US$ 165/mês contra
centavos das três primeiras).

**Três armadilhas viraram guarda executável**, em vez de parágrafo de README: bucket de state
inexistente (o `up-00` para e imprime o bootstrap manual — a raiz guarda o próprio state no bucket que
gerencia, e automatizar às cegas um passo de uma vez esconde o problema); região negada pela SCP (o
`up-01` faz um `describe-vpcs` antes do primeiro `Create*`); e **zona pai que já tem NS para o label**
(o `up-02` recusa — delegação antiga colide no apply e a mensagem do Azure não diz que a causa é um
record set preexistente).

**Camada 2 aplicada e verificada.** Subzona `nonprod.<domínio>`, `Z087731898SD8PA9OXYR`, conta
`network`, 2 record sets. Delegação provada por `dig +trace`: o name server do Azure entrega a
delegação e o do Route 53 responde o SOA — a cadeia atravessa as duas clouds. Propagação quase
imediata.

Três coisas aprendidas na execução:

- **A pai já tinha uma delegação NS no mesmo formato** (`NS sandbox` → zona Azure). O `NS nonprod`
  ficou ao lado dela, apontando para o Route 53 em vez de para outra zona Azure. Nada de novo na pai —
  e foi o que justificou o guard de colisão do `up-02`.
- **O TTL 300 está no NS da PAI, não na subzona.** O `NS` dentro da zona do Route 53 nasce com 172800
  (default da AWS). Quem governa a repropagação da delegação é o da pai — que é o que se configurou.
- **A conta `network` não tem permission set**, então ver a zona no console exige switch-role para
  `OrganizationAccountAccessRole`. Já era item do backlog da Frente A; agora incomoda na prática.
