# Profile layer in the binding policy: environment > profile > platform

**Status:** Aceito (2026-10-12)

## Contexto

O ADR 0031 definiu a política de binding em camadas: override da branch > política do ambiente > padrão da plataforma. O perfil do ambiente (`ephemeral`, `shared`) era só gravado em `Environment.spec.profile`, e nenhum provider o lia. O deck promete que o perfil é o golden path do ambiente, e que um ambiente `ephemeral` ganha `postgres` em `compose` no `shared-pg` sem passo de admin. Na prática, um dev recebia `provision`, a não ser que um `platform-admins` escrevesse a política daquele ambiente (#329).

## Decisão

**A política de binding ganha a camada de perfil, entre a do ambiente e a da plataforma: override da branch > ambiente > perfil > plataforma.**

- **Escopo da policy:** uma `BindingPolicy` com `spec.profile` vale para todo ambiente daquele perfil. `spec.profile` e `spec.environment` são exclusivos, e uma policy sem nenhum dos dois é o padrão da plataforma.
- **Precedência:** o ambiente vence o perfil. O admin que define a política de um ambiente específico decide sobre o padrão do perfil.
- **A plataforma traz `profile-ephemeral`** (`postgres` → `compose` em `shared-pg`). O `platform init` a cria só quando ela falta e nunca a reaplica, porque os `platform-admins` a mudam pela API (`PUT /v1/profiles/{profile}/binding-policy`, `platform environment profile policy set`).
- **Por enquanto, o perfil carrega só a política de binding.** `--expires` padrão, tamanho e a lista de registries (#366, camada `Profile` do `RegistryBinding`) entram quando houver necessidade, no mesmo desenho de camadas.
- **Mudar uma camada não muda um recurso que já existe.** O próximo deploy termina `ResourceModeChanged`, como em qualquer mudança de política (ADR 0031). Ambientes `ephemeral` com um `postgres` `provision` de antes desta mudança passam por isso.

## Consequências

- O `Forager` lê `Environment.spec.profile` para montar as camadas.
- `environment policy get` mostra três camadas (`LAYER` = `environment`, `profile`, `default`).
- Escrever a política de um perfil afeta todos os ambientes dele, inclusive os que já existem, a partir do próximo deploy de cada um.
- Este ADR complementa o 0031 sem substituí-lo: as regras de casamento (`type`, `class`, `id`, primeiro que casa vence) não mudam.
