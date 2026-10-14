# Output formats

Every command that prints a result accepts `--output` (short: `-o`) with one of these formats:

| Format | What it prints |
| --- | --- |
| `table` | the default, for people |
| `json` | indented JSON, for `jq` and scripts |
| `jsonc` | the same JSON, colored |
| `yaml` | the same data as YAML; multi-line values (kubeconfigs, keys) as literal blocks |
| `yamlc` | the same YAML, colored |

Every format but `table` is for machines: no progress lines and no prompts (`platform catalog import -o yaml` without `--yes` is a dry run). The colored formats keep their colors through a pipe (`platform team list -o jsonc | less -R`) and drop them when `NO_COLOR` is set. `platform catalog template render --output` is a folder, not a format, so it has no `-o`.

## JSON

```bash
platform environment list \
  --output json
```

``` { .json .output title="output" }
[
  {
    "name": "greetings-test",
    "profile": "ephemeral",
    "expiresAt": "2026-10-10T21:35:22Z",
    "status": "ready",
    "message": "vcluster running in namespace env-greetings-test, API on 127.0.0.1:7100",
    "port": 7100,
    "createdAt": "2026-10-10T20:35:22Z"
  }
]
```

Lists never include a kubeconfig; `platform environment get` returns it only to those who can use the environment. Errors keep one shape: `{"error": {"code", "message"}}`.

```bash
platform environment list --output json | jq -r '.[].name'
```

## YAML

```bash
platform team get team-a -o yaml
```

``` { .yaml .output title="output" }
name: team-a
members:
- email: dev@example.com
  username: dev
```
