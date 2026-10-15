"""The template renderer (ADR 0024): Jinja2 with the Backstage delimiters."""
from pathlib import Path

import pytest
import yaml

from wasp_templates.render import RenderError, annotate_origin, load_template, render

REPO = Path(__file__).parents[4]
SEED = REPO / "platform" / "templates" / "python-service"


def write(root: Path, files: dict[str, str]) -> Path:
  for path, text in files.items():
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text)
  return root


def test_values_and_dump_filter(tmp_path):
  source = write(tmp_path / "src", {"a.yaml": "name: ${{ values.name }}\nowner: ${{ values.owner | dump }}\n"})
  render(source, tmp_path / "out", {"name": "demo", "owner": "team-alpha"})
  assert (tmp_path / "out" / "a.yaml").read_text() == 'name: demo\nowner: "team-alpha"\n'


def test_missing_variable_names_it(tmp_path):
  source = write(tmp_path / "src", {"a.txt": "${{ values.port }}"})
  with pytest.raises(RenderError, match=r"a\.txt: .*'port'"):
    render(source, tmp_path / "out", {"name": "demo"})


def test_copy_without_rendering_keeps_bytes(tmp_path):
  workflow = "run: echo ${{ github.sha }}\n"
  source = write(tmp_path / "src", {".github/workflows/ci.yaml": workflow, "README.md": "# ${{ values.name }}"})
  render(source, tmp_path / "out", {"name": "demo"}, copy_without_rendering=[".github/workflows/*"])
  assert (tmp_path / "out" / ".github" / "workflows" / "ci.yaml").read_text() == workflow
  assert (tmp_path / "out" / "README.md").read_text() == "# demo"


def test_file_and_folder_names_are_rendered(tmp_path):
  source = write(tmp_path / "src", {"${{ values.name }}/main_${{ values.name }}.py": "x"})
  render(source, tmp_path / "out", {"name": "demo"})
  assert (tmp_path / "out" / "demo" / "main_demo.py").read_text() == "x"


def test_plain_double_braces_are_literal(tmp_path):
  # Variables are ${{ }} only, as in the Backstage scaffolder: Helm-style {{ }} stays as written.
  text = "a: {{ .Values.x }}\n"
  source = write(tmp_path / "src", {"a.txt": text})
  render(source, tmp_path / "out", {"name": "demo"})
  assert (tmp_path / "out" / "a.txt").read_text() == text


def test_blocks_work_as_in_backstage(tmp_path):
  source = write(tmp_path / "src", {"a.txt": "{% if values.system %}system: ${{ values.system }}{% endif %}"})
  render(source, tmp_path / "out", {"system": None})
  assert (tmp_path / "out" / "a.txt").read_text() == ""


def test_output_must_not_exist(tmp_path):
  source = write(tmp_path / "src", {"a.txt": "x"})
  (tmp_path / "out").mkdir()
  (tmp_path / "out" / "keep").write_text("mine")
  with pytest.raises(RenderError, match="already exists"):
    render(source, tmp_path / "out", {"name": "demo"})


def test_load_template_reads_platform_format(tmp_path):
  write(tmp_path / "t", {"template.yaml": "name: t\ntype: service\nparameters:\n  type: object\n  properties:\n    port: {type: integer, default: 8080}\ncopyWithoutRendering: ['.github/workflows/*']\n", "content/a.txt": "x"})
  template = load_template(tmp_path / "t")
  assert template.name == "t"
  assert template.content == tmp_path / "t" / "content"
  assert template.copy_without_rendering == [".github/workflows/*"]
  assert template.defaults() == {"port": 8080}


def test_seed_renders_clean(tmp_path):
  template = load_template(SEED)
  out = tmp_path / "demo"
  render(template.content, out, {**template.defaults(), "name": "demo", "owner": "team-alpha", "description": "Demo", "system": "greeter"}, template.copy_without_rendering)
  annotate_origin(out, "python-service@abc")
  rendered = [path for path in out.rglob("*") if path.is_file() and not path.match(".github/workflows/*")]
  assert rendered and not any("${{" in path.read_text() for path in rendered)
  for workflow in ("ci.yaml", "platform-build.yaml"):
    original = SEED / "content" / ".github" / "workflows" / workflow
    assert (out / ".github" / "workflows" / workflow).read_bytes() == original.read_bytes()
  assert 'tag_format = "v$version"' in (out / ".cz.toml").read_text()
  catalog = (out / "catalog-info.yaml").read_text()
  assert "name: demo" in catalog
  assert "system: greeter" in catalog
  assert "platform.wasp.silvios.me/template: python-service@abc" in catalog


def test_node_seed_renders_clean_and_keeps_its_javascript_as_written(tmp_path):
  seed = REPO / "platform" / "templates" / "node-service"
  template = load_template(seed)
  out = tmp_path / "demo"
  render(template.content, out, {**template.defaults(), "name": "demo", "owner": "team-alpha", "description": "Demo", "system": "greeter"}, template.copy_without_rendering)
  rendered = [path for path in out.rglob("*") if path.is_file() and not path.match(".github/workflows/*")]
  assert rendered and not any("${{" in path.read_text() for path in rendered)
  # The JavaScript carries ${ } of its own: copied byte for byte, never through Jinja2.
  for source in (seed / "content").glob("src/*.js"):
    assert (out / "src" / source.name).read_bytes() == source.read_bytes()
  assert '"name": "demo"' in (out / "package.json").read_text()
  assert yaml.safe_load((out / "package-lock.json").read_text())["packages"][""]["name"] == "demo"
  assert "EXPOSE 3000" in (out / "Dockerfile").read_text()
  assert "APP_THEME: green" in (out / "app-spec.yaml").read_text()
  assert (out / "docs" / "prd.md").read_text().startswith("# demo: product requirements")
  assert (out / "AGENTS.md").is_file()
  app_spec = (out / "app-spec.yaml").read_text()
  assert app_spec.startswith("apiVersion: score.dev/v1b1")
  assert "type: postgres" in app_spec


def test_annotate_origin_keeps_the_rest(tmp_path):
  (tmp_path / "catalog-info.yaml").write_text("apiVersion: backstage.io/v1alpha1\nkind: Component\nmetadata:\n  name: demo\n  annotations:\n    a: b\nspec:\n  type: service\n")
  annotate_origin(tmp_path, "python-service@v1")
  text = (tmp_path / "catalog-info.yaml").read_text()
  assert text.index("kind:") < text.index("metadata:") < text.index("spec:")
  assert yaml.safe_load(text)["metadata"]["annotations"] == {"a": "b", "platform.wasp.silvios.me/template": "python-service@v1"}


def test_annotate_origin_without_catalog_info_does_nothing(tmp_path):
  annotate_origin(tmp_path, "python-service@v1")
  assert list(tmp_path.iterdir()) == []


def test_templates_cannot_reach_python_internals(tmp_path):
  # A registered template comes from someone else's repo and renders on the caller's machine.
  source = write(tmp_path / "src", {"a.txt": "${{ ''.__class__.__mro__[1].__subclasses__() }}"})
  with pytest.raises(RenderError, match="a.txt"):
    render(source, tmp_path / "out", {"name": "demo"})
  assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("name", ["../escape", "/tmp/escape", "a/../../escape"])
def test_rendered_paths_stay_inside_output(tmp_path, name):
  source = write(tmp_path / "src", {"${{ values.name }}.txt": "x"})
  with pytest.raises(RenderError, match="outside the output folder"):
    render(source, tmp_path / "out", {"name": name})
  assert not (tmp_path / "escape.txt").exists()


@pytest.mark.parametrize("link", ["file", "folder"])
def test_symlinks_in_content_are_refused(tmp_path, link):
  # A fetched template must not pull files from outside its content (~/.ssh/id_rsa) into the result.
  secret = tmp_path / "secret"
  secret.mkdir()
  (secret / "id_rsa").write_text("PRIVATE")
  source = write(tmp_path / "src", {"a.txt": "x"})
  if link == "file":
    (source / "key").symlink_to(secret / "id_rsa")
  else:
    (source / "keys").symlink_to(secret)
  with pytest.raises(RenderError, match="symlinks are not allowed"):
    render(source, tmp_path / "out", {"name": "demo"})
  assert not (tmp_path / "out").exists()


def test_runtime_errors_are_render_errors_and_clean_up(tmp_path):
  source = write(tmp_path / "src", {"a.txt": "ok", "b.txt": "${{ values.port + 'x' }}"})
  with pytest.raises(RenderError, match="b.txt"):
    render(source, tmp_path / "out", {"port": 1})
  assert not (tmp_path / "out").exists()


DEMO = REPO / "platform" / "templates" / "python-service-with-postgresql-for-demo-only"


def test_the_demo_template_is_python_service_with_database_details():
  """The demo template is a copy of python-service: only its name, its description, the template name in
  README/AGENTS and SHOW_DATABASE_DETAILS may differ. A change to python-service goes to both."""
  base_files = {path.relative_to(SEED / "content").as_posix() for path in (SEED / "content").rglob("*") if path.is_file() and "__pycache__" not in path.parts}
  demo_files = {path.relative_to(DEMO / "content").as_posix() for path in (DEMO / "content").rglob("*") if path.is_file() and "__pycache__" not in path.parts}
  assert base_files == demo_files
  for relative in sorted(base_files):
    base = (SEED / "content" / relative).read_bytes()
    demo = (DEMO / "content" / relative).read_bytes()
    if relative in ("README.md", "AGENTS.md"):
      demo = demo.replace(b"`python-service-with-postgresql-for-demo-only`", b"`python-service`")
    if relative == "app-spec.yaml":
      assert b'SHOW_DATABASE_DETAILS: "false"' in base
      demo = demo.replace(b'SHOW_DATABASE_DETAILS: "true"', b'SHOW_DATABASE_DETAILS: "false"')
    assert demo == base, f"{relative} differs between python-service and the demo template"
  base_definition = yaml.safe_load((SEED / "template.yaml").read_text())
  demo_definition = yaml.safe_load((DEMO / "template.yaml").read_text())
  assert base_definition.get("default") is True and "default" not in demo_definition
  for key in ("type", "owner", "parameters", "copyWithoutRendering"):
    assert demo_definition[key] == base_definition[key], key
