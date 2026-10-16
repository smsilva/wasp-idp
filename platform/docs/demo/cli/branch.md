# A branch and a change

A new branch:

```bash
git -C /tmp/seat-selection switch --create feat/seat-pick
```

A new endpoint, and its line in `app/features.py`, the list the home page shows under "What this version does":

```bash
cat >> /tmp/seat-selection/app/main.py <<'PY'


class SeatPick(BaseModel):
    seat: str


@app.put("/api/bookings/{booking}/passengers/{passenger}/seat", tags=["seats"], summary="Pick a seat for a passenger at check-in")
def pick_seat(booking: str, passenger: str, pick: SeatPick) -> dict[str, str]:
    return {"booking": booking, "passenger": passenger, "seat": pick.seat, "status": "held"}
PY
```

```bash
cat >> /tmp/seat-selection/app/features.py <<'PY'

FEATURES.append(Feature(name="Picks a seat at check-in", description="Holds the seat a passenger picks for their booking.", endpoint="PUT /api/bookings/{booking}/passengers/{passenger}/seat", new=True))
PY
```

A `feat:` commit, which makes the version `0.1.0`:

```bash
git -C /tmp/seat-selection commit --all --message "feat: pick a seat at check-in"
```
