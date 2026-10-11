# JSON output

```bash
platform environment list --output json
```

```json
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

A lista nunca traz o kubeconfig. O `platform environment get` o recebe só para quem pode usar o ambiente: quem o criou, quem está em `platform-admins` ou nos times com que ele foi compartilhado. Os demais veem o status, sem o acesso.

```bash
platform environment list --output json | jq -r '.[].name'
```
