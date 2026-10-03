# Subdomains

A subdomain is a `Domain` with `spec.subdomainOf`. Backstage draws it under its parent in the catalog graph and lists it on the parent's page.

## messaging

Owned by `team-alpha`. Produces greetings and publishes one `greeting.created` event per greeting.

- System `greeter`: `greeting-api`, `greeting-db` (database), `greeting-events` (topic), `greeting-avatars` (bucket)

## notifications

Owned by `team-beta`. Reacts to greeting events and writes reports.

- System `notifier`: `notification-api`, `notification-db` (database), `notification-jobs` (queue), `notification-reports` (bucket)
