# GitHub App for ArgoCD repository access

Roteiro do pré-requisito de console que dá ao ArgoCD acesso de leitura ao repositório de GitOps (`wasp-gitops`). Escrito em 2026-08-28, ao destravar o `Known Broken 23` — o ArgoCD da célula sobe sem credencial de repositório, com zero `Application` e nenhum secret de repo, e por isso o lado GitOps do `3.1` foi instalado por `helm upgrade --install` a partir do checkout local. **Enquanto isso não existir, "GitOps instala o chart" é desenho, não estado.**

**Validado ponta a ponta num k3d local antes de tocar na célula** — ver "O que o laboratório k3d provou", incluindo a descoberta de que o repositório era **público**, o que invalidava o teste que se pretendia fazer.

Mesma categoria da aplicação SAML do `2.2` (`02-private-access.md`): passo manual de console que a API não cria, cujo produto entra no Terraform por arquivo ou por secret. Não é preguiça de automatizar — ver "Por que não é Terraform".

## Por que GitHub App e não deploy key SSH

Em PoCs anteriores o caminho foi chave SSH. A App ganha em quatro eixos, em ordem de peso:

| Eixo | GitHub App | Deploy key SSH |
|---|---|---|
| **Vida da credencial** | *installation token* de ~1 h, renovado pelo próprio ArgoCD | chave de vida longa, em disco e em secret, sem rotação |
| **Escopo** | `contents: read` nos repositórios selecionados; uma App serve N repos | por repositório: N repos ⟹ N secrets |
| **Revogação** | suspender a instalação corta tudo de uma vez, no nível da conta | configuração por repositório, fácil de perder de vista |
| **Auditoria** | eventos atribuídos à instalação da App | atribuídos à chave, sem contexto |

O eixo da vida da credencial é o que decide: este repo já tem em aberto o `Known Broken 4` (access key de longa duração do Crossplane), e escolher SSH aqui seria criar de novo, de propósito, o problema que já queremos remover.

**Consequência que a App impõe:** ela autentica por **HTTPS**, não por SSH. O `repoURL` do app-of-apps tem de ser `https://github.com/...`. Ver "O que muda no wasp-gitops".

## Criar a App

`github.com/settings/apps` → **New GitHub App**.

| Campo | Valor | Por quê |
|---|---|---|
| **GitHub App name** | `wasp-gitops` (ou o que preferir) | precisa ser único no GitHub |
| **Description** | opcional | aparece na página pública da App |
| **Homepage URL** | `https://github.com/smsilva/wasp-gitops` | **puramente cosmético.** Só aparece na página pública, para quem fosse instalar a App; numa App server-to-server ninguém visita. É obrigatório porque o formulário exige, não porque algo o consome |
| **Callback URL** | deixar **vazia** | serve ao fluxo de autorização de **usuário** (OAuth). O ArgoCD autentica como a *instalação*, com token derivado da chave privada — não há usuário no caminho |
| **Webhook → Active** | **desmarcar** | marcado, o GitHub tenta entregar evento num endpoint que não existe e a App acumula falha de entrega. O ArgoCD desta PoC descobre mudança por **polling** |
| **Repository permissions → Contents** | `Read-only` | é a única permissão necessária para clonar e ler. `Metadata: Read-only` é anexada automaticamente e é obrigatória |
| **Where can this be installed** | *Only on this account* | o repositório é pessoal; não há outra conta a servir |

**Nada além de `Contents: Read-only`.** Em particular, não conceder `Contents: Read and write` — o ArgoCD desta PoC não escreve no repo (nada de write-back de imagem/tag), e a permissão de escrita transformaria um comprometimento do cluster em comprometimento do repositório.

Depois de criar:

1. Anotar o **App ID**, no topo da página da App.
2. **Generate a private key** → baixa um `.pem`. É a credencial de verdade; ver "Onde guardar o `.pem`".
3. **Install App** → *Only select repositories* → `wasp-gitops`.
4. Anotar o **Installation ID**, que aparece na URL depois de instalar: `.../settings/installations/<installation-id>`.

Os três valores — `App ID`, `Installation ID`, `.pem` — são o que o ArgoCD consome.

## Onde guardar o `.pem`

**Fora dos dois repositórios.** Nem `wasp-idp` nem `wasp-gitops` têm caminho de segredo no `.gitignore`, então um `.pem` largado na árvore entra num `git add .` sem aviso. Sugestão: `~/.secrets/wasp-gitops-argocd.pem`, com `chmod 600`.

Na célula AWS ele não vive em disco: vai para o **Secrets Manager** e chega ao cluster por **ESO** — ver abaixo.

**Antes de escrever qualquer Terraform, confirmar o estado real, não presumir:** a App já foi criada no GitHub (identificadores e caminho local do `.pem` em `CLAUDE.local.md`, gitignored). O que não está confirmado neste documento é se o `.pem`/`App ID`/`Installation ID` **já foram promovidos ao Secrets Manager da conta `cicd`** (região `us-east-1`) ou se isso ainda é um passo manual pendente (`aws secretsmanager create-secret`/`put-secret-value`). Checar `CLAUDE.local.md` primeiro; se o secret não existir na conta, criá-lo é o passo zero desta entrega, antes do `ExternalSecret`.

## Como a credencial chega ao ArgoCD

O ArgoCD lê credencial de um `Secret` no namespace dele, rotulado com um de **dois** tipos — e a escolha entre eles importa:

| Rótulo | O que é | Quando |
|---|---|---|
| `secret-type: repository` | registra **um** repositório explicitamente, casando a `url` inteira | quando se quer a lista de repositórios como inventário |
| `secret-type: repo-creds` | credencial para **qualquer** repositório cuja URL comece pelo prefixo em `url` | quando um dono/organização serve N repositórios |

**Escolhido: `repo-creds`**, com `url` no prefixo `https://github.com/<owner>`. Uma credencial serve o `wasp-gitops` e qualquer repositório futuro do mesmo dono, sem secret novo. É também o padrão já em produção na trilha Azure (módulo `argo-cd` do repo `azure-kubernetes`, caminho em `CLAUDE.local.md`), o que torna a forma comparável entre as duas trilhas.

Consequência a saber: **`argocd repo list` fica vazio** com `repo-creds` puro — a credencial aparece em `argocd repocreds list`. Procurar no comando errado leva a concluir que nada foi configurado.

As chaves, para GitHub App:

```yaml
stringData:
  type: git
  url: https://github.com/<owner>          # PREFIXO com repo-creds; URL exata com repository
  githubAppID: "<app-id>"                  # NUMÉRICO — ver armadilha do Client ID
  githubAppInstallationID: "<installation-id>"
  githubAppPrivateKey: |
    -----BEGIN RSA PRIVATE KEY-----
    ...
```

**A `url` casa por string com a `repoURL` das `Application`** — prefixo, no caso de `repo-creds`. Divergência silenciosa (inclusive um `.git` sobrando de um lado só, quando se usa `repository`) aparece como *"repository not accessible"* mesmo com credencial correta.

Dois caminhos de entrega, e a diferença entre eles é o ponto do exercício local:

**No k3d de laboratório:** `kubectl create secret generic` com `--from-file=githubAppPrivateKey=<pem>`. Nunca colar a chave na linha de comando — ela iria para o histórico do shell. Rápido, descartável, não exige AWS.

**Na célula (camada 04): pelo `extraObjects` do próprio chart do ArgoCD**, como um `ExternalSecret` que o ESO materializa a partir do Secrets Manager. O módulo `src/helm/modules/argo-cd` já aceita `var.extra_values` como segundo documento de values (`main.tf:41`), mecanismo genérico e testado. **O que NÃO existe ainda, apesar do comentário no código sugerir o contrário:** o `clientSecret` do OIDC é só um placeholder (`$oidc.<nome>.clientSecret`, `main.tf:9`) com um comentário dizendo que "o ESO o mescla com `creationPolicy: Merge`" — mas `install_argocd_oidc = false` na célula real, e não existe nenhum `ExternalSecret` de OIDC escrito em lugar nenhum do repo. Este será o **primeiro** `extraObjects`/`ExternalSecret` de fato escrito e testado neste módulo, não a cópia de um exemplo que já funciona.

**Isto resolve a pergunta de ownership**: não existe `Secret` criado fora do release brigando com ele — o `ExternalSecret` é entregue **pelo próprio release**, e o ESO é o dono do `Secret` resultante (`creationPolicy: Owner`, porque é um secret novo, não uma mesclagem). Forma, com o escape que Helm exige para os templates do ESO:

```yaml
extraObjects:
  - apiVersion: external-secrets.io/v1
    kind: ExternalSecret
    metadata:
      name: argocd-repo-creds-github
    spec:
      refreshInterval: 1h0m0s
      secretStoreRef:
        kind: ClusterSecretStore
        name: <store da célula>
      target:
        name: argocd-repo-creds-github
        creationPolicy: Owner
        template:
          type: Opaque
          metadata:
            labels:
              argocd.argoproj.io/secret-type: repo-creds
          data:
            type: git
            url: |
              {{`{{ .url | toString }}`}}
            githubAppID: |
              {{`{{ .appId | toString }}`}}
            githubAppInstallationID: |
              {{`{{ .installationId | toString }}`}}
            githubAppPrivateKey: |
              {{`{{ .privateKeyBase64 | b64dec | toString }}`}}
      data:
        - secretKey: privateKeyBase64
          remoteRef:
            key: <prefixo>/argocd-github-app-private-key-base64
        # ... appId, installationId, url
```

**Guardar o `.pem` em base64 no Secrets Manager e fazer `b64dec` no template** é o truque que a trilha Azure já usa, e existe por um motivo: PEM é multilinha, e multilinha sobrevive mal a passar por JSON de secret e por template. Base64 é uma linha só.

**Conferido em `aws/terraform/control-plane/main.tf` (`module.pod_identity_eso`): a policy já é `Resource = "*"` em `secretsmanager:GetSecretValue`/`DescribeSecret` — não há prefixo restringindo nada hoje.** Não é preciso "descobrir" prefixo; a decisão em aberto é se vale apertar a policy para um prefixo específico (hardening) antes ou depois deste wire — não bloqueia a entrega.

**`ClusterSecretStore`/`SecretStore` não existe em lugar nenhum do repo** — nem na célula real, nem no lab k3d de referência (confirmado por busca no repo; os logs de `destroy` da camada 04 mostram literalmente o aviso padrão do ESO "you will need to set up a SecretStore"). Criar o `ClusterSecretStore` é parte do trabalho desta entrega, não uma verificação de algo pré-existente.

## O que muda no `wasp-gitops`

Duas mudanças que a App exige, e uma lacuna que ela revela. Nenhuma é opcional.

**1. `repoURL` de SSH para HTTPS.** O default em `infrastructure/charts/applications/values.yaml` é `git@github.com:smsilva/wasp-gitops.git`. Decidido em 2026-08-28: **não trocar o default** — ele serve a outra trilha, e não se sabe quem depende da deploy key hoje. Cada cluster ganha um values overlay com HTTPS (`values-k3d.yaml`, `values-aws.yaml`), aditivo e visível em diff. Precedente: `values-kind.yaml` já usa HTTPS.

**2. `AppProject infra` não existe em lugar nenhum.** Todo `Application` do app-of-apps declara `project: infra` por default, mas o projeto não está versionado no `wasp-gitops` nem é criado pelo módulo `argo-cd` da camada 04 (é um `helm_release` puro, sem `project` nem configuração de repositório). Sem o projeto, o ArgoCD recusa a `Application` com erro que não nomeia o projeto como causa.

Decidido em 2026-08-28: o `AppProject` nasce **onde o ArgoCD nasce** — `kubectl` no laboratório, Terraform na célula. Não pode vir por GitOps: ele precisa existir *antes* de qualquer `Application` sincronizar, e só chegaria *por* uma `Application`. Bônus de fazer assim: as restrições do projeto (repositórios e destinos permitidos) passam a ser guardrail real em vez de decoração.

**3. `values-kind.yaml` está velho** — aponta para `infrastructure/raw/ingress-nginx-kind`, e `infrastructure/` só contém `charts/`. Não serve de base para o overlay novo.

## Armadilhas

**O `httpbin` de `infrastructure/charts/` renderiza Ingress com `ingressClassName: "nginx"`, e o k3d vem com Traefik.** O objeto é criado, mas nunca ganha `status.loadBalancer.ingress` — e o health check nativo do ArgoCD para `Ingress` espera exatamente isso. A `Application` fica em `Progressing` para sempre, o que se lê como falha sem ser. No laboratório, desligar `ingress.enabled`. O chart não renderiza nenhum CRD do Istio, então sincroniza num k3d puro — essa parte não é problema.

**Polling, não webhook.** Sem webhook, o ArgoCD descobre mudança por polling (3 min por default no 3.5.1). Um `httpbin` que não aparece logo depois do push é isso, não credencial. `argocd app get <app> --refresh` força.

**Token de instalação expira em ~1 h.** É o comportamento desejado, mas muda o que um erro significa: falha de autenticação *depois de horas funcionando* aponta para chave privada revogada ou instalação suspensa, não para configuração errada — configuração errada falha na primeira tentativa.

## Por que não é Terraform

A API do GitHub **não cria GitHub App**. `POST /app-manifests/{code}/conversions` existe, mas exige um `code` produzido por uma sequência de navegador (a conversão de *app manifest*), então não há caminho headless. Mesma forma da aplicação SAML do Identity Center no `2.2`, onde `CreateApplication` só cria OAuth 2.0 customizado — e a mesma consequência: o produto do passo manual entra no Terraform como **dado** (arquivo ou secret), nunca como recurso.

Registrado como ideia, não implementado: cachear os três valores no Secrets Manager para não perdê-los entre máquinas, exatamente como `2026-08-27-saml-metadata-secrets-manager.md` propõe para o `saml-metadata.xml`. O `.pem` já vai para lá pelo caminho da célula; o que falta é o `App ID`/`Installation ID` não viverem só num handoff.

## O que o laboratório k3d provou (2026-08-28)

Exercitado antes de tocar na célula, exatamente para as surpresas aparecerem barato. Cluster `k3d-argocd-lab` (1 server — o gotcha de quórum do etcd neste host está em `aws/CLAUDE.md`), chart `argo-cd` **10.4.0** (ArgoCD 3.5.1, a mesma versão da célula, senão o teste não transfere).

Provado, na ordem em que quebra: `argocd repocreds list` mostra o prefixo → `AppProject infra` existe → `Application` `Synced`/`Healthy` → `curl /get` pelo Service devolve o JSON do httpbin → nenhum `Ingress` criado.

### O repositório era PÚBLICO, e isso invalidava o teste inteiro

`gh repo view` devolveu `"visibility":"PUBLIC"`. Duas consequências, e a segunda é a lição:

**O `Known Broken 23` do `HANDOFF.md` estava factualmente errado** ao afirmar que o `wasp-gitops` é privado. A conclusão que dependia disso — o ArgoCD não consegue puxá-lo sem credencial — não se sustentava: ele conseguiria anonimamente.

**Com repo público, um sync bem-sucedido não prova autenticação nenhuma.** O `httpbin` subiria igual com a GitHub App ausente, quebrada ou com chave inválida, e o wire seria declarado funcionando sem uma linha dele ter sido exercitada. O repositório foi fechado (`private`) antes de continuar. Risco conferido antes de fechar: as composite actions em `actions/` são referenciadas **só pelo próprio repo**, e referência interna sobrevive ao fechamento.

### Sync verde não é prova: exigir o vermelho

Mesmo com o repo já privado, o primeiro `Synced` **não** provava autenticação — o ArgoCD podia estar servindo de cache um clone feito enquanto o repo era público (o commit sincronizado era o mesmo lido antes do fechamento). A prova exige mutação, a mesma disciplina dos testes de Terraform:

1. Apagar o `Secret` de repo-creds.
2. **Reiniciar o `argocd-repo-server` e o redis** — sem isso o cache responde e o teste dá falso verde.
3. `argocd app get --hard-refresh` tem de falhar com `ComparisonError: ... authentication required: Repository not found.`
4. Recriar o secret → volta a `Synced`.

Sem o passo 3 vermelho, o passo 4 verde não significa nada. Confirmado nos dois sentidos.

### `ingress.enabled` do chart httpbin é decorativo

O value óbvio para suprimir o Ingress **não faz nada**: `.Values.ingress.enabled` é lido apenas pelo `NOTES.txt`. O gate real dos dois templates é `global.environment.cluster.ingress.type` (`nginx` ou `azure`), com default **`nginx`**. Qualquer outro valor (usei `none`) suprime os dois.

Importa porque o k3d vem com **Traefik**, não nginx: o `Ingress` seria criado, nunca ganharia `status.loadBalancer.ingress`, e o health check nativo do ArgoCD para `Ingress` deixaria a `Application` em `Progressing` para sempre — falso negativo. (O laboratório de referência em `~/git/kubernetes/lab/argo/argocd` resolve por outro caminho: desliga o Traefik no `k3d cluster create` e instala o nginx ingress controller.)

### O `AppProject` precisa das duas whitelists

Além de `sourceRepos` e `destinations`, o projeto precisa de `clusterResourceWhitelist` e `namespaceResourceWhitelist`. Sem elas o sync falha com `resource not permitted in project` — e charts de infraestrutura criam `Namespace`, `CustomResourceDefinition` e `ClusterRole`. Incluídas preventivamente no laboratório; a restrição que faz o projeto valer a pena sobre o `default` é a `sourceRepos` (`https://github.com/<owner>/*`).

## Aceite

O `httpbin` de `infrastructure/charts/httpbin` sincroniza no cluster de laboratório a partir do repositório privado, sem nenhuma credencial em disco além do `.pem` fora da árvore, e os pods ficam `Running`.

Verificações na ordem em que quebram:

1. `argocd repocreds list` mostra o prefixo. **Não `argocd repo list`** — esse fica vazio com `repo-creds` puro, e olhar no comando errado leva a concluir que nada foi configurado.
2. `kubectl -n argocd get appproject infra` existe.
3. `argocd app get httpbin` mostra `Synced` e a `Application` não está presa em `Progressing` por causa do Ingress.
4. `kubectl port-forward` no Service e `curl localhost:<porta>/get` devolve o JSON do httpbin.

Se o passo 1 passa e o 3 falha com erro de autenticação, o problema é pareamento de URL (prefixo do secret vs. `repoURL` da Application), não credencial.
