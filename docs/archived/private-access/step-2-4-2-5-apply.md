# Steps 2.4+2.5 — Apply And Acceptance

_2026-08-27_


**Aceite conjunto PASSOU, os cinco critérios:** `up-03` aplicado (18 recursos); `aws-vpn-client`
conectado, SAML completou sozinho (sessão SSO do navegador já ativa); `up-04` aplicado com o endpoint
já fechado desde a criação do cluster; `dig +short <endpoint>` devolveu IP de `10.2.0.0/16`
(`10.2.29.144`/`10.2.32.64`) **de primeira, sem precisar do ligar-desligar preventivo cogitado no plano**; `kubectl get
nodes` respondeu com 2 nós `Ready`; túnel desconectado, `kubectl get nodes` travou em timeout (20s,
sem resposta) — nunca devolveu `Unauthorized`. Fase 2 completa.

**O `aws-vpn-client` registrado como instalado no `2.1` não sobreviveu à sessão seguinte** — máquina
sem o binário, teve de ser reinstalado do zero (mesma versão `6.0.1`, mesma URL versionada
`https://d20adtppz83p9s.cloudfront.net/GTK/6.0.1/awsvpnclient_amd64.deb`, sha256 conferido contra as
release notes oficiais da AWS antes do `dpkg --install`). "Instalado nesta máquina" num registro de
sessão anterior não é garantia entre sessões/máquinas diferentes — conferir sempre.

**Mesma classe de achado do `2.3`, duas vezes na mesma sessão: `up-04` morreu no meio por timeout de
processo, não por bug.** A primeira vez por `timeout 100` explícito do operador; a segunda pelo timeout
default de 2 minutos do harness do agente ao rodar `terraform apply | tee log` sem pedir background
explicitamente. As duas vezes a AWS continuou provisionando depois do processo morto — EKS cluster, NAT
Gateway, node group e addon `aws-ebs-csi-driver` todos nasceram na AWS fora do state, e a segunda
tentativa de criar um NAT Gateway novo colidiu de verdade com o Elastic IP já associado ao órfão da
primeira (`Resource.AlreadyAssociated`). Recuperado com a receita já documentada no `CLAUDE.md` desta
pasta: `terraform force-unlock` (uma vez sem precisar do operador, uma vez via `! <comando>` porque o
classifier bloqueou o agente) + `terraform import` de cada órfão + `plan` provando **zero duplicata**
antes de reaplicar. Nenhum recurso foi recriado; o `Apply complete!` final bateu exatamente com o plano
de recuperação (4 to add, 1 to change, 0 to destroy). **Lição operacional, não de código: nunca rodar
um `apply`/`destroy` de vários minutos fora de `nohup ... & disown` (ou do padrão que os `up-NN` já
usam) — o problema não era o Terraform, era a sessão interativa dependurada num apply longo.**

Por causa da recuperação no meio, o tempo total do apply não é comparável ao ~13 min de referência (era
apply único; este foram dois applies mais uma recuperação manual) — não registrar como regressão de
performance.

**Ideia registrada, não implementada, motivada pelo mesmo atrito de "instalação não sobrevive entre
sessões":** cachear o `saml-metadata.xml` no Secrets Manager, em
`docs/superpowers/specs/2026-08-27-saml-metadata-secrets-manager.md`.

**Achado extra do teardown, mesma sessão: o `destroy` tinha o mesmo problema de ordem que o `apply`, na
direção contrária — CORRIGIDO na mesma sessão.** O `depends_on` explícito que a regra de `443` recebeu
para a subida (`CLAUDE.md` desta pasta) não tinha equivalente para a destruição — o `terraform destroy`
real do `control-plane` apagou o `aws_ec2_transit_gateway_vpc_attachment` da spoke (e a rota
`aws_route.spoke_to_hub`) **antes** de terminar de remover o `kubernetes_config_map_v1` e o
`helm_release` do Crossplane, cortando a rota para o endpoint privado no meio do processo
(`dial tcp ...:443: i/o timeout`). Os dois recursos presos não têm contraparte AWS própria — são só
objetos da API do Kubernetes, e o `destroy` do cluster EKS os leva junto de qualquer forma — então
`terraform state rm` dos dois + reaplicar o `destroy` resolveu sem risco de órfão. **Fix aplicado**: os
seis recursos de rede que cortam o caminho ganharam `depends_on` explícito nos quatro consumidores da
API. `terraform validate` + 21 testes offline passam; a aresta em si não é testável offline (mesma
limitação de "ordenação por referência" já catalogada) — só um próximo `destroy` real prova.

**Avaliação registrada, não implementada, sobre a orquestração em si — dois eixos:** se vale trocar o
padrão bash por Terragrunt (avaliado item a item, recomendação é não trocar agora) e o alvo declarado
pelo usuário de tirar agente/humano do loop de provisionamento (pipeline de CI/CD, ainda sem desenho),
em `docs/superpowers/specs/2026-08-27-terraform-orchestration-tooling.md`.
