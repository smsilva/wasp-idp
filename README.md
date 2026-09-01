# wasp-idp

Plataforma AWS multi-tenant (hub-and-spoke, EKS) com um IDP (Backstage) por cima. Ponto de entrada
único do repo — cada linha abaixo é uma porta para um tronco de documentação.

## Por onde começar

| Se você quer... | Vá para |
|---|---|
| Entender a arquitetura de referência AWS (hub-and-spoke, domínios) | [`aws/docs/README.md`](aws/docs/README.md) |
| Provisionar a plataforma (Terraform, sequência, raízes) | [`aws/terraform/README.md`](aws/terraform/README.md) |
| Usar ou desenvolver o Backstage (IDP) | [`docs/idp/README.md`](docs/idp/README.md) |
| Ver decisões de arquitetura já tomadas (ADRs) | [`docs/adr/README.md`](docs/adr/README.md) |
| Ver o histórico do que já foi entregue | [`docs/archived/README.md`](docs/archived/README.md) |
| Entender por que uma decisão passada foi tomada, ou reler um plano antigo | [`docs/superpowers/README.md`](docs/superpowers/README.md) |
| Retomar de onde a última sessão parou | [`HANDOFF.md`](HANDOFF.md) |

## Convenções deste repo

- `CLAUDE.md` de cada pasta = regras para quem edita ali. `README.md` de cada pasta = índice do
  que existe. Nunca duplicar o mesmo conteúdo nos dois.
- Um documento cobre um assunto; quando uma seção se aprofunda demais num subtema, ela vira um
  arquivo próprio, referenciado de onde fazia sentido.
- Antes de renomear qualquer arquivo `.md`, rodar `scripts/bin/check-doc-links`.
