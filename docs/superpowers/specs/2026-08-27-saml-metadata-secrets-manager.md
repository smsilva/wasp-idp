# SAML metadata do Client VPN: cachear no Secrets Manager

**Status:** ideia registrada, não implementada. Sem decisão de desenho fechada — é ponto de partida
para quem pegar a tarefa.

## Problema

`aws/terraform/connectivity/us-east-1/saml-metadata.xml` é passo de console, não Terraform (a API
`CreateApplication` do Identity Center só cria aplicação OAuth 2.0 customizada — ver
`02-private-access.md`, seção "O passo de console, clique a clique"). O arquivo é gitignored de
propósito, porque identifica a instância de Identity Center de quem roda.

Consequência observada na prática: numa troca de máquina (ou perda do arquivo local), o
`generate-tfvars` da camada `connectivity/` falha pedindo o download manual de novo — mesmo a
aplicação `hub-client-vpn` já existindo no Identity Center (nesse caso o caminho no console muda:
**Applications → nome da aplicação → Actions → Edit configuration**, em vez do fluxo de criação).
Repetir esse passo manual a cada máquina/sessão é o atrito que esta ideia elimina.

## Ideia

Guardar o conteúdo do XML baixado num secret do Secrets Manager, na conta `network` (mesma conta
onde o `aws_iam_saml_provider` é criado, e onde já existe o padrão `poc-idp/crossplane-poc-credentials`
para outro tipo de credencial — mesmo prefixo `poc-idp/` faria sentido: `poc-idp/saml-metadata-hub-client-vpn`).

Fluxo proposto para o `generate-tfvars` da camada `connectivity/`:

1. Se `saml-metadata.xml` existe localmente, usar como hoje.
2. Se não existe, tentar buscar do secret antes de falhar — `aws secretsmanager get-secret-value`
   com o profile `network`. Se achar, escrever o arquivo local e seguir.
3. Se o secret também não existe (primeira vez, ou secret nunca criado), cair no comportamento atual:
   imprimir o walkthrough e sair pedindo o download manual.
4. **Depois de um download manual bem-sucedido**, o próprio `generate-tfvars` (ou um script novo,
   `save-saml-metadata`) sobe o conteúdo para o secret, resolvendo o ovo-e-galinha — a próxima
   máquina/sessão não precisa mais do passo de console.

## Coisas a decidir antes de implementar

- **Conta dona do secret.** `network` é a candidata óbvia (mesma conta do IAM SAML provider), mas
  cabe confirmar que o profile usado pelo `generate-tfvars` (hoje `--org-profile personal` para
  Identity Center/Organizations, `--network-profile network` para o resto) tem permissão de escrita
  em Secrets Manager nessa conta.
- **Rotação.** O certificado dentro do metadata do Identity Center pode rotacionar (a AWS gerencia
  isso). Não há hoje um jeito barato de saber se o XML cacheado no secret ficou velho — na pior
  hipótese, o Client VPN falha na validação e o sintoma seria confuso sem uma nota apontando para cá.
  Precisa de um plano de invalidação (TTL? checagem de data de criação do secret contra alguma
  heurística?) ou aceitar o risco documentado.
- **Custo.** Secrets Manager cobra por secret armazenado (~US$ 0,40/mês) — comparável ao restante do
  "custo recorrente: só centavos" já tolerado pelo repo (ex.: a subzona de DNS), mas é custo novo,
  não zero.
- **Segurança.** O metadata SAML não é credencial de acesso por si (é a chave pública do IdP, não uma
  privada), mas ainda identifica a instância do Identity Center — mesma classe de sensibilidade que
  hoje justifica o gitignore. Convém restringir o secret aos mesmos principals que já leem
  `poc-idp/crossplane-poc-credentials`, não abrir mais que isso.
- **Onde entra no código.** Provavelmente um script irmão de
  `aws/terraform/connectivity/us-east-1/scripts/generate-tfvars` (mesmo padrão "só leitura, valida
  antes de escrever arquivo" descrito no `CLAUDE.md`), não um novo passo dentro do `up-03-connectivity`.

## Não faz parte desta ideia

- Automatizar a criação da própria aplicação SAML — isso continua impossível via API (limitação do
  provider Identity Center, não deste repo).
- Guardar segredos de outras camadas (o TGW, o certificado ACM, etc.) — esses já são geridos pelo
  Terraform normalmente; só o metadata SAML tem esse problema por não ser um recurso Terraform.
