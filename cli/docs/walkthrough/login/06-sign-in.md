# Sign in

```bash
platform login --use-device-code
```

Open the printed URL in the browser and go through the screens: **confirm the code**, **sign in with Google**, **review the profile** (first sign-in only) and **authorize the terminal**. The terminal ends with `✓ Logged in as you@example.com (platform-admins, platform-users)`.

!!! tip
    `platform login` without a flag opens the default browser by itself. Use the device code when the default browser is signed in to a different Google account, or in a presentation, to show the Keycloak screens.
