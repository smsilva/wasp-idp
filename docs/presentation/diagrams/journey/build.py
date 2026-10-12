#!/usr/bin/env python3
"""Journey slides: one SVG per moment of the delivery line, a CLI session revealed command by command.

Commands and outputs follow the real `platform` CLI (`cli/docs/walkthrough/`), cropped to fit the terminal;
the steps that depend on an open issue show the target shape, and the slide notes say which.
Parts: `strip` (the line, current moment lit, with the terminal), `cmd.N` (a command) and `cmd.N-out` / `cmd.N-editor`
(what it shows, one step later). The setup sessions (moment 0, the platform team) have `terminal` instead of `strip`.
"""
import pathlib

OUT = pathlib.Path(__file__).parent
BG, PANEL, LINE = "#0a0e1a", "#111827", "#1f2937"
WHITE, MUTED, SOFT = "#ffffff", "#6b7a8d", "#9fb3c8"
AMBER, BLUE, GREEN = "#e5c07b", "#4a9ef4", "#7ee787"
MONO = 'font-family="DejaVu Sans Mono, Consolas, monospace"'

def esc(s): return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def T(x, y, s, size=20, weight=500, fill=WHITE, anchor="start", extra=""):
  return (f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" fill="{fill}" text-anchor="{anchor}" '
          f'dominant-baseline="middle" xml:space="preserve" {extra}>{esc(s)}</text>')

# (moment, label, capability it uses — the box the audience saw lit in the landscape).
MOMENTS = [
  ("plan", "Plan", "Software Catalog"),
  ("code", "Code", "App Declaration"),
  ("build", "Build", "CI · Registry"),
  ("env", "Environment", "Resource"),
  ("deploy", "Deploy", "Delivery"),
  ("run", "Run", "Observability"),
]

class Editor:
  """Output that is not text: a simple editor window opens over the terminal with the file."""
  def __init__(self, file, split=None):
    self.file, self.split = file, split

# YAML highlight in SVG, same palette as render-outline's code frame (key, string, number, placeholder).
KEY, STR, NUM, PH, LINENO = "#9cdcfe", "#ce9178", "#b5cea8", "#dcdcaa", "#858585"

def yaml_spans(line):
  import re
  m = re.match(r"^(\s*)([\w.-]+)(:)(\s.*|)$", line)
  if not m:
    return f'<tspan fill="{STR}">{esc(line)}</tspan>'
  indent, key, colon, rest = m.groups()
  out = f'<tspan>{esc(indent)}</tspan><tspan fill="{KEY}">{esc(key)}</tspan><tspan fill="{WHITE}">{colon}</tspan>'
  for chunk in re.split(r"(\$\{[^}]+\})", rest):
    if not chunk:
      continue
    color = PH if chunk.startswith("${") else NUM if chunk.strip().isdigit() else STR
    out += f'<tspan fill="{color}" font-weight="{700 if color == PH else 500}">{esc(chunk)}</tspan>'
  return out

def editor(file, split=None, x0=200, y0=324, x1=1462, y1=846):
  """Editor window: title bar with the file name, line numbers, two columns.

  The right column starts at the top-level key `split`, else at the blank line nearest the middle.
  """
  lines = (OUT / file).read_text().splitlines()
  blanks = [i for i, l in enumerate(lines) if not l.strip()]
  if split:
    cut = lines.index(f"{split}:") - 1
  else:
    cut = min(blanks, key=lambda i: max(i, len(lines) - i - 1))
  columns = [list(enumerate(lines[:cut], 1)), list(enumerate(lines[cut + 1:], cut + 2))]
  out = f'<rect x="{x0 + 10}" y="{y0 + 12}" width="{x1 - x0}" height="{y1 - y0}" rx="12" fill="#000" opacity="0.45"/>'
  out += f'<rect x="{x0}" y="{y0}" width="{x1 - x0}" height="{y1 - y0}" rx="12" fill="#1e1e1e" stroke="#3a3a3a" stroke-width="2"/>'
  out += f'<path d="M{x0},{y0 + 12} a12,12 0 0 1 12,-12 h{x1 - x0 - 24} a12,12 0 0 1 12,12 v28 h-{x1 - x0} z" fill="#2d2d2d"/>'
  out += "".join(f'<circle cx="{x0 + 24 + i * 22}" cy="{y0 + 20}" r="6.5" fill="{c}"/>' for i, c in enumerate(("#ff5f57", "#febc2e", "#28c840")))
  out += T(x0 + 100, y0 + 20, file.replace(".golden", ""), 16, 600, "#c8c8c8", "start")
  step = min(34, (y1 - y0 - 80) / max(len(c) for c in columns))
  for col, rows in enumerate(columns):
    cx = x0 + 30 + col * (x1 - x0) * 0.56  # left column holds the longest lines
    for row, (number, text) in enumerate(rows):
      y = y0 + 72 + row * step
      out += T(cx + 22, y, str(number), 17, 500, LINENO, "end", MONO)
      out += (f'<text x="{cx + 44}" y="{y}" font-size="20" font-weight="500" dominant-baseline="middle" '
              f'xml:space="preserve" {MONO}>{yaml_spans(text)}</text>')
  return out

# One CLI session per moment: (command, [output lines]). Output starting with ✓ is green, "#" is a comment,
# "+" marks a line to highlight (the "+" is not shown): what the previous command created.
# `PAGE` starts a new slide of the same moment (the terminal is full): `plan.svg`, `plan-2.svg`…
PAGE = None
# Commands with more than one option are a list, one argument per line (the bash-scripts convention).
SESSIONS = {
  "plan": [
    # Real output has a TEMPLATE column (`python-service@<sha40>`): left out, it overflows the terminal.
    ("platform catalog component list --system greeter",
     ["NAME             SYSTEM   OWNER       LIFECYCLE",
      "greeting-web     greeter  team-alpha  production",
      "greeting-worker  greeter  team-alpha  experimental"]),
    # `--wait` also prints the six creation steps (Validated … Registered) before this summary.
    (["platform catalog component create greeting-api",
      "--system greeter",
      "--prd docs/idea.md",
      "--wait"],
     ["✓ golden path “python-service” (default for service): repo wasp-foundry/greeting-api created",
      "✓ registered in the catalog (lifecycle: experimental)",
      "✓ docs/prd.md and AGENTS.md added to the repo",
      "✓ app-spec.yaml generated: container, postgres, route /"]),
    PAGE,
    ("platform catalog component list --system greeter",
     ["NAME             SYSTEM   OWNER       LIFECYCLE",
      "+greeting-api     greeter  team-alpha  experimental",
      "greeting-web     greeter  team-alpha  production",
      "greeting-worker  greeter  team-alpha  experimental"]),
  ],
  "code": [
    # The platform resolves the repo from the catalog; the git command it runs shows as a comment.
    ("platform catalog component clone greeting-api",
     ["# git clone git@github.com:wasp-foundry/greeting-api.git"]),
    ("cd greeting-api", []),
    ("git switch --create feat/greetings", []),
    # The spec the golden path generated: what the app needs, not where or how.
    ("code app-spec.yaml", Editor("app-spec.golden.yaml", split="service")),
    PAGE,
    ("agent \"implement GET /greetings as described in docs/prd.md\"",
     ["# reads docs/prd.md, AGENTS.md, app-spec.yaml and the catalog entry",
      "✓ greetings read from DATABASE_HOST / _NAME / _USER / _PASSWORD",
      "✓ psycopg added to requirements.txt",
      "✓ 4 files changed · tests pass"]),
    ("git push --set-upstream origin feat/greetings", ["✓ pushed feat/greetings"]),
  ],
  "build": [
    (["platform build create",
      "--component greeting-api",
      "--branch feat/greetings",
      "--wait"],
     ["building from feat/greetings @ 1a2b3c4 …",
      "✓ app-spec.yaml valid · db (postgres), dns, route",
      "✓ image greeting-api:0.1.0-greetings.1a2b3c4 pushed to the registry"]),
    ("platform build list --component greeting-api",
     ["VERSION                  BRANCH          CREATED",
      "+0.1.0-greetings.1a2b3c4  feat/greetings  2026-10-12T14:02:11Z"]),
  ],
  "env": [
    # Real output also has OWNER and SHARED columns.
    ("platform environment list",
     ["NAME     PROFILE  STATUS  EXPIRES",
      "dev      shared   ready   —",
      "staging  shared   ready   —"]),
    # The dev picks the kind of environment; the profile (platform-owned) decides where it runs.
    (["platform environment create greetings-test",
      "--profile ephemeral",
      "--expires 3d",
      "--wait"],
     ["provisioning greetings-test (profile: ephemeral) …",
      "✓ greetings-test ready"]),
  ],
  "deploy": [
    (["platform workload deploy",
      "--component greeting-api",
      "--environment greetings-test",
      "--branch feat/greetings",
      "--wait"],
     ["✓ greeting-api@greetings-test revision 1: 0.1.0-greetings.1a2b3c4 running · 1/1 replicas available"]),
    # Real output also has component, image, replicas, revision and message.
    (["platform workload get",
      "--component greeting-api",
      "--environment greetings-test"],
     ["greeting-api@greetings-test (Available)",
      "  url           https://greeting-api.greetings-test.platform.example.com",
      "  resource      db (postgres, compose): Ready"]),
  ],
  "run": [
    ("curl https://greeting-api.greetings-test.platform.example.com/greetings",
     ['{"greetings": [{"id": 1, "message": "hello"}], "version": "0.1.0-greetings.1a2b3c4"}']),
    (["platform workload signals",
      "--component greeting-api",
      "--environment greetings-test"],
     ["latency p95 42 ms · traffic 3 req/s · errors 0% · saturation 12%"]),
  ],
}

# Moment 0: what the platform team does once, before any dev arrives. No strip: the line is the dev's journey.
# Outputs are the real CLI's, cropped: `init` also prints its progress lines, `scm connection add` a "then run" hint.
SETUP_SESSIONS = [
  (["platform init",
    "--target local",
    "--admin admin@example.com"],
   ["✓ Platform API at http://127.0.0.1:9090 · config in ~/.config/platform/config.yaml",
    "✓ Keycloak issuer http://localhost:8180/realms/platform"]),
  ("platform login",
   ["Opening the browser to sign in …",
    "✓ Logged in as admin@example.com (platform-admins, platform-users)"]),
  ("platform team member add team-alpha dev@example.com",
   ["✓ dev@example.com added to team-alpha"]),
  PAGE,
  (["platform scm connection add wasp-foundry",
    "--vendor github",
    "--org wasp-foundry",
    "--default"],
   ["→ opening the browser to create the GitHub App \"wasp-foundry-platform\" …",
    "✓ app created (id 5274859) · private key stored by the platform",
    "→ install it on the org: github.com/apps/wasp-foundry-platform/installations/new"]),
  ("platform scm connection verify wasp-foundry --wait",
   ["✓ wasp-foundry ready (wasp-foundry, all repositories)"]),
  PAGE,
  (["platform cloud account add nonprod-aws",
    "--role-arn arn:aws:iam::123456789012:role/platform"],
   ["✓ cloud account nonprod-aws added (pending)",
    "# apply the printed trust policy (sts:ExternalId) to the role"]),
  ("platform cloud account verify nonprod-aws --wait",
   ["✓ nonprod-aws ready (account 123456789012)"]),
  # Real output also has REF (a 40-char sha) and SOURCE (a URL) columns.
  # Only python-service exists today: nodejs-service and go-service are illustrative (one stack per audience).
  ("platform catalog template list",
   ["NAME            TYPE     DEFAULT",
    "go-service      service  —",
    "nodejs-service  service  —",
    "python-service  service  yes"]),
  PAGE,
  # Cropped from the 22 rows of `idp/catalog/`, realigned to the rows that stay.
  ("platform catalog import idp/catalog/",
   ["KIND      NAME           ACTION  DETAIL",
    "Group     team-beta      create",
    "Domain    communication  create",
    "Domain    messaging      create  parent communication",
    "System    greeter        create  domain messaging",
    "Resource  greeting-db    create  system greeter",
    "…",
    "19 to create, 0 to update, 1 unchanged, 2 skipped.",
    "Apply? [y/N]: y",
    "✓ 19 created, 0 updated"]),
]

X0, X1 = 120, 1480

def strip(current):
  out, n = "", len(MOMENTS)
  gap = 14
  w = (X1 - X0 - gap * (n - 1)) / n
  idx = [m[0] for m in MOMENTS].index(current)
  for i, (key, label, capability) in enumerate(MOMENTS):
    x = X0 + i * (w + gap)
    on, done = i == idx, i < idx
    fill = "#2a2213" if on else PANEL
    stroke = AMBER if on else LINE
    color = AMBER if on else (WHITE if done else MUTED)
    out += f'<rect x="{x}" y="190" width="{w}" height="74" rx="12" fill="{fill}" stroke="{stroke}" stroke-width="2"/>'
    out += T(x + 20, 216, f"{i + 1:02d}", 15, 700, MUTED)
    out += T(x + 20, 244, label, 22, 800, color)
    if on:
      out += T(x + w - 18, 216, capability, 13, 600, SOFT, "end")
  return out

# Command highlight: the command words white, `--options` light blue, their values soft amber.
OPTION, VALUE = "#7cc4ff", "#e5c07b"

# URL parts: app, environment and path each in its own color; scheme and domain stay grey.
APP_C, ENV_C, PATH_C, DOMAIN_C = "#e5c07b", "#7cc4ff", "#c3a6ff", "#6b7a8d"

def url_spans(url, base):
  """https://<app>.<env>.<domain><path>: each concept in its own color; the rest in `base`."""
  import re
  m = re.match(r"(https://)([\w-]+)(\.)([\w-]+)(\.[\w.]+)(/\S*)?$", url)
  if not m:
    return f'<tspan fill="{base}">{esc(url)}</tspan>'
  scheme, app, dot, env, domain, path = m.groups()
  out = (f'<tspan fill="{DOMAIN_C}">{scheme}</tspan><tspan fill="{APP_C}">{esc(app)}</tspan>'
         f'<tspan fill="{DOMAIN_C}">{dot}</tspan><tspan fill="{ENV_C}">{esc(env)}</tspan>'
         f'<tspan fill="{DOMAIN_C}">{esc(domain)}</tspan>')
  return out + (f'<tspan fill="{PATH_C}">{esc(path)}</tspan>' if path else "")

def command_line(x, y, text):
  import re
  spans, after_option = "", False
  for token in re.split(r"(\s+)", text):
    if token.startswith("https://"):
      spans += url_spans(token, WHITE)
      continue
    if not token or token.isspace() or token == "\\":
      color = WHITE
    elif token.startswith("--"):
      color, after_option = OPTION, True
      spans += f'<tspan fill="{color}">{esc(token)}</tspan>'
      continue
    elif after_option:
      color = VALUE
    else:
      color = WHITE
    if token and not token.isspace():
      after_option = False if color == VALUE else after_option
    spans += f'<tspan fill="{color}">{esc(token)}</tspan>'
  return (f'<text x="{x}" y="{y}" font-size="23" font-weight="500" dominant-baseline="middle" '
          f'xml:space="preserve" {MONO}>{spans}</text>')

# Working directory in the terminal title: the repo is cloned in Code, so Plan runs from home.
CWD = {"plan": "~", "plan-2": "~", "code": "~", "setup": "~", "setup-2": "~", "setup-3": "~", "setup-4": "~"}  # per page: `code-2` runs after the `cd`

def session(key, commands, name):
  parts = {}
  x, y = X0, 290
  h = 852 - y
  frame = f'<rect x="{x}" y="{y}" width="{X1 - X0}" height="{h}" rx="16" fill="#070b14" stroke="{LINE}" stroke-width="2"/>'
  frame += f'<path d="M{x},{y + 16} a16,16 0 0 1 16,-16 h{X1 - X0 - 32} a16,16 0 0 1 16,16 v26 h-{X1 - X0} z" fill="{PANEL}"/>'
  frame += "".join(f'<circle cx="{x + 28 + i * 24}" cy="{y + 21}" r="7" fill="{c}"/>' for i, c in enumerate(("#ff5f57", "#febc2e", "#28c840")))
  frame += T((X0 + X1) / 2, y + 21, CWD.get(name, "~/greeting-api"), 16, 700, SOFT, "middle", MONO)
  if key == "setup":
    parts["terminal"] = frame
  else:
    parts["strip"] = strip(key) + frame
  # Empty prompt: a `$` and a cursor where the first command will be typed (hidden once it appears).
  # Drawn after `strip`, or the terminal background covers it.
  cy = y + 84
  parts["prompt"] = (T(x + 30, cy, "$ ", 23, 700, BLUE, "start", MONO)
                     + f'<rect x="{x + 60}" y="{cy - 13}" width="13" height="26" fill="{SOFT}" opacity="0.8"/>')
  for n, (cmd, lines) in enumerate(commands, start=1):
    # A long command breaks one argument per line: trailing `\`, continuation indented 2 spaces.
    args = [cmd] if isinstance(cmd, str) else cmd
    body = T(x + 30, cy, "$ ", 23, 700, BLUE, "start", MONO)
    for i, arg in enumerate(args):
      text = ("  " if i else "") + arg + (" \\" if i < len(args) - 1 else "")
      body += command_line(x + 60, cy, text)
      cy += 36 if i < len(args) - 1 else 42
    if isinstance(lines, Editor):
      # The command first; the window opens on the next step (its own part, `cmd.N-editor`).
      parts[f"cmd.{n}"] = body
      parts[f"cmd.{n}-editor"] = editor(lines.file, lines.split)
      cy += 10
      continue
    # The output is its own part (`cmd.N-out`): the command appears first, the result on the next step.
    parts[f"cmd.{n}"] = body
    if not lines:
      cy += 10
      continue
    body = ""
    for line in lines:
      if line.startswith("+"):
        line = line[1:]
        # Subtle: a faint band and white text, no border; the other rows stay grey.
        body += (f'<rect x="{x + 48}" y="{cy - 17}" width="{len(line) * 12.7 + 24}" height="34" rx="4" '
                 f'fill="{WHITE}" fill-opacity="0.06"/>')
        body += T(x + 60, cy, line, 21, 500, WHITE, "start", MONO)
      elif "https://" in line:
        head, url = line.split("https://", 1)
        body += (f'<text x="{x + 60}" y="{cy}" font-size="21" font-weight="500" dominant-baseline="middle" '
                 f'xml:space="preserve" {MONO}><tspan fill="{SOFT}">{esc(head)}</tspan>{url_spans("https://" + url, SOFT)}</text>')
      else:
        color = GREEN if line.startswith("✓") else MUTED if line.startswith("#") else SOFT
        body += T(x + 60, cy, line, 21, 500, color, "start", MONO)
      cy += 36
    cy += 26
    parts[f"cmd.{n}-out"] = body
  return parts

def pages(commands):
  page = []
  for command in commands:
    if command is PAGE:
      yield page
      page = []
    else:
      page.append(command)
  yield page

for old in OUT.glob("*.svg"):
  old.unlink()
for key, sessions in [("setup", SETUP_SESSIONS)] + [(key, SESSIONS[key]) for key, _, _ in MOMENTS]:
  for number, commands in enumerate(pages(sessions), start=1):
    name = key if number == 1 else f"{key}-{number}"
    parts = session(key, commands, name)
    body = "".join(f'<g data-part="{k}">{v}</g>' for k, v in parts.items())
    (OUT / f"{name}.svg").write_text(f'<svg viewBox="100 170 1400 702" xmlns="http://www.w3.org/2000/svg" font-family="system-ui, sans-serif">{body}</svg>\n')
print("journey ok", len(MOMENTS))
