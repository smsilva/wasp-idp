# Pick a seat

```bash
curl \
  --request PUT \
  --header "Content-Type: application/json" \
  --data '{"seat": "12A"}' \
  http://seat-selection.demo.localhost:7080/api/bookings/TW4821/passengers/1/seat
```

``` { .text .output title="output" }
{"booking":"TW4821","passenger":"1","seat":"12A","status":"held"}
```

The same call is in **Open the API docs**, on the home page.
