# Join the team

As admin, join `team-alpha`, created in the [catalog](../catalog/hierarchy.md) (ADR 0026). Teams travel in the token: since you add yourself, `member add` renews yours, and the team works at once.

```bash
platform team member add team-alpha you@example.com

platform team get team-alpha
```

``` { .text .output title="output" }
✓ you@example.com added to team-alpha · token renewed, team-alpha is in it
team-alpha: 1 member(s)
EMAIL            USERNAME
you@example.com   you@example.com
```
