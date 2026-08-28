# Orquestração do Terraform: ferramenta e quem dirige a execução

**Status:** avaliação, não implementada. Sem decisão fechada — ponto de partida para quem pegar a
tarefa. Motivada por atrito real de uma sessão de execução (2026-08-27), não por preferência a priori
por ferramenta. Dois eixos distintos e ortogonais: **qual ferramenta** estrutura os arquivos
(Terragrunt vs. o padrão bash atual) e **quem dirige a execução** (agente/humano interativo vs.
pipeline de CI/CD). O primeiro é avaliado e a recomendação é não trocar agora; o segundo é alvo
declarado, ainda sem desenho.

## Contexto

O aceite conjunto `2.4`+`2.5` (`docs/superpowers/plans/2026-08-26-private-access-and-ingress/`) foi a
primeira vez, nesta máquina, que a sequência completa de subida (`state-backend` → `network-foundation`
→ `dns` → `connectivity` → túnel → `control-plane`) rodou do zero. Três atritos concretos apareceram, e
nenhum é bug de código — são lacunas de **orquestração** em torno de módulos Terraform corretos:

1. **Versão do binário incompatível com todos os 14 `versions.tf` do repo** (`required_version = ">=
   1.15"`, binário instalado em `1.14.8`). Sem `tfenv`/`asdf` na máquina — o binário é gerenciado à
   mão em `~/bin/terraform`. Descoberto só ao rodar `terraform init` na primeira camada.
2. **`-backend-config="bucket=tfstate-o-e4r8ndteju"` repetido em 6 raízes** (`grep -rln 'backend "s3"'
   aws/terraform --include=*.tf` conta 6). O valor é o mesmo em todas — `CLAUDE.md` desta pasta já
   documenta a razão de o bucket ficar fora do `versions.tf` (evitar hardcode), mas o preço é digitar
   o mesmo `-backend-config` seis vezes, uma por raiz, uma por máquina.
3. **Um `apply` interrompido por engano deixou lock órfão no S3 — duas vezes, na mesma sessão.** A
   primeira por `timeout 100` explícito; a segunda pelo timeout **default de 2 minutos do próprio
   harness do agente** ao rodar `terraform apply | tee log` sem pedir background explicitamente — a
   mesma classe de erro, disfarçada. As duas vezes, a AWS continuou provisionando depois do processo
   morrer (exatamente o que `CLAUDE.md` desta pasta já descreve): EKS cluster, NAT Gateway, node group
   e addon `aws-ebs-csi-driver` todos nasceram na AWS sem entrar no state local, e um deles (o NAT
   Gateway do segundo apply, tentando reusar o mesmo Elastic IP do primeiro) chegou a falhar por
   conflito genuíno (`Resource.AlreadyAssociated`). Recuperado com `terraform force-unlock` + `terraform
   import` de cada órfão + `plan` provando **zero duplicata** antes de reaplicar — a receita já estava
   escrita no `CLAUDE.md`, só nunca tinha sido exercida nesta sessão. O lock em si é do backend S3
   puro — nenhuma camada de orquestração muda isso; o que teria evitado os dois incidentes é nunca
   rodar um `apply`/`destroy` fora de `nohup ... & disown` ou do padrão que os scripts `up-NN` já usam
   (que, por sinal, o harness já backgrounda sozinho quando invocado como está — o erro nas duas vezes
   foi um comando de terraform solto, fora do script `up-NN`, escrito à mão no meio de uma recuperação).

A pergunta do usuário: **Terragrunt** resolveria essa classe de atrito? Vale adotar?

## O que já existe e por quê (não repetir sem reler)

`aws/terraform/CLAUDE.md` e `aws/terraform/README.md` já documentam decisões deliberadas nesta
direção:

- **Escopo fino, cardinalidade × churn** (`decisions.md` §7, ligado de
  `docs/superpowers/specs/2026-08-25-terraform-bootstrap-module-design.md`): Terraform entrega o que
  se cria uma vez por região; GitOps entrega o que muda toda semana. Adicionar uma camada de
  orquestração é o tipo de decisão que esse princípio pede para revisitar antes de ampliar, não
  ignorar.
- **A sequência de subida já é executável, não só documentada**: `aws/terraform/scripts/up-NN-<camada>`
  + `up-all`, na ordem de dependência, com custo e nível de permanência por camada. Isso é, em
  essência, um orquestrador caseiro — pequeno, mas já resolve "rodar na ordem certa".
- **`scripts/lib`, sourced por todo `up-NN`**: log com timestamp, captura de exit code via
  `PIPESTATUS[0]`, confirmação antes de aplicar, descoberta do bucket — uma vez só, não duplicado por
  script.
- **Cada raiz tem seu próprio `generate-tfvars`**, que não é geração de arquivo comum: valida contra a
  AWS **antes** de escrever (VPC única por tag, CIDR livre, região aprovada na SCP, bucket existente) e
  falha com mensagem específica em vez de deixar o `plan` falhar longe da causa.

## Avaliação — o que o Terragrunt resolveria, o que não

| Atrito | Terragrunt resolve? | Como / por quê não |
|---|---|---|
| `-backend-config` repetido em 6 raízes | **Sim** | `remote_state` num `terragrunt.hcl` raiz, herdado por `include` — gera o bloco `backend` e roda `init` sozinho. Elimina a duplicação real observada. |
| Ordem de subida (00→01→02→03+túnel→04) | **Parcial** | `dependency`/`dependencies` blocks expressam o grafo e `run-all apply` respeita a ordem — mas o passo manual do túnel (console, não Terraform) continua fora do grafo de qualquer jeito. E o repo já tem isso via `up-NN` + comentário de dependência no próprio script. |
| Camadas pagas (03, 04) fora do `up-all` por default | **Não nativo** | Terragrunt não tem o conceito "essa unidade custa dinheiro, não entra no run-all sem flag". Precisaria de convenção própria (tag/exclude por padrão de diretório), reconstruindo o que `up-all --with-connectivity --with-control-plane` já faz em bash. |
| `generate-tfvars` com validação contra a AWS antes de escrever arquivo | **Não** | É lógica de negócio específica (CIDR livre, VPC única por tag, SCP aprovada), não geração de config. Terragrunt gera `inputs` a partir de `dependency.outputs` ou valores estáticos — não substitui uma checagem "essa combinação é segura antes de eu escrever qualquer coisa". Continuaria sendo script bash, chamado antes do `terragrunt plan`. |
| Versão do binário do Terraform incompatível | **Não diretamente** | Terragrunt tem `terraform_version_constraint` para **falhar cedo com mensagem clara** se a versão for errada — mas não baixa nem troca o binário. Quem resolve isso é um gerenciador de versão (`tenv`, sucessor do `tfenv`, ou `asdf` com plugin terraform) lendo um `.terraform-version`/`.tool-versions` versionado. Terragrunt e gerenciador de versão são ortogonais; os dois juntos cobririam o atrito #1 by acidente, mas o gerenciador de versão sozinho já resolve. |
| Lock órfão após apply morto | **Não** | Lock é do backend S3 (`DynamoDB`/S3 conditional write), não da ferramenta de orquestração. Terragrunt herda o mesmo mecanismo do Terraform puro. |
| Log com timestamp + captura de exit code correta | **Não precisa** | Já resolvido por `scripts/lib`, sourced. Terragrunt não muda esse comportamento — a saída de `run-all` teria de passar pelo mesmo tratamento se alguém quisesse manter o padrão. |

## Custo de adotar

- **Nova dependência de toolchain** (`terragrunt` binário, versão própria para pinar) — mais uma
  ferramenta para instalar/atualizar em toda máquina que rodar este repo, incluindo o mesmo tipo de
  problema do atrito #1 (versão do binário) aplicado a uma segunda ferramenta.
- **Reescrita de todas as 6+ raízes** para o layout Terragrunt (`terragrunt.hcl` por diretório,
  `include`/`generate` para backend e provider) — trabalho real, não incremental, e sob o mesmo
  princípio de cardinalidade × churn que já limitou o escopo do Terraform: são 6 raízes hoje, não 60.
  O ponto de virada em que orquestração declarativa paga o próprio custo geralmente é dezenas de
  módulos com combinações de ambiente (dev/staging/prod × regiões) — não é o formato deste repo.
- **Nenhum dos dois atritos mais dolorosos da sessão (versão do binário, lock órfão) é resolvido por
  Terragrunt em si** — são resolvidos por um gerenciador de versão e por disciplina operacional
  (nunca matar um apply com `timeout`), respectivamente.

## Um eixo diferente, e mais importante: tirar o agente/humano do loop (alvo declarado, 2026-08-27)

Terragrunt-vs-bash é uma pergunta sobre **qual ferramenta estrutura os arquivos**. Há uma pergunta
ortogonal e mais urgente, levantada pelo usuário na mesma sessão que motivou este documento: **quem
dirige a execução**. Hoje é sempre um humano ou um agente, de um laptop, rodando `up-NN` um a um,
plantado em frente ao log de um `apply` de 10+ minutos, pronto para recuperar à mão se algo morrer no
meio. **O alvo é a subida do hub/control-plane sair desse modelo** e virar automação independente —
pipeline de CI/CD, não sessão interativa. Já é meta registrada no `CLAUDE.md` raiz do repo ("CI/CD via
GitHub Actions"); esta sessão deixou claro que o Terraform-como-está não chega lá sozinho.

**Evidência da própria sessão de por que isso importa, não é só principle:** dois `apply` desta sessão
morreram no meio por timeout — um por engano do operador (`timeout 100`), um pelo timeout default de
2 minutos do harness do agente. Os dois deixaram recurso órfão na AWS fora do state, recuperado por
`terraform force-unlock` + `import` + `plan` sem duplicata. Um pipeline de CI não tem esse problema
por natureza — não existe timeout de "sessão de chat" numa GitHub Actions job rodando um `apply` de 13
minutos. **A fragilidade não era do Terraform; era de rodar um apply de vários minutos dependurado
numa sessão interativa.**

O que concretamente falta para esse alvo, descoberto por atrito real e não por suposição:

1. **Dois passos são literalmente manuais, não automatizáveis como estão.** A aplicação SAML no
   Identity Center (a API `CreateApplication` só cria OAuth 2.0 customizado — `CLAUDE.md` desta pasta)
   e o download do metadata XML dela. Uma pipeline pode **consumir** um metadata já cacheado (é
   exatamente a ideia já registrada em
   `docs/superpowers/specs/2026-08-27-saml-metadata-secrets-manager.md`), mas não pode fazer o
   clique-a-clique da primeira vez — isso continua sendo bootstrap humano, uma vez por Identity Center,
   não por execução.
2. **O endpoint privado do EKS só é alcançável hoje pelo túnel do Client VPN de um operador humano**
   (SAML + navegador). Um runner do GitHub Actions hospedado pela GitHub não tem rota para dentro da
   VPC privada. Portas possíveis, nenhuma escolhida ainda: runner self-hosted vivendo dentro da VPC
   hub/spoke; CodeBuild com configuração de VPC; ou algum mecanismo de VPN máquina-a-máquina distinto
   do fluxo SAML pensado para pessoa. **Decisão de desenho própria, não trivial** — o mecanismo de
   acesso privado inteiro (`2.1`-`2.5`) foi desenhado assumindo um operador humano.
3. **Credencial teria de trocar de modelo.** Hoje é cadeia de profiles pensada para sessão interativa
   (`personal` via SSO → `network`/`cicd` via `OrganizationAccountAccessRole`). CI usa OIDC do
   GitHub Actions assumindo role diretamente — outro desenho de trust, não extensão do atual.
4. **Applies de 10+ minutos deixam de ser problema, não continuam sendo.** É argumento a favor da
   migração, não obstáculo: CI não tem o teto de tempo de uma chamada de ferramenta de agente que
   causou os dois incidentes desta sessão.
5. **Recuperação de órfão continua existindo como classe de risco** (processo de CI pode morrer por
   outros motivos — timeout de job, runner reciclado) mas fica mais rara e mais fácil de tornar segura:
   uma pipeline pode adotar a receita já documentada (`force-unlock` + `import` + `plan` sem duplicata)
   como step automatizado de recuperação, em vez de intervenção manual.

**Não desenhado aqui de propósito** — é maior que este documento e merece spec própria quando alguém
pegar a tarefa: qual runner/rede resolve o item 2, layout de workflow do GitHub Actions, quais camadas
entram na pipeline primeiro (as de custo zero/centavos são candidatas óbvias de começar; `connectivity`
e `control-plane`, por serem T1/T2 com custo por hora, precisam de gatilho explícito, não merge
automático — mesma cautela que hoje vive em `--with-connectivity`/`--with-control-plane`).

## Recomendação (não decisão — para quem pegar a tarefa avaliar)

**Não trocar a orquestração por Terragrunt agora.** A avaliação linha a linha mostra que ele resolve
de verdade só um atrito (duplicação de `-backend-config`), que tem solução mais barata dentro do
padrão já existente (ver abaixo), e que os dois atritos que mais custaram tempo na sessão são
ortogonais à ferramenta.

Correções pontuais, mais baratas, no padrão já estabelecido pelo repo:

1. **Fixar a versão do Terraform num arquivo versionado** (`.terraform-version`, formato lido por
   `tfenv`/`tenv`/`asdf`) e documentar no `README.md` desta pasta como parte do preflight — mesmo
   lugar onde hoje já vive a checagem do `aws-vpn-client --version`. Resolve o atrito #1 sem nova
   ferramenta de orquestração.
2. **Fatorar o `-backend-config` para dentro do `scripts/lib`** (já lido por todo `up-NN`), em vez de
   repetir a string em cada script/comando manual — reduz a duplicação real sem trocar a stack.
   Já existe precedente: `scripts/lib` já descobre o nome do bucket.
3. **Item já no backlog do `HANDOFF.md` (Next Steps → Frente D) que ataca a mesma dor por outro
   ângulo:** um script `status`/`platform-status` que responde "o que está de pé e quanto custa/h" —
   não é sobre ordem de apply, mas sobre a mesma classe de "orquestração que falta", e é mais barato
   que adotar uma ferramenta nova.

Se a topologia crescer de verdade — múltiplas contas spoke com o mesmo conjunto de camadas repetido
por spoke, várias regiões em paralelo — revisitar esta avaliação nesse momento, não antes. É o mesmo
critério que `decisions.md` §7 já aplica ao escopo do Terraform.
