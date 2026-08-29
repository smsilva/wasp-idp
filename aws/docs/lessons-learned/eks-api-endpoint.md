# Lessons learned — EKS API endpoint

Fato + porquê, um por linha. Narrativa completa de cada achado, quando existe, em
[`docs/archived/`](../../../docs/archived/index.md).

- **A private hosted zone do endpoint privado é invisível na conta** — a AWS a cria e associa à
  VPC do cluster, mas ela não aparece nos recursos de Route 53 da conta. Qualquer desenho que
  dependa de associá-la a outra VPC está morto na origem.
- **Com o público fechado, o DNS público resolve para IP privado.** Não precisa de Resolver
  inbound endpoint, zona própria nem `dns_servers` no Client VPN. Ressalva da doc: cluster que já
  existia e não resolve privado se corrige ligando e desligando o acesso público uma vez.
- **O que a doc exige para rede conectada por TGW é `443/tcp` no security group do CLUSTER** — é
  ele que governa o endpoint privado, e `public_access_cidrs` não o afeta. Origem: o CIDR do
  **hub** (SNAT).
- **`public_access_cidrs` omitido, nunca vazio, quando o endpoint público está desligado** — o
  provider só faz drift detection do atributo *"when present in a configuration"*, e `[]`
  brigaria para sempre com o `0.0.0.0/0` que a EKS guarda.
- **O `depends_on` que abre o caminho no `apply` não protege o `destroy` na direção contrária.** O
  TGW attachment e a rota da spoke podem ser destruídos antes de o Terraform terminar de remover o
  `kubernetes_config_map_v1`/`helm_release` do Crossplane, cortando a rota até o endpoint no meio
  do processo (`i/o timeout`, não credencial). Fix: `depends_on` explícito nos seis recursos de
  rede apontando para os quatro consumidores da API. Só um `destroy` real prova a aresta.
