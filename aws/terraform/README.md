# Terraform — bootstrap da plataforma AWS

Substitui o bootstrap por k3d + Crossplane. Desenho em
`docs/superpowers/specs/2026-08-25-terraform-bootstrap-module-design.md`; planos em
`docs/superpowers/plans/2026-08-25-terraform-network-foundation.md` (camada 1) e
`docs/superpowers/plans/2026-08-25-terraform-control-plane.md` (camada 2).

## Raízes

| Raiz | Conta | State key | Entrega | Estado |
|---|---|---|---|---|
| `state-backend/` | `network` | `state-backend/` | O bucket de state, uma vez, sem região | **aplicada** |
| `network-foundation/us-east-1/` | `network` | `network-foundation/us-east-1/` | VPC hub `10.1.0.0/16` | **aplicada** |
| `network-foundation/us-west-2/` | `network` | `network-foundation/us-west-2/` | VPC hub `10.3.0.0/16` | **aplicada** |
| `control-plane/` | `cicd` | `control-plane/` | VPC spoke `10.2.0.0/16`, EKS, ESO, ArgoCD, Crossplane | **aplicada** |

A camada 2 aplicou 39 recursos num único `terraform apply`, sem `-target`: EKS 1.36, dois nós
`t3.medium`, três Pod Identities e os três charts. Prova o que estava em aberto no desenho — os
providers `kubernetes` e `helm` configurados a partir de outputs do módulo do cluster resolvem
na hora do apply. **Não** inventar apply em duas fases.

A VPC hub entra por `data "aws_vpc"` filtrando `tag:Name` num provider `aws` aliasado com o
profile `network` — não por `terraform_remote_state`. O acoplamento é ao recurso, não ao arquivo
de state da camada 1. O filtro tem de devolver exatamente um id, senão quebra no plan;
`control-plane/scripts/generate-tfvars` confere isso antes de gerar arquivo.

### Por que o bucket de state tem raiz própria

Ele guarda o state de **todas** as camadas e regiões. Enquanto vivia junto da
`network-foundation` de `us-east-1`, um `terraform destroy` daquele hub levaria junto o mapa de
toda a infraestrutura. Numa raiz própria, nenhum destroy de região o alcança — o bucket não está
no state de nenhuma delas. Fix estrutural, não guarda por convenção.

Somam-se duas proteções: `prevent_destroy = true` no recurso, e `force_destroy = false` (default)
— a AWS recusa deletar bucket não-vazio, e ele nunca estará vazio.

### Uma raiz por região, não uma raiz com `-reconfigure`

Cada região tem diretório e state key próprios. A alternativa — uma raiz só, alternando backend
com `terraform init -reconfigure` — tem um footgun permanente: esquecer de trocar o backend antes
do apply mistura as regiões, e nada no Terraform pega isso. Os valores de região, CIDR e AZs
ficam **inline** em cada `main.tf`: são decisões de desenho documentadas
(`aws/docs/network/01-cidr-addressing.md`), não segredo.

Isolamento verificado: `terraform plan -destroy` em `us-west-2` mostra 13 recursos, zero menção
ao bucket ou ao CIDR de `us-east-1`.

### Alocação de CIDR

Supernet `10.0.0.0/12`, um `/16` por VPC. N=0 reservado à Organization, N=1 e N=3 em uso, N=2
para o `control-plane`. **Teto de 15, e região multiplica** — ver
`aws/docs/network/01-cidr-addressing.md`. É a única decisão irreversível da cadeia.

**A VPC spoke nunca pode ser separada do state do cluster.** No teardown, o egress
*pod → subnet privada → NAT → IGW → API do ELB* precisa sobreviver até o último nó sair; o grafo
de dependências do Terraform garante isso somente dentro de um mesmo state. Separar
`rede | cluster` reintroduz o bug do NLB órfão sem o mecanismo que o compensava na Composition
de referência (as ~40 `ClusterUsage`).

O corte `hub | spoke+cluster` é seguro **hoje** porque não há TGW: os nós não roteiam pelo hub.
Quando o TGW entrar, este raciocínio precisa ser revisitado.

## Pré-requisitos

- `aws sso login --profile personal` ativo.
- Profiles locais `network` e `cicd` assumindo `OrganizationAccountAccessRole`.
- `terraform.tfvars` preenchido em cada raiz (gitignored; valores em `CLAUDE.local.md`).
- Para a camada 2: a conta `cicd` na OU `Deployments`. **Já existe** — criada em 2026-08-25.

## Submódulos

| Submódulo | Equivale a | Notas |
|---|---|---|
| `src/network` | XR `Network` (L1a) | 16 recursos com NAT ligado. Subnets derivadas do CIDR com `cidrsubnet()`, não fixas — por isso serve qualquer região sem alteração |
| `src/state-backend` | — | Bucket de state endurecido, com `prevent_destroy` |
| `src/cluster` | XR `Cluster` (L1b) | EKS `authentication_mode = "API"` (sem `aws-auth` ConfigMap), role do cluster, role compartilhada dos nós, access entries e os dois addons de base |
| `src/nodegroup` | idem | Node groups por mapa. `ignore_changes` no `desired_size` para não brigar com autoscaler futuro |
| `src/pod-identity` | trust de Pod Identity das Compositions | Molde dos três consumidores. O trust precisa de `sts:AssumeRole` **e** `sts:TagSession` — só o primeiro falha |
| `src/helm/modules/{external-secrets,argo-cd,crossplane}` | XR `ClusterBootstrap` | Um chart por módulo, versão fixada |

Sobre `src/pod-identity` e `src/cluster`: o trust e o `assume_role_policy` usam `jsonencode()`,
não `data "aws_iam_policy_document"`. Com `mock_provider`, o data source devolve string sintética
— a assertion sobre `sts:TagSession` passaria sem verificar nada. Com `jsonencode` é o próprio
Terraform que computa o documento, e o teste vê o valor real.

## Nova região

Duas coisas, nesta ordem. A SCP vem primeiro — sem ela o `apply` falha no `CreateVpc`, não no
código:

```bash
cd ../docs/accounts/scripts
AWS_PROFILE=personal ./apply-baseline-service-control-policy --regions us-east-1,<nova-região>
```

Isso vale para a **Organization inteira**, não só para a conta `network`. Depois, copiar um
diretório de região existente e ajustar região e CIDR (N livre do supernet):

```bash
cp -r network-foundation/us-west-2 network-foundation/<nova-região>
# editar main.tf (region, CIDR, AZs) e versions.tf (key do backend)
cd network-foundation/<nova-região>
terraform init -backend-config="bucket=<state-bucket-name>"
terraform plan -out=hub.tfplan
terraform apply hub.tfplan
```

Nenhuma linha de `src/network` muda — foi feito reutilizável e há teste provando que a
aritmética de CIDR acompanha o valor recebido.

## Ordem de apply

O `bucket` do backend fica fora do `versions.tf` porque é valor real; entra por
`-backend-config`. O `profile` **está** no bloco de backend de propósito: o backend é
inicializado antes de o provider ser configurado, então não herda `profile` do bloco `provider`.

A camada 2 tem três scripts em `control-plane/scripts/`, nesta ordem:

```bash
cd control-plane
./scripts/generate-tfvars                              # descobre e valida; só leitura
terraform init -backend-config="bucket=<state-bucket>"  # o bucket sai do script acima
./scripts/apply                                        # plan, confirma, aplica, guarda o log
```

O `generate-tfvars` falha **antes** de gerar arquivo se a tag da VPC hub não for univoca, se o
CIDR pedido já estiver em uso na conta, se a região não passar na SCP ou se o bucket não existir
— erros que de outro modo apareceriam no meio do apply, com recursos já criados atrás.

O `apply` lê o exit code por `PIPESTATUS[0]`: o `tee` sempre retorna 0, e sem isso um apply que
falhou passaria por sucesso. Os logs vão para `control-plane/logs/`, gitignored — a saída carrega
account id, ARN e endpoint reais.

## Ordem de teardown

**Inverso do apply: `control-plane` antes de `network-foundation`.**

Dentro de uma camada a ordem é de graça — é o grafo de dependências do Terraform. O que **não**
é de graça: XRs que o Crossplane tenha criado dentro do cluster depois do bootstrap. Eles não
estão no state, e destruir o cluster primeiro deixa recurso AWS órfão sem controlador. Antes de
destruir a `control-plane`:

```bash
kubectl get managed     # tem de vir vazio
kubectl get composite   # idem
```

Se não vier vazio, deletar os XRs e esperar a reconciliação terminar **antes** do
`terraform destroy`.

`control-plane/scripts/destroy` faz essa checagem antes de chamar o Terraform. Ele também
confere que o contexto corrente do `kubectl` casa com o cluster do state: o contexto pode estar
apontando para o k3d `control-plane`, e um `get managed` vazio no cluster errado é pior que
nenhuma checagem.

## Testes

Sem credencial, sem chamada à AWS — `mock_provider` + `command = plan`:

```bash
for module in src/network src/state-backend src/cluster src/nodegroup src/pod-identity \
              src/helm/modules/external-secrets src/helm/modules/argo-cd \
              src/helm/modules/crossplane \
              network-foundation/us-east-1 network-foundation/us-west-2 control-plane; do
  (cd "${module}" && terraform init -backend=false && terraform test)
done
```

Hoje: 45 testes em 11 diretórios, 0 falhas.

Cada raiz de região testa que seu CIDR **cai dentro do supernet**. Essa validação vivia na
variável `hub_vpc_cidr` da raiz única; com os valores inline ela viraria um buraco silencioso,
e um typo no CIDR é irreversível depois de aplicado.

### Duas limitações do framework que já custaram tempo

1. **`command = plan` só avalia valores conhecidos antes do apply.** ID de subnet não é um
   deles, então `aws_nat_gateway.this[0].subnet_id == aws_subnet.public[0].id` não compila.
   Saída: `override_resource` com `override_during = plan`, dando IDs conhecidos — e
   **distintos** entre pública e privada, senão a assertion passa mesmo com o NAT na privada.
2. **Alguns blocos são `set`, não `list`.** `aws_s3_bucket_server_side_encryption_configuration.this.rule[0]`
   falha com "cannot index a set value"; é preciso um `for`. E com `length(...) == 1`, porque
   `alltrue([])` é `true` e um `for` sem checar tamanho passaria com zero regras.

Assertion nova sobre propriedade que importa merece **teste de mutação**: quebre a
implementação de propósito e confirme que o teste falha. Duas das assertions atuais eram vazias
até isso ser feito.

## Custo

A camada 1 tem **custo recorrente zero**: VPC, subnets, IGW, route tables e bucket vazio não
cobram por hora, e o NAT está desligado (sem TGW, nada roteia pelo hub — ligá-lo custaria
~US$ 32/mês servindo zero tráfego). O bucket cobra armazenamento e requisições, na casa de
centavos.

A camada 2 é a que custa: **~US$ 165/mês** — EKS control plane ~73 + NAT ~32 + 2×`t3.medium` ~60.
Números anteriores de ~US$ 105 omitiam os nós. O NAT aqui é deliberado, ao contrário do hub: sem
TGW não há egress pelo hub, e os nós dependem dele para chegar à API do EKS e aos registries.

Por isso a camada 2 não fica de pé entre sessões de trabalho — sobe, valida, desce
(`control-plane/scripts/destroy`). O state fica no bucket, então subir de novo é o mesmo
`generate-tfvars` + `apply`.
