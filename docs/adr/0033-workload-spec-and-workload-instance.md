# Workload Spec and Workload Instance replace Promotion

**Status:** Aceito (2026-10-11)

## Contexto

O ADR 0030 decidiu construir o índice de versões e um CRD `Promotion`, um objeto por ato (component, versão do índice, `Environment`), e chamou o conceito de implantação de promoção. Ao desenhar a CLI da #262 pela jornada do dev, dois problemas apareceram:

- **"Promote" pressupõe um ambiente de origem.** No Kargo, no Google Cloud Deploy, no Heroku Pipelines, no Spinnaker e no Codefresh, promover é levar uma versão de um ambiente para o próximo. Num ambiente efêmero, ou no primeiro deploy, não há origem. Quando não há origem, Octopus, Humanitec, Qovery, Radius e Waypoint chamam o ato de deploy.
- **Um objeto por ato não responde "o que está rodando aqui".** Ele registra o que aconteceu, mas a pergunta do dev e do portal é o estado presente de um component num ambiente: versão, saúde, URL. O Port modela isso como um blueprint "Running Service", de onde os dados são coletados.

A jornada também mostrou que um mesmo ambiente pode ter mais de uma instância do mesmo component. O deck descreve o shared sandbox, em que a versão de um PR roda ao lado da estável e recebe tráfego por header.

O desenho completo está em [`docs/superpowers/specs/2026-10-11-workload-instance-design.md`](../superpowers/specs/2026-10-11-workload-instance-design.md).

## Decisão

**O conceito de implantação passa a ser a Workload Instance, uma Workload Spec viva num `Environment`. A `Promotion` do ADR 0030 não é criada; o ato vira uma revisão da instância.**

- **Workload Spec** é o Score (`app-spec.yaml`) de uma versão, imutável, gravado na `Version` do índice. O termo segue o Score, que se define como *workload specification*.
- **Workload Instance** (CRD `WorkloadInstance`, grupo `platform.wasp.silvios.me`) é uma spec viva num ambiente, mantida pela plataforma e fonte dos dados de runtime. É para a Workload Spec o que uma Helm Release é para um Chart.
- **Cada ato é uma revisão** (CRD `WorkloadRevision`), imutável, com o resultado em conditions: deploy, rollback, remove. O número vem do nome (`<environment>.<instance>.<n>`), o que dá concorrência otimista sem lock. É a fonte das métricas DORA.
- **A API escreve só a revisão** pelo `StateWriter` (ADR 0022); um controller aplica no vcluster e mantém a instância. A credencial do destino nunca sai da plataforma, como no ADR 0030.
- **A instância fica fora do catálogo**, assim como o `ResourceRequest` (ADR 0023). O catálogo a mostra como join de leitura.
- **A identidade da instância é (ambiente, nome da instância)**, com o component como atributo. A primeira fatia permite uma instância por component, mas labels, seletor de Service, namespace e plano já são chaveados pela instância, para que instâncias extras e roteamento entrem sem migração.
- **A palavra do usuário é `deploy`** (`platform workload deploy`). "Release" continua reservado ao GitHub Release. "Promote" fica para um futuro gate entre ambientes, que criaria uma revisão nova.

## Consequências

- **Substitui a parte de promoção do ADR 0030.** O índice de versões, o contrato de build e o adiamento do Kargo continuam valendo. Onde o ADR 0022 dizia `Release` e o 0030 dizia `Promotion`, leia `WorkloadRevision`.
- A `Version` ganha o campo `appSpec`, gravado pelo `scm_github`; a validação do Score vai para um lib compartilhado entre o `scm_github` e a API.
- A plataforma mantém um provider novo (`workload`) e dois CRDs em vez de um.
- O deck (#202) troca `release`/`promote` por `workload deploy` e `workload history`.
- O Forager (#263) resolve os resources para a revisão; até lá, uma spec com `resources` termina com `ResourcesNotSupported`.
- Roteamento entre instâncias exige mesh ou Gateway API nos vclusters e propagação de header nas chamadas internas, o que vira contrato do template quando a fase 3 chegar.
