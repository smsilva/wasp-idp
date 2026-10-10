# Current state and next steps

Contexto para o fechamento "onde estamos / próximos passos". A plataforma é um projeto pessoal de aprendizado (este repo); os fatos vêm do código, dos ADRs em `docs/adr/` e do board do GitHub Project #6.

## Onde estamos: MVP 1

- **Ambiente sob demanda:** um claim `Environment` vira um cluster EKS com rede, DNS, certificado, identidade e GitOps em ~28-30 min ([`poc.md`](poc.md)).
- **Control plane:** k3d local rodando Crossplane e Argo CD; a topologia AWS é hub-and-spoke (conta `network` com o hub e células por região).
- **Portal:** Backstage local com catálogo descoberto da org GitHub, template que cria app (repo + PR no GitOps central) e deploy em `development` e `production`.
- **Nível de maturidade:** Level 1 — o agente (Claude Code) sugere e o humano executa.

## Próximos passos (issues abertas no board)

- **Platform API como fronteira única:** CLI, portal e agentes falam só com ela; Crossplane e Argo CD ficam atrás como implementação.
- **Identidade:** Keycloak como broker (Google autentica, Keycloak guarda grupos), sem Dex — ADR 0021, aceito em 2026-10-10.
- **Fonte da verdade:** API do Kubernetes para estado desejado, Postgres como journal e projeção para o portal — ADR 0022, aceito em 2026-10-10.
- **CLI `platform`:** `init --target local` e `environment create|list|delete` já entregues (#152); falta `login` com PKCE e device code e `whoami`.
- **Portal:** redesign da página de Component e aba Environments com as Applications do Argo CD.

## Oportunidade

- O Backstage é **só o developer portal**: guarda o modelo mental humano (catálogo) e interage com a plataforma por plugins. Ele não é a plataforma.
- **Mais de um client para a mesma plataforma:** portal, CLI e agentes são clients do mesmo contrato.
- **Uma identidade para todos os clients:** a plataforma sabe o que cada usuário pode ver e fazer, igual em qualquer client ([`sso-dex.md`](sso-dex.md) registra a avaliação inicial com Dex, depois substituída pelo Keycloak).

## Sequência sugerida para o fechamento

1. MVP 1: ambiente sob demanda, já funcionando em pequeno.
2. Onde ele está na escala de maturidade e a J-Curve.
3. Próximo: Platform API, identidade única, CLI e portal sobre o mesmo contrato.
