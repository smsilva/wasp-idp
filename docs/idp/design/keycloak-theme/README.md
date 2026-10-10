# Keycloak Theme

Mockups da fase 1 da #173: o tema das telas do Keycloak (realm `platform`, `http://localhost:8180`) e da página de callback do `platform login`. Hoje todas usam o tema padrão `keycloak.v2`. Nada aqui altera o Keycloak; a implementação é a fase 2, depois da aprovação.

Os arquivos são HTML autocontidos e abrem direto no navegador. Os dados são fictícios (`voce@example.com`).

| Proposta | Arquivo | Ideia |
|---|---|---|
| A — Panel | [`a-panel.html`](a-panel.html) | Cartão centralizado sobre o fundo do deck. Google é a ação principal; a conta local fica recolhida. Mantém a estrutura de página do `keycloak.v2`: CSS mais um `header` próprio. |
| B — Split | [`b-split.html`](b-split.html) | Tela dividida: à esquerda, o contexto e o terminal que pediu o login; à direita, a ação. Device code em oito caixas e uma trilha de três passos. Exige um `template.ftl` próprio. |

## Telas cobertas

1. Login (padrão e conta local com erro).
2. Device code (digitar, código preenchido, código inválido ou usado) e 2b, o consentimento do `platform-cli`.
3. Erro (falha no Google, sessão expirada).
4. Primeiro login pelo Google (revisar perfil).
5. Account Console: só na A, porque é uma app React (`keycloak.v3`) com tema próprio, que não usa o layout das telas de login.
6. Callback da CLI (`cli/src/wasp_platform/auth.py`, `_Callback`).

## O que as duas mudam em relação ao tema padrão

- O título "PLATFORM" e o fundo poligonal cinza dão lugar à marca **wasp · platform** e ao fundo do deck (`#0a0e1a`, painéis `#111827`, azul `#4a9ef4`).
- O Google vira a ação principal. A conta local, que ninguém usa hoje, sai do caminho sem sumir.
- O erro de device code explica o que fazer ("rode o comando de novo"). Hoje só diz "Invalid code, please try again", mesmo quando o código já foi usado com sucesso.
- O erro do Google mostra o código do evento e o horário, que é o que se procura no log do Keycloak. O detalhe técnico fica fora da tela.

## Custo de implementação

- **A:** `theme.properties` herdando `keycloak.v2`, um CSS e um `template.ftl` que só troca o cabeçalho. Sobrevive bem a upgrades do Keycloak.
- **B:** um `template.ftl` com o layout em duas colunas e textos por tela (`login.ftl`, `login-oauth2-device-verify-user-code.ftl`, `error.ftl`). As oito caixas do device code pedem um pouco de JS. A cada upgrade, o `template.ftl` precisa ser comparado com o do `keycloak.v2`.

## Escolha

Pendente de aprovação na #173.
