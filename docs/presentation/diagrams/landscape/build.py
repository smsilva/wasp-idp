#!/usr/bin/env python3
"""Build landscape slide variants (same content, different shapes) as standalone HTML."""
import math, pathlib, sys

OUT = pathlib.Path(__file__).parent
BG, PANEL, LINE = "#0a0e1a", "#111827", "#1f2937"
WHITE, MUTED, SOFT = "#ffffff", "#6b7a8d", "#9fb3c8"
AMBER, BLUE = "#e5c07b", "#4a9ef4"

PLANES = {
  "dev": "Developer Control", "ind": "Integration & Delivery", "res": "Resource",
  "obs": "Observability", "sec": "Security",
}
STEP = {"dev": 1, "ind": 2, "res": 3, "obs": 4, "sec": 5}
CAPS = {
  "dev": ["IDE (local/cloud)", "Copilots / Agents", "Portal"],
  "ind": ["Version Control", "App Spec", "CI / CD", "Registry", "Orchestrator", "IaC"],
  "res": ["Compute", "Data", "Networking", "Services"],
  "obs": ["Monitoring & Logging", "Observability", "FinOps", "Incident Mgmt"],
  "sec": ["Code Analysis", "Secrets", "Identity", "Policy", "Network Security"],
}
ACT, TOPIC, HEADING = "Where we're heading", "The proposal", "From intent to running software"

def esc(s): return s.replace("&", "&amp;").replace("<", "&lt;")

def T(x, y, s, size=26, weight=600, fill=WHITE, anchor="start", ls=0, extra=""):
  lines = s.split("\n")
  dy0 = -(len(lines) - 1) * size * 0.6
  spans = "".join(f'<tspan x="{x}" dy="{dy0 if i == 0 else size * 1.2}">{esc(l)}</tspan>' for i, l in enumerate(lines))
  return (f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" fill="{fill}" '
          f'text-anchor="{anchor}" letter-spacing="{ls}" dominant-baseline="middle" {extra}>{spans}</text>')

def R(x, y, w, h, rx=12, fill=PANEL, stroke=LINE, sw=2, extra=""):
  return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}" {extra}/>'

def A(x1, y1, x2, y2, color=BLUE, sw=4, dash=""):
  d = f'stroke-dasharray="{dash}"' if dash else ""
  return f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="{sw}" {d} marker-end="url(#ah-{color[1:]})"/>'

def G(key_or_step, body):
  step = STEP.get(key_or_step, key_or_step)
  return f'<g class="st" data-step="{step}">{body}</g>'

def label_plane(x, y, key, size=30, fill=WHITE, anchor="start"):
  return T(x, y - size * 0.9, "PLANE", 14, 700, MUTED, anchor, 3) + T(x, y, PLANES[key], size, 700, fill, anchor)

# ── variants ─────────────────────────────────────────────
def v01():  # reference layout (slide 2): bands top/bottom, flow in the middle
  out = []
  out.append(G("obs", R(120, 190, 1360, 80, 14, PANEL, AMBER) + T(160, 230, "Observability", 30, 700, AMBER) + T(1440, 230, "PLANE", 14, 700, MUTED, "end", 3)))
  out.append(G("sec", R(120, 740, 1360, 80, 14, PANEL, AMBER) + T(160, 780, "Security", 30, 700, AMBER) + T(1440, 780, "PLANE", 14, 700, MUTED, "end", 3)))
  xs = [120, 610, 1100]
  for i, k in enumerate(["dev", "ind", "res"]):
    body = R(xs[i], 320, 380, 370, 16) + label_plane(xs[i] + 190, 515, k, 32, anchor="middle")
    if i: body = A(xs[i] - 100, 505, xs[i] - 18, 505) + body
    out.append(G(k, body))
  return out

def v02():  # same as 01 + capabilities as empty chips
  out = []
  for key, y in (("obs", 180), ("sec", 730)):
    body = R(120, y, 1360, 100, 14, PANEL, AMBER) + T(150, y + 50, PLANES[key], 26, 700, AMBER)
    cx = 420
    w = (1450 - cx - 10 * (len(CAPS[key]) - 1)) / len(CAPS[key])
    for c in CAPS[key]:
      body += R(cx, y + 22, w, 56, 10, "#0a0e1a", LINE) + T(cx + w / 2, y + 50, c, 19, 500, SOFT, "middle")
      cx += w + 10
    out.append(G(key, body))
  xs = [120, 610, 1100]
  for i, k in enumerate(["dev", "ind", "res"]):
    x = xs[i]
    body = R(x, 310, 380, 390, 16) + T(x + 30, 352, PLANES[k], 26, 700)
    caps = CAPS[k]
    cols = 2 if len(caps) > 4 else 1
    cw = (320 - 12 * (cols - 1)) / cols
    for j, c in enumerate(caps):
      cx = x + 30 + (j % cols) * (cw + 12)
      cy = 390 + (j // cols) * 72
      body += R(cx, cy, cw, 58, 10, "#0a0e1a", LINE) + T(cx + cw / 2, cy + 29, c, 19, 500, SOFT, "middle")
    if i: body = A(x - 100, 505, x - 18, 505) + body
    out.append(G(k, body))
  return out

def chevron(x, y, w, h, tip=50, first=False):
  pts = [(x, y), (x + w - tip, y), (x + w, y + h / 2), (x + w - tip, y + h), (x, y + h)]
  if not first: pts.append((x + tip, y + h / 2))
  return "<polygon points='" + " ".join(f"{a},{b}" for a, b in pts) + f"' fill='{PANEL}' stroke='{BLUE}' stroke-width='2'/>"

def v03():  # chevrons + support rails underneath
  out = []
  xs = [120, 580, 1040]
  centers = []
  for i, k in enumerate(["dev", "ind", "res"]):
    x = xs[i]
    cx = x + (440 + (0 if i == 0 else 50)) / 2 - 10
    centers.append(cx)
    out.append(G(k, chevron(x, 230, 440, 240, 60, i == 0) + label_plane(cx + 10, 370, k, 30, anchor="middle")))
  for key, y in (("obs", 600), ("sec", 730)):
    body = R(330, y, 1150, 90, 45, PANEL, AMBER) + T(120, y + 45, PLANES[key], 26, 700, AMBER)
    for cx in centers:
      body += f'<line x1="{cx + 10}" y1="478" x2="{cx + 10}" y2="{y}" stroke="{AMBER}" stroke-width="2" stroke-dasharray="4 8" opacity="0.6"/>'
      body += f'<circle cx="{cx + 10}" cy="{y + 45}" r="9" fill="{AMBER}"/>'
    out.append(G(key, body))
  return out

def v04():  # rows top→down with chips; support as tall side pills (ref: Naver)
  out = []
  ys = [200, 410, 620]
  for i, k in enumerate(["dev", "ind", "res"]):
    y = ys[i]
    body = R(330, y, 940, 180, 18, PANEL, BLUE) + T(370, y + 90, PLANES[k].replace(" & ", "\n& "), 26, 700)
    cx, cw = 640, 190
    for j, c in enumerate(CAPS[k]):
      col, row = j % 3, j // 3
      ry = y + (90 - 30 if len(CAPS[k]) <= 3 else 30 + row * 66)
      body += R(cx + col * (cw + 12), ry, cw, 54, 10, "#0a0e1a", LINE) + T(cx + col * (cw + 12) + cw / 2, ry + 27, c, 18, 500, SOFT, "middle")
    if i: body = A(360, y - 34, 360, y - 6, BLUE, 4) + body
    out.append(G(k, body))
  grad = (f'<defs><linearGradient id="gobs" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{AMBER}"/><stop offset="1" stop-color="#b8863b"/></linearGradient></defs>')
  out.append(G("obs", grad + R(1310, 200, 170, 600, 26, "url(#gobs)", "none", 0) + T(1395, 500, "Observability", 24, 800, "#0a0e1a", "middle", 0, 'transform="rotate(-90 1395 500)"')))
  out.append(G("sec", R(120, 200, 170, 600, 26, "url(#gobs)", "none", 0) + T(205, 500, "Security", 24, 800, "#0a0e1a", "middle", 0, 'transform="rotate(-90 205 500)"')))
  return out

def v05():  # nested circles: Resource at the core (ref: IMC process)
  out = []
  cx, cy = 1620, 560
  rings = [("dev", 860, "#0f1524", 890), ("ind", 600, "#151d30", 1150), ("res", 340, "#1c2640", 1430)]
  for k, r, f, _ in rings:
    out.append(G(k, f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{f}" stroke="#24304a" stroke-width="2"/>'))
  for k, r, f, tx in rings:
    out.append(G(k, T(tx, 395, "PLANE", 14, 700, MUTED, "middle", 3) + T(tx, 450, PLANES[k].replace(" & ", "\n& "), 28, 700, WHITE, "middle")))
  out.append(G("dev", A(780, 250, 1500, 250, BLUE, 3) + T(780, 215, "FROM INTENT TO RUNNING SOFTWARE", 14, 700, BLUE, "start", 3)))
  out.append(G("obs", R(120, 610, 360, 76, 38, PANEL, AMBER) + T(300, 648, "Observability", 26, 700, AMBER, "middle")))
  out.append(G("sec", R(120, 710, 360, 76, 38, PANEL, AMBER) + T(300, 748, "Security", 26, 700, AMBER, "middle")))
  out.append(G("obs", T(120, 570, "ACROSS ALL LAYERS", 14, 700, AMBER, "start", 3)))
  return out

def v06():  # numbered columns, current one lit (ref: portfolio menu)
  out = []
  keys = ["dev", "ind", "res", "obs", "sec"]
  x, w = 120, 252
  for i, k in enumerate(keys):
    gap = 40 if i == 3 else 10
    if i: x += w + gap
    support = k in ("obs", "sec")
    stroke = AMBER if support else LINE
    dash = 'stroke-dasharray="8 8"' if support else ""
    body = (f'<rect class="col" data-on="{STEP[k]}" x="{x}" y="250" width="{w}" height="560" rx="4" fill="{PANEL}" stroke="{stroke}" stroke-width="2" {dash}/>'
            + T(x + 26, 300, f"0{i + 1}", 34, 800, WHITE)
            + T(x + 26, 560, {"dev": "Developer\nControl", "ind": "Integration\n& Delivery"}.get(k, PLANES[k]), 28, 700))
    for j, c in enumerate(CAPS[k]):
      body += T(x + 26, 640 + j * 30, c, 18, 500, SOFT)
    out.append(G(k, body))
  out.append(G("dev", A(146, 215, 900, 215, BLUE, 3)))
  out.append(G("obs", T(1180, 215, "SUPPORTING", 16, 700, AMBER, "start", 4)))
  return out

def iso(cx, cy, hw, hh, th, top, side, stroke):
  t = f"{cx},{cy - hh} {cx + hw},{cy} {cx},{cy + hh} {cx - hw},{cy}"
  l = f"{cx - hw},{cy} {cx},{cy + hh} {cx},{cy + hh + th} {cx - hw},{cy + th}"
  r = f"{cx + hw},{cy} {cx},{cy + hh} {cx},{cy + hh + th} {cx + hw},{cy + th}"
  return (f"<polygon points='{l}' fill='{side}' stroke='{stroke}'/><polygon points='{r}' fill='{side}' opacity='0.8' stroke='{stroke}'/>"
          f"<polygon points='{t}' fill='{top}' stroke='{stroke}'/>")

def arc(cx, cy, r, a0, a1):
  p = lambda a: (cx + r * math.cos(math.radians(a)), cy + r * math.sin(math.radians(a)))
  (x0, y0), (x1, y1) = p(a0), p(a1)
  large = 1 if abs(a1 - a0) > 180 else 0
  return f"M{x0:.1f},{y0:.1f} A{r},{r} 0 {large} 1 {x1:.1f},{y1:.1f}"

def v07():  # orbit around stacked layers (ref: isometric orbit)
  out = []
  cx = 800
  out.append(G("dev", f'<circle cx="{cx}" cy="230" r="28" fill="{WHITE}"/>' + T(cx + 50, 230, "Developer Control", 24, 700)))
  out.append(G("ind", f'<line x1="{cx}" y1="260" x2="{cx}" y2="400" stroke="{BLUE}" stroke-width="3" marker-end="url(#ah-{BLUE[1:]})"/>'
               + iso(cx, 450, 150, 62, 18, "#2a3550", "#1a2238", "#3a4766") + iso(cx, 420, 150, 62, 18, "#3a4766", "#222c45", "#4a5878")
               + T(cx + 170, 440, "Integration\n& Delivery", 22, 700)))
  out.append(G("res", f'<line x1="{cx}" y1="520" x2="{cx}" y2="575" stroke="{BLUE}" stroke-width="3" marker-end="url(#ah-{BLUE[1:]})"/>'
               + iso(cx, 650, 230, 92, 70, "#c9d3e0", "#5b6678", "#e6ecf3") + T(cx, 830, "Resource", 22, 700, WHITE, "middle")))
  out.append(G("obs", f'<path d="{arc(cx, 530, 340, 125, 235)}" fill="none" stroke="{AMBER}" stroke-width="5"/>'
               + f'<line x1="300" y1="530" x2="450" y2="530" stroke="{AMBER}" stroke-width="2"/>' + T(280, 530, "Observability", 28, 700, AMBER, "end")))
  out.append(G("sec", f'<path d="{arc(cx, 530, 340, -55, 55)}" fill="none" stroke="{AMBER}" stroke-width="5"/>'
               + f'<line x1="1150" y1="530" x2="1300" y2="530" stroke="{AMBER}" stroke-width="2"/>' + T(1320, 530, "Security", 28, 700, AMBER)))
  return out

def v08():  # loop: Observability feeds back to the developer; Security at the hub
  out = []
  cx, cy, r = 800, 525, 250
  segs = [("dev", -145, -40), ("ind", -30, 60), ("res", 70, 160), ("obs", 170, 200)]
  labels = {"dev": (800, 210), "ind": (1150, 470), "res": (800, 850), "obs": (430, 470)}
  for k, a0, a1 in segs:
    color = AMBER if k == "obs" else BLUE
    body = f'<path d="{arc(cx, cy, r, a0, a1)}" fill="none" stroke="{color}" stroke-width="44" stroke-linecap="butt"/>'
    p = (cx + r * math.cos(math.radians(a1)), cy + r * math.sin(math.radians(a1)))
    body += f'<polygon points="0,-36 30,0 0,36" fill="{color}" transform="translate({p[0]:.1f},{p[1]:.1f}) rotate({a1 + 90:.1f})"/>'
    lx, ly = labels[k]
    anchor = "middle" if k in ("dev", "res") else ("start" if k == "ind" else "end")
    body += T(lx, ly, PLANES[k].replace(" & ", "\n& ") if k == "ind" else PLANES[k], 28, 700, color if k == "obs" else WHITE, anchor)
    out.append(G(k, body))
  # obs closes the loop back to dev
  
  out.append(G("sec", f'<circle cx="{cx}" cy="{cy}" r="150" fill="{PANEL}" stroke="{AMBER}" stroke-width="3" stroke-dasharray="6 8"/>' + T(cx, cy, "Security", 30, 700, AMBER, "middle")))
  return out

def v09():  # temple: flow layers held by two pillars
  out = []
  ys = [250, 430, 610]
  for i, k in enumerate(["dev", "ind", "res"]):
    y = ys[i]
    body = R(340, y, 920, 120, 14, PANEL, BLUE) + T(800, y + 60, PLANES[k], 32, 700, WHITE, "middle")
    if i: body = A(800, y - 58, 800, y - 8, BLUE, 4) + body
    out.append(G(k, body))
  out.append(G("obs", R(130, 220, 170, 540, 10, PANEL, AMBER) + T(215, 490, "Observability", 28, 700, AMBER, "middle", 0, 'transform="rotate(-90 215 490)"')))
  out.append(G("sec", R(1300, 220, 170, 540, 10, PANEL, AMBER) + T(1385, 490, "Security", 28, 700, AMBER, "middle", 0, 'transform="rotate(-90 1385 490)"')))
  out.append(G("obs", R(110, 780, 1380, 26, 6, "#1a2238", LINE)))
  return out

def v10():  # subway line: stations on the flow, two tracks running along
  out = []
  xs = [260, 800, 1340]
  for i, k in enumerate(["dev", "ind", "res"]):
    x = xs[i]
    body = f'<circle cx="{x}" cy="420" r="26" fill="{BG}" stroke="{BLUE}" stroke-width="8"/>' + T(x, 340, PLANES[k], 30, 700, WHITE, "middle")
    if i: body = f'<line x1="{xs[i - 1] + 30}" y1="420" x2="{x - 30}" y2="420" stroke="{BLUE}" stroke-width="10"/>' + body
    out.append(G(k, body))
  for key, y in (("obs", 600), ("sec", 720)):
    body = f'<line x1="120" y1="{y}" x2="1480" y2="{y}" stroke="{AMBER}" stroke-width="4" stroke-dasharray="14 10"/>' + T(120, y - 34, PLANES[key], 26, 700, AMBER)
    for x in xs:
      body += f'<line x1="{x}" y1="450" x2="{x}" y2="{y}" stroke="{AMBER}" stroke-width="2" opacity="0.35"/><circle cx="{x}" cy="{y}" r="10" fill="{AMBER}"/>'
    out.append(G(key, body))
  return out

FULL = {"dev": "Developer Control\nPlane", "ind": "Integration & Delivery\nPlane", "res": "Resource\nPlane"}

def v01b():  # 01 with full names ("... Plane")
  out = []
  out.append(G("obs", R(120, 190, 1360, 80, 14, PANEL, AMBER) + T(160, 230, "Observability Plane", 30, 700, AMBER)))
  out.append(G("sec", R(120, 740, 1360, 80, 14, PANEL, AMBER) + T(160, 780, "Security Plane", 30, 700, AMBER)))
  xs = [120, 610, 1100]
  for i, k in enumerate(["dev", "ind", "res"]):
    body = R(xs[i], 320, 380, 370, 16) + T(xs[i] + 190, 505, FULL[k], 30, 700, WHITE, "middle")
    if i: body = A(xs[i] - 100, 505, xs[i] - 18, 505) + body
    out.append(G(k, body))
  return out

def v02b():  # 02 with full names ("... Plane")
  out = []
  for key, y in (("obs", 180), ("sec", 730)):
    body = R(120, y, 1360, 100, 14, PANEL, AMBER) + T(150, y + 50, PLANES[key] + "\nPlane", 24, 700, AMBER)
    cx = 420
    w = (1450 - cx - 10 * (len(CAPS[key]) - 1)) / len(CAPS[key])
    for c in CAPS[key]:
      body += R(cx, y + 22, w, 56, 10, "#0a0e1a", LINE) + T(cx + w / 2, y + 50, c, 19, 500, SOFT, "middle")
      cx += w + 10
    out.append(G(key, body))
  xs = [120, 610, 1100]
  for i, k in enumerate(["dev", "ind", "res"]):
    x = xs[i]
    body = R(x, 310, 380, 390, 16) + T(x + 30, 352, PLANES[k] + " Plane", 24 if k != "ind" else 22, 700)
    caps = CAPS[k]
    cols = 2 if len(caps) > 4 else 1
    cw = (320 - 12 * (cols - 1)) / cols
    for j, c in enumerate(caps):
      cx = x + 30 + (j % cols) * (cw + 12)
      cy = 390 + (j // cols) * 72
      body += R(cx, cy, cw, 58, 10, "#0a0e1a", LINE) + T(cx + cw / 2, cy + 29, c, 19, 500, SOFT, "middle")
    if i: body = A(x - 100, 505, x - 18, 505) + body
    out.append(G(k, body))
  return out

DEV_CLI = ["IDE (local/cloud)", "Copilots / Agents", "Portal", "CLI"]

CHIP_FS = 17

def landscape(x0=120, x1=1480, yo=180, yb=310, hb=390, ys=730, dev=None, ch=58, step=72, hl=None, full=False, gap=110, tfs=None, pill=False, bandcaps=True, arrow=BLUE):
  """v02 layout, parametrized; hl = capability to highlight."""
  out, caps = [], dict(CAPS, dev=dev or CAPS["dev"])
  def chip(x, y, w, h, c):
    on = c == hl
    fs = CHIP_FS
    return (R(x, y, w, h, 10, "#0d1a2e" if on else "#0a0e1a", BLUE if on else LINE, 2)
            + T(x + w / 2, y + h / 2, c, fs, 700 if on else 500, WHITE if on else SOFT, "middle"))
  for key, y in (("obs", yo), ("sec", ys)):
    if not bandcaps:
      out.append(G(key, R(x0, y + 12, x1 - x0, 76, 38, PANEL, AMBER) + T((x0 + x1) / 2, y + 50, PLANES[key], 26, 700, AMBER, "middle")))
      continue
    body = R(x0, y, x1 - x0, 100, 50 if pill else 14, PANEL, AMBER) + T(x0 + (50 if pill else 30), y + 50, PLANES[key], 26, 700, AMBER)
    cx = x0 + 300
    room = x1 - (40 if pill else 30) - cx - 10 * (len(caps[key]) - 1)
    tot = sum(len(c) + 6 for c in caps[key])
    for c in caps[key]:
      w = room * (len(c) + 6) / tot
      body += chip(cx, y + 22, w, 56, c).replace('rx="10"', 'rx="28"') if pill else chip(cx, y + 22, w, 56, c)
      cx += w + 10
    out.append(G(key, body))
  room = x1 - x0 - 2 * gap
  widths = [room * f for f in (0.3, 0.4, 0.3)]
  for i, k in enumerate(["dev", "ind", "res"]):
    bw = widths[i]
    x = x0 + sum(widths[:i]) + i * gap
    title = PLANES[k] + (" Plane" if full else "")
    body = R(x, yb, bw, hb, 16) + T(x + 30, yb + 42, title, tfs or ((22 if k == "ind" else 24) if full else 26), 700)
    cols = 2 if len(caps[k]) > 4 else 1
    cw = (bw - 60 - 12 * (cols - 1)) / cols
    for j, c in enumerate(caps[k]):
      body += chip(x + 30 + (j % cols) * (cw + 12), yb + 80 + (j // cols) * step, cw, ch, c)
    if i: body = A(x - gap + 18, yb + hb / 2, x - 14, yb + hb / 2, arrow) + body
    out.append(G(k, body))
  return out

def v02c():  # CLI as one more door in Developer Control
  return landscape(dev=DEV_CLI, ch=50, step=62, hl="CLI")

def v02g():  # 02c with full names on the flow planes only
  return landscape(dev=DEV_CLI, ch=50, step=62, hl="CLI", full=True)

def v02d():  # terminal window framing the whole platform
  out = [G("dev", f'<rect x="100" y="172" width="1400" height="676" rx="16" fill="none" stroke="{BLUE}" stroke-width="3"/>'
         + f'<path d="M100,188 a16,16 0 0 1 16,-16 h1368 a16,16 0 0 1 16,16 v34 h-1400 z" fill="#0d1a2e"/>'
         + "".join(f'<circle cx="{130 + i * 26}" cy="197" r="8" fill="{c}"/>' for i, c in enumerate(("#ff5f57", "#febc2e", "#28c840")))
         + T(220, 197, "$ platform  —  one CLI, every plane", 20, 700, BLUE, "start", 0, 'font-family="DejaVu Sans Mono, monospace"'))]
  return out + landscape(x0=130, x1=1470, yo=240, yb=360, hb=330, ys=720, step=66, ch=54)

def v02e():  # Portal, CLI and agents are clients of one Platform API bus
  out = landscape(dev=["IDE (local/cloud)", "Portal", "CLI", "Copilots / Agents"], yo=175, yb=295, hb=330, ys=715, ch=48, step=58, hl="CLI")
  y = 668
  bus = R(120, y - 20, 1360, 40, 20, "#0d1a2e", BLUE) + T(800, y, "PLATFORM API", 16, 800, BLUE, "middle", 4)
  for xc in centers(120, 1480, 110):
    bus += f'<line x1="{xc}" y1="625" x2="{xc}" y2="{y - 20}" stroke="{BLUE}" stroke-width="3"/><circle cx="{xc}" cy="{y - 20}" r="6" fill="{BLUE}"/>'
  for xc in (300, 1300):
    bus += f'<line x1="{xc}" y1="{y + 20}" x2="{xc}" y2="715" stroke="{BLUE}" stroke-width="3"/><circle cx="{xc}" cy="715" r="6" fill="{BLUE}"/>'
  bus += f'<path d="M1480,{y} h20 V225 h-20" fill="none" stroke="{BLUE}" stroke-width="3"/><circle cx="1480" cy="225" r="6" fill="{BLUE}"/>'
  return out + [G("dev", bus)]

def v02f():  # CLI spine on the left touching every plane
  out = landscape(x0=300, x1=1480)
  sp = R(120, 180, 130, 650, 16, "#0d1a2e", BLUE) + T(185, 225, ">_", 34, 800, BLUE, "middle", 0, 'font-family="DejaVu Sans Mono, monospace"')
  sp += T(185, 505, "CLI", 34, 800, WHITE, "middle", 6, 'transform="rotate(-90 185 505)"')
  for y in (230, 780):
    sp += f'<line x1="250" y1="{y}" x2="300" y2="{y}" stroke="{BLUE}" stroke-width="3"/><circle cx="300" cy="{y}" r="6" fill="{BLUE}"/>'
  cs = centers(300, 1480, 110)
  sp += f'<path d="M250,295 H{cs[-1]}" fill="none" stroke="{BLUE}" stroke-width="3"/>'
  for xc in cs:
    sp += f'<line x1="{xc}" y1="295" x2="{xc}" y2="310" stroke="{BLUE}" stroke-width="3"/><circle cx="{xc}" cy="310" r="6" fill="{BLUE}"/>'
  return out + [G("dev", sp)]

MONO = 'font-family="DejaVu Sans Mono, monospace"'
SX0, SX1, GAP = 290, 1480, 70

def centers(x0=SX0, x1=SX1, gap=GAP):
  room = x1 - x0 - 2 * gap
  ws = [room * f for f in (0.3, 0.4, 0.3)]
  return [x0 + sum(ws[:i]) + i * gap + ws[i] / 2 for i in range(3)]

def taps(x_from, yo=180, yb=330, ys=730, x0=SX0, color=BLUE):
  """Connectors from a vertical spine (right edge x_from) to every plane."""
  bus = yb - 26
  out = ""
  for y in (yo + 50, ys + 50):
    out += f'<line x1="{x_from}" y1="{y}" x2="{x0}" y2="{y}" stroke="{color}" stroke-width="3"/><circle cx="{x0}" cy="{y}" r="6" fill="{color}"/>'
  cs = centers(x0)
  out += f'<path d="M{x_from},{bus} H{cs[-1]}" fill="none" stroke="{color}" stroke-width="3"/>'
  for xc in cs:
    out += f'<line x1="{xc}" y1="{bus}" x2="{xc}" y2="{yb}" stroke="{color}" stroke-width="3"/><circle cx="{xc}" cy="{yb}" r="6" fill="{color}"/>'
  return out

def flow(**kw):
  return landscape(x0=SX0, x1=SX1, gap=GAP, yo=180, yb=330, hb=370, ys=730, full=True, tfs=21, **kw)

def v02h():  # spine, refined: full names, more room
  sp = R(120, 180, 130, 650, 16, "#0d1a2e", BLUE) + T(185, 228, ">_", 34, 800, BLUE, "middle", 0, MONO)
  sp += T(185, 505, "CLI", 34, 800, WHITE, "middle", 6, 'transform="rotate(-90 185 505)"')
  return flow() + [G("dev", sp + taps(250))]

def v02i():  # spine + a sample command on each connector
  sp = R(120, 180, 130, 650, 16, "#0d1a2e", BLUE) + T(185, 228, ">_", 34, 800, BLUE, "middle", 0, MONO)
  sp += T(185, 505, "CLI", 34, 800, WHITE, "middle", 6, 'transform="rotate(-90 185 505)"')
  cs = centers()
  lab = lambda x, y, c: T(x, y, c, 15, 700, BLUE, "start", 0, MONO)
  cmds = lab(cs[0] + 12, 292, "init") + lab(cs[1] + 12, 292, "deploy") + lab(cs[2] + 12, 292, "db create")
  cmds += lab(258, 214, "logs") + lab(258, 764, "secrets")
  return flow() + [G("dev", sp + taps(250) + cmds)]

def v02j():  # spine as a terminal window listing commands
  sp = R(110, 180, 170, 650, 14, "#070b14", BLUE)
  sp += f'<path d="M110,194 a14,14 0 0 1 14,-14 h142 a14,14 0 0 1 14,14 v24 h-170 z" fill="#0d1a2e"/>'
  sp += "".join(f'<circle cx="{132 + i * 20}" cy="199" r="6" fill="{c}"/>' for i, c in enumerate(("#ff5f57", "#febc2e", "#28c840")))
  lines = ["$ platform", "  init", "  deploy", "  db create", "  logs", "  cost", "  secrets", "  access", "", "> _"]
  for i, l in enumerate(lines):
    sp += T(128, 262 + i * 46, l, 18, 600 if i else 800, BLUE if i in (0, 9) else SOFT, "start", 0, MONO + ' xml:space="preserve"')
  return flow() + [G("dev", sp + taps(280))]

def v02k():  # Developer Control becomes the left column that reaches every plane
  out = landscape(x0=530, x1=1480, gap=90, yo=180, yb=330, hb=370, ys=730, full=True, tfs=22)
  out = [o for o in out if 'Developer Control' not in o]
  # rebuild flow as two boxes: Integration & Delivery, Resource
  out = [o for o in out if 'Integration' not in o and 'Resource Plane' not in o]
  bw = (1480 - 530 - 90) / 2
  for i, k in enumerate(["ind", "res"]):
    x = 530 + i * (bw + 90)
    body = R(x, 330, bw, 370, 16) + T(x + 30, 372, PLANES[k] + " Plane", 22, 700)
    cols = 2
    cw = (bw - 60 - 12) / cols
    for j, c in enumerate(CAPS[k]):
      cx, cy = x + 30 + (j % cols) * (cw + 12), 410 + (j // cols) * 70
      body += R(cx, cy, cw, 56, 10, "#0a0e1a", LINE) + T(cx + cw / 2, cy + 28, c, 19, 500, SOFT, "middle")
    if i: body = A(x - 72, 515, x - 14, 515) + body
    out.append(G(k, body))
  d = R(120, 180, 330, 650, 16, PANEL, BLUE) + T(150, 225, "Developer\nControl Plane", 24, 700)
  for j, c in enumerate(["IDE (local/cloud)", "Copilots / Agents", "Portal", "CLI"]):
    on = c == "CLI"
    d += R(150, 300 + j * 76, 270, 58, 10, "#0d1a2e" if on else "#0a0e1a", BLUE if on else LINE) + T(285, 329 + j * 76, c, 19, 700 if on else 500, WHITE if on else SOFT, "middle")
  for y in (230, 780):
    d += f'<line x1="450" y1="{y}" x2="530" y2="{y}" stroke="{BLUE}" stroke-width="3"/><circle cx="530" cy="{y}" r="6" fill="{BLUE}"/>'
  d += A(458, 515, 516, 515)
  return out + [G("dev", d)]

def v02l():  # minimal: thin line with a CLI badge
  sp = f'<line x1="185" y1="230" x2="185" y2="780" stroke="{BLUE}" stroke-width="4"/>'
  sp += R(130, 470, 110, 70, 35, "#0d1a2e", BLUE) + T(185, 505, ">_ CLI", 22, 800, WHITE, "middle", 0, MONO)
  return flow() + [G("dev", sp + taps(185))]

def api_frame(x0, y0, x1, y1, label="PLATFORM API"):
  f = f'<path d="M{x0},{y0 + 18} a18,18 0 0 1 18,-18 h{x1 - x0 - 36} a18,18 0 0 1 18,18 v28 h-{x1 - x0} z" fill="#0d1a2e"/>'
  f += f'<rect x="{x0}" y="{y0}" width="{x1 - x0}" height="{y1 - y0}" rx="18" fill="none" stroke="{BLUE}" stroke-width="3"/>'
  f += T(x0 + 28, y0 + 24, label, 17, 800, BLUE, "start", 4)
  return f

def cli_box(x, y, w=150, h=110):
  return (R(x, y, w, h, 14, "#0d1a2e", BLUE, 3) + T(x + w / 2, y + 40, ">_", 30, 800, BLUE, "middle", 0, MONO)
          + T(x + w / 2, y + 80, "CLI", 26, 800, WHITE, "middle", 4))

def inner(**kw):
  return landscape(x0=320, x1=1460, gap=70, yo=232, yb=362, hb=340, ys=732, full=True, tfs=20, ch=50, step=62, **kw)

def v02m():  # Platform API wraps everything; CLI is a small box outside
  fr = api_frame(290, 182, 1490, 862)
  cli = cli_box(80, 470) + A(232, 525, 284, 525, BLUE, 4)
  return [G("dev", fr)] + inner() + [G("dev", cli)]

def v02n():  # outside clients: CLI, Portal, Agents → Platform API
  fr = api_frame(290, 182, 1490, 862)
  dev = ["IDE (local/cloud)", "Copilots / Agents", "Portal"]
  side = ""
  for j, (ic, name) in enumerate(((">_", "CLI"), ("◧", "Portal"), ("✦", "Agents"))):
    y = 330 + j * 150
    on = name == "CLI"
    side += R(80, y, 150, 110, 14, "#0d1a2e" if on else PANEL, BLUE if on else LINE, 3 if on else 2)
    side += T(155, y + 40, ic, 28, 800, BLUE if on else SOFT, "middle", 0, MONO) + T(155, y + 80, name, 22, 800 if on else 600, WHITE if on else SOFT, "middle")
    side += A(232, y + 55, 284, y + 55, BLUE if on else MUTED, 3)
  side += T(155, 300, "CLIENTS", 14, 700, MUTED, "middle", 3)
  return [G("dev", fr)] + inner(dev=dev) + [G("dev", side)]

def v02o():  # CLI box sits on the frame edge, like a plug
  fr = api_frame(170, 182, 1490, 862)
  cli = cli_box(100, 470, 150, 110)
  body = landscape(x0=320, x1=1460, gap=70, yo=232, yb=362, hb=340, ys=732, full=True, tfs=20, ch=50, step=62)
  return [G("dev", fr)] + body + [G("dev", cli + A(252, 525, 314, 525, BLUE, 4))]

def v02p():  # CLI on top, issuing into the frame
  fr = api_frame(120, 262, 1480, 862)
  cli = R(640, 168, 320, 70, 14, "#0d1a2e", BLUE, 3) + T(800, 203, ">_  CLI", 26, 800, WHITE, "middle", 2, MONO)
  cli += A(800, 240, 800, 258, BLUE, 4)
  body = landscape(x0=150, x1=1450, gap=80, yo=312, yb=432, hb=290, ys=742, full=True, tfs=21, ch=44, step=54)
  body = [b.replace('y="830"', 'y="830"') for b in body]
  return [G("dev", fr)] + body + [G("dev", cli)]

def spine():
  sp = R(120, 180, 130, 650, 16, "#0d1a2e", BLUE) + T(185, 228, ">_", 34, 800, BLUE, "middle", 0, MONO)
  return sp + T(185, 505, "CLI", 34, 800, WHITE, "middle", 6, 'transform="rotate(-90 185 505)"')

def v02q():  # 02h with Observability / Security as pills (ref. 05)
  return flow(pill=True) + [G("dev", spine() + taps(250))]

def v02r():  # 02h with plain pills, no capabilities (ref. 05)
  return flow(bandcaps=False) + [G("dev", spine() + taps(250))]

def clients_side(names):
  side = T(155, 300, "CLIENTS", 14, 700, MUTED, "middle", 3)
  icons = {"CLI": ">_", "Portal": "◧", "Agents": "✦", "IDE": "{ }"}
  for j, name in enumerate(names):
    y = 330 + j * 150
    side += R(80, y, 150, 110, 14, "#0d1a2e", BLUE, 3)
    side += T(155, y + 40, icons[name], 28, 800, BLUE, "middle", 0, MONO) + T(155, y + 80, name, 22, 800, WHITE, "middle")
    side += A(232, y + 55, 284, y + 55, BLUE, 3)
  return side

def v02s():  # no duplication: clients outside, Developer Control holds what they consume
  fr = api_frame(290, 182, 1490, 862)
  dev = ["Software Catalog", "Golden Paths", "App Declaration"]
  return [G("dev", fr)] + inner(dev=dev) + [G("dev", clients_side(["CLI", "Portal", "Agents"]))]

def v02t():  # same, IDE joins the clients
  fr = api_frame(290, 182, 1490, 862)
  dev = ["Software Catalog", "Golden Paths", "App Declaration"]
  side = clients_side(["IDE", "CLI", "Portal", "Agents"]).replace("330 + j", "x")
  out = [G("dev", fr)] + inner(dev=dev)
  side = T(155, 225, "CLIENTS", 14, 700, MUTED, "middle", 3)
  icons = {"CLI": ">_", "Portal": "◧", "Agents": "✦", "IDE": "{ }"}
  for j, name in enumerate(["IDE", "CLI", "Portal", "Agents"]):
    y = 255 + j * 150
    side += R(80, y, 150, 110, 14, "#0d1a2e", BLUE, 3)
    side += T(155, y + 40, icons[name], 28, 800, BLUE, "middle", 0, MONO) + T(155, y + 80, name, 22, 800, WHITE, "middle")
    side += A(232, y + 55, 284, y + 55, BLUE, 3)
  return out + [G("dev", side)]

DEV_INNER = ["Software Catalog", "Golden Paths", "App Declaration"]

def inner_narrow(**kw):
  return landscape(x0=420, x1=1470, gap=56, yo=232, yb=362, hb=340, ys=732, full=True, tfs=18, ch=50, step=62, dev=DEV_INNER, arrow=SOFT, **kw)

def client_card(x, y, w, h, icon, name, lines, hl=False):
  c = R(x, y, w, h, 14, PANEL, LINE, 2)
  c += T(x + 22, y + 30, icon, 22, 800, SOFT, "start", 0, MONO) + T(x + 70, y + 30, name, 22, 800, WHITE)
  for i, l in enumerate(lines):
    mono = l.startswith("$") or l.endswith((".yaml", ".md"))
    c += T(x + 22, y + 68 + i * 28, l, 17, 500, SOFT, "start", 0, (MONO if mono else "") + ' xml:space="preserve"')
  return c + A(x + w + 4, y + h / 2, 394, y + h / 2, SOFT, 3)

def v02u():  # 02t + an example of each client's interaction
  fr = api_frame(400, 182, 1490, 862)
  # CLIENTS label on the same line as PLATFORM API; cards span Observability top → Security bottom
  cards = T(120, 206, "CLIENTS", 17, 800, MUTED, "start", 4)
  items = [
    ("{ }", "IDE", ["app.yaml", "AGENTS.md"]),
    (">_", "CLI", ["$ platform init", "$ platform deploy"]),
    ("◧", "Portal", ["Browse the catalog", "Create from template"]),
    ("✦", "Agents", ["“Create a Postgres", "for greeting-api”"]),
  ]
  for j, (ic, name, lines) in enumerate(items):
    cards += client_card(120, 232 + j * 155, 236, 135, ic, name, lines, name == "CLI")
  return [G("dev", fr)] + inner_narrow() + [G("dev", cards)]

def v02v():  # 02t, CLI expanded as a terminal listing commands
  fr = api_frame(400, 182, 1490, 862)
  side = T(70, 200, "CLIENTS", 14, 700, MUTED, "start", 3)
  small = [("{ }", "IDE", 222), ("◧", "Portal", 642), ("✦", "Agents", 752)]
  for ic, name, y in small:
    side += R(60, y, 290, 90, 14, "#0b1220", BLUE, 2) + T(90, y + 45, ic, 24, 800, BLUE, "start", 0, MONO) + T(150, y + 45, name, 22, 800, WHITE)
    side += A(354, y + 45, 394, y + 45, BLUE, 3)
  y0, h = 332, 290
  side += R(60, y0, 290, h, 14, "#070b14", BLUE, 3)
  side += f'<path d="M60,{y0 + 14} a14,14 0 0 1 14,-14 h262 a14,14 0 0 1 14,14 v22 h-290 z" fill="#0d1a2e"/>'
  side += "".join(f'<circle cx="{82 + i * 20}" cy="{y0 + 18}" r="6" fill="{c}"/>' for i, c in enumerate(("#ff5f57", "#febc2e", "#28c840")))
  side += T(200, y0 + 18, "CLI", 16, 800, WHITE, "middle", 3)
  cmds = ["$ platform", "  init", "  deploy", "  db create", "  logs", "  cost", "  access"]
  for i, l in enumerate(cmds):
    side += T(84, y0 + 64 + i * 32, l, 18, 700 if i == 0 else 500, BLUE if i == 0 else SOFT, "start", 0, MONO + ' xml:space="preserve"')
  side += A(354, y0 + h / 2, 394, y0 + h / 2, BLUE, 4)
  return [G("dev", fr)] + inner_narrow() + [G("dev", side)]

CLI_GROUPS = [
  ("dev", "Developer Control", BLUE, [
    ("platform init greeting-api --template api", "new app from a golden path"),
    ("platform catalog search payments", "who owns what"),
  ]),
  ("ind", "Integration & Delivery", BLUE, [
    ("platform deploy --env dev", "build, ship, expose"),
    ("platform promote --to prod", "same artifact, next ring"),
  ]),
  ("res", "Resource", BLUE, [
    ("platform db create postgres", "database for the app"),
    ("platform llm enable --model claude", "AI through the gateway"),
  ]),
  ("obs", "Observability", AMBER, [
    ("platform logs --follow", "live logs"),
    ("platform cost --last 30d", "what this app costs"),
  ]),
  ("sec", "Security", AMBER, [
    ("platform secrets set API_KEY", "into the vault, never the repo"),
    ("platform access request --env prod", "audited, time-boxed"),
  ]),
]

def v_cli_examples():  # one CLI, every plane: example commands (illustrative)
  x0, y0, x1, y1 = 120, 182, 1480, 852
  out = R(x0, y0, x1 - x0, y1 - y0, 16, "#070b14", LINE, 2)
  out += f'<path d="M{x0},{y0 + 16} a16,16 0 0 1 16,-16 h{x1 - x0 - 32} a16,16 0 0 1 16,16 v30 h-{x1 - x0} z" fill="{PANEL}"/>'
  out += "".join(f'<circle cx="{x0 + 28 + i * 24}" cy="{y0 + 23}" r="7" fill="{c}"/>' for i, c in enumerate(("#ff5f57", "#febc2e", "#28c840")))
  out += T((x0 + x1) / 2, y0 + 23, "platform — one CLI, every plane", 17, 700, SOFT, "middle", 0, MONO)
  cols = [(x0 + 40, CLI_GROUPS[:3]), (x0 + 700, CLI_GROUPS[3:])]
  for cx, groups in cols:
    y = y0 + 100
    for k, name, color, cmds in groups:
      out += T(cx, y, "# " + name, 18, 800, color, "start", 0, MONO)
      y += 40
      for cmd, why in cmds:
        out += T(cx, y, "$ " + cmd, 18, 600, WHITE, "start", 0, MONO + ' xml:space="preserve"')
        out += T(cx + 24, y + 28, why, 16, 500, MUTED)
        y += 70
      y += 16
  return [G("dev", out)]

VARIANTS = [
  ("01-reference-bands", "Reference: bands top & bottom", "slide 2 do deck base, só os planes", v01),
  ("02c-cli-door", "CLI as a door", "CLI ao lado de IDE, agentes e portal no Developer Control", v02c),
  ("02e-cli-api-bus", "Platform API bus", "portal, CLI e agentes como clientes de uma mesma API que toca todos os planes", v02e),
  ("02m-api-frame-cli-box", "Platform API frame + CLI box", "a Platform API envolve tudo; a CLI é uma caixinha de fora que entra pela API", v02m),
  #("02n-api-frame-clients", "Platform API + clients", "CLI, Portal e Agents como clientes de fora; a CLI em destaque", v02n),
  ("02u-api-clients-examples", "Clients with examples", "a 02t com um exemplo de interação em cada cliente", v02u),
  ("cli-examples", "CLI examples", "uma CLI, todos os planes: exemplos de operação (ilustrativos)", v_cli_examples),
  ("04-rows-pillars", "Rows + side pills", "fluxo de cima para baixo com chips; suporte em pílulas laterais (ref. Naver)", v04),
  ("09-temple", "Temple", "camadas do fluxo apoiadas em dois pilares", v09),
]

# ── layered landscape for the technical deck ────────────
# The 02u drawing split into named parts (<g data-part>); render-outline's `diagram`
# slides reveal them one at a time. Arrowheads are polygons, not markers: the SVG is
# inlined once per step and markers break inside hidden (display: none) stages.
# `<key>-plane`: the empty plane (outline + name); `<key>.N`: its capabilities, one part each.
PARTS = ["dev-plane", "ind-plane", "res-plane", "obs-plane", "sec-plane", "api"]  # plus dev.N … sec.N and clients.N

def arrow(x1, y, x2, color=SOFT, sw=3):
  return (f'<line x1="{x1}" y1="{y}" x2="{x2 - 10}" y2="{y}" stroke="{color}" stroke-width="{sw}"/>'
          f'<polygon points="{x2 - 14},{y - 8} {x2},{y} {x2 - 14},{y + 8}" fill="{color}"/>')

def layered():
  x0, x1, gap, yo, yb, hb, ys = 420, 1470, 56, 232, 362, 340, 732
  parts = {k: "" for k in PARTS}
  # Integration & Delivery in flow order (code → artifact → spec → resources), read row by row.
  # Developer Control in narrative order: the catalog, how an app enters it, then the path that creates both.
  caps = dict(CAPS, dev=["Software Catalog", "App Declaration", "Golden Paths"], ind=["Version Control", "CI", "Registry", "Orchestrator", "IaC", "Delivery"])
  def chip(x, y, w, h, c):
    return R(x, y, w, h, 10, "#0a0e1a", LINE, 2) + T(x + w / 2, y + h / 2, c, CHIP_FS, 500, SOFT, "middle")
  for key, y in (("obs", yo), ("sec", ys)):
    parts[f"{key}-plane"] += R(x0, y, x1 - x0, 100, 14, PANEL, AMBER) + T(x0 + 30, y + 50, PLANES[key], 26, 700, AMBER)
    cx = x0 + 300
    room = x1 - 30 - cx - 10 * (len(caps[key]) - 1)
    tot = sum(len(c) + 6 for c in caps[key])
    for c in caps[key]:
      w = room * (len(c) + 6) / tot
      parts.setdefault(f"{key}.{len([p for p in parts if p.startswith(key + '.')]) + 1}", "")
      parts[f"{key}.{len([p for p in parts if p.startswith(key + '.')])}"] += chip(cx, y + 22, w, 56, c)
      cx += w + 10
  room = x1 - x0 - 2 * gap
  widths = [room * f for f in (0.3, 0.4, 0.3)]
  for i, k in enumerate(["dev", "ind", "res"]):
    bw = widths[i]
    x = x0 + sum(widths[:i]) + i * gap
    parts[f"{k}-plane"] += R(x, yb, bw, hb, 16) + T(x + 30, yb + 42, PLANES[k] + " Plane", 18, 700)
    cols = 2 if len(caps[k]) > 4 else 1
    cw = (bw - 60 - 12 * (cols - 1)) / cols
    for j, c in enumerate(caps[k]):
      parts[f"{k}.{j + 1}"] = chip(x + 30 + (j % cols) * (cw + 12), yb + 80 + (j // cols) * 62, cw, 50, c)
    if i:
      # The arrow into a plane is part of it: it appears with the box it points to.
      parts[f"{k}-plane"] = arrow(x - gap + 12, yb + hb / 2, x - 8) + parts[f"{k}-plane"]
  parts["api"] = api_frame(400, 182, 1490, 862)
  items = [
    ("{ }", "IDE", ["app.yaml", "AGENTS.md"]),
    (">_", "CLI", ["$ platform init", "$ platform deploy"]),
    ("◧", "Portal", ["Browse the catalog", "Create from template"]),
    ("✦", "Agents", ["“Create a Postgres", "for greeting-api”"]),
  ]
  # The label belongs to the first client; each card is its own part (`clients.1` …).
  for j, (ic, name, lines) in enumerate(items):
    parts[f"clients.{j + 1}"] = (T(120, 206, "CLIENTS", 17, 800, MUTED, "start", 4) if j == 0 else "") + client_card(120, 232 + j * 155, 236, 135, ic, name, lines).rsplit("<line", 1)[0] + arrow(360, 232 + j * 155 + 67.5, 396)
  # Capabilities are parts of their own (`dev.1`, `dev.2`…); `dev` addresses them all.
  body = "".join(f'<g data-part="{k}">{v}</g>' for k, v in parts.items() if v)
  return (f'<svg viewBox="100 170 1400 702" xmlns="http://www.w3.org/2000/svg" font-family="system-ui, sans-serif">{body}</svg>\n')

PAGE = """<!doctype html><html><head><meta charset="utf-8"><title>{title}</title><style>
html,body{{margin:0;height:100%;background:#000;font-family:system-ui,sans-serif}}
.wrap{{position:absolute;inset:0;display:flex;align-items:center;justify-content:center}}
svg{{width:100vw;height:56.25vw;max-height:100vh;max-width:177.78vh;background:{bg}}}
.st{{transition:opacity .35s}} .st.off{{opacity:0}}
.col.on{{fill:#2a2213;stroke:{amber};stroke-dasharray:none}}
.hud{{position:fixed;right:12px;bottom:8px;color:#6b7a8d;font-size:13px}}
</style></head><body><div class="wrap">
<svg viewBox="0 0 1600 900" xmlns="http://www.w3.org/2000/svg">
<defs>{markers}</defs>
<text x="120" y="70" font-size="18" font-weight="700" fill="#6b7a8d" letter-spacing="5">{act}</text>
<text x="120" y="104" font-size="26" font-weight="700" fill="#fff">{topic}</text>
<text x="120" y="150" font-size="22" font-weight="400" fill="#9fb3c8">{heading}</text>
{body}
<text x="120" y="878" font-size="14" fill="#6b7a8d">Source: platformengineering.org/platform-tooling · planes as parallel layers; the journey order is ours</text>
</svg></div><div class="hud">{name} · ←/→ steps · A all</div>
<script>
const els=[...document.querySelectorAll('.st')], max=5;
let cur=parseInt(location.hash.slice(1)); if(isNaN(cur)) cur=max;
function show(n){{cur=Math.max(0,Math.min(max,n)); location.replace('#'+cur);
 els.forEach(e=>e.classList.toggle('off',+e.dataset.step>cur));
 document.querySelectorAll('[data-on]').forEach(e=>e.classList.toggle('on',+e.dataset.on===cur));}}
document.addEventListener('keydown',e=>{{
 if(['ArrowRight','ArrowDown',' ','PageDown'].includes(e.key)){{e.preventDefault();show(cur+1)}}
 if(['ArrowLeft','ArrowUp','PageUp'].includes(e.key)){{e.preventDefault();show(cur-1)}}
 if(e.key==='a'||e.key==='A')show(max); if(e.key==='Home')show(0);}});
window.addEventListener('hashchange',()=>show(parseInt(location.hash.slice(1))||0));
show(cur);
</script></body></html>"""

def markers():
  return "".join(f'<marker id="ah-{c[1:]}" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="{c}"/></marker>' for c in (BLUE, AMBER, SOFT))

INDEX = """<!doctype html><html><head><meta charset="utf-8"><title>Landscape previews</title><style>
body{{margin:0;padding:24px;background:#05070d;color:#c0d2e4;font-family:system-ui,sans-serif}}
h1{{font-size:20px;margin:0 0 4px}} p.hint{{color:#6b7a8d;margin:0 0 20px}}
.grid{{display:grid;grid-template-columns:repeat(2,1fr);gap:28px}}
.card a{{color:#e5c07b;text-decoration:none;font-weight:700;font-size:17px}}
.card .d{{color:#6b7a8d;font-size:14px;margin:4px 0 8px}}
iframe{{width:100%;aspect-ratio:16/9;border:1px solid #1f2937;border-radius:6px;pointer-events:none}}
</style></head><body><h1>Landscape vazia — {n} variantes</h1>
<p class="hint">Mesmo conteúdo em todas. Clique no título para abrir em tela cheia (←/→ revela plane a plane; A mostra tudo).</p>
<div class="grid">{cards}</div></body></html>"""

# Exploration previews (variant grid and deck) only on request: the slides use landscape.svg.
if "--previews" in sys.argv:
  cards = []
  for fname, title, desc, fn in VARIANTS:
    body = "\n".join(fn())
    page = PAGE.format(title=title, bg=BG, amber=AMBER, markers=markers(), act=ACT.upper(), topic=TOPIC,
                       heading=HEADING, body=body, name=fname)
    (OUT / f"{fname}.html").write_text(page)
    cards.append(f'<div class="card"><a href="{fname}.html#0" target="_blank">{fname} — {title}</a><div class="d">{desc}</div><iframe src="{fname}.html#5"></iframe></div>')
  (OUT / "index.html").write_text(INDEX.format(n=len(VARIANTS), cards="".join(cards)))
  print("ok", len(VARIANTS))

  # ── deck: one variant per slide ──────────────────────────
  DECK = """<!doctype html><html><head><meta charset="utf-8"><title>Landscape — variantes</title><style>
  html,body{{margin:0;height:100%;background:#000;font-family:system-ui,sans-serif;overflow:hidden}}
  .slide{{position:absolute;inset:0;display:none;align-items:center;justify-content:center}}
  .slide.on{{display:flex}}
  svg{{width:100vw;height:56.25vw;max-height:100vh;max-width:177.78vh;background:{bg}}}
  .hud{{position:fixed;right:14px;bottom:10px;color:#6b7a8d;font-size:14px}}
  </style></head><body>{slides}
  <div class="hud" id="hud"></div>
  <script>
  const s=[...document.querySelectorAll('.slide')];let cur=(parseInt(location.hash.slice(1))||1)-1;
  function show(n){{cur=Math.max(0,Math.min(s.length-1,n));s.forEach((e,i)=>e.classList.toggle('on',i===cur));
   location.replace('#'+(cur+1));document.getElementById('hud').textContent=s[cur].dataset.name+'  ·  '+(cur+1)+'/'+s.length+'  ·  ←/→  ·  F tela cheia';}}
  document.addEventListener('keydown',e=>{{
   if(['ArrowRight','ArrowDown',' ','PageDown'].includes(e.key)){{e.preventDefault();show(cur+1)}}
   if(['ArrowLeft','ArrowUp','PageUp'].includes(e.key)){{e.preventDefault();show(cur-1)}}
   if(e.key==='Home')show(0); if(e.key==='End')show(s.length-1);
   if(e.key==='f'||e.key==='F')document.fullscreenElement?document.exitFullscreen():document.documentElement.requestFullscreen();}});
  show(cur);
  </script></body></html>"""

  slides = []
  for i, (fname, title, desc, fn) in enumerate(VARIANTS, 1):
    body = "\n".join(fn()).replace('class="col" data-on="5"', 'class="col"')
    svg = (f'<svg viewBox="0 0 1600 900" xmlns="http://www.w3.org/2000/svg"><defs>{markers()}</defs>'
           f'<text x="120" y="70" font-size="18" font-weight="700" fill="#6b7a8d" letter-spacing="5">{ACT.upper()}</text>'
           f'<text x="120" y="104" font-size="26" font-weight="700" fill="#fff">{TOPIC}</text>'
           f'<text x="120" y="150" font-size="22" font-weight="400" fill="#9fb3c8">{HEADING}</text>'
           f'{body}<text x="120" y="878" font-size="14" fill="#6b7a8d">Source: platformengineering.org/platform-tooling · '
           f'planes as parallel layers; the journey order is ours</text>'
           f'<text x="1480" y="70" font-size="18" font-weight="700" fill="#e5c07b" text-anchor="end">{fname.split("-")[0]} · {esc(title)}</text></svg>')
    svg = svg.replace("ah-", f"ah{i}-")
    slides.append(f'<div class="slide" data-name="{fname}">{svg}</div>')
  (OUT / "deck.html").write_text(DECK.format(bg=BG, slides="".join(slides)))
  print("deck ok")

(OUT / "landscape.svg").write_text(layered())
print("landscape.svg ok")
# The CLI terminal as a one-part diagram, for the technical deck.
(OUT / "cli.svg").write_text('<svg viewBox="100 170 1400 702" xmlns="http://www.w3.org/2000/svg" font-family="system-ui, sans-serif">'
                             f'<g data-part="cli">{"".join(v_cli_examples())}</g></svg>\n')
print("cli.svg ok")
