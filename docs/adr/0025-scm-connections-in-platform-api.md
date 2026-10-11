# SCM connections in the Platform API: ScmConnection CRD, GitHub App via manifest flow, SecretStore

**Status:** Aceito (2026-10-11)

## Contexto

O spec do catálogo (`docs/superpowers/specs/2026-10-10-platform-catalog-design.md`, decisão 6) e o ADR 0023 definiram que `platform catalog component create` cria o repo da aplicação pelo golden path, a partir de um template (ADR 0024). Para isso, a Platform API precisa saber **em qual organização de código criar repos e com que credencial**.

Hoje quem cria repos é o scaffolder do Backstage (`idp/templates/python-service/template.yaml`, `publish:github` em `github.com?owner=wasp-foundry`), com o GitHub App `wasp-foundry-backstage` (ADR 0018). A chave fica só no arquivo local do Backstage. A Platform API não tem nenhuma integração com plataforma de código.

A plataforma começa pelo GitHub (org `wasp-foundry`) e depois atende GitLab, Bitbucket e Azure DevOps.

O nome do conceito é **scm connection**. "provider" foi descartado porque já tem dois donos (providers de capacidade da plataforma e providers do Crossplane). "SCM" é o termo do Backstage (`ScmIntegrations`) e do ArgoCD (SCM Provider generator); "connection" é o termo do Azure DevOps (*service connection*). Uma connection representa uma org do GitHub, um group do GitLab, um workspace do Bitbucket ou uma organization+project do Azure DevOps.

## Decisão

**A Platform API é dona das connections com plataformas de código; cada connection é um `ScmConnection` neutro de vendor, e a credencial vai do vendor direto para um cofre atrás da API, sem passar pela CLI nem pelo disco de ninguém.**

- **`ScmConnection` é um CRD do grupo `platform.wasp.silvios.me`**, namespaced em `platform-system`, com `spec.vendor: github | gitlab | bitbucket | azure-devops` e um bloco por vendor.
  - Uma connection pode ser marcada como **padrão**. `component create` usa a padrão, ou a que vier em `--scm <nome>`. O dev não precisa saber em que org o código mora.
- **Só `platform-admins` criam, alteram ou removem connections**, porque uma connection dá poder de criar e apagar repos na org inteira. Times trazendo a própria org fica para depois.
- **No GitHub, um App por papel** (continua o ADR 0018): o App novo `wasp-foundry-platform` é da Platform API, com as permissões de repositório `administration`, `contents`, `workflows` e `pull_requests` em escrita e `metadata` em leitura, instalado em todos os repos da org.
- **Manifest flow é o caminho padrão no GitHub:**
  1. A API gera o manifesto com as permissões acima e um `state` de uso único, criado por um admin autenticado.
  2. O navegador envia o manifesto ao GitHub, e o admin confirma.
  3. O GitHub redireciona ao callback da API com `code`; a API troca o código pela chave (`POST /app-manifests/{code}/conversions`) e a grava direto no cofre.
  4. O `setup_url` do App leva de volta à API depois da instalação na org, com o `installation_id`.
  - Alternativa para um App que já existe: `--app-id` mais `--private-key-file`.
- **Primeiro segredo atrás da Platform API**, antecipando o que o ADR da #192 deixaria para quando a chave estática entrasse:
  - **Interface `SecretStore` por target.** No `local`, um Secret do Kubernetes em `platform-system`; na nuvem, o cofre nativo via External Secrets Operator.
  - **Segredo é write-only na API:** não volta em nenhuma rota, não vai para o CRD, nem para a projeção, nem para o journal.
  - **O journal passa a ter redação explícita** (`<redacted, sha256:…>`). Hoje `platform/api/src/platform_api/journal.py` grava o `spec` completo.
- **Validação por condition**, no padrão do ADR 0022: `Ready=True` com reason `Verified`; `Ready=False` com `AppNotCreated`, `NotInstalled`, `NotAllRepositories` ou `MissingPermissions`.
- **Outros vendors** entram como outro bloco do mesmo objeto, cada um com a credencial nativa dele: group access token ou OAuth app no GitLab, workspace access token no Bitbucket, service principal com workload identity no Azure DevOps. CLI e API não mudam.

## Consequências

- Passam a existir rotas da API que o navegador chama sem JWT (o callback do manifest flow e o `setup_url`). Elas são protegidas pelo `state` de uso único criado por um admin autenticado.
- A chave do App é o segredo mais poderoso do target local: ela cria e apaga repos na org.
- O manifest flow exige navegador, então o `scripts/demo/cli-smoke` não o exercita; a #199 decide se o smoke pula o passo ou usa uma connection já registrada.
- Quando a criação de repo passar para a plataforma, o `wasp-foundry-backstage` pode cair para só leitura (discovery, ADR 0020). Fica registrado, sem mudar agora.
- O scaffolder do Backstage e a plataforma convivem criando repos até a fatia 2 do catálogo migrar o golden path.
- Templates em repos privados (ADR 0024) passam a ler o conteúdo com a credencial da connection.
- O `SecretStore` e a redação do journal são reaproveitados pelas cloud accounts (#192), que seguem o mesmo padrão de objeto e handshake.
- A implementação da fatia GitHub é a #199.
