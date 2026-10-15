# Google credentials

!!! context "Optional"
    Without it, sign-in works with a password.

    The OAuth client is created once with [Keycloak](https://github.com/smsilva/wasp-idp/blob/main/platform/keycloak/README.md).

Create `google.env` at the root of the checkout and fill in the values:

```bash
cat > google.env <<'EOF'
export GOOGLE_CLIENT_ID=<id>.apps.googleusercontent.com
export GOOGLE_CLIENT_SECRET=<secret>
EOF
```

Make sure git ignores it:

```bash
git check-ignore google.env
```

``` { .text .output title="output" }
google.env
```

Load it:

```bash
source google.env
```

Check, showing only the prefix:

```bash
echo "${GOOGLE_CLIENT_ID:0:12}… ${GOOGLE_CLIENT_SECRET:0:3}…"
```

``` { .text .output title="output" }
123456789012… GOC…
```
