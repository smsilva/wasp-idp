# Terraform — bootstrap da plataforma AWS

Substitui o bootstrap por k3d + Crossplane. Desenho em
`docs/superpowers/specs/2026-08-25-terraform-bootstrap-module-design.md`; plano da camada 1 em
`docs/superpowers/plans/2026-08-25-terraform-network-foundation.md`.

## Camadas

| Camada | Conta | State | Entrega | Estado |
|---|---|---|---|---|
| `network-foundation` | `network` | S3, `network-foundation/terraform.tfstate` | VPC hub, bucket de state | **aplicada** |
| `platform-cell` | `cicd` | S3, `platform-cell/terraform.tfstate` | VPC spoke, EKS, ESO, ArgoCD, Crossplane | não escrita |

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
| `src/network` | XR `Network` (L1a) | 16 recursos com NAT ligado. Subnets derivadas do CIDR com `cidrsubnet()`, não fixas |
| `src/state-backend` | — | Bucket de state endurecido. Só o `network-foundation` usa |

## Ordem de apply

```bash
cd network-foundation
cp terraform.tfvars.example terraform.tfvars   # preencher
terraform init -backend-config="bucket=<state-bucket-name>"
terraform plan -out=foundation.tfplan
terraform apply foundation.tfplan
```

O `bucket` do backend fica fora do `versions.tf` porque é valor real; entra por
`-backend-config`. O `profile` **está** no bloco de backend de propósito: o backend é
inicializado antes de o provider ser configurado, então não herda `profile` do bloco `provider`.

## Ordem de teardown

**Inverso do apply: `platform-cell` antes de `network-foundation`.**

Dentro de uma camada a ordem é de graça — é o grafo de dependências do Terraform. O que **não**
é de graça: XRs que o Crossplane tenha criado dentro do cluster depois do bootstrap. Eles não
estão no state, e destruir o cluster primeiro deixa recurso AWS órfão sem controlador. Antes de
destruir a `platform-cell`:

```bash
kubectl get managed     # tem de vir vazio
kubectl get composite   # idem
```

Se não vier vazio, deletar os XRs e esperar a reconciliação terminar **antes** do
`terraform destroy`.

## Testes

Sem credencial, sem chamada à AWS — `mock_provider` + `command = plan`:

```bash
for module in src/network src/state-backend network-foundation; do
  (cd "${module}" && terraform init -backend=false && terraform test)
done
```

Hoje: 17 testes, 0 falhas.

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

A camada 2 é a que custa: EKS control plane ~US$ 73/mês + NAT ~US$ 32/mês + nós.
