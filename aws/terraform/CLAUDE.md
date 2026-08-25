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
