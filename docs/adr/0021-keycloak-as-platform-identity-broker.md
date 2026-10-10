# Keycloak as the platform identity broker

**Status:** Aceito (2026-10-10)

## Contexto

A plataforma expõe uma **Platform API** como fronteira única. A CLI `platform`, o portal Backstage e os agentes externos falam só com ela, nunca direto com Crossplane, ArgoCD ou o resolvedor. A API precisa de identidade com usuários e grupos (`platform-admins`, `platform-users`), e a CLI precisa de login interativo no estilo do `az login`: navegador ou device code.

A primeira ideia era encadear Dex → Keycloak → Google. Dois fatos a descartaram:

- **Grupos.** Com conta Google pessoal, fora do Workspace, o Google não fornece grupos. Eles precisam morar em algum lugar, e o Dex não guarda usuários nem grupos; o Keycloak guarda.
- **Fluxos.** O Keycloak implementa nativamente o Authorization Code com PKCE e o Device Authorization Grant (RFC 8628). Com ele, o Dex seria um segundo broker sem função.

## Decisão

**O Keycloak, sem Dex, é o broker de identidade da plataforma.**

- **Google autentica, Keycloak autoriza.** O Google entra como Identity Provider do realm `platform`. Os grupos `platform-admins` e `platform-users` vivem no Keycloak. Todo usuário novo cai em `platform-users`, e o e-mail passado em `platform init --admin` entra em `platform-admins` por um mapper do Identity Provider, sem senha padrão de admin.
- **A Platform API valida o JWT do Keycloak:** assinatura via JWKS, `iss`, `aud` contendo `platform-api` e expiração. Ela lê os grupos da claim `groups`.
- **A CLI usa o client público `platform-cli`.** O padrão é Authorization Code com PKCE e redirect em `127.0.0.1`; `--use-device-code` usa o Device Authorization Grant, para SSH, containers e máquinas sem navegador.
- **O realm é declarado como código** (keycloak-config-cli) e aplicado pelo `platform init`.

## Consequências

- O Keycloak vira componente com estado. No perfil local, ele roda em `start-dev`, com banco embutido; fora dele, precisa de Postgres.
- O hostname público do Keycloak precisa ser fixo (`KC_HOSTNAME`). O issuer gravado no token vem dele, e a Platform API, de dentro do cluster, compara contra esse valor público enquanto busca o JWKS pela URL interna. Sem isso, a validação falha.
- O Google só aceita redirect para `localhost` ou para domínio público. Por isso, no perfil local, o Keycloak é exposto em `localhost`.
- Trocar ou somar provedores (Entra ID no perfil `azure`, GitHub) é só outro Identity Provider no mesmo realm. CLI e Platform API não mudam.
- O Backstage continua autenticando direto no Google (`idp/packages/backend/src/googleAuthModule.ts`). Migrá-lo para o Keycloak fica em aberto e não é decidido aqui.
