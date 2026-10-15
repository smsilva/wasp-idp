# Create the team and join it

Every catalog entity has a team as its owner (ADR 0026), so the team comes before the catalog. As an admin, create `team-alpha` and join it. Teams travel in the token: since you add yourself, `member add` renews yours, and the team works at once.

```bash
platform team create team-alpha

platform team member add team-alpha you@example.com

platform team get team-alpha
```

``` { .text .output title="output" }
✓ team team-alpha created
✓ you@example.com added to team-alpha · token renewed, team-alpha is in it
team-alpha: 1 member(s)
EMAIL            USERNAME
you@example.com   you@example.com

next:

  platform team member add team-alpha <email>
```
