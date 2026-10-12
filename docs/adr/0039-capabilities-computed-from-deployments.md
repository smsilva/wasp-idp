# Capabilities computed from the Deployments that implement them

**Status:** Aceito (2026-10-12)

## Contexto

O ADR 0034 §4 decidiu que `GET /v1/capabilities` passa a ser calculado, e que "cada controller publica que está vivo e o que atende, no padrão que o `aws_account` já usa (um ConfigMap atualizado por ele)". Até a #269, a rota devolvia um dicionário fixo em `app.py`: só `cloud-account` era calculado, `build` aparecia como `NoProviderForCapability` embora o `scm_github` o atendesse, e `resources` nem aparecia.

Uma capability tem mais de uma implementação e mais de uma instância. Numa organização grande, parte dos repos está no GitHub e parte no Bitbucket (dois drivers de `scm`, com várias connections), e as cloud accounts são de mais de um vendor (dois drivers de `cloud-account`, cada um com a sua base identity). O status de uma capability é o resumo dos seus drivers e das suas instâncias, não o de um objeto só.

Para que cada provider publique um sinal de vida, cada um dos cinco projetos precisaria de uma thread de heartbeat (um `Lease` renovado, ou um ConfigMap). O Kubernetes já sabe se o pod de cada provider está pronto, e a imagem de cada um já carrega a versão (`platform init` marca cada build com o image id).

## Decisão

**A API calcula cada capability a partir dos Deployments que a implementam e do estado que os operadores configuram. Nenhum provider muda.**

- **Cada Deployment se declara por labels:**
  - `platform.wasp.silvios.me/provider` (`scm_github`);
  - `platform.wasp.silvios.me/capabilities`, separadas por ponto (`scm.build`), porque o valor de um label não aceita vírgula;
  - `platform.wasp.silvios.me/vendor` (`github`), quando o provider é o driver de um vendor num subsistema neutro (ADR 0034 §5).
- **A API lista os Deployments com esse label** em `platform-system` e `platform-auth` (RBAC `list` em `deployments` nos dois). Um driver está vivo quando tem réplica pronta, e a versão é a tag da imagem.
- **O status de uma capability**, no vocabulário das conditions (ADR 0022):

  | Status | Regra |
  |---|---|
  | `NoProviderForCapability` | nenhum driver instalado |
  | `Unreachable` | todos os drivers sem réplica pronta |
  | `NotConfigured` | drivers vivos e nada configurado: nenhuma `ScmConnection`, nenhuma base identity |
  | `Degraded` | algo funciona e uma parte não: um driver fora do ar, ou uma connection que não está `Ready` |
  | `Active` | caso contrário |

- **O que conta como configuração é de cada subsistema:**
  - `scm`: as `ScmConnection`s. São dos `platform-admins` e servem a organização inteira, então uma que não está `Ready` degrada a capability.
  - `registry`: os `OCIRegistry`s (ADR 0037), também dos `platform-admins`. Um que não está `Ready`, ou nenhum padrão (um build sem `--registry` recebe `NoDefaultRegistry`), degrada a capability.
  - `build` herda o status de `scm` e de `registry`: um build roda pela connection e faz o push no registry.
  - `cloud-account`: a base identity de cada driver. Uma conta que não está `Ready` é problema do dono dela (ADR 0029): entra no detalhe, contada por vendor e nunca nomeada, e não degrada a capability.
  - `identity`: sem o Google IdP, continua `Active`, com o detalhe e a correção. O login por senha funciona sem ele. O `platform init` anota o Deployment do Keycloak (`platform.wasp.silvios.me/identity-providers`), porque a API não lê o Secret `keycloak-google`.
- **Detalhe por papel:** `platform-users` recebem nome e status; `platform-admins` recebem também drivers, versões, detalhe, correção e as instâncias.
- `platform status` lê `GET /v1/capabilities` e `GET /v1/capabilities/{name}`, e sai com `1` quando alguma capability instalada não está `Active`.

## Alternativas consideradas

- **Um `Lease` renovado por cada provider** (`coordination.k8s.io`, com `renewTime`). Pega também um loop travado com o pod de pé, que a prontidão do Deployment não vê. Custa uma thread de heartbeat em cada provider, e hoje nenhum tem probe que diferencie as duas situações. Fica para quando um loop travado for um problema observado. A API muda só a leitura do sinal; os labels continuam.
- **Um CRD `Provider`**: mais campos que um `Lease`, com schema próprio, e o mesmo custo de escrita nos providers. Rejeitada pelo mesmo motivo.
- **O ConfigMap por provider, como o `aws-base-identity`** (o texto do ADR 0034 §4). O ConfigMap do `aws_account` continua sendo a fonte da base identity, que é configuração e não sinal de vida.

## Consequências

- Altera o "como" do ADR 0034 §4 (o controller não publica nada) e mantém o "o quê": a capability é calculada. O `503 NoProviderForCapability` nas rotas de um subsistema ausente, também do §4, fica para outra issue.
- Um provider novo entra em `platform status` só com os labels no Deployment dele. Um segundo vendor (`scm_bitbucket`, `azure_subscription`) entra como mais um driver da mesma capability, sem mudar a API nem a CLI.
- Um provider com o pod pronto e o loop travado aparece `Active`.
