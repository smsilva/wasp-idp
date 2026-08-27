# Steps 2.4+2.5 — EKS Private Endpoint

_2026-08-27_


Nada tocou a AWS. Regressão: **111 testes em 13 diretórios, 0 falhas** (eram 104), com **6 mutações
rodadas e 6 capturadas** no root e 1 no módulo.

**O `2.4` foi escrito no plano com uma premissa dupla, e a doc do EKS desfez as duas metades.** O
passo pedia associar a private hosted zone do endpoint do EKS à VPC hub, com plano B de Resolver
inbound endpoint se o lookup se mostrasse frágil.

- **Plano A é impossível, não frágil.** *"Amazon EKS creates a Route 53 private hosted zone on your
  behalf (…) This private hosted zone is managed by Amazon EKS, and it doesn't appear in your
  account's Route 53 resources."* Não há `zone_id` para ler, e não se autoriza associação de zona que
  não é sua. O risco registrado no plano (*"o lookup por hostname é frágil"*) subestimava: não havia
  o que procurar.
- **Plano B é desnecessário, o que é melhor motivo ainda para não construir.** Com o endpoint público
  desligado, *"the cluster's API server endpoint is resolved by public DNS servers to a private IP
  address from the VPC"*. Custaria ~US$ 0,25/h — **mais que o control plane do EKS** — para resolver
  um problema que a AWS já resolve.

**Sobrou o que a doc prescreve para "connected network":** *"your Amazon EKS control plane security
group contains rules to allow ingress traffic on port 443 from your connected network"*. Um recurso,
custo zero, no state da spoke — e a origem é o CIDR da **VPC hub**, não o client CIDR, pelo SNAT já
provado com pacote no `2.3`.

**O `2.5` veio junto porque só junto é verificável** (com o endpoint público ligado, o DNS devolve IP
público e `kubectl` pelo túnel não prova nada), e ficou mais forte do que o plano previa: o endpoint
público fecha **por default**. O `1.2` tinha posto o falha-fechado na variável (*"sem default, quem
aplica é obrigado a declarar o `/32`"*); agora está no flag — **não existe valor de tfvars que
exponha a API ao mundo**, e abrir é break-glass com `generate-tfvars --enable-public-endpoint`, que
só nesse caso descobre o IP da máquina.

Quatro coisas aprendidas na execução, registradas em `aws/terraform/CLAUDE.md`: `public_access_cidrs`
tem de ser omitido, não vazio, com o endpoint fechado (drift detection só corre *"when present in a
configuration"*); consumir atributo de data source num campo validado obriga a overridar esse data
source em todo arquivo de teste da raiz; `local.*` do módulo é alcançável na asserção do teste, não só
`output` e recurso; e asserção entre dois computados não avalia offline.

**Docs atualizadas juntas, como a regra do spec exige:** a camada `06` da sequência de provisionamento
passou de "private DNS" a **dissolvida na `05`** (não sobrou recurso próprio, logo não há raiz nova
nem fronteira de state nova), o índice do dicionário ganhou
`aws_vpc_security_group_ingress_rule` e os dois recursos de Route 53 viraram **`Rejected`** — mantidos
como registro de desenho, com o motivo de cada um (um impossível, o outro desnecessário), não
apagados.

**Falta o `apply`** que prova o caminho privado inteiro (aceite conjunto `2.4`+`2.5`); enquanto ele
não roda, o que existe é código e teste, não comportamento observado.
