// The home page: server-rendered HTML, no frontend build, no external CDN (it works offline in the
// environment). Every value from outside this file goes through escape().
const { href } = require('./features');

const RUNTIME = [`Node.js ${process.versions.node}`, `Fastify ${require('fastify/package.json').version}`];

function escape(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

const STYLE = `
  :root {
    --paper: #f2f5f3;
    --surface: #ffffff;
    --ink: #18231c;
    --muted: #55625a;
    --line: #d0d9d3;
    --ok: #1d7a43;
    --ok-wash: #e4f3ea;
    --fail: #c62828;
    --fail-wash: #fdecec;
    --fail-ink: #7f1414;
    --idle: #87928b;
    --band: #1e4d2b;
    --band-ink: #ffffff;
    --glow: #9ad97a;
    --accent: #2f7d3a;
    --sans: "Avenir Next", "Avenir", "Nunito Sans", "Ubuntu", "Trebuchet MS", system-ui, sans-serif;
    --mono: "Ubuntu Mono", "Cascadia Code", "Menlo", "DejaVu Sans Mono", ui-monospace, monospace;
  }
  [data-theme="lime"]   { --band: #3b4a0f; --glow: #cbe85f; --accent: #56720c; }
  [data-theme="sky"]    { --band: #0b3d5c; --glow: #86cdf3; --accent: #0a679c; }
  [data-theme="violet"] { --band: #3a2366; --glow: #c8aef6; --accent: #6a45bd; }

  @media (prefers-color-scheme: dark) {
    :root {
      --paper: #0f1511;
      --surface: #18211b;
      --ink: #e2eae4;
      --muted: #9aa89f;
      --line: #2f3b33;
      --ok: #52c785;
      --ok-wash: #15301f;
      --fail: #ff6b6b;
      --fail-wash: #3a1719;
      --fail-ink: #ffd4d4;
      --idle: #7d8a82;
      --band: #163a20;
      --accent: #8fd36f;
    }
    [data-theme="lime"]   { --band: #2c380a; --accent: #c3e05a; }
    [data-theme="sky"]    { --band: #082e46; --accent: #7cc6ef; }
    [data-theme="violet"] { --band: #2b1a4d; --accent: #c0a5f3; }
  }

  * { box-sizing: border-box; }
  body {
    margin: 0;
    background: var(--paper);
    color: var(--ink);
    font: 400 1rem/1.55 var(--sans);
    -webkit-font-smoothing: antialiased;
  }
  a { color: var(--accent); text-underline-offset: 0.2em; }
  a:focus-visible { outline: 3px solid var(--accent); outline-offset: 3px; border-radius: 2px; }
  code { font-family: var(--mono); font-size: 0.95em; }
  .wrap { max-width: 66rem; margin: 0 auto; padding: 0 1.5rem; }

  /* The band: the theme's color across the whole width, the build answering on its right. */
  .band { background: var(--band); color: var(--band-ink); padding: 2.5rem 0 6rem; }
  .band .wrap { display: grid; grid-template-columns: 1fr auto; gap: 2rem 3rem; align-items: end; }
  .runtime { display: flex; flex-wrap: wrap; gap: 0.5rem; margin: 0 0 1.75rem; padding: 0; list-style: none; }
  .runtime li {
    display: inline-flex; align-items: center; gap: 0.45rem;
    padding: 0.2rem 0.75rem 0.2rem 0.55rem;
    font-size: 0.85rem; font-weight: 600;
    color: var(--glow);
    border: 1px solid color-mix(in srgb, var(--glow) 55%, transparent);
    border-radius: 999px;
  }
  .runtime li::before {
    content: ""; width: 0.8rem; height: 0.9rem; background: var(--glow);
    clip-path: polygon(50% 0, 100% 25%, 100% 75%, 50% 100%, 0 75%, 0 25%);
  }
  h1 {
    margin: 0;
    font-size: clamp(2.5rem, 6.5vw, 4.5rem);
    font-weight: 700;
    letter-spacing: -0.03em;
    line-height: 1;
    overflow-wrap: anywhere;
  }
  .description { margin: 1rem 0 0; max-width: 36rem; font-size: 1.125rem; color: color-mix(in srgb, var(--band-ink) 78%, transparent); }

  .build { margin: 0; text-align: right; }
  .build .version { display: block; font: 700 clamp(1.5rem, 3.2vw, 2.1rem)/1.1 var(--mono); color: var(--glow); overflow-wrap: anywhere; }
  .build dl { margin: 0.6rem 0 0; display: grid; grid-template-columns: auto auto; justify-content: end; gap: 0.1rem 0.75rem; font-size: 0.875rem; }
  .build dt { color: color-mix(in srgb, var(--band-ink) 65%, transparent); }
  .build dd { margin: 0; font-family: var(--mono); text-align: left; overflow-wrap: anywhere; }

  /* The connection rides over the band's edge; its left rail carries the state. */
  .link {
    --state: var(--ok);
    position: relative;
    margin: -4rem 0 0;
    padding: 1.75rem 2rem 1.5rem 2.5rem;
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: 0.375rem;
    box-shadow: 0 1.25rem 2.5rem -1.5rem rgb(15 30 20 / 0.35);
  }
  .link::before { content: ""; position: absolute; inset: -1px auto -1px -1px; width: 0.5rem; background: var(--state); border-radius: 0.375rem 0 0 0.375rem; }
  .link[data-state="failed"] { --state: var(--fail); background: var(--fail-wash); border-color: var(--fail); }
  .link[data-state="not-configured"] { --state: var(--idle); }

  .link h2 { margin: 0; font-size: 1.45rem; font-weight: 700; color: var(--state); }
  .link[data-state="failed"] h2 { font-size: clamp(1.6rem, 4vw, 2.1rem); }
  .link .lede { margin: 0.3rem 0 0; color: var(--muted); }
  .link[data-state="failed"] .lede { color: var(--fail-ink); }

  .wire { display: flex; align-items: center; margin: 1.5rem 0; }
  .node { flex: 0 1 auto; min-width: 0; padding: 0.55rem 0.9rem; background: var(--paper); border-radius: 0.375rem; }
  .link[data-state="failed"] .node { background: var(--surface); }
  .node b { display: block; font-size: 0.95rem; }
  .node span { display: block; font-family: var(--mono); font-size: 0.85rem; color: var(--muted); overflow-wrap: anywhere; }
  .cable { flex: 1 1 4rem; position: relative; display: flex; justify-content: center; align-items: center; height: 2.25rem; }
  .cable::before { content: ""; position: absolute; inset: 50% 0 auto; height: 2px; border-top: 3px dotted var(--state); }
  .link[data-state="connected"] .cable::before { border-top-style: solid; }
  .cable em {
    position: relative; padding: 0.05rem 0.6rem;
    font: 700 0.9rem/1.6 var(--mono); font-style: normal;
    color: var(--surface); background: var(--state); border-radius: 0.25rem;
  }
  .link[data-state="failed"] .cable em { font-size: 1.35rem; padding: 0 0.7rem; }

  .facts { margin: 0; display: grid; grid-template-columns: repeat(auto-fit, minmax(9rem, 1fr)); gap: 0.9rem 2rem; }
  .facts dt { font-size: 0.85rem; color: var(--muted); }
  .facts dd { margin: 0.1rem 0 0; font-family: var(--mono); overflow-wrap: anywhere; }
  .error {
    margin: 0 0 1.25rem; padding: 0.9rem 1rem;
    font: 0.92rem/1.5 var(--mono); color: var(--fail-ink);
    background: var(--surface); border: 1px solid var(--fail); border-radius: 0.375rem;
    white-space: pre-wrap; overflow-wrap: anywhere;
  }
  .hint { margin: 1.25rem 0 0; font-size: 0.95rem; }
  .checked { margin: 1.25rem 0 0; font-size: 0.85rem; color: var(--muted); }

  /* Features: what this version does, from src/features.js. */
  .features { margin: 3.5rem 0 0; }
  .features h2 { margin: 0; font-size: 1.3rem; font-weight: 700; }
  .features > p { margin: 0.35rem 0 1.25rem; color: var(--muted); }
  .cards { margin: 0; padding: 0; list-style: none; display: grid; grid-template-columns: repeat(auto-fill, minmax(17rem, 1fr)); gap: 1rem; }
  .card { display: flex; flex-direction: column; padding: 1.1rem 1.2rem; background: var(--surface); border: 1px solid var(--line); border-top: 3px solid var(--accent); border-radius: 0.375rem; }
  .card h3 { margin: 0; font-size: 1.05rem; }
  .card p { margin: 0.3rem 0 1rem; color: var(--muted); flex: 1; }
  .card .new { align-self: flex-start; margin: 0 0 0.5rem; padding: 0.05rem 0.5rem; font-size: 0.78rem; font-weight: 700; color: var(--surface); background: var(--accent); border-radius: 0.25rem; }
  .endpoint { align-self: flex-start; display: inline-flex; font-family: var(--mono); font-size: 0.88rem; text-decoration: none; border: 1px solid var(--line); border-radius: 0.25rem; overflow: hidden; }
  .endpoint:hover { border-color: var(--accent); }
  .endpoint .method { padding: 0.15rem 0.45rem; font-weight: 700; color: var(--surface); background: var(--accent); }
  .endpoint .path { padding: 0.15rem 0.55rem; color: var(--ink); overflow-wrap: anywhere; }

  footer { margin: 3.5rem 0 0; padding: 1.25rem 0 2.5rem; border-top: 1px solid var(--line); display: flex; flex-wrap: wrap; gap: 0.5rem 1.75rem; font-size: 0.95rem; }
  footer .docs { font-weight: 700; }
  footer .meta { margin-left: auto; color: var(--muted); }

  @media (max-width: 44rem) {
    .wrap { padding: 0 1rem; }
    .band { padding: 2rem 0 5.5rem; }
    .band .wrap { grid-template-columns: 1fr; }
    .build { text-align: left; }
    .build dl { justify-content: start; }
    .link { padding: 1.5rem 1.25rem 1.25rem 1.75rem; }
    .wire { flex-direction: column; align-items: stretch; }
    .cable { flex-basis: 3rem; height: 3rem; }
    .cable::before { inset: 0 auto 0 50%; width: 0; height: auto; border-top: 0; border-left: 3px dotted var(--state); }
    .link[data-state="connected"] .cable::before { border-left-style: solid; }
    footer .meta { margin-left: 0; }
  }
`;

function databasePanel(app, db) {
  const target = db.details ? `${db.host ?? ''}:${db.port}/${db.database ?? ''}` : 'details hidden';
  const wire = (label, cable, right, rightDetail) => `
    <div class="wire" role="img" aria-label="${escape(label)}">
      <div class="node"><b>${escape(app)}</b><span>this pod</span></div>
      <div class="cable">${cable}</div>
      <div class="node"><b>${escape(right)}</b><span>${escape(rightDetail)}</span></div>
    </div>`;

  if (db.status === 'connected') {
    const checked = db.checkedAt.slice(11, 19);
    return `
  <section class="link" data-state="connected" aria-labelledby="db-title">
    <h2 id="db-title">Connected to PostgreSQL</h2>
    <p class="lede">The database answered this page's query.</p>
    ${wire(`${app} is connected to the database, ${db.latencyMs} ms`, `<em>${Math.round(db.latencyMs)} ms</em>`, `PostgreSQL ${db.serverVersion ?? ''}`, target)}
    ${db.details ? `
    <dl class="facts">
      <div><dt>Host</dt><dd>${escape(db.host)}</dd></div>
      <div><dt>Server address</dt><dd>${escape(db.serverAddress ?? 'unknown')}</dd></div>
      <div><dt>Database</dt><dd>${escape(db.database)}</dd></div>
      <div><dt>User</dt><dd>${escape(db.user)}</dd></div>
    </dl>` : `
    <p class="hint">The host, user and server version stay off this page: <code>SHOW_DATABASE_DETAILS=true</code> shows them, for demos only.</p>`}
    <p class="checked">Checked when this page loaded, ${checked} UTC. Reload to check again.</p>
  </section>`;
  }

  if (db.status === 'failed') {
    return `
  <section class="link" data-state="failed" role="alert" aria-labelledby="db-title">
    <h2 id="db-title">Can't reach the database</h2>
    <p class="lede">${escape(app)} is running, but the connection to PostgreSQL failed.</p>
    ${wire(`The connection from ${app} to the database is broken`, '<em aria-hidden="true">✕</em>', 'PostgreSQL', target)}
    ${db.details ? `
    <pre class="error">${escape(db.error)}</pre>
    <dl class="facts">
      <div><dt>Tried host</dt><dd>${escape(db.host)}</dd></div>
      <div><dt>Port</dt><dd>${escape(db.port)}</dd></div>
      <div><dt>Database</dt><dd>${escape(db.database ?? 'not set')}</dd></div>
      <div><dt>User</dt><dd>${escape(db.user ?? 'not set')}</dd></div>
    </dl>` : ''}
    <p class="hint">See the state of the <code>db</code> resource with <code>platform workload get ${escape(app)} --environment &lt;environment&gt;</code>.${db.details ? '' : " The error is in the pod's log; <code>SHOW_DATABASE_DETAILS=true</code> also shows it here, for demos only."} The page checks again on every reload.</p>
  </section>`;
  }

  return `
  <section class="link" data-state="not-configured" aria-labelledby="db-title">
    <h2 id="db-title">No database configured</h2>
    <p class="lede"><code>DATABASE_HOST</code> is not set, so this run has no database to check.</p>
    ${wire(`${app} has no database configured`, '<em>not set</em>', 'PostgreSQL', 'no host')}
    <p class="hint">In an environment, the platform sets it from the <code>db</code> resource in <code>app-spec.yaml</code>. To run locally with a database, export <code>DATABASE_HOST</code>, <code>DATABASE_PORT</code>, <code>DATABASE_NAME</code>, <code>DATABASE_USER</code> and <code>DATABASE_PASSWORD</code>.</p>
  </section>`;
}

function card(feature) {
  const [method, path] = feature.endpoint.split(' ');
  return `
      <li class="card">
        ${feature.new ? '<span class="new">New in this version</span>' : ''}
        <h3>${escape(feature.name)}</h3>
        <p>${escape(feature.description)}</p>
        <a class="endpoint" href="${escape(href(feature))}"><span class="method">${escape(method)}</span><span class="path">${escape(path)}</span></a>
      </li>`;
}

function page({ info, theme, db }) {
  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${escape(info.title)}</title>
<style>${STYLE}</style>
</head>
<body data-theme="${escape(theme)}">
<header class="band">
  <div class="wrap">
    <div>
      <ul class="runtime" aria-label="Runtime">${RUNTIME.map((item) => `<li>${escape(item)}</li>`).join('')}</ul>
      <h1>${escape(info.title)}</h1>
      ${info.description ? `<p class="description">${escape(info.description)}</p>` : ''}
    </div>
    <div class="build" aria-label="Build answering this request">
      <span class="version">${escape(info.version)}</span>
      <dl>
        <dt>commit</dt><dd>${escape(info.commit.slice(0, 7))}</dd>
        <dt>pod</dt><dd>${escape(info.pod)}</dd>
      </dl>
    </div>
  </div>
</header>
<main class="wrap">
  ${databasePanel(info.app, db)}

  <section class="features" aria-labelledby="features">
    <h2 id="features">What this version does</h2>
    <p>Listed in <code>src/features.js</code>. Add one there and it shows here after the next deploy.</p>
    <ul class="cards">${info.features.map(card).join('')}
    </ul>
  </section>

  <footer>
    <a class="docs" href="/docs">Open the API docs</a>
    <a href="/openapi.json">OpenAPI document</a>
    <span class="meta">Made from a platform template</span>
  </footer>
</main>
</body>
</html>
`;
}

module.exports = { page, escape };
