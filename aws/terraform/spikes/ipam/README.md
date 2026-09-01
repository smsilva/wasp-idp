# Spike: IPAM scope for CIDR allocation

**Status: aplicado e destruído em 2026-09-01, duas vezes — nada permanece na AWS.** Spike descartável da [issue #15](https://github.com/smsilva/wasp-idp/issues/15), decidida na [ADR 0015](../../../../docs/adr/0015-defer-ipam-adoption.md).

Verificação final: `describe-ipams` = 0 em `us-east-1` e `us-west-2`, `list-delegated-administrators` = 0, state vazio, e a única VPC no supernet é o hub `10.1.0.0/16`, intacto.

> ## ⚠️ O achado: o IPAM entregou um CIDR já em uso
>
> A VPC de prova nasceu com **`10.1.0.0/24`** — dentro de `10.1.0.0/16`, a VPC do hub que estava **de pé** na conta `network`. Duas VPCs sobrepostas, em contas que se falam pelo TGW. Exatamente a colisão que o IPAM existe para impedir.
>
> **Causa: `auto_import` é assíncrono e a alocação não espera por ele.** O Terraform criou o pool e pediu o CIDR segundos depois; nenhuma VPC existente tinha sido importada ainda, então o pool via `10.0.0.0/14` inteiro como livre. Quinze minutos depois, `10.1.0.0/16` **continuava não importada**.
>
> Não foi falha de descoberta: `get-ipam-discovered-resource-cidrs` já listava 14 recursos, **incluindo a VPC hub e suas quatro subnets**. O IPAM sabia da VPC. O que não aconteceu foi a promoção de *descoberto* para *alocado* — e **essas duas coisas são distintas**, o que `08-ipam.md` não separava.
>
> Pior, e por regra documentada: com a alocação `/24` existindo, a VPC `/16` que a cobre **não pode mais ser auto-importada** — *"a VPC with an overlapping CIDR cannot be automatically imported"*. Uma alocação prematura **envenena o pool** de forma que a adoção do legado deixa de ser possível.
>
> ### A lição que muda a ordem de operações da adoção
>
> **Adotar primeiro, alocar depois — e verificar a adoção, não esperá-la.** Criar pool com `auto_import` e alocar no mesmo `terraform apply` é uma race silenciosa. A adoção real precisa ser em duas fases separadas por verificação explícita:
>
> 1. criar IPAM e pools, **sem nada que aloque**;
> 2. confirmar por `get-ipam-pool-allocations` que **cada bloco legado entrou** como alocação;
> 3. só então liberar alocação dinâmica.
>
> Alternativa mais segura, e que inverte o papel que eu tinha atribuído à allocation explícita: **reservar cada bloco legado por `aws_vpc_ipam_pool_cidr_allocation` antes de qualquer alocação dinâmica**, usando a allocation como barreira determinística em vez de depender da descoberta assíncrona. É o único mecanismo aqui que é síncrono e revisável em PR.
>
> Consequência para a [ADR 0015](../../../../docs/adr/0015-defer-ipam-adoption.md): a migração para IPAM **não** é o passo mecânico e seguro que `08-ipam.md` descrevia. Ela tem uma janela de corrida capaz de produzir a exata colisão que o serviço deveria prevenir — argumento novo, e melhor que os anteriores, a favor de adiar.

> **Isto não é uma camada.** Não entra em `up-all`, não tem script `up-NN`, e o state é **local** de propósito. A decisão do repo é **adiar** o IPAM; este diretório existe para que a decisão tenha sido tomada com o desenho provado, não com o desenho imaginado — e para que a adoção futura comece de código que já funcionou em vez de página em branco.

## O que ele responde

O desenho de [`aws/docs/network/08-ipam.md`](../../../docs/network/08-ipam.md) é bom no papel. Sete afirmações dele só valem se um `apply` real as confirmar, e são exatamente as que decidem a issue #15.

| # | Prova | Como se verifica | Resultado |
|---|---|---|---|
| 1 | Free Tier **recusa** pool no escopo privado | `apply` com `tier = "free"` tem de falhar | ⬜ **não executado** — exigiria um segundo apply deliberadamente quebrado |
| 2 | A management é **recusada** como IPAM account | o `precondition` do `main.tf` barra antes da API | 🟡 **inconclusivo** — o `precondition` não disparou porque os profiles estavam certos. A recusa da própria AWS não foi exercitada |
| 3 | As VPCs `10.1`/`10.2` são **adotadas sem serem recriadas** | `get-ipam-pool-allocations` + `terraform plan` em `regions/us-east-1/` | 🔴 **falhou na adoção, passou na não-destruição** — ver o aviso acima |
| 4 | Uma VPC nasce com CIDR **escolhido pelo pool**, cross-account | `terraform output proof_vpc_cidr` | ✅ **sim, e é assim que o defeito apareceu** — `10.1.0.0/24`, alocado do pool compartilhado por RAM, sem nenhum CIDR escrito na configuração. O mecanismo funciona; o que falta é a barreira |
| 5 | Alocação **sem a tag exigida falha** | `-var proof_vpc_omit_tag=true -replace=aws_vpc.proof` | ✅ **sim** — `InvalidParameterValue: The resource is missing one or more of the resource tags required by the IPAM pool.` A criação foi **recusada pela AWS** |
| 6 | Custo real por IP ativo | usage type `IPAddressManager-IP-Hours` no Cost Explorer | ⬜ **não executado** — precisaria de ~24h de dados, e o spike viveu ~20 min |
| 7 | `destroy` devolve a Organization ao estado anterior | `describe-ipams` vazio, `list-delegated-administrators` sem o IPAM | ✅ **sim, mas lento** — 13 destruídos; `describe-ipams` = 0, `list-delegated-administrators` = 0, VPC hub intacta. **18m29s só na VPC**, contra ~1 min para os 12 recursos restantes |

**Detalhamento da prova 3, que é o critério de aceite literal da issue.** Ela tem duas metades e elas deram resultados opostos:

- **Não-destruição: passou.** `terraform plan -target=module.hub` em `regions/us-east-1/` deu `0 to add, 1 to change, 0 to destroy`, e a única mudança é o drift **pré-existente** do `aws_iam_saml_provider.client_vpn`, já registrado em Known Broken. Nenhuma VPC recriada, nenhuma rota tocada. Criar um IPAM sobre uma árvore Terraform viva não a perturba.
- **Adoção: não aconteceu.** Descoberta sim (14 recursos, incluindo `10.1.0.0/16` e suas subnets), importação como alocação não — nem em 15 minutos, e provavelmente nunca, pelo envenenamento descrito acima.

**A prova 5 é a que separa IPAM de planilha, e passou.** A VPC foi recriada sem a tag exigida pelo pool e a AWS **recusou a criação**:

```
Error: creating EC2 VPC: ... api error InvalidParameterValue:
The resource is missing one or more of the resource tags required by the IPAM pool.
```

Isso prova no mecanismo — não por citação da doc — que `allocation_resource_tags` é **condição de alocação**. Um `terraform apply` que esqueça a tag não pega um bloco errado: ele falha, e falha no `CreateVpc`, antes de qualquer recurso existir. É a única coisa que um arquivo markdown de alocação nunca conseguirá fazer.

**Cuidado ao reproduzir:** só vale com `-replace`. A regra é avaliada na **criação**; um `apply` que apenas remova a tag de uma VPC já criada e já alocada passa sem erro, e o resultado se lê como "a regra não funciona".

**Expectativa que ficou registrada e não chegou a ser observada:** as VPCs adotadas apareceriam como `noncompliant`, por não terem a tag `cell = spike` — a doc é explícita que o `auto_import` *"will import a CIDR regardless of its compliance"*. Como nenhuma foi importada, isso não foi visto.

## Números observados

| | |
|---|---|
| Recursos criados | 13 (`apply` completo, ~5 min) |
| Criação da VPC via pool | **4m22s** — alocação por IPAM é lenta, orçar isso em qualquer apply que dependa dela |
| Destruição da mesma VPC | **18m29s**, e a VPC já não existia na AWS (`InvalidVpcID.NotFound`) muito antes de o Terraform seguir em frente. O provider fica preso esperando a **desalocação no IPAM**, que é assíncrona — um destroy que parece travado e não está. Vale para qualquer VPC com `ipv4_ipam_pool_id` |
| Destruição de todo o resto | **~1 min**, IPAM, pools, RAM share e delegação inclusos. Medido duas vezes (12 e 9 recursos) — **toda a lentidão está na VPC**, nada mais |
| Estado final verificado | `describe-ipams` = 0, `list-delegated-administrators` = 0, VPC hub `10.1.0.0/16` intacta, state do spike vazio |
| Adoção do legado em 15 min | **0 de 2** blocos |
| Recursos descobertos pelo IPAM | 14 na conta `network` (VPCs, subnets, EIPs) |
| Vida do spike | ~20 min de operação útil |
| Custo | desprezível (~US$ 0,05/dia de taxa; nem chegou a fechar uma hora de billing) |

## Segunda rodada: o cenário greenfield (`us-west-2`)

O spike acima rodou em **brownfield** — havia VPC pré-existente, e é daí que veio o defeito. A pergunta que ele não responde é se o problema existe no **dia zero**, quando o IPAM nasce antes de qualquer VPC. A resposta esperada é que não exista: sem nada a importar, `auto_import` é irrelevante e a race some.

`us-west-2` permite testar isso sem criar uma Organization: `regions/us-west-2/` nunca foi aplicada, e o `/14` daquela região (`10.4.0.0/14`) não contém nenhuma VPC. No que importa para o IPAM — o espaço do pool — é greenfield de verdade.

```bash
terraform plan  -var-file=greenfield-us-west-2.tfvars      # 10 recursos
terraform apply -var-file=greenfield-us-west-2.tfvars
terraform output proof_vpc_cidr                            # esperado: dentro de 10.4.0.0/14
terraform output proof_vpc_is_inside_regional_block         # esperado: true
```

A VPC default de `us-west-2` (`172.31.0.0/16`) **não interfere**: está fora do supernet, logo fora de qualquer pool. Ela é assunto da issue #67.

### Resultado (2026-09-01)

**Limpo, e confirma que o defeito é exclusivo de brownfield.**

| | |
|---|---|
| `proof_vpc_cidr` | **`10.4.0.0/24`** — dentro do `/14` da região |
| `proof_vpc_is_inside_regional_block` | `true` |
| Alocações no pool | exatamente uma, a própria VPC de prova |
| VPCs no supernet em `us-west-2` | só a de prova — **nenhuma sobreposição** |
| VPCs default (`172.31.0.0/16`, 3 contas) | descobertas, **fora do pool**, como previsto |
| Recursos | 10 |

Comparando as duas rodadas lado a lado, com a mesma configuração e a mesma sequência de apply:

| | Brownfield (`us-east-1`) | Greenfield (`us-west-2`) |
|---|---|---|
| CIDR devolvido | `10.1.0.0/24` | `10.4.0.0/24` |
| Já estava em uso? | **sim**, sob a VPC hub `10.1.0.0/16` | não |
| Adoção do legado | falhou, e o pool ficou envenenado | não se aplica |

**A conclusão que isso sustenta:** o IPAM funciona como anunciado quando entra antes da primeira VPC. O que ele não faz é entrar com segurança *depois*, sem a sequência disciplinada de quatro fases da [ADR 0015](../../../../docs/adr/0015-defer-ipam-adoption.md). O risco não está no serviço — está na migração.

### A prova 5, que ficou faltando, cabe aqui

Com o ambiente de pé, `var.proof_vpc_omit_tag = true` tira a tag exigida pelo pool. Mas **um `apply` simples não prova nada**: mudar tag não força replace, então o Terraform apenas removeria a tag de uma VPC **já criada e já alocada** — a condição de alocação nunca seria reavaliada, o apply passaria, e o resultado se leria como "a regra não funciona".

A regra vale na **criação**. Então a VPC precisa nascer de novo, sem a tag:

```bash
terraform apply -var-file=greenfield-us-west-2.tfvars \
  -var proof_vpc_omit_tag=true \
  -replace=aws_vpc.proof
```

Leva ~20 min (a destruição da VPC sozinha passa de 18). O apply tem de **falhar na criação**.

Se ele **passar**, a descoberta é maior que a prova: `allocation_resource_tags` não estaria sendo aplicada, e o argumento de que "o IPAM transforma convenção em condição" cairia junto — que é a principal vantagem dele sobre uma tabela markdown.

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
# NUNCA sincrono: passa de 15 minutos, quase todos numa unica linha do log.
nohup terraform destroy -no-color -auto-approve > /tmp/spike-ipam-destroy.log 2>&1 < /dev/null & disown
```

O `destroy` fica **mais de 15 minutos** em `aws_vpc.proof: Still destroying...`, e a VPC já não existe na AWS (`describe-vpcs` devolve `InvalidVpcID.NotFound`) muito antes disso — o provider está esperando a **liberação da alocação no IPAM**, que é assíncrona. `cascade = true` garante que pools e escopos saiam sem ordem manual, mas não acelera essa espera.

**Um destroy que pareça travado provavelmente não está.** Ao diagnosticar, conferir o processo com `pgrep -af terraform` **sem truncar a saída** — nesta sessão um `| head -3` mostrou só o language server e o MCP server, e a ausência foi lida como processo morto. Um segundo `destroy` concorrente sobre o mesmo state teria sido um problema real.

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
