# CLAUDE.md — aws/terraform/

Camada Terraform do bootstrap. Estrutura, ordem de apply e as duas limitações do framework de
teste estão no `README.md` desta pasta — ler antes de mexer. Aqui ficam só as armadilhas que
custaram tempo e não são visíveis no código.

## Fronteira: o que é Terraform e o que não é

Terraform entrega o que se cria uma vez por região e revisa com cuidado; GitOps entrega o que
muda toda semana (`../../decisions.md` §7, cardinalidade × churn). O escopo fino está fechado em
`docs/superpowers/specs/2026-08-25-terraform-bootstrap-module-design.md` — **não ampliar sem
revisitar aquela decisão.**

A **especificação funcional do provisionamento EKS são as Compositions Crossplane** do repo de
referência interno (caminho em `CLAUDE.local.md`), não as fases do chart `aws/eks/chart/templates/`.
As fases são a mesma coisa menos decomposta e com bugs já corrigidos do outro lado.

## State

- **Nunca pôr o bucket de state no state de uma região.** Ele guarda o mapa de tudo; destruir a
  região levaria o mapa junto. Raiz própria em `state-backend/`, com `prevent_destroy`.
- **`profile` precisa estar DENTRO do bloco `backend "s3"`.** O backend é inicializado antes de o
  provider ser configurado, então não herda `profile` do bloco `provider`. Omitir dá erro de
  credencial no `init`, não no `apply`.
- **`bucket` fica fora do `versions.tf`** (valor real) e entra por `-backend-config`. A `key`
  fica no arquivo, porque carrega a região e é o que separa os states.
- Migração de state entre raízes: blocos declarativos, não `state rm` na unha. `removed` com
  `lifecycle { destroy = false }` solta sem destruir; `import` adota do outro lado. Plan limpo é
  o critério de parada de cada passo.
- Trocar a `key` de um state existente: copiar o objeto no S3 para a nova key, `init` na nova
  raiz, conferir `state list` e `plan -detailed-exitcode` = 0, e só então apagar a key antiga.

## Testes

- `terraform test` com `mock_provider` + `command = plan` roda **sem credencial e sem tocar a
  AWS**. É o ciclo red-green padrão aqui; usar antes de qualquer `apply`.
- **`terraform init -backend=false` num diretório só com `tests/` falha** com `unknown provider`.
  Criar o `versions.tf` primeiro; o teste continua vermelho pelo motivo certo.
- **Assertion nova sobre propriedade que importa exige teste de mutação:** quebrar a
  implementação de propósito e confirmar que o teste falha. Duas assertions desta base eram
  vazias até isso ser feito — uma comparava dois valores desconhecidos, outra usava
  `alltrue([])`, que é `true`.
- Validação que vive numa `variable` some quando os valores viram inline. Ao mover valores para
  dentro do `main.tf`, transformar a validação em assertion de teste — senão vira buraco
  silencioso. Foi o que aconteceu com a checagem de supernet do CIDR.

## Providers `kubernetes` e `helm`

- **Configurar os providers a partir de outputs do módulo do cluster e aplicar tudo num
  `terraform apply` único funciona** — a configuração do provider só precisa estar resolvida
  na hora de configurá-lo, já no apply. Não inventar apply em duas fases com `-target`.
- O que quebra é **data source** desses providers durante o plan. Manter o que for
  Kubernetes como `resource`.
- **`-target` volta a ser necessário noutro caso:** um data source que fica "known after
  apply" cascateia para os providers e faz o Terraform propor recriar **todos** os
  `helm_release`. Sintoma: plan propondo substituir releases sem motivo.
- No **provider `helm` 3.x o `kubernetes` virou atributo**, não bloco: `kubernetes = { ... }`
  com `exec = { ... }` dentro. Exemplo vivo da composição inteira (AKS + ArgoCD + Istio) em
  `examples/cluster_argocd_ingress_istio` do repo `azure-kubernetes` (caminho em
  `CLAUDE.local.md`).

## Versões de chart

- **Conferir no repositório, nunca herdar** do repo interno de referência nem dos scripts de
  `aws/eks/scripts/` — ambos ficaram para trás.
- **O ArtifactHub indexa o canal `master` do Crossplane**, que publica release candidates.
  Para o `stable`, ler `https://charts.crossplane.io/stable/index.yaml` direto.
- ESO 2.9.0 **não serve mais** `external-secrets.io/v1beta1` nem `v1alpha1`. Manifestos
  `ExternalSecret` têm que ser `v1`.

## Load balancer: quem é dono do quê

- **`src/network` NÃO aplica as tags de descoberta do AWS Load Balancer Controller** —
  `kubernetes.io/role/elb` nas públicas e `kubernetes.io/role/internal-elb` nas privadas. Sem elas o
  LBC não encontra onde criar load balancer e o sintoma é obscuro. Bug latente, não hipótese.
- **`TargetGroupBinding` aceita target group criado fora do controller** — verificado na doc do LBC,
  que descreve provisionar o load balancer *"completely outside of Kubernetes"* e ainda gerenciar os
  targets pelo Service. Campos: `targetGroupARN`, `targetType: ip`, `serviceRef`, `vpcID` e
  `networking.ingress` (é este que faz o controller cuidar das regras de SG para targets IP).
  Consequência: **Terraform pode ser dono do NLB/target group sem quebrar o apply único** — o
  workload entra depois só registrando pods. Ressalva: o CR pode referenciar qualquer target group,
  então em cenário multi-tenant exige RBAC.

## Rede

- **TGW nasce com `default_route_table_association` e `default_route_table_propagation` LIGADOS.**
  Desligar os dois é o que torna isolamento por tenant possível — com eles ligados todo attachment
  aprende todo mundo.
- **Ler IPs privados de um NLB é frágil** (`aws_lb` não os expõe; o caminho usual é caçar ENI por
  descrição). **Fixar** com `subnet_mapping { private_ipv4_address = cidrhost(<cidr>, N) }`:
  determinístico, conhecido em tempo de plan, e estável entre recriações.
- **`client_cidr_block` do Client VPN precisa de /22 ou maior e não pode sobrepor VPC nem rota.**
  Carvar fora do supernet.

## Raiz com dois providers de cloud

Sem credencial do segundo provider, o `plan` falha mesmo para mudança que só toca o primeiro. Manter
o recurso da outra cloud atrás de um `local.manage_*` para poder desligar sem editar o resto.

## Custo

- **`enable_nat_gateway = false` nos hubs é deliberado**, não esquecimento: sem TGW nada roteia
  pelo hub, e cada NAT custaria ~US$ 32/mês servindo zero tráfego. Há teste cobrindo a ausência
  do EIP. Ligar só quando o TGW entrar.
- Antes de qualquer `apply`, conferir no plan que não aparecem `aws_nat_gateway` nem `aws_eip`
  onde não deveriam. VPC, subnets, IGW, route tables e bucket vazio não cobram por hora.

## Regiões

- Uma raiz por região (`network-foundation/<região>/`), com `key` de backend própria. **Não**
  usar uma raiz só alternando backend com `init -reconfigure`: esquecer de trocar mistura as
  regiões e nada no Terraform pega isso.
- Região, CIDR e AZs ficam **inline** em cada `main.tf` — são decisões de desenho documentadas em
  `../docs/network/01-cidr-addressing.md`, não segredo.
- **Aprovar a região na SCP antes do `apply`** (`../docs/accounts/CLAUDE.md`). Sem isso o erro
  aparece no `Create*`, parecendo bug de código.
- CIDR é a **única decisão irreversível da cadeia**. Supernet `10.0.0.0/12`, um `/16` por VPC,
  teto de 15, e região multiplica.
