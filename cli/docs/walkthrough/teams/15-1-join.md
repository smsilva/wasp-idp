# Join the team

As admin, join `team-alpha`, created in the [catalog](../catalog/13-1-hierarchy.md) (ADR 0026). The team reaches the token **on the next login**.

```bash
platform team member add team-alpha you@example.com

platform team get team-alpha
```

``` { .text .output title="output" }
✓ you@example.com added to team-alpha
team-alpha: 1 member(s)
EMAIL            USERNAME
you@example.com   you@example.com
```
