# Call it there

The same version, with the database of this environment: `checkin-test` is `ephemeral`, so its `db` is a database of its own in the shared instance `shared-pg` (`compose`), the host `/api/db` names.

```bash
curl http://seat-selection.checkin-test.localhost:7080/api/db
```

The home page, [http://seat-selection.checkin-test.localhost:7080/](http://seat-selection.checkin-test.localhost:7080/), shows it in the browser.
