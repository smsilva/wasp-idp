# A branch and a change

A new branch:

```bash
git -C /tmp/hello-api switch --create feat/greetings
```

A new endpoint, and its line in `app/features.py`, the list the home page shows under "What this version does":

```bash
cat >> /tmp/hello-api/app/main.py <<'PY'


@app.get("/api/greet/{name}", tags=["greetings"], summary="Say hello to someone")
def greet(name: str) -> dict[str, str]:
    return {"message": f"Hello, {name}!"}
PY
```

```bash
cat >> /tmp/hello-api/app/features.py <<'PY'

FEATURES.append(Feature(name="Greets by name", description="Says hello to whoever is named in the path.", endpoint="GET /api/greet/{name}", new=True))
PY
```

A `feat:` commit, which makes the version `0.1.0`:

```bash
git -C /tmp/hello-api commit --all --message "feat: greet by name"
```
