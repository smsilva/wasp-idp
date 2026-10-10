# internaldeveloperplatform.org

- Fonte: <https://internaldeveloperplatform.org/> (lido em 2026-10-07). Páginas usadas: "What is an IDP" <https://internaldeveloperplatform.org/what-is-an-internal-developer-platform/>, "Core components" <https://internaldeveloperplatform.org/core-components/>, "Environment management" <https://internaldeveloperplatform.org/core-components/environment-management/>.
- Site comunitário de curadoria sobre IDPs ("Everything the WWW has around Internal Developer Platforms in one curated space"). Parte dos contribuidores trabalha na **Humanitec**, que o próprio site chama de "the market leader in IDPs" — a Humanitec vende platform orchestrator. Mesma cautela dos materiais de vendor: o enquadramento favorece a categoria orquestrador.

## Definições (literais)

- IDP: "An Internal Developer Platform (IDP) is built by a platform team to build golden paths and enable developer self-service." A plataforma integra várias tecnologias para reduzir a carga cognitiva sem tirar o acesso às tecnologias de baixo.
- Portal (citando Gartner): "Internal developer portals serve as the interface through which developers can discover and access internal developer platform capabilities." O portal é **uma** interface baseada em UI para o IDP; a plataforma é a camada inteira por baixo.
- Platform team: constrói e mantém o IDP **como produto** para os devs (clientes internos), ouvindo infra/ops, segurança, arquitetura e executivos.
- O nome importa: Internal (não externo), Developer (o usuário principal é o dev de aplicação), Platform (categoria de produto). O site rejeita "internal platform" e "developer portal/platform".

## Cinco core components (literais)

1. Application Configuration Management — "Manage application configuration in a dynamic, scalable and reliable way."
2. Infrastructure Orchestration — "Orchestrate your infrastructure in a dynamic and intelligent way depending on the context."
3. Environment Management — "Enable developers to create new and fully provisioned environments whenever needed."
4. Deployment Management — "Implement a delivery pipeline for Continuous Delivery or even Continuous Deployment (CD)."
5. Role-Based Access Control — "Manage who can do what in a scalable way."

## Environment management (detalhe)

- "With Internal Developer Platforms (IDPs) developers can self-serve fully provisioned environments on demand."
- "Each new environment is provisioned as defined by the platform team."
- Criação por "a user interface (UI), a command-line interface (CLI), or an API".
- Tipos de ambiente definidos pela plataforma (máquinas menores em dev, maiores em produção).
- "automated teardown or pausing of environments if they are not needed to avoid unnecessary costs".

## Citação

- "I'm convinced the majority of people managing infrastructure just want a PaaS. The only requirement: it has to be built by them." — Kelsey Hightower, 2017-04-11 (citado no site).

## Uso na apresentação

- **Environment Management é literalmente o MVP 1:** o dev pede um `Environment` provisionado como a plataforma definiu, por UI, CLI ou API. Dá uma fonte externa para dizer "o MVP 1 entrega um dos cinco componentes centrais de um IDP".
- Teardown/pausa automático para evitar custo = mesma ideia do Fury (`mercadolibre-fury.md`).
- UI, CLI ou API como formas de criar = `many-clients`.
- RBAC como core component = `single-sign-on`/`who-decides`.
- Definição Gartner de portal reforça `portal-is-not-platform`, com fonte menos enviesada que Port/configure8 (ainda via site ligado à Humanitec).
- Os cinco componentes são outro recorte, por **capacidade**, diferente dos cinco planes (por **camada**, `base-deck.md`). Não misturar os dois "cinco" na mesma tela.
