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
