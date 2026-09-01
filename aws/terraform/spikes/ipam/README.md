# Spike: IPAM scope for CIDR allocation

**Status: código escrito, ainda não aplicado.** Spike descartável da [issue #15](https://github.com/smsilva/wasp-idp/issues/15), decidida na [ADR 0015](../../../../docs/adr/0015-defer-ipam-adoption.md).

> **Isto não é uma camada.** Não entra em `up-all`, não tem script `up-NN`, e o state é **local** de propósito. A decisão do repo é **adiar** o IPAM; este diretório existe para que a decisão tenha sido tomada com o desenho provado, não com o desenho imaginado — e para que a adoção futura comece de código que já funcionou em vez de página em branco.

## O que ele responde

O desenho de [`aws/docs/network/08-ipam.md`](../../../docs/network/08-ipam.md) é bom no papel. Sete afirmações dele só valem se um `apply` real as confirmar, e são exatamente as que decidem a issue #15.

| # | Prova | Como se verifica | Resultado |
|---|---|---|---|
| 1 | Free Tier **recusa** pool no escopo privado | `apply` com `tier = "free"` tem de falhar | ⬜ não executado |
| 2 | A management é **recusada** como IPAM account | o `precondition` do `main.tf` barra antes da API; trocar `management_profile` por `network_profile` tem de dar erro | ⬜ não executado |
| 3 | As VPCs `10.1`/`10.2` são **adotadas sem serem recriadas** | `get-ipam-pool-allocations` lista as duas **e** `terraform plan` em `regions/us-east-1/` continua `0 changes` | ⬜ não executado |
| 4 | Uma VPC nasce com CIDR **escolhido pelo pool**, cross-account | `terraform output proof_vpc_cidr` — nenhum CIDR foi escrito na configuração | ⬜ não executado |
| 5 | Alocação **sem a tag exigida falha** | remover a tag `cell` do `aws_vpc.proof` e aplicar | ⬜ não executado |
| 6 | Custo real por IP ativo | `TotalActiveIpCount` no CloudWatch e o usage type `IPAddressManager-IP-Hours` no Cost Explorer | ⬜ não executado |
| 7 | `destroy` devolve a Organization ao estado anterior | `describe-ipams` vazio e `list-delegated-administrators` sem o IPAM | ⬜ não executado |

**As duas provas mais importantes são a 3 e a 5**, e por motivos opostos. A 3 é o critério de aceite literal da issue ("adoção do bloco existente no pool do IPAM, não realocação"). A 5 é o que separa IPAM de planilha: a regra de tag é o que torna "cada célula tem seu bloco" uma **condição de alocação** em vez de uma convenção que alguém pode esquecer.

**Resultado esperado da 3, que parece erro e não é:** as VPCs adotadas vão aparecer como `noncompliant`. Elas não têm a tag `cell = spike`, e a doc é explícita que o `auto_import` *"will import a CIDR regardless of its compliance with the pool's allocation rules"*. Isso é informação — o IPAM mostrando que o legado não satisfaz a política nova — não falha da adoção.

## Rodar

Pré-requisitos: SSO ativo nos três profiles (`personal`, `network`, `cicd`) e Terraform >= 1.15.

```bash
cd aws/terraform/spikes/ipam
terraform init
terraform plan          # a leitura do plan já vale: 12 recursos, nenhum caro
terraform apply         # via `! terraform apply`, como todo apply deste repo
```

O `apply` leva ~2 min. A adoção do `auto_import` é **assíncrona** (a doc registra até ~20 min de atraso no monitoramento): lista de alocações vazia logo depois do apply **não** é resultado negativo — esperar antes de concluir qualquer coisa sobre a prova 3.

```bash
terraform destroy       # cascade = true no aws_vpc_ipam garante que isto termina
```

## Custo

**~US$ 0,05/dia** no estado atual do ambiente. O Advanced Tier cobra US$ 0,00027 por IP ativo/hora, e a Organization inteira tem 7 IPs ativos com só `module.hub` de pé (medido em 2026-09-01). A VPC de prova acrescenta **zero** — não tem ENI dentro.

O que muda esse número: se a célula subir durante o spike, a frota vai a ~40 IPs ativos (~US$ 0,26/dia), porque o VPC CNI pré-aloca IPs secundários por nó. O custo do IPAM escala com a frota de **pods**, não com o número de VPCs.

## Riscos aceitos ao rodar isto

- **É ação org-wide.** `aws_vpc_ipam_organization_admin_account` cria a service-linked role `AWSServiceRoleForIPAM` em **todas** as contas membro, e o IPAM passa a monitorar (e cobrar) todo IP ativo da Organization — não só o das contas que alocam de pool. Reversível pelo `destroy`, mas é mudança na Organization, não numa conta.
- **Só existe um IPAM por conta/região.** Enquanto este spike estiver de pé, o slot da conta `network` está ocupado.
- **Destroy pela metade trava o downgrade** para Free Tier, que exige apagar pools privados, escopos não-default, pools com locale ≠ home region e alocações cross-account. Mitigado por `cascade = true`.
- **`auto_import` tem latência.** Não concluir "não funcionou" antes de ~20 min.

## O que este spike deliberadamente não faz

- **Não cria o segundo escopo privado.** O escopo adicional é a primitiva que sustenta CIDR repetido entre tenants que não se falam — o argumento mais forte do IPAM, e o único gatilho que provavelmente dispara antes dos outros. Mas ele depende de uma decisão de tenancy ainda em aberto (`aws/docs/tenancy/CLAUDE.md`, decisão 2); construí-lo aqui seria escolher a resposta pelo caminho errado.
- **Não migra `src/hub` nem `src/cell`** para `ipv4_ipam_pool_id`. Essa é a adoção de verdade, e ela só acontece quando um gatilho da ADR 0015 disparar.
- **Não toca `us-west-2`.** O pool regional dela é criado (é uma linha de `for_each`), mas nenhuma VPC de lá é adotada — aquela região tem zero recursos.
