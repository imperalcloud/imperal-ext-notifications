# imperal-ext-notifications

Imperal-owned system extension for notification preferences. Lets Webbee show
and change where each app's notifications get delivered, from chat.

## Tools

- `get_preferences` (read) — the current routing matrix: global switch,
  default row, per-app overrides, and which channels are actually connected
  for this user.
- `set_preferences` (write) — change exactly one thing per call: the global
  switch, the default row, or one app's channels. Passing an empty channel
  list for an app mutes it.

## How preferences work

Every app's notifications route to one or more channels:

- `bell` — the panel notification bell
- `telegram` — delivered only once the user has linked Telegram
- `email`

Apps without their own override use the `default` row. Routing to `telegram`
before it is linked is saved as-is; the tool reports that delivery starts only
after linking so the assistant can tell the user, without blocking the change.

## Access

System app — available to every user without an explicit install.

## Deploy

Published through the Imperal Cloud Developer Portal at
https://panel.imperal.io/developer.
