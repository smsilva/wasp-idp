# Step 2.2 — Connectivity Root

_2026-08-26_


TGW isolado por default, certificado do ACM, provider SAML e Client VPN completo, em
`aws/terraform/connectivity/us-east-1/`. **22 testes offline, 14 mutações, 13 capturadas.** Custo até
aqui: zero — nada tocou a AWS além de leitura de documentação.

**Três desvios do esboço, cada um por achado, não por preferência:**

- **O certificado virou público do ACM validado por DNS.** O esboço descartava a opção porque *"cert
  público exigiria o domínio, que só chega no `1.3`"* — e o `1.3` chegou. Compra nenhuma chave privada
  em state nem em disco, e rotação automática que o Client VPN acompanha. Isso **moveu o certificado de
  T0 para T1**, e o argumento sobrevive melhor: a estabilidade que importava (material de client
  inalterado entre recriações) vem da CA pública da Amazon, não da vida longa do recurso.
- **`transit_gateway_configuration` ficou de fora**, apesar de existir e parecer mais direto que
  associar subnet: o attachment que aquele bloco cria leva horas para deletar, o provider não espera, e
  isso impede deletar o TGW — incompatível com destruir a camada toda noite.
- **Subnet privada confirmada como target network.** A exigência de rota para o IGW que preocupava é dos
  *Prerequisites* do tutorial de mutual auth, não dos requisitos de target network.

**O passo que não é código, e a razão:** a aplicação SAML no Identity Center **não pode ser Terraform**
— a API `CreateApplication` só cria aplicação OAuth 2.0 customizada. O `generate-tfvars` para e imprime
o roteiro completo (ACS URL `http://127.0.0.1:35001`, audience `urn:amazon:webservices:clientvpn`,
`Subject` → `${user:email}`, `memberOf` → `${user:groups}`) em vez de deixar o apply falhar num provider
com mensagem que não explica o que falta.

**Cinco coisas aprendidas escrevendo os testes**, todas registradas em `aws/terraform/CLAUDE.md`:

- **Bloco repetível do provider costuma ser SET, não lista** — `authentication_options[0]` não compila
  (*"set elements do not have addressable keys"*). Para bloco único, `one(...)`.
- **`override_resource` substitui os atributos computados por inteiro.** Sobrescrever só o `arn` de
  `aws_acm_certificate` deixa `domain_validation_options` como set vazio, e o erro parece bug do código.
- **Validação de schema do provider roda sob `mock_provider`** — é client-side. O
  `aws_iam_saml_provider` recusa metadata com menos de 1000 caracteres no plan, então a fixture tem de
  ser realista em **tamanho**, não só em forma.
- **Validações de uma variável são todas avaliadas, não param na primeira.** Duas chamando `cidrhost`
  fazem um valor malformado produzir *"Call to function cidrhost failed"* em vez da mensagem que
  explica. Cadeia precisa de guarda `!can(...) || <condição>`.
- **Ordenação por referência não é testável offline.** O endpoint referencia
  `aws_acm_certificate_validation.vpn.certificate_arn` para nascer depois da validação, mas o ARN é
  idêntico ao do certificado — a mutação passa verde. Escrito no teste, não escondido.

O `up-all` mudou: `connectivity` saiu do "roda se o diretório existir" e virou `--with-connectivity`,
pelo mesmo critério de custo da 04. Antes, criar a raiz teria feito o `up-all` ligar ~US$ 110/mês por
default — o oposto do que o script promete.
