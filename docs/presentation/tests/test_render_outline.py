import copy
import re
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
  assert ro.validate(yaml.safe_load((HERE / "idp.yaml").read_text()), HERE) == []


def test_parts_exist_in_the_diagram(tmp_path):
  (tmp_path / "d.svg").write_text(SVG)
  data = outline()
  assert ro.validate(data, tmp_path) == []
  slide(data, "map")["links"] = {"p.9": "box"}
  slide(data, "box")["focus"] = ["nope"]
  errors = ro.validate(data, tmp_path)
  assert "map: part 'p.9' is not in d.svg" in errors and "box: part 'nope' is not in d.svg" in errors


def test_a_parent_part_names_its_children(tmp_path):
  # `p` is not a group of its own: it stands for `p.1`, `p.2` (they inherit its state).
  (tmp_path / "d.svg").write_text(SVG)
  assert ro.validate(outline(), tmp_path) == []


def test_a_detail_comes_after_its_parent():
  data = outline()
  box_a = data["slides"].pop(3)
  data["slides"].insert(2, box_a)
  assert "box-a: comes before its parent 'box'" in ro.validate(data)


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


def names(steps):
  return [step["slide"]["name"] if step["slide"] else None for step in steps]


def test_details_come_after_the_main_track():
  steps = ro.build_steps(outline())
  assert names(steps) == ["title", "map", "map", "map", "map", "full", "full", "box", "box-a", "box-a", "box-b", "box-b"]
  assert [step.get("detail") for step in steps[7:]] == ["box"] * 5
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
  # The overlay is the root's whole subtree: (label, slide, children).
  assert box["overlay"] == [("A", "box-a", [("B", "box-b", [])])] and "overlay" not in steps[8]
  assert box["up"] == ("map", True) and box_b["up"] == ("box-a", False)


def test_entry_and_exit():
  steps = ro.build_steps(outline())
  assert [i for i, step in enumerate(steps) if step.get("entry")] == [7]
  assert [i for i, step in enumerate(steps) if step.get("exit")] == [11]


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
  assert "data-detail='box' data-up='4' data-out='4' data-entry" in stage(page, 7)
  assert "data-up='8' data-out='4' data-exit" in stage(page, 11)
  assert "data-detail" not in stage(page, 6)


def test_diagram_focus_and_links(tmp_path):
  page = deck(tmp_path)
  assert '<g data-part="p.1" class="part-on part-focus part-link" data-go-slide="box">' in stage(page, 3)
  assert '<g data-part="plane" class="part-on part-focus">' in stage(page, 2)


def test_breadcrumb_and_overlay(tmp_path):
  page = deck(tmp_path)
  root = stage(page, 7)
  assert ("<div class='overlay'><div class='ov-bar'><i></i><i></i><i></i><span>Box</span></div><div class='ov-tree'>"
          "<div class='ov-topic'><div class='ov-r ov-d0'><a data-go-slide='box-a'>A</a></div>"
          "<div class='ov-r ov-d1'><a data-go-slide='box-b'>B</a></div></div></div></div>") in root


def test_detail_header_matches_the_main_track(tmp_path):
  # A detail slide keeps the main track's header: the plane small, the box as the title.
  page = deck(tmp_path)
  header = "<div class='section has-topic'><div class='act-name'>Plane</div><div class='topic'>Box</div></div>"
  assert stage(page, 7).startswith(f"<div class='stage' data-step='7' data-slide='box'") and header in stage(page, 7)
  assert header in stage(page, 10)


def test_trail_in_the_footer(tmp_path):
  # The whole path, faint, in the footer: back, every level as a link, then the slide itself.
  page = deck(tmp_path)
  assert ("<div class='trail'><a data-back>↩</a><a data-go-slide='full'>Platform</a> / <a data-go-slide='map'>Plane</a> / "
          "<a data-go-slide='box'>Box</a> / <a data-go-slide='box-a'>A</a> / <span class='here'>B</span></div>") in stage(page, 10)


def test_trail_sits_above_the_slide():
  # `.inner` covers the whole stage (inset: 0): without a z-index it takes the trail's clicks.
  assert ".stage .trail { position: absolute; z-index: 2;" in ro.CSS


def test_index_cursor_from_a_detail():
  # Opened from a detail step, the index selects the row of the main-track step the detail hangs from.
  assert "const at = stages[current].dataset.out !== undefined ? Number(stages[current].dataset.out) : current;" in ro.SCRIPT


def test_agenda_range_skips_details(tmp_path):
  page = deck(tmp_path)
  assert "data-go='1' data-last='4'" in page


def test_divider_steps_are_marked(tmp_path):
  # A link (box, breadcrumb) to `full` skips its topic divider and lands on the diagram.
  page = deck(tmp_path)
  assert "data-slide='full' data-last-step='6' data-divider>" in stage(page, 5)
  assert "data-divider" not in stage(page, 6)


def test_first_step_knows_the_last(tmp_path):
  # A breadcrumb link to a main-track slide opens its last step: the diagram complete, as `data-up` does.
  page = deck(tmp_path)
  assert "data-slide='map' data-last-step='4'" in stage(page, 1)


def test_focus_dims_the_rest(tmp_path):
  # With a focus, every lit part outside it dims: p.1 (already revealed) when p.2 enters.
  page = deck(tmp_path)
  assert '<g data-part="p.1" class="part-dim part-link" data-go-slide="box">' in stage(page, 4)
  assert '<g data-part="p.2" class="part-on part-focus">' in stage(page, 4)


def test_focus_keeps_original_colors():
  # The focus stands out because the rest dims: no border or text color of its own.
  assert ".part-focus >" not in ro.CSS


def test_every_detail_step_knows_the_way_out(tmp_path):
  # With no origin (direct link, index), → on a subtree's last step and ← on its root leave to the
  # main track (`data-out`, the root's parent), never to a slide inside the subtree.
  page = deck(tmp_path)
  for n in (7, 8, 9, 10):
    assert "data-out='4'" in stage(page, n)


def test_sync_carries_the_origin():
  # The presenter window gets the origin with the step, or its back and exit lose the way.
  assert "channel.postMessage({ step: current, origin: sessionStorage.getItem(ORIGIN_KEY) })" in ro.SCRIPT



def test_overlay_tree_one_row_per_slide():
  # An indented tree: one row per slide, the depth as a class.
  items = [("Views", "views", [("Business", "biz", [("System", "sys", [])])]), ("Ours", "ours", [])]
  # Each top-level topic is wrapped in `ov-topic`, so a column never splits it.
  assert ro.overlay_tree(items) == ("<div class='ov-topic'><div class='ov-r ov-d0'><a data-go-slide='views'>Views</a></div>"
                                    "<div class='ov-r ov-d1'><a data-go-slide='biz'>Business</a></div>"
                                    "<div class='ov-r ov-d2'><a data-go-slide='sys'>System</a></div></div>"
                                    "<div class='ov-topic'><div class='ov-r ov-d0'><a data-go-slide='ours'>Ours</a></div></div>")


def test_overlay_examples_are_a_small_mark():
  # A child labelled "<parent> example" is a "▸ ex" link on its parent's row, never a row of its own.
  items = [("System", "sys", [("System example", "sys-ex", [])])]
  assert ro.overlay_tree(items) == ("<div class='ov-topic'><div class='ov-r ov-d0'><a data-go-slide='sys'>System</a>"
                                    "<a class='ov-ex' data-go-slide='sys-ex' title='System example'>▸&nbsp;example</a></div></div>")


SVG_COLORS = ('<svg><g data-part="obs-plane"><rect fill="#101010" stroke="#aa8800" /></g>'
              '<g data-part="dev-plane"><rect fill="#202020" stroke="#303030" /><text fill="#fefefe">P</text></g>'
              '<g data-part="dev.1"><rect fill="#050505" stroke="#404040" /><text fill="#909090">B</text></g></svg>')

def test_detail_slide_without_heading_shows_its_label(tmp_path):
  # `box-b` has a `label` and no `heading`: like a heading, the label opens the slide alone, then dims
  # as the items enter.
  page = deck(tmp_path)
  first, second = stage(page, 10), stage(page, 11)
  assert "<div class='item heading'>B</div>" in first and "<div class='item hidden'>y</div>" in first
  assert "<div class='item dim heading'>B</div>" in second and "<div class='item '>y</div>" in second


def test_label_with_only_sub_items():
  # A value that starts with "- " has no head line: the label alone heads the sub-items.
  out = ro.rich("**`x` service**\n- _shows_ a\n- _holds_ b", subs=1)
  assert out.startswith("<strong class='lbl'><code class='mono'>x</code> service</strong>")
  assert "<span class='sub'><em>shows</em> a</span><span class='sub hidden'><em>holds</em> b</span>" in out


def test_entity_markup():
  # {kind:name type}: the name in its kind's color, the type after it; the kind picks the color.
  out = ro.rich("_provided by_ {component:seat-selection service}")
  assert ("<span class='entity k-component'><span class='n'>seat-selection</span>"
          "<span class='sp'> </span><span class='t'>service</span></span>") in out
  assert ro.rich("{api:seats rest api}").endswith("<span class='n'>seats</span><span class='sp'> </span><span class='t'>rest<span class='sp'> </span>api</span></span>")
  assert ro.rich("{system:seat-map}") == "<span class='entity k-system'><span class='n'>seat-map</span></span>"
  # An unknown kind is not markup.
  assert "entity" not in ro.rich("{nope:x y}")
  assert ro.rich_class("{group:team-airport team}") == " rich"


def test_color_key_slide(tmp_path):
  # `columns`: one column per view, each kind with its examples in the kind's color.
  data = outline()
  slide(data, "box-b")["columns"] = [{"title": "business view", "note": "how it is grouped",
                                      "kinds": [{"kind": "domain", "name": "Domain", "examples": ["tailwind domain"]}]}]
  steps = ro.build_steps(data)
  assert [step.get("columns") is not None for step in steps].count(True) == 1
  (tmp_path / "o.yaml").write_text(yaml.safe_dump(data))
  (tmp_path / "d.svg").write_text(SVG)
  html_out = ro.render_html(data, tmp_path)
  assert "<div class='key k-domain'>" in html_out
  assert "<span class='entity k-domain'><span class='n'>tailwind</span><span class='sp'> </span><span class='t'>domain</span></span>" in html_out


def test_aligned_subitems():
  # `align: true` on a value made of sub-items: each word group in its own column of an invisible table.
  out = ro.rich("**{resource:t topic}**\n- _read by_ {component:a service} in {domain:x subdomain}\n- _read by_ {component:bb service} in {domain:y subdomain}", table=True)
  assert "<span class='value table' style='--cols: 7'>" in out
  assert ("<span class='c'><em>read by</em></span><span class='c'><span class='entity k-component'><span class='n'>a</span></span></span>"
          "<span class='c'><span class='entity k-component'><span class='t'>service</span></span></span><span class='c'>in</span>") in out
