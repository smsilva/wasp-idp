# Deck navigation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The deck's main track walks only the landscape diagram; a box's detail opens on click, with a breadcrumb (where I am) and a back link (where I came from).

**Architecture:** `render-outline` (one Python script that writes one self-contained HTML) learns detail slides (`parent`): their steps go after the main track and carry their breadcrumb, overlay and exit data; the HTML marks them with `data-*` attributes and the inline JS turns those into navigation. `idp.yaml` regroups the Developer Control Plane under three roots.

**Tech Stack:** Python 3 + PyYAML (`render-outline`), vanilla JS/CSS inlined in the HTML, pytest via `uv run --with`.

**Spec:** `docs/superpowers/specs/2026-10-12-deck-navigation-design.md`

## Global Constraints

- `render-outline` keeps its style: 2-space indent, one-line comments explaining the YAML field they implement, no new dependency beyond PyYAML.
- The HTML (`idp.html`) is generated, never edited by hand, and goes in the same commit as `idp.yaml`.
- Existing slide content (screen, notes, code) does not change; only `parent`, `label`, `links`, `focus`, `spotlight` and the three `landscape-dev-*` slides change.
- A click navigates only on `[data-go-slide]` or `[data-back]`; any other click keeps doing nothing (text selection stays safe).
- The "stack" of the spec has depth 1: links push only from a main-track step, and any main-track step clears it. It lives in `sessionStorage` under `idp-outline-origin`.
- Tests: `uv run --with pytest --with pyyaml pytest docs/presentation/tests` from the repo root.

## Review Focus

- A detail opened from a direct link (`#present-detail-catalog`) or from the index has no origin: back must go to the parent (the root goes to the last step of `landscape-dev`, all boxes shown). Pinned in Task 3 (`data-up`) and checked in Task 5.
- → on the last main-track step (the end of the deck's last act) must not walk into the appendix; End must stop there too. Checked in Task 5.
- The agenda's part range (the "here" highlight in the index) must not stretch over appendix steps. Pinned in Task 3.
- A detail slide whose subtree is split in the YAML would make → leave a subtree half-way: validation must refuse it. Pinned in Task 1.
- Clicking a box that is still hidden (`part-hidden`) must do nothing: `visibility: hidden` already drops pointer events; checked in Task 5 on the `start: empty` step.

---

### Task 1: Validation of the new fields

**Files:**
- Create: `docs/presentation/tests/test_render_outline.py`
- Modify: `docs/presentation/render-outline` (`validate`, new helpers `detail_root`, `ancestors`, `label`)

**Interfaces:**
- Produces: `detail_root(slides: dict[str, dict], slide: dict) -> dict`, `ancestors(slides: dict[str, dict], slide: dict) -> list[dict]` (nearest parent first, ends at the main-track slide), `label(slide: dict) -> str | None` (`label`, else `heading`). The test module exposes `ro` (the loaded script) and `outline()` (a fixture outline) used by Tasks 2–3.

- [ ] **Step 1: Write the failing tests**

`docs/presentation/tests/test_render_outline.py`:

```python
import copy
import importlib.machinery
import importlib.util
import pathlib

import yaml

HERE = pathlib.Path(__file__).resolve().parent.parent
loader = importlib.machinery.SourceFileLoader("render_outline", str(HERE / "render-outline"))
ro = importlib.util.module_from_spec(importlib.util.spec_from_loader("render_outline", loader))
loader.exec_module(ro)

SVG = '<svg><g data-part="plane"><rect/></g><g data-part="p.1"><rect/></g><g data-part="p.2"><rect/></g></svg>'


def outline():
  return copy.deepcopy({
    "deck": {"title": "T", "home": "full", "agendaSteps": False},
    "acts": [{"name": "opening", "title": "Opening"},
             {"name": "plane", "title": "Plane", "opening": False},
             {"name": "next", "title": "Next", "opening": False}],
    "parts": [{"title": "Plane", "message": "m", "acts": ["plane"], "items": [{"label": "Box", "go": "box"}]}],
    "slides": [
      {"name": "title", "act": "opening", "message": "t", "screen": ["Title"], "animations": "none"},
      {"name": "map", "act": "plane", "topic": "Plane", "label": "Plane", "message": "m", "diagram": "d.svg",
       "show": ["plane"], "focus": ["plane"], "start": "empty", "reveal": ["p.1", "p.2"], "accumulate": True,
       "spotlight": True, "links": {"p.1": "box"}},
      {"name": "box", "act": "plane", "topic": "Plane", "parent": "map", "heading": "Box", "message": "m",
       "diagram": "d.svg", "dim": ["plane", "p.2"], "show": ["p.1"], "focus": ["p.1"]},
      {"name": "box-a", "act": "plane", "topic": "Plane", "parent": "box", "heading": "A", "message": "m", "screen": ["x"]},
      {"name": "box-b", "act": "plane", "topic": "Plane", "parent": "box-a", "label": "B", "message": "m",
       "screen": ["y"], "animations": "none"},
      {"name": "full", "act": "next", "topic": "All", "message": "m", "diagram": "d.svg", "show": ["plane", "p"],
       "links": {"p.1": "box"}},
    ]})


def slide(data, name):
  return next(s for s in data["slides"] if s["name"] == name)


def test_fixture_is_valid():
  assert ro.validate(outline()) == []


def test_idp_yaml_is_valid():
  assert ro.validate(yaml.safe_load((HERE / "idp.yaml").read_text())) == []


def test_unknown_parent():
  data = outline()
  slide(data, "box-a")["parent"] = "nope"
  assert "box-a: parent unknown slide 'nope'" in ro.validate(data)


def test_parent_cycle():
  data = outline()
  slide(data, "box")["parent"] = "box-b"
  assert any("parent cycle" in error for error in ro.validate(data))


def test_root_needs_a_diagram():
  data = outline()
  slide(data, "box-a")["parent"] = "map"
  assert "box-a: a detail root needs a diagram" in ro.validate(data)


def test_detail_needs_a_label():
  data = outline()
  del slide(data, "box-b")["label"]
  assert "box-b: detail slide without label or heading" in ro.validate(data)


def test_unknown_link_target():
  data = outline()
  slide(data, "full")["links"] = {"p.1": "nope"}
  assert "full: link p.1 goes to unknown slide 'nope'" in ro.validate(data)


def test_unknown_home():
  data = outline()
  data["deck"]["home"] = "nope"
  assert "deck.home: unknown slide 'nope'" in ro.validate(data)


def test_subtree_must_be_consecutive():
  data = outline()
  data["slides"].insert(4, {"name": "other", "act": "plane", "parent": "map", "heading": "O", "message": "m",
                            "diagram": "d.svg", "show": ["p.2"]})
  assert "box-b: detail slides of 'box' are not consecutive" in ro.validate(data)


def test_ancestors_and_root():
  data = outline()
  slides = {s["name"]: s for s in data["slides"]}
  assert [s["name"] for s in ro.ancestors(slides, slides["box-b"])] == ["box-a", "box", "map"]
  assert ro.detail_root(slides, slides["box-b"])["name"] == "box"
  assert ro.label(slides["box-b"]) == "B" and ro.label(slides["box-a"]) == "A"
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `uv run --with pytest --with pyyaml pytest docs/presentation/tests -q`
Expected: FAIL — `AttributeError: module 'render_outline' has no attribute 'ancestors'` and the validation tests with missing messages. `test_idp_yaml_is_valid` passes (no detail slides yet).

- [ ] **Step 3: Implement the helpers and the validation**

In `render-outline`, right before `def validate(outline):`:

```python
def label(slide):
  """A detail slide's name in breadcrumbs and overlays: `label`, else `heading`."""
  return slide.get("label") or slide.get("heading")


def ancestors(slides, slide):
  """Parents of a detail slide, nearest first, ending at its main-track slide."""
  chain = []
  while slide.get("parent"):
    slide = slides[slide["parent"]]
    chain.append(slide)
  return chain


def detail_root(slides, slide):
  """The detail slide right under the main track that `slide` hangs from (itself for a root)."""
  while slides[slide["parent"]].get("parent"):
    slide = slides[slide["parent"]]
  return slide
```

In `validate`, replace the loop that checks `show/dim/reveal without diagram` with:

```python
  for slide in outline["slides"]:
    parts = set(slide.get("show", [])) | set(slide.get("dim", [])) | set(slide.get("reveal", [])) | set(slide.get("focus", []))
    if parts and not slide.get("diagram"):
      errors.append(f"{slide['name']}: show/dim/reveal/focus without diagram")
  # `parent`: detail slides, off the main track and opened by a link (`links`, overlay, breadcrumb).
  by_name = {slide["name"]: slide for slide in outline["slides"]}
  details = [slide for slide in outline["slides"] if slide.get("parent")]
  tree_ok = True
  for slide in details:
    name = slide["name"]
    if slide["parent"] not in by_name:
      errors.append(f"{name}: parent unknown slide '{slide['parent']}'")
      tree_ok = False
      continue
    seen, current = set(), slide
    while current is not None and current.get("parent"):
      if current["name"] in seen:
        errors.append(f"{name}: parent cycle")
        tree_ok = False
        break
      seen.add(current["name"])
      current = by_name.get(current["parent"])
    if not label(slide):
      errors.append(f"{name}: detail slide without label or heading")
    if not by_name[slide["parent"]].get("parent") and not slide.get("diagram"):
      errors.append(f"{name}: a detail root needs a diagram")
  if details and outline["deck"].get("home") not in by_name:
    errors.append(f"deck.home: unknown slide '{outline['deck'].get('home')}'")
  for slide in outline["slides"]:
    for part, target in (slide.get("links") or {}).items():
      if target not in by_name:
        errors.append(f"{slide['name']}: link {part} goes to unknown slide '{target}'")
  # → walks a subtree in YAML order and leaves it at its last step: its slides must be consecutive.
  if tree_ok:
    roots = [detail_root(by_name, slide)["name"] for slide in details]
    for n in range(1, len(roots)):
      if roots[n] != roots[n - 1] and roots[n] in roots[:n]:
        errors.append(f"{details[n]['name']}: detail slides of '{roots[n]}' are not consecutive")
```

- [ ] **Step 4: Run the tests**

Run: `uv run --with pytest --with pyyaml pytest docs/presentation/tests -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add docs/presentation/render-outline docs/presentation/tests/test_render_outline.py
git commit -m "feat(presentation): validate detail slides, links and deck.home (#386)"
```

---

### Task 2: Detail steps after the main track

**Files:**
- Modify: `docs/presentation/render-outline` (`build_steps`, new `slide_steps`)
- Test: `docs/presentation/tests/test_render_outline.py`

**Interfaces:**
- Consumes: `ancestors`, `detail_root`, `label` (Task 1).
- Produces: steps of detail slides carry `detail: str` (root name), `crumbs: list[tuple[str, str]]` (label, slide name; `("Platform", deck.home)` first, the main-track ancestor next, the slide itself excluded), `up: tuple[str, bool]` (parent name, is the slide a root), `entry: True` on a root's first step, `exit: True` on a subtree's last step, `overlay: list[tuple[str, str]]` on a root's steps (its direct children). Diagram steps carry `focus: set[str]` and `links: dict[str, str]`.

- [ ] **Step 1: Write the failing tests** (append)

```python
def names(steps):
  return [step["slide"]["name"] if step["slide"] else None for step in steps]


def test_details_come_after_the_main_track():
  steps = ro.build_steps(outline())
  assert names(steps) == ["title", "map", "map", "map", "map", "full", "full", "box", "box-a", "box-a", "box-b"]
  assert [step.get("detail") for step in steps[7:]] == ["box"] * 4
  assert not any(step.get("detail") for step in steps[:7])


def test_no_divider_for_details():
  steps = ro.build_steps(outline())
  assert not any(step.get("divider") for step in steps[7:])


def test_focus_and_spotlight():
  steps = ro.build_steps(outline())
  assert [steps[i]["focus"] for i in (2, 3, 4)] == [{"plane"}, {"plane", "p.1"}, {"plane", "p.2"}]
  assert steps[3]["links"] == {"p.1": "box"}
  assert steps[7]["focus"] == {"p.1"}


def test_crumbs_overlay_and_up():
  steps = ro.build_steps(outline())
  box, box_b = steps[7], steps[10]
  assert box["crumbs"] == [("Platform", "full"), ("Plane", "map")]
  assert box_b["crumbs"] == [("Platform", "full"), ("Plane", "map"), ("Box", "box"), ("A", "box-a")]
  assert box["overlay"] == [("A", "box-a")] and "overlay" not in steps[8]
  assert box["up"] == ("map", True) and box_b["up"] == ("box-a", False)


def test_entry_and_exit():
  steps = ro.build_steps(outline())
  assert [i for i, step in enumerate(steps) if step.get("entry")] == [7]
  assert [i for i, step in enumerate(steps) if step.get("exit")] == [10]
```

- [ ] **Step 2: Run to see them fail**

Run: `uv run --with pytest --with pyyaml pytest docs/presentation/tests -q -k "details or divider or focus or crumbs or entry"`
Expected: FAIL (detail slides still inline, no `focus`/`crumbs` keys).

- [ ] **Step 3: Split `build_steps`**

Move the body that turns one slide into steps (from `if slide.get("diagram"):` to the end of the loop body) into a new function placed before `build_steps`, appending to a local list and returning it instead of `continue`:

```python
def slide_steps(outline, slide, act, section):
  """The steps of one slide (see build_steps)."""
  steps = []
  # `diagram`: ... (keep the existing comment block)
  if slide.get("diagram"):
    reveal = slide.get("reveal") or []
    shown = {**{part: "dim" for part in slide.get("dim", [])}, **{part: "on" for part in slide.get("show", [])}}
    # `focus`: parts with a highlighted border on every step; `spotlight: true` adds the part revealed in the step.
    # `links`: parts that open a slide when clicked (detail slides, `parent`).
    focus = set(slide.get("focus", []))
    spot = lambda part: focus | ({part} if slide.get("spotlight") else set())
    extra = {"links": slide.get("links") or {}}
    if not reveal or slide.get("start") == "empty":
      steps.append({"slide": slide, "act": act, "section": section, "items": [], "focus": focus, **extra,
                    "diagram": {**shown, **{part: "on" for part in slide.get("empty", [])}}})
    group = lambda part: part.split("-")[0]
    def kept(done, part):
      if slide.get("accumulate") == "commands":
        return "on" if group(done) == group(part) else "dim"
      return "on" if slide.get("accumulate") else "dim"
    for n, part in enumerate(reveal):
      steps.append({"slide": slide, "act": act, "section": section, "items": [], "focus": spot(part), **extra,
                    "diagram": {**shown, **{done: kept(done, part) for done in reveal[:n]}, part: "on"}})
    return steps
  # ... the rest of the existing body unchanged (screen / code / animations / heading),
  # with `steps.append(...)` kept as is, ending with:
  return steps
```

`build_steps` keeps its agenda/opening/section/divider logic for main-track slides and calls `slide_steps`; detail slides follow:

```python
  slides = {slide["name"]: slide for slide in outline["slides"]}
  for slide in outline["slides"]:
    # `parent`: a detail slide, off the main track; its steps come after it (below).
    if slide.get("parent"):
      continue
    act = acts[slide["act"]]
    # ... existing agenda / opening / section / divider code, unchanged ...
    previous_section = section
    steps.extend(slide_steps(outline, slide, act, section))
  # Detail slides: after the main track, in YAML order, with no divider or agenda. A link opens them;
  # → walks their root's subtree and, on its last step, returns to where the link came from.
  home = outline["deck"].get("home")
  for slide in outline["slides"]:
    if not slide.get("parent"):
      continue
    act, chain, root = acts[slide["act"]], ancestors(slides, slide), detail_root(slides, slide)
    crumbs = [("Platform", home)] + [(label(parent), parent["name"]) for parent in reversed(chain)]
    children = [(label(child), child["name"]) for child in outline["slides"] if child.get("parent") == slide["name"]]
    own = slide_steps(outline, slide, act, (act["title"], label(slide)))
    for step in own:
      step.update({"detail": root["name"], "crumbs": crumbs, "up": (slide["parent"], slide is root)})
      if slide is root:
        step["overlay"] = children
    if slide is root:
      own[0]["entry"] = True
    steps.extend(own)
  for n, step in enumerate(steps):
    if step.get("detail") and (n + 1 == len(steps) or steps[n + 1].get("detail") != step["detail"]):
      step["exit"] = True
  return steps
```

Note: the `crumbs` of the first test exclude `Platform`'s duplicate — `reversed(chain)` starts at the main-track ancestor (`map`), so a root gets `[("Platform", home), ("Plane", "map")]`.

- [ ] **Step 4: Run all tests**

Run: `uv run --with pytest --with pyyaml pytest docs/presentation/tests -q`
Expected: all PASS. Then `cd docs/presentation && ./render-outline idp.yaml && git diff --stat idp.html` — expected: no diff (no detail slide in `idp.yaml` yet; `focus`/`links` are not rendered yet).

- [ ] **Step 5: Commit**

```bash
git add docs/presentation/render-outline docs/presentation/tests/test_render_outline.py
git commit -m "feat(presentation): detail slides after the main track, with crumbs and overlay data (#386)"
```

---

### Task 3: HTML and CSS for focus, links, breadcrumb and overlay

**Files:**
- Modify: `docs/presentation/render-outline` (`CSS`, `render_stage`, `render_html`)
- Test: `docs/presentation/tests/test_render_outline.py`

**Interfaces:**
- Consumes: step keys from Task 2.
- Produces (for Task 4's JS): on `#deck .stage`: `data-detail='<root>'`, `data-up='<step index>'`, `data-entry`, `data-exit`; anywhere inside a stage: `[data-go-slide='<slide name>']` (box `<g>`, breadcrumb `<a>`, overlay `<a>`) and `[data-back]` (`<a>`).

- [ ] **Step 1: Write the failing tests** (append)

```python
import re


def deck(tmp_path):
  (tmp_path / "d.svg").write_text(SVG)
  return ro.render_html(outline(), tmp_path)


def stage(page, n):
  body = page.split("<div id='deck'>")[1]
  start = body.index(f"<div class='stage' data-step='{n}'")
  end = body.find("<div class='stage' data-step=", start + 1)
  return body[start:end if end > 0 else body.index("<template")]


def test_stage_attributes(tmp_path):
  page = deck(tmp_path)
  # root `box` goes up to the last step of `map` (4); `box-b` to the first step of `box-a` (8)
  assert "data-detail='box' data-up='4' data-entry" in stage(page, 7)
  assert "data-up='8' data-exit" in stage(page, 10)
  assert "data-detail" not in stage(page, 6)


def test_diagram_focus_and_links(tmp_path):
  page = deck(tmp_path)
  assert '<g data-part="p.1" class="part-on part-focus part-link" data-go-slide="box">' in stage(page, 3)
  assert '<g data-part="plane" class="part-on part-focus">' in stage(page, 2)


def test_breadcrumb_and_overlay(tmp_path):
  page = deck(tmp_path)
  box_b = stage(page, 10)
  assert "<a data-back>↩ back</a>" in box_b
  assert "<a data-go-slide='full'>Platform</a> › <a data-go-slide='map'>Plane</a> › <a data-go-slide='box'>Box</a> › <a data-go-slide='box-a'>A</a>" in box_b
  root = stage(page, 7)
  assert "<div class='overlay'><div class='ov-title'>Box</div><a data-go-slide='box-a'>A</a></div>" in root


def test_agenda_range_skips_details(tmp_path):
  page = deck(tmp_path)
  assert "data-go='1' data-last='4'" in page
```

Step indexes in the fixture: 0 `title`, 1 divider of `map`, 2–4 `map`, 5 divider of `full`, 6 `full`, 7 `box`, 8–9 `box-a`, 10 `box-b`.

- [ ] **Step 2: Run to see them fail**

Run: `uv run --with pytest --with pyyaml pytest docs/presentation/tests -q -k "stage_attributes or focus_and_links or breadcrumb or agenda_range"`
Expected: FAIL.

- [ ] **Step 3: Implement**

CSS, after `.stage .diagram .part-dim { opacity: 0.32; }`:

```css
.stage .diagram .part-focus > rect:first-of-type { stroke: #4a9ef4; stroke-width: 4; }
.stage .diagram .part-link { cursor: pointer; }
.stage .diagram .part-link:hover > rect:first-of-type { stroke: #7cc4ff; }
.stage .crumbs .act-name a { color: #4a9ef4; cursor: pointer; }
.stage .crumbs .act-name a[data-back] { margin-right: 1.4cqw; }
.stage .overlay { position: absolute; right: 5cqw; top: 12cqw; width: 30cqw; box-sizing: border-box; background: rgba(17, 24, 39, 0.96); border: 1px solid #4a9ef4; border-radius: 1cqw; padding: 2cqw 2.4cqw; display: flex; flex-direction: column; gap: 1cqw; }
.stage .overlay .ov-title { font-size: 2.2cqw; font-weight: 700; color: #fff; margin-bottom: 0.6cqw; }
.stage .overlay a { font-size: 1.6cqw; color: #c0d2e4; cursor: pointer; }
.stage .overlay a::before { content: '→ '; color: #4a9ef4; }
```

`render_stage`, right after the `has_topic` / `section` block:

```python
  # Detail slides (`parent`): a breadcrumb of links replaces the act name, with "↩ back" before it.
  if step.get("crumbs"):
    trail = " › ".join(f"<a data-go-slide='{esc(name)}'>{esc(text)}</a>" for text, name in step["crumbs"])
    # A text slide shows its own heading as its first item: keep the topic line for the others.
    topic = "" if step["slide"].get("heading") and step.get("diagram") is None and not step.get("code") else step["section"][1]
    section = (f"<div class='section has-topic crumbs'><div class='act-name'><a data-back>↩ back</a>{trail}</div>"
               + (f"<div class='topic'>{esc(topic)}</div>" if topic else "") + "</div>")
```

In the diagram branch, change `if heading:` to `if heading and not step.get("crumbs"):`, and replace the `<g data-part>` substitution and the return with:

```python
    focus, links = step.get("focus") or set(), step.get("links") or {}
    def group(match):
      part = match[1]
      classes = f"part-{state(part)}" + (" part-focus" if part in focus else "") + (" part-link" if part in links else "")
      link = f' data-go-slide="{esc(links[part])}"' if part in links else ""
      return f'<g data-part="{part}" class="{classes}"{link}>'
    svg = re.sub(r'<g data-part="([\w.-]+)">', group, svg)
    source = step["slide"].get("source")
    source_html = f"<div class='source'>Source: {esc(source)}</div>" if source else ""
    # A detail root lists its children over the dimmed diagram.
    overlay = ""
    if step.get("overlay"):
      overlay = (f"<div class='overlay'><div class='ov-title'>{esc(step['section'][1])}</div>"
                 + "".join(f"<a data-go-slide='{esc(name)}'>{esc(text)}</a>" for text, name in step["overlay"]) + "</div>")
    return f"{section}<div class='inner diagram-inner'><div class='diagram'>{svg}</div></div>{overlay}<div class='footer'></div>{source_html}"
```

`render_html`: after `steps = build_steps(outline)` / `stages = ...`, build the stage attributes:

```python
  first_step, last_step = {}, {}
  for i, step in enumerate(steps):
    if step["slide"] is not None:
      first_step.setdefault(step["slide"]["name"], i)
      last_step[step["slide"]["name"]] = i
  # Detail steps: the JS walks them by these attributes (back target, subtree entry and exit).
  def detail_attrs(i):
    step = steps[i]
    if not step.get("detail"):
      return ""
    parent, is_root = step["up"]
    up = last_step[parent] if is_root else first_step[parent]
    return (f" data-detail='{esc(step['detail'])}' data-up='{up}'"
            + (" data-entry" if step.get("entry") else "") + (" data-exit" if step.get("exit") else ""))
```

and in the `deck_html` join, insert `+ detail_attrs(i)` right after the `data-slide` part:

```python
  deck_html = "".join(f"<div class='stage' data-step='{i}'" + (f" data-slide='{esc(steps[i]['slide']['name'])}'" if first_of(i) else "") + detail_attrs(i) + f">{stage}</div>"
                      for i, stage in enumerate(stages))
```

In the agenda `part_ranges`, skip detail steps:

```python
      own = [i for i, step in enumerate(steps) if step["act"]["name"] in part["acts"] and step.get("agenda") is None and not step.get("detail")]
```

- [ ] **Step 4: Run all tests**

Run: `uv run --with pytest --with pyyaml pytest docs/presentation/tests -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add docs/presentation/render-outline docs/presentation/tests/test_render_outline.py
git commit -m "feat(presentation): focus, clickable parts, breadcrumb and overlay in the HTML (#386)"
```

---

### Task 4: Navigation in the inline JS

**Files:**
- Modify: `docs/presentation/render-outline` (`SCRIPT`)

**Interfaces:**
- Consumes: the attributes from Task 3.

No unit test harness exists for the inline JS; it is verified in the browser in Task 5.

- [ ] **Step 1: Add origin, links, back, next and previous**

In `SCRIPT`, after `let syncing = false;`:

```js
// Detail steps (`parent`) come after the main track: → never walks into them, a link opens them.
const firstDetail = Array.from(stages).findIndex((stage) => stage.dataset.detail !== undefined);
const lastMain = (firstDetail < 0 ? stages.length : firstDetail) - 1;
// Where the link into a detail came from: set only from a main-track step, cleared on any main-track step.
const ORIGIN_KEY = 'idp-outline-origin';
```

In `show(index)`, after `current = ...`:

```js
  if (stages[current].dataset.detail === undefined) sessionStorage.removeItem(ORIGIN_KEY);
```

After `function present(index) {...}`:

```js
function goSlide(name) {
  const target = deck.querySelector(`.stage[data-slide='${name}']`);
  if (!target) return;
  if (stages[current].dataset.detail === undefined) sessionStorage.setItem(ORIGIN_KEY, String(current));
  show(Number(target.dataset.step));
}
// Back: to the step the link came from; with none (direct link, index), to the parent slide.
function back() {
  const origin = sessionStorage.getItem(ORIGIN_KEY);
  show(origin !== null ? Number(origin) : Number(stages[current].dataset.up));
}
function next() {
  if (stages[current].dataset.exit !== undefined) back();
  else if (current !== lastMain) show(current + 1);
}
function previous() {
  if (stages[current].dataset.entry !== undefined) back(); else show(current - 1);
}
// Clicks navigate only on links (box, breadcrumb, overlay, back): elsewhere a click keeps the text selection.
deck.addEventListener('click', (event) => {
  if (!deck.classList.contains('on')) return;
  const link = event.target.closest('[data-go-slide], [data-back]');
  if (!link) return;
  event.stopPropagation();
  if (link.dataset.back !== undefined) back(); else goSlide(link.dataset.goSlide);
});
```

- [ ] **Step 2: Route keys and taps through them**

Touch handler: change the exclusion to `if (event.target.closest('a, .notes-panel, [data-go-slide]')) return;` and `show(current + 1)` / `show(current - 1)` to `next()` / `previous()`.

Key handler, replacing the two arrow lines and `End`:

```js
  if (['ArrowRight', 'ArrowDown', 'PageDown', ' ', 'Enter'].includes(event.key)) { event.preventDefault(); next(); }
  else if (event.key === 'Backspace' && stages[current].dataset.detail !== undefined) { event.preventDefault(); back(); }
  else if (['ArrowLeft', 'ArrowUp', 'PageUp', 'Backspace'].includes(event.key)) { event.preventDefault(); previous(); }
  else if (event.key === 'Home') show(0);
  else if (event.key === 'End') show(lastMain);
```

Update the hint text: `← → avançar · Backspace voltar do detalhe · I índice · ...`.

- [ ] **Step 3: Check the script still renders**

Run: `uv run --with pytest --with pyyaml pytest docs/presentation/tests -q && cd docs/presentation && ./render-outline idp.yaml`
Expected: PASS and the HTML path printed. Open `idp.html#present-1` in Chrome, press → twice and ← once: the deck still moves (no detail slides yet, so behavior is unchanged). Check the console has no errors.

- [ ] **Step 4: Commit**

```bash
git add docs/presentation/render-outline docs/presentation/idp.html
git commit -m "feat(presentation): back, links and subtree exit in presentation mode (#386)"
```

---

### Task 5: Developer Control Plane as a tree

**Files:**
- Modify: `docs/presentation/idp.yaml`, `docs/presentation/idp.html` (generated), `docs/presentation/CONTRIBUTING.md`

- [ ] **Step 1: `deck.home` and the main-track slide**

In `deck:` add `home: landscape-full` with the comment `# Breadcrumb root of detail slides (\`parent\`): "Platform" opens it.`

Replace `landscape-dev-1` (keep its notes for `detail-catalog`) with:

```yaml
  - name: landscape-dev
    act: developer-control
    topic: "Developer Control Plane"
    label: "Developer Control Plane"
    message: "O Developer Control Plane tem três peças: catálogo, declaração da app e golden paths."
    heading: "Three capabilities"
    diagram: "diagrams/landscape/landscape.svg"
    show: [dev-plane, ind-plane, res-plane, obs-plane, sec-plane]
    focus: [dev-plane]
    start: "empty"
    reveal: [dev.1, dev.2, dev.3]
    accumulate: true
    spotlight: true
    links: {dev.1: detail-catalog, dev.2: detail-app-declaration, dev.3: detail-golden-paths}
    source: "platformengineering.org/platform-tooling · planes as parallel layers; the journey order is ours"
    notes: |-
      O que queremos dizer: **o developer entra por aqui** — o catálogo diz quem a app é, a declaração diz do que ela precisa, e o golden path cria os dois de uma vez.

      Cada caixa abre o seu detalhe com um clique; ↩ volta para cá.
```

- [ ] **Step 2: The three roots**

Right after `landscape-dev`:

```yaml
  - name: detail-catalog
    act: developer-control
    topic: "Software Catalog"
    parent: landscape-dev
    message: "O catálogo diz o que existe e quem é dono."
    heading: "Software Catalog"
    diagram: "diagrams/landscape/landscape.svg"
    dim: [dev-plane, ind-plane, res-plane, obs-plane, sec-plane, dev.2, dev.3]
    show: [dev.1]
    focus: [dev.1]
    source: "platformengineering.org/platform-tooling · planes as parallel layers; the journey order is ours"
    notes: |-
      (the notes of the old landscape-dev-1, unchanged)
```

Replace `landscape-dev-2` by `detail-app-declaration` (same shape: `parent: landscape-dev`, `heading: "App Declaration"`, `dim` with `dev.1, dev.3`, `show`/`focus: [dev.2]`, its message and notes) and `landscape-dev-3` by `detail-golden-paths` (`heading: "Golden Paths"`, `dim` with `dev.1, dev.2`, `show`/`focus: [dev.3]`, its message and notes).

- [ ] **Step 3: Hang the existing slides**

Add `parent` (and `label` where noted) to each slide, leaving everything else as is:

| Slide | `parent` | `label` |
|---|---|---|
| `catalog-ownership` | `detail-catalog` | |
| `catalog-levels` | `detail-catalog` | `Two views` |
| `catalog-business-view` | `catalog-levels` | |
| `catalog-engineering-view` | `catalog-levels` | |
| `entity-component`, `entity-api`, `entity-resource` | `catalog-engineering-view` | |
| `entity-system`, `entity-domain` | `catalog-business-view` | |
| `spotify-tree`, `catalog-tree` | `detail-catalog` | |
| `declare-name` | `detail-catalog` | `catalog-info.yaml` |
| `declare-system` | `declare-name` | `System` |
| `declare-ownership` | `declare-name` | `Ownership` |
| `ip-lifecycle` | `declare-name` | |
| `declare-apis` | `declare-name` | `APIs` |
| `declare-dependencies` | `declare-name` | `Dependencies` |
| `declare-discovery` | `declare-name` | |
| `no-versions` | `detail-catalog` | |
| `major-breaking`, `plugins` | `no-versions` | |
| `spec-db` | `detail-app-declaration` | `Resources` |
| `spec-variables` | `detail-app-declaration` | `Variables` |
| `spec-route` | `detail-app-declaration` | `Route` |
| `spec-service` | `detail-app-declaration` | `Service` |
| `score-what-not` | `detail-app-declaration` | |
| `golden-paths` | `detail-golden-paths` | |

- [ ] **Step 4: Agenda and final picture**

Agenda items of "Developer Control Plane": `go: detail-catalog`, `detail-app-declaration`, `detail-golden-paths`. On `landscape-full` add `links: {dev.1: detail-catalog, dev.2: detail-app-declaration, dev.3: detail-golden-paths}`.

- [ ] **Step 5: Render and test**

Run: `uv run --with pytest --with pyyaml pytest docs/presentation/tests -q && cd docs/presentation && ./render-outline idp.yaml`
Expected: PASS (including `test_idp_yaml_is_valid`) and the HTML path.

- [ ] **Step 6: Check in Chrome** (chrome-devtools MCP, page on `idp.html#present-landscape-dev`)

- The plane's border is blue on every step; the box revealed in the step is blue too; on the empty first step, clicking where a box will be does nothing.
- → after Golden Paths lands on the Integration & Delivery opening (no catalog slide in between).
- Click Software Catalog → `detail-catalog` with the overlay; click "Two views" → breadcrumb `↩ back Platform › Developer Control Plane › Software Catalog`, topic "Two views"; Backspace → back on `landscape-dev`, same step as left.
- From `detail-catalog`, → to the end of the subtree (`plugins`), → once more → back on the origin step.
- On `detail-catalog`, ← → back on the origin.
- `#present-landscape-full`: click Golden Paths → `detail-golden-paths`; → walks `golden-paths`; → again → back on `landscape-full`.
- `#present-detail-catalog` opened in a fresh tab: back → `landscape-dev`, all three boxes shown.
- End key → the deck's last main-track step, not an appendix step.
- Console without errors (`list_console_messages`).

- [ ] **Step 7: Document the fields**

In `CONTRIBUTING.md`, in the outline fields table, add rows for `parent`, `label`, `focus`, `spotlight`, `links` and `deck.home`, in the language and style of the existing rows (pt-BR), e.g.:

| Campo | Obrigatório | Significado |
|---|---|---|
| `parent` | não | Slide de detalhe: sai da trilha principal e vai para um apêndice, aberto por link (`links`, janela, breadcrumb). A raiz (pai na trilha principal) precisa de `diagram` e lista os filhos numa janela. → percorre a subárvore e, no último passo, volta à origem; Backspace e "↩ back" voltam a qualquer momento. |
| `label` | não | Nome do slide no breadcrumb e na janela; sem ele, `heading`. Obrigatório (um dos dois) em slides de detalhe. |
| `focus` | não | Partes do `diagram` com a borda destacada em todos os passos. |
| `spotlight` | não | `true`: a parte revelada no passo também ganha a borda. |
| `links` | não | `{<parte>: <slide>}`: a parte do diagrama abre o slide com um clique. |
| `deck.home` | com `parent` | Slide aberto por "Platform", a raiz do breadcrumb. |

Also add under "3. Conferir": `uv run --with pytest --with pyyaml pytest tests` (from `docs/presentation`).

- [ ] **Step 8: Commit**

```bash
git add docs/presentation/idp.yaml docs/presentation/idp.html docs/presentation/CONTRIBUTING.md
git commit -m "docs(presentation): Developer Control Plane as a tree of details on click (#386)"
```

---

### Task 6: PR

- [ ] **Step 1:** Push and open the PR with `Closes #386`; description in `/tmp/feat/386-deck-navigation-pr.txt` (repo-relative paths), ending with the Claude Code line.

```bash
git push --set-upstream origin feat/386-deck-navigation
gh pr create --base main --title "docs(presentation): diagram as the main track, details on click (#386)" --body-file /tmp/386-deck-navigation-pr.txt
```

- [ ] **Step 2:** Open the deck at `idp.html#present-landscape-dev` for the user's review; do not merge before the user's ok.
