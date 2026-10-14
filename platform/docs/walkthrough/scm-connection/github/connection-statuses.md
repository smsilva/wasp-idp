# Connection statuses

Each status of the connection, what to do, and how `verify --wait` behaves:

| Status | What to do | `verify --wait` |
|---|---|---|
| `AppNotCreated` | run `add` again | — |
| `NotInstalled` | install the App via the `installUrl` from `get` | waits |
| `NotAllRepositories` | switch the installation to All repositories | stops |
| `MissingPermissions` | update the App and accept it on the org (the message lists what is missing) | stops |
| `ready` | nothing; the controller revalidates every 6 h | finishes |
