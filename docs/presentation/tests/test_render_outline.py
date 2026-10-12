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
  # The overlay is the root's whole subtree: (label, slide, children).
  assert box["overlay"] == [("A", "box-a", [("B", "box-b", [])])] and "overlay" not in steps[8]
  assert box["up"] == ("map", True) and box_b["up"] == ("box-a", False)


def test_entry_and_exit():
  steps = ro.build_steps(outline())
  assert [i for i, step in enumerate(steps) if step.get("entry")] == [7]
  assert [i for i, step in enumerate(steps) if step.get("exit")] == [10]


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
  assert "data-up='8' data-out='4' data-exit" in stage(page, 10)
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
  assert ("<div class='overlay'><div class='ov-title'>Box</div><div class='ov-item'><a data-go-slide='box-a'>A</a>"
          "<div class='ov-sub'><a data-go-slide='box-b'>B</a></div></div></div>") in root


def test_overlay_groups_grandchildren():
  # A child with children of its own shows them after it: "Business view: System · Domain".
  item = ("Two views", "levels", [("Business", "biz", [("System", "sys", []), ("Domain", "dom", [])]), ("Engineering", "eng", [])])
  html = ro.overlay_item(item)
  assert ("<div class='ov-sub'><span class='ov-group'><a data-go-slide='biz'>Business</a>: <a data-go-slide='sys'>System</a> · "
          "<a data-go-slide='dom'>Domain</a></span> · <a data-go-slide='eng'>Engineering</a></div>") in html


def test_agenda_range_skips_details(tmp_path):
  page = deck(tmp_path)
  assert "data-go='1' data-last='4'" in page


def test_divider_steps_are_marked(tmp_path):
  # A link (box, breadcrumb) to `full` skips its topic divider and lands on the diagram.
  page = deck(tmp_path)
  assert "data-slide='full' data-last-step='6' data-divider>" in stage(page, 5)
  assert "data-divider" not in stage(page, 6)


def test_breadcrumb_sits_above_the_diagram():
  # `.inner` covers the whole stage (inset: 0): without a z-index it takes the clicks of the breadcrumb.
  assert ".stage .section.crumbs { z-index: 2; }" in ro.CSS


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
