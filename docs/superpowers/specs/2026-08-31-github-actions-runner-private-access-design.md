# Acesso privado do runner GitHub Actions à célula (issue #41, obstáculo 2)

Decisão de como um runner **github-hosted** (efêmero, sem infraestrutura própria) alcança o
endpoint privado da API do EKS para aplicar `module.cell`. Não cobre o desenho do trust
OIDC→IAM para o `apply` em si (item 3 da issue #41, próximo passo depois deste) nem o workflow
inteiro — só o mecanismo de rede.

## Contexto

`module.hub` não precisa de rede privada nenhuma: TGW, Client VPN e ALB são criados via chamadas
normais à API da AWS, de qualquer máquina com credencial. **Só `module.cell`** exige alcançar o
endpoint privado — os providers `helm`/`kubernetes` falam com o API server a partir da máquina que
roda o `apply` (mesma exigência documentada em `aws/terraform/CLAUDE.md`, "Endpoint da API do EKS").
Hoje isso só funciona com o túnel do Client VPN conectado por um operador humano.

Gatilho decidido: **manual (`workflow_dispatch`), sob demanda** — não roda em todo push. Isso pesou
contra manter qualquer infraestrutura de rede persistente (runner self-hosted vivo, segundo Client
VPN sempre associado): o custo/complexidade de manter algo de pé para um uso esporádico não se
justifica aqui.

## Abordagens consideradas

| Abordagem | Por que não |
|---|---|
| CodeBuild com `vpcConfig`, disparado via OIDC | Recomendação inicial deste brainstorming — sem lifecycle de runner, ENI nativo na VPC. Preterida pela escolhida abaixo por decisão do usuário; registrada como candidata de produção na issue #45 |
| Runner self-hosted efêmero (EC2 na VPC) | Mais peças para manter (bootstrap, IAM da instância, risco de runner/EC2 zumbi se o job morrer no meio) sem ganho sobre CodeBuild para o gatilho sob-demanda decidido |
| Client VPN mTLS (segundo endpoint, cert em Secrets Manager rotacionado por Terraform) | A doc da AWS confirma: combinar mutual authentication com federated authentication no MESMO endpoint exige os dois juntos, não é alternativa — não dá para reaproveitar o endpoint humano (SAML) sem forçar operador humano a também ter certificado. Precisaria de um SEGUNDO Client VPN endpoint, somando custo (~metade da parcela de Client VPN do hub, hoje ~US$146/mês) por um mecanismo usado sob demanda. Descartada para a PoC; registrada como candidata de produção na issue #45 |
| AWS Verified Access | Desenhado para tráfego HTTP/browser contra ALB/NLB, não para `kubectl`/`helm` genérico sem proxy adicional — descartada, mesma razão já registrada na issue #40 |
| AWS Cloud WAN | Resolve peering entre TGWs multi-região, problema diferente deste (CI→VPC de uma região só) — já descartado em `aws/docs/network/00-topology.md` para o caso mais amplo |

## Decisão

**Reaproveitar o break-glass já existente** (`endpoint_public_access` + `public_access_cidrs` do
`src/cluster`/`src/cell`), automatizado: o job descobre o próprio IP de saída, abre o endpoint da
API do EKS restrito a esse `/32` só pela duração do `apply`, fecha ao final.

Zero infraestrutura nova. O toggle é uma chamada de API do EKS (`UpdateClusterConfig`), não
recriação de recurso — rápido (ordem de segundos a ~1 min), sem custo de infraestrutura parada.

**Postura de segurança aceita, não ignorada:** a API do EKS fica exposta à internet, restrita a um
`/32`, mas continua exigindo autenticação IAM (`aws eks get-token`) — alcançar a porta não basta
para agir no cluster. Ainda assim é superfície de ataque a mais (CVE de auth bypass, DoS),
**aceitável só para PoC**. A issue #45 é onde a decisão de produção (provavelmente CodeBuild ou
ARC-em-cluster) se resolve antes de qualquer uso real.

## Pré-requisito descoberto nesta sessão: o break-glass está QUEBRADO hoje

`regions/<região>/main.tf` não declara nem repassa `endpoint_public_access`/`public_access_cidrs`
para `module.cell` — o bloco `module "cell"` do `main.tf` de cada região simplesmente omite essas
duas chaves. Editar `variables/values.tfvars` (como o `README.md` já documenta) produz só um
warning de "variável não declarada" na raiz regional; `src/cell` sempre usa os próprios defaults
(`false`/`[]`), nunca o valor do humano. **Isto é resíduo da consolidação da ADR 0014** — o
mecanismo funcionava na `control-plane/` antiga e nunca foi re-wired para `regions/<região>/`.

Corrigir este wiring é pré-requisito direto deste design (as duas flags novas do `up-02-region`
dependem exatamente deste caminho existir) — entra no plano de implementação, não é decisão
separada.

## Interface: duas flags novas em `up-02-region`

Sem passthrough genérico de `-var` (evita expor todo o espaço de variáveis do Terraform pela CLI
do script); duas flags nomeadas, cada uma mapeando para um par de `-var` interno:

- `--public-cidr <cidr>` → `-var endpoint_public_access=true -var 'public_access_cidrs=["<cidr>"]'`
- `--close-public-access` → `-var endpoint_public_access=false` (sem `-var public_access_cidrs`:
  o módulo já OMITE o atributo quando o endpoint está fechado — mandar lista vazia explícita seria
  a pegadinha de perpetual diff já documentada em `aws/terraform/CLAUDE.md`)
- nenhuma das duas → comportamento de hoje, inalterado (lê só `values.tfvars`/defaults)

Mutuamente exclusivas — passar as duas juntas é erro de uso, o script recusa.

**Por que `--close-public-access` é uma flag própria, e não "ausência de `--public-cidr`":** se o
cleanup só reaplicasse sem override nenhum, o resultado dependeria do que `values.tfvars` disser
naquele momento — inclusive, se um humano tiver o break-glass manual ligado por outro motivo, o
"cleanup" do CI **fecharia o acesso do humano também**, silenciosamente. A flag explícita não
resolve essa colisão (ver limitação abaixo), mas pelo menos o comportamento de cada chamada é
determinístico e legível no log/YAML do workflow, não dependente de estado externo.

## Fluxo de dados (do workflow, quando existir — não é escopo desta spec)

1. `workflow_dispatch` (região como input) → job github-hosted.
2. OIDC → assume role na conta `cicd` (desenho da policy: issue #41, item 3, spec futura).
3. Descobre o próprio IP público (`curl -s https://checkip.amazonaws.com` ou equivalente).
4. `up-02-region --region <r> --with-cell --public-cidr <ip>/32 --yes`.
5. Passos de validação da célula (já existem como roteiro manual — `HANDOFF.md`).
6. `if: always()`: `up-02-region --region <r> --with-cell --close-public-access --yes`.

## Limitações conhecidas, aceitas para a PoC

- **Job morto sem rodar o passo 6** deixa o endpoint público até a próxima execução. Decisão
  explícita do usuário: sem sweep agendado como rede de segurança — aceitar o risco.
- **Break-glass humano concorrente:** os dois (humano via `values.tfvars`, CI via
  `--public-cidr`/`--close-public-access`) escrevem o mesmo par de variáveis. Rodar o workflow
  enquanto um humano tem o break-glass manual ligado faz o cleanup do CI fechar o acesso do humano
  também. Regra operacional a documentar (não a resolver em código): não usar os dois ao mesmo
  tempo.
- **IP descoberto precisa ser IPv4** — runners github-hosted não garantem IPv6 estável. Assumir
  IPv4; falhar alto (não silenciosamente) se vier outro formato.

## Testes

- `terraform test` (mock) cobrindo os dois `-var` no `src/cluster`/`src/cell` — conferir se a
  cobertura de `endpoint_public_access`/`public_access_cidrs` já existe antes de escrever teste
  novo (evitar duplicar).
- Teste de regressão para o wiring corrigido: `regions/<região>` repassando os dois valores até
  `module.cell` (mutação: trocar o valor e confirmar que o teste denuncia se o repasse sumir de
  novo).
- `up-02-region --help` documentando as duas flags novas.
- `up-02-region` recusa as duas flags juntas (`--public-cidr` + `--close-public-access`).
- Aceite real: `up-02-region --with-cell --public-cidr <meu-ip>/32` seguido de
  `aws eks describe-cluster` confirmando `endpointPublicAccess: true` e o CIDR certo; depois
  `--close-public-access` e confirmar que fecha (`endpointPublicAccess: false`).

## Fora de escopo

- Trust OIDC GitHub→AWS e a policy IAM da role que roda o `apply` (issue #41, item 3).
- O workflow YAML em si, passos de validação da célula, o que fazer em caso de falha do `apply`
  além do que já existe documentado.
- Decisão de mecanismo de produção — issue #45.
- Sweep agendado de fechamento — descartado por decisão explícita, não esquecido.

## Referências

- Issue #41 (workflow GitHub Actions) — obstáculo 2 do corpo original.
- Issue #45 (decisão de produção, aberta nesta sessão).
- Issue #40 (acesso administrativo humano único) — mecanismo pode convergir, ainda sem decisão.
- `aws/terraform/CLAUDE.md`, "Endpoint da API do EKS": o gotcha de `public_access_cidrs` omitido
  vs. vazio, e por que o endpoint fechado exige rota privada.
