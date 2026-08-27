# Step 2.1 — AWS VPN Client Gate

_2026-08-26_


Branch `feat/private-access-phase-2`, a partir de `main` já com a fase 1 mergeada por fast-forward.
Custo: zero — nada tocou a AWS, só a máquina local.

**O risco que motivou o portão não existe mais.** A doc lista **Ubuntu 22.04, 24.04 e 26.04 (AMD64)**
como suportados; esta máquina é 24.04.4 x86_64 sob GNOME/X11. O client de hoje é build GTK/Electron
(o caminho de download é `/GTK/`), não o Mono/WPF que exigia distro antiga e era a origem do medo.

Instalado o **6.0.1** por URL de versão, sha256 conferido contra as release notes. `dpkg --install`
exit 0, `apt-get check` limpo, daemon `enabled`+`active`, GUI abrindo e renderizando, CLI respondendo.
Perfil SAML sintético importado, listado, lido por `get-config` e apagado — **tudo sem `sudo`**, e o
client classificou `auth-type: saml` a partir do `auth-federate`. Portas 8096–8115 livres. Nenhum
resíduo: perfil apagado, `/tmp` limpo.

**A premissa que caiu:** a decisão 3 do plano pagava como preço *"o client da AWS no Linux é aplicação
desktop, então `connect` não é scriptável"*. A **6.0.1 (12/08/2026)** instala
`/usr/local/bin/aws-vpn-client`, com `connect`, `disconnect`, `import-profile`, `get-config`,
`get-connection-status`, `list-connections`, `put-preference`. O script `vpn` deixa de ser
`config`/`status` só.

Três coisas aprendidas que valem mais que o resultado do portão:

- **`latest` é uma armadilha.** `.../GTK/latest/` e o repo apt da própria doc entregam **5.4.1**
  (25/08/2026), que **não tem CLI** — a AWS mantém o 5.x como linha default enquanto o 6.0.x é major
  mais novo e não promovido. Data maior, capacidade menor. E a falha é silenciosa: instala, a GUI abre,
  e o `aws-vpn-client` só não existe.
- **Dependência satisfeita por `Provides` conta.** O 6.0.1 declara `libgtk-3-0` e `libasound2`, que
  **não existem com esse nome no noble** — a transição t64 renomeou os dois. Instala porque
  `libgtk-3-0t64` e `libasound2t64` declaram `Provides` com versão. Conferir `apt-cache policy` do nome
  declarado e concluir "não existe, vai quebrar" é errado.
- **`import-profile` aceita o que `connect` recusa.** A validação do CA é no `connect`
  (`Invalid configuration file`), não no import. O script `vpn` não pode tratar import bem-sucedido
  como configuração válida.

**O que o portão não podia provar:** o aceite escrito no passo pedia "completa login SAML", e completar
login SAML exige o endpoint e a aplicação SAML — que são o `2.2`. O critério foi movido para lá, junto
com a pergunta que sobrou: se `aws-vpn-client connect` num perfil SAML abre o navegador sozinho.
