# Lessons learned — Terraform layers

Fato + porquê, um por linha. Narrativa completa de cada achado, quando existe, em
[`docs/archived/`](../../../docs/archived/index.md).

- Referência funcional do provisionamento EKS são as Compositions Crossplane, não o chart
  `aws/eks/chart/templates/`.
- Corte de teardown é `hub | spoke+cluster`, nunca `rede | cluster` — Terraform destrói em ordem
  reversa só dentro do mesmo state, e o corte sobrevive ao TGW (AWS recusa deletar TGW com
  attachment vivo).
- EBS CSI pertence à abstração `Cluster` (L2b) conceitualmente, mas **não pode nascer no módulo
  `src/cluster`**: ele consome uma Pod Identity association que só o chamador cria. Mora em
  `src/cell`, com `depends_on` explícito — ver o item da race, abaixo.
- Trust de Pod Identity exige `sts:TagSession` além de `sts:AssumeRole`.
- `authentication_mode = "API"` — sem `aws-auth` ConfigMap.
- `Network` de referência tem as 4 subnets hardcoded em `172.16.{1,2,3,4}.0/24` — não herdar.
- ~~Race de Pod Identity do EBS CSI não existe no Terraform — o grafo já ordena addon depois da
  association.~~ **FALSO, e caro.** O grafo não ordenava nada: `aws_eks_addon` e
  `module.pod_identity_ebs_csi` não se referenciam, então o Terraform os criava em paralelo. Na run
  `33505550033` (01/09/2026) o addon começou 7s **antes** da association e o apply morreu 20min
  depois com `DEGRADED`. Corrigido movendo o addon de `src/cluster` para `src/cell` com
  `depends_on = [module.pod_identity_ebs_csi, module.nodegroup]`. **A lição de segunda ordem é a que
  vale: "o grafo já ordena" só é verdade se existir uma referência de dado entre os dois recursos.**
  Ausência de `depends_on` não é evidência de ordenação — é evidência de ausência de ordenação.
- Race de Pod Identity **não se conserta com timeout.** Os env vars (`AWS_CONTAINER_CREDENTIALS_FULL_URI`
  + volume do token) são injetados por webhook na **admissão** do pod, uma vez; pod spec é imutável,
  então restart nunca recupera e esperar mais só adia a falha. O sintoma que denuncia isto: nós
  `Ready` e association existindo há minutos, e o addon ainda `DEGRADED`.
- Nunca fixar versão de Kubernetes/chart/addon em documento de plano. A `kubernetes_version` é
  default de variável, fixada no código e revisada a olho contra a doc do EKS ao subir — não mais
  descoberta (o `describe-cluster-versions` do antigo `generate-tfvars` fazia a versão do cluster
  mudar sozinha entre dois applies da mesma árvore).
- `curl | tr` engole a falha do `curl` (exit code é o do `tr`) — sem pipe, `--fail`, e validar
  também o formato da resposta (portal cativo devolve HTML com 200).
- **Reachability dependia de onde a AWS resolveu pôr as ENIs do endpoint privado.** A rota para o
  supernet existia só nas route tables privadas, mas tanto o cluster (que recebe as 4 subnets)
  quanto o ALB do hub (que vive nas públicas) podem estar do outro lado. Corrigido nas duas
  camadas (`8731fae`, `bfdc1da`). **Regra geral: rota para a malha existe em TODAS as route tables
  da VPC, ou o alcance é sorteado a cada apply.** Auditar qualquer camada nova sob essa lente — e
  desconfiar de `i/o timeout` atribuído a `depends_on` sem antes conferir a tabela de rotas da
  subnet onde o recurso realmente nasceu.
- **`terraform_plan_and_apply` ignora plano que só muda OUTPUT.** A contagem é
  `grep --count '^  # '`, que conta recursos, então um plan com apenas `Changes to Outputs` é
  reportado como "nothing to change" e o output nunca chega ao state. Se um script passar a
  depender de output novo, forçar um apply que o materialize.
