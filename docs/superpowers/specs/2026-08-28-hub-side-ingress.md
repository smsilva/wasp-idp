# Hub-side ingress (`3.2`)

Detalhamento do passo `3.2` de `docs/superpowers/plans/2026-08-26-private-access-and-ingress/03-ingress.md`, escrito depois do aceite do `3.1` (2026-08-28) e incorporando o que o AWS real mostrou naquele aceite. O plano continua sendo a fonte da decisão; esta spec é o roteiro de execução e a lista de armadilhas.

## O que já existe (não reconstruir)

`3.1` está aceito e verificado na AWS. Do lado da spoke, de pé:

| Peça | Valor |
|---|---|
| NLB interno | `control-plane-ingress`, `internal`, `active` |
| Endereços FIXOS, um por AZ | `10.2.32.10` (us-east-1a), `10.2.48.10` (us-east-1b) |
| Listener | 80/TCP → target group do gateway |
| Target group da spoke | tipo `ip`, nome gerado por `name_prefix`, pod do gateway `healthy` |
| Security group do NLB | ingress 80/tcp **só** do CIDR da VPC hub (`10.1.0.0/16`) |
| Gateway Istio | `ClusterIP`, `TargetGroupBinding` registrando o pod |

Os endereços fixos são o contrato com o hub, e são **conhecidos em tempo de plan** (`module.ingress.private_ips`, derivado de `cidrhost` sobre os CIDRs das privadas). Foi exatamente para isso que foram fixados: o `3.2` pode ser escrito e planejado sem esperar o NLB existir.

## O que NÃO existe e o plano assume que existe

**O ALB do hub não foi criado por nenhuma camada.** A tabela "Quem cria o quê" do plano atribui "ALB, listener `:443`" ao Terraform em `connectivity/`, como recurso permanente — mas `connectivity/us-east-1/` não tem nenhum `aws_lb`. Verificado por `grep` no código, não por memória.

Consequência prática: **`3.2` inclui criar o ALB**, e isso é mais trabalho do que "acrescentar uma listener rule". Também levanta uma decisão de fronteira que o plano não resolveu — ver abaixo.

Faltam ainda, na mesma categoria:

- **A raiz do hub não expõe os ids das subnets públicas.** `network-foundation/us-east-1/` tem só `hub_vpc_id`, `hub_vpc_cidr`, `hub_private_subnet_ids` e `hub_control_plane_subnet_ids`. As públicas existem no state (o módulo as cria, com `kubernetes.io/role/elb = 1` e `Name = <nome>-public-<az>`), mas não saem.
- **Nenhum registro DNS aponta para o ALB**, e a subzona `nonprod.<domínio>` (camada 02, conta `network`) é onde ele tem de entrar.

## Decisão de fronteira: onde mora o ALB

O ALB é **permanente e compartilhado** (um listener `:443`, N certificados por SNI, uma rule por cluster) — pelo critério de cardinalidade × churn isso é `connectivity/`, não `control-plane/`. Mas `connectivity/` é o nível **T1, destruído ao fim do dia**, e derrubar o ALB derruba o ingress de todos os clusters.

**Decidido 2026-08-28: ALB em `connectivity/`** — uma instância por hub, nascendo com o plano de conectividade da região. Três razões, em ordem de peso:

1. **Dependência funcional.** Sem TGW o ALB não alcança spoke nenhuma — é um listener servindo 404. O ciclo de vida dele *é* o do plano de conectividade.
2. **Composabilidade por hub.** O segundo hub (outra região) ganha `connectivity/<região>/` com ALB próprio, sem tocar em nada existente. Vale notar que isso **não** discrimina T0 de T1: `network-foundation/` também é uma raiz por região. O discriminador é o item 1.
3. **Custo prorrateado.** Os ~US$ 16/mês do ALB só correm nas horas em que a 03 está de pé.

A ordem de subida/descida já existente resolve sozinha o churn do DNS name do ALB: a célula sobe **depois** da conectividade e desce **antes** dela, então o registro alias do `control-plane/` nunca aponta para um ALB morto.

Consequência aceita: **derrubar o T1 derruba o ingress público de todas as células**, e o `curl` de aceite do `3.2` só funciona com a camada 03 de pé.

Rejeitados: ALB em `network-foundation/` (T0) — daria DNS name estável e zero aresta cross-state, ao preço de a raiz T0 deixar de ser custo zero e de amarrar o ingress a uma camada que não sabe se há conectividade; e raiz permanente própria para o ALB — quinta camada por um recurso só.

**Horizonte declarado (não é escopo do `3.2`):** ingress **por célula**, para que o ALB do hub deixe de ser ponto único de falha. Hoje uma configuração errada no listener compartilhado derruba todas as células, inclusive silos (célula dedicada a um cliente). Quando isso for exercitado, o ALB do hub passa a ser um caminho entre vários, não *o* caminho — o que reforça mantê-lo numa camada descartável em vez de canonizá-lo na T0.

O que fica em `control-plane/` (via provider `aws.network`, fronteira de state segue o ciclo de vida): certificado do cluster, target group do cluster, listener rule do cluster, `aws_lb_listener_certificate` e o registro DNS do cluster. Destruir a célula leva os cinco junto, sem órfão do lado do hub.

## Peças a escrever

### Em `connectivity/us-east-1/` — permanente, uma vez

1. **Security group do ALB**: ingress 443/tcp de `0.0.0.0/0` (é o ponto de entrada público, e aqui `0.0.0.0/0` é o valor certo — ao contrário do NLB da spoke, onde é proibido por decisão), egress 80/tcp para o supernet `10.0.0.0/12` (alcança qualquer spoke presente ou futura pelo TGW).
2. **ALB público** nas subnets **públicas** do hub, `internet-facing`, `ip_address_type = ipv4`.
3. **Listener `:443`** com um certificado default e `default_action` de `fixed_response` 404 — sem rule casando, a resposta é 404 explícito, não erro de configuração. O certificado default pode ser o wildcard da própria subzona (`*.nonprod.<domínio>`), emitido aqui; os certificados por cluster entram por `aws_lb_listener_certificate` a partir do outro state.
4. **Listener `:80`** com `redirect` para 443 — opcional, mas é o que faz `curl http://...` não parecer quebrado.
5. **Outputs**: `alb_arn`, `alb_listener_arn`, `alb_dns_name`, `alb_zone_id`, `alb_security_group_id`.
6. **Guard do `destroy`**: recusar enquanto o listener `:443` tiver certificado ou rule que este state não conhece — ver Armadilhas.

Como `control-plane/` não lê state de outra camada (padrão do repo: descoberta por tag), o ALB e o listener precisam ser **encontráveis por tag** — `data "aws_lb"` por `tags` e `data "aws_lb_listener"` por `load_balancer_arn` + `port`.

### Em `network-foundation/us-east-1/` — um output

7. **`hub_public_subnet_ids`** — **feito 2026-08-28, nas duas regiões**, com dois `override_module` de tamanhos diferentes (2 e 3) provando a ligação, não o valor. Duas mutações capturadas: ligar nas privadas (pega nos dois runs) e lista fixa igual à injetada (pega **só** no segundo — a prova empírica de que um override sozinho passaria verde).

   **Correção do que esta spec dizia antes:** o output **não** é o caminho de consumo do ALB. `connectivity/` deliberadamente não lê state de outra camada — descobre por tag na API (`data "aws_vpc" "hub"` por `tag:Name`, `data "aws_subnets" "hub_private"` por `tag:Name = <nome>-private-*`), com o comentário explicando o porquê: depender do recurso existir, e não do arquivo de state, sobrevive a mudança de backend ou de key do outro lado. Logo o ALB consome **`data "aws_subnets" "hub_public"` por `tag:Name = <nome>-public-*`**, espelhando o irmão — a tag existe (`src/network` a aplica em toda pública, junto de `kubernetes.io/role/elb`).

   O output fica de todo modo, por simetria com `hub_private_subnet_ids`, que já existe embora a 03 também descubra as privadas por tag. Consequência prática boa: **nenhum `apply` da `network-foundation` é pré-requisito do passo 2** — se o consumo fosse por output, seria (output só existe para quem o lê depois de materializado no state).

### Em `control-plane/` — por cluster, via provider `aws.network`

8. **Certificado wildcard no ACM**: `*.<var.name>.nonprod.<domínio>`, validação por **DNS**, com os registros de validação na subzona da camada 02 e um `aws_acm_certificate_validation` para o apply esperar. Wildcard cobre **um nível só**: `*.nonprod.<dom>` não cobre `app.<id>.nonprod.<dom>`, e `*.*.` não existe.
9. **`aws_lb_listener_certificate`** anexando o certificado ao listener `:443` compartilhado (é o SNI que permite N clusters num listener só).
10. **Target group do hub**: tipo `ip`, protocolo **HTTP**, porta **80**, na VPC **hub**, com os dois endereços fixos do NLB como `aws_lb_target_group_attachment`. Registrar IP fora da VPC do load balancer é suportado para faixas RFC 1918 alcançáveis por TGW — é o caso.
11. **Listener rule** com `condition { host_header { values = ["*.<var.name>.nonprod.<domínio>"] } }` e `action` de forward para a target group do hub. `priority` precisa ser único no listener — derivar de algo estável da célula, não `count.index`.
12. **Registro DNS** na subzona: `*.<var.name>.nonprod.<domínio>` como **A alias** para o ALB (`alb_dns_name` + `alb_zone_id`). Wildcard no DNS evita um registro por app, casando com o wildcard do certificado.

## Armadilhas

**O guard do `destroy` da 03 não cobre o que o `3.2` acrescenta — é a mesma aresta cross-state que já falhou duas vezes.** `connectivity/us-east-1/scripts/destroy` recusa enquanto houver **attachment de TGW** de fora do próprio state, mas o `3.2` pendura no listener `:443` mais dois objetos alheios: `aws_lb_listener_certificate` e a listener rule, ambos no state do `control-plane/`. Destruir a 03 com a 04 de pé tem a mesma forma de falha do Known Broken 22. A ordem correta (`04` antes de `03`) já é a documentada, mas ordem documentada não é ordem imposta — **estender o guard** para recusar quando o listener tiver certificado ou rule que o próprio state não conhece. Item de trabalho do `3.2`, não detalhe de polimento.

**O health check do hub vai bater 404, e isso é o esperado.** A target group do hub aponta para os endereços do NLB na porta 80; o pacote chega ao Envoy do gateway com `Host` igual ao **IP**, que não casa nenhum `VirtualService`, e o Istio responde 404. Com o `matcher` default (`200`) todos os targets ficam `unhealthy` sem nada estar errado. Duas saídas: `matcher = "200-404"` (simples, mas aceita um gateway realmente quebrado) ou uma rota de health no `Gateway`/`VirtualService` casando o host do IP. **Preferir a segunda se o tempo permitir; documentar a escolha no código.** Não existe porta de status alcançável daqui — a 15021 é do gateway dentro da spoke, e o listener do NLB só escuta 80.

**O IP do cliente real.** Com ALB na frente, o Istio vê o IP do nó do ALB. O IP do usuário chega em `X-Forwarded-For`, e o gateway precisa de `numTrustedProxies` configurado — senão qualquer política por IP de origem olha para o lugar errado. É config do lado GitOps, não do Terraform.

**O ALB não valida certificado de backend.** Por isso o trecho hub→spoke é HTTP puro de propósito: TLS ali custaria gerência sem ganhar verificação. O TLS que o usuário vê termina no ALB.

**`aws_lb_target_group_attachment` de IP exige `availability_zone`.** Para IP fora da VPC do load balancer, o valor é `"all"`. Omitir dá erro que não explica a causa.

**Ordenação do certificado.** Referenciar `aws_acm_certificate.this.arn` no `aws_lb_listener_certificate` não espera a validação — é preciso referenciar `aws_acm_certificate_validation.this.certificate_arn`. Os dois ARNs são idênticos, então **nenhuma asserção de valor distingue as duas referências** e a mutação passa verde offline (armadilha já catalogada em `aws/terraform/CLAUDE.md`; o sintoma real é certificado `PENDING_VALIDATION` no listener).

**Propagação de DNS.** O registro alias resolve rápido, mas a **validação** do certificado depende do CNAME entrar na subzona e o ACM enxergá-lo — pode levar minutos. O `aws_acm_certificate_validation` bloqueia o apply até lá; não confundir com trava.

## Aceite

`curl https://app.<id>.nonprod.<domínio>/httpbin/get` **da internet, sem túnel**, devolve o workload com TLS válido (sem `-k`).

Verificações intermediárias, na ordem em que quebram:

1. `dig +short app.<id>.nonprod.<domínio>` devolve IPs públicos do ALB.
2. O certificado do cluster aparece no listener (`describe-listener-certificates`).
3. A target group do hub tem os dois endereços do NLB `healthy`.
4. A listener rule casa o host e aponta para essa target group.
5. `X-Envoy-External-Address` na resposta é o IP do **nó do ALB** (`10.1.x.x`), provando que o pacote atravessou hub → TGW → NLB → gateway.

O `3.1` continua verificável em paralelo, pelo túnel, com `curl` direto nos endereços do NLB — se o `3.2` falhar, esse `curl` é o que separa "quebrou no hub" de "quebrou na spoke".

## Custo

+~US$ 16/mês pelo ALB, mais LCU. Sobe para T3 (`connectivity` + `control-plane` + ALB). Como o ALB fica em `connectivity/`, o teardown noturno da 03 já o leva junto.
