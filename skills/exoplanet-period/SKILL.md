---
name: exoplanet-period
description: "Confirmed exoplanet orbital period by name. Before web_search, use tool_search and tool_call exoplanet_lookup. A non-exact name stays a candidate."
---

For this kind of request, before web_search, use tool_search and tool_call exoplanet_lookup.

The tool is `exoplanet_lookup`. Pass `name`.

An exact name returns the official name, the disposition, the orbital period in days, the discovery year, and the discovery facility. Copy `discovery_note` when it is present. An alias the catalog lists for the same planet counts as exact and returns the official name's period. A shorter name or a different planet stays in `candidates` and has no period. Do not present a candidate as the planet the user named.

When `discovery_note` says the year and facility could not be retrieved, repeat that sentence. When the note says the archive returned no row, or more than one row, leave the year empty. Do not fill the year from a different planet.

## When a read fails

Copy `error_type` and `next_step`. A timeout, a redirect, a body over 1000000 bytes, or an error status is not a completed miss. `not_found` is only the identifier read that finished with no planet. `no_confirmed_row` means the exact name had no confirmed period in days. `not_exact` means the catalog named a different official name. Quote `candidates` and stop.

This plugin does not set approval-card text. Before the user runs `hermes exoplanet-period schedule`, show the watched planet names, the 08:00 job, and that delivery is local only. The job spends 0 tokens. Empty stdout sends nothing. The job does not fire until a scheduler is serving this profile.

Turn one surface off with `hermes tools disable exoplanet-period --platform <platform>`.
