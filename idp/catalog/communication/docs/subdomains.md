# Subdomains

A subdomain is a `Domain` with `spec.subdomainOf`. Backstage draws it under its parent in the catalog graph and lists it on the parent's page.

## messaging

Owned by `team-alpha`. Produces greetings and publishes one `greeting.created` event per greeting.

- System `greeter`: `hello-alpha`, `hello-alpha-db` (database), `hello-alpha-events` (topic), `hello-alpha-uploads` (bucket)

## notifications

Owned by `team-beta`. Reacts to greeting events and writes reports.

- System `notifier`: `hello-beta`, `hello-beta-db` (database), `hello-beta-jobs` (queue), `hello-beta-reports` (bucket)
