# Exoplanet Period

A confirmed exoplanet name returns the orbital period in days, the discovery year, and the discovery facility.

## Install and first call

From this directory, with Hermes 0.21.4 or newer:

```
hermes plugins install "file://$PWD" --enable
hermes plugins enable exoplanet-period
hermes exoplanet-period call exoplanet_lookup --json '{"name":"WASP-12 b"}'
```

No API key is required. The command prints one JSON object. `orbital_period_days` is the period. `discovery_year` and `discovery_facility` come from the archive when that read returns one exact row. `source_url` is the MAST properties URL for the official name.

## What you get

`exoplanet_lookup` reads the MAST identifier for the name you pass. The getting-started page is https://exo.mast.stsci.edu/docs/getting_started.html. An exact match, after case and spaces are folded, then reads that official name's properties. The period is taken from the latest row whose disposition is `confirmed planet` and whose period unit is days. A later modified date wins. The same date keeps the earlier catalog name.

`WASP-12` is not `WASP-12 b`. The result is `not_exact`, the candidate is the official name, and `orbital_period_days` is null. A shorter name such as `WASP-1` stays a candidate for the official name MAST returned. This plugin does not return a different planet as the one you named.

The discovery year and the discovery facility are read from the NASA Exoplanet Archive, one exact row in the composite table. The archive home is https://exoplanetarchive.ipac.caltech.edu/. When that read returns one row, those two fields are filled. When the row leaves a field empty, `discovery_note` says that field is absent. When the archive returns no row, or more than one exact row, the year and the facility stay empty and `discovery_note` says which of those happened. When the archive does not answer, times out, or returns an error status, the MAST fields stay, and `discovery_note` is `Discovery year and facility could not be retrieved.`

A finished identifier object with no planet is `not_found`. An exact name with no confirmed period in days is `no_confirmed_row`. A timeout, a redirect, a body over 1,000,000 bytes, or an error status is not either of those.

The properties URL is requested without a trailing slash. A redirect is not followed. The period is not taken from a row whose disposition is not `confirmed planet`.

This plugin does not read light-curve FITS files. The lightkurve package is not included.

## What is sent, and what stays here

The planet name you pass is sent to `exo.mast.stsci.edu` and, after an exact match, to `exoplanetarchive.ipac.caltech.edu`, over HTTPS. Nothing else is sent. Redirects are not followed. An HTTP proxy in the environment is not used. Each request stops at 20 seconds. A timeout, a connection failure, or HTTP 429, 500, 502, 503, or 504 is tried once more. Any other status is returned once. The read tool does not write a file.

The tool starts enabled on every surface. An empty gateway allowlist still leaves it enabled, so a person who can message that surface can call it. Turn one surface off with `hermes tools disable exoplanet-period --platform <platform>`. The CLI call still runs after that.

The watch file under `plugin-data/exoplanet-period` stays on this machine. It stores at most 20 official planet names, with the catalog name and the modified date. The file stops at 8192 bytes. Each directory is opened from the filesystem root. A symlink under the Hermes home is refused. The first directory of an absolute path may be an operating-system alias. On macOS, `/tmp` and `/var` are aliases of a private directory. A home under those aliases is written through the real directory. A symlink on a later directory, or on the file itself, is refused.

## Morning watch

This plugin does not set approval-card text. The morning job is a CLI command. Before you run it, read the watched planet names, the 08:00 schedule, and the local-only delivery. Those are the whole change. The job compares one saved modified date. It does not change the catalog.

```
hermes exoplanet-period watch add "WASP-12 b"
hermes exoplanet-period watch list
hermes exoplanet-period schedule
hermes exoplanet-period status
hermes exoplanet-period unschedule
```

`schedule` accepts only `local`. Any other deliver target is refused before a job is created. It writes `scripts/exoplanet-period-watch.py` and creates one cron job named `exoplanet-period-watch`. The schedule is 08:00. Hermes uses the profile timezone when one is set, and otherwise the machine local time. The run has no model turn and spends 0 tokens. The job does not fire until a scheduler is serving this profile. Local delivery keeps a printed line under `cron/output` and sends nothing to a chat. The same modified date prints no line. A later date prints one line that the date moved forward, with both dates and the catalog name. An earlier date prints one line that the date moved backward, with both dates and the catalog name. An empty script sends nothing. A failed read keeps the saved date and prints that the date could not be read.

`unschedule` removes the cron job and `scripts/exoplanet-period-watch.py`. The watch file remains.

After `hermes plugins remove`, three leftovers remain: the cron job, `scripts/exoplanet-period-watch.py`, and `plugin-data/exoplanet-period/watch.json`. Copy the id from `hermes exoplanet-period status` or from `hermes cron list` before you remove the plugin. `hermes cron status` prints the active job count and the next run. It does not print the id. Stop the leftover job with `hermes cron remove <id>`. On a profile other than `default`, use the `hermes -p <profile>` prefix printed by `status`. Delete `scripts/exoplanet-period-watch.py` and `plugin-data/exoplanet-period/watch.json` if they are still there. `hermes cron remove` with no id exits 2 and the job stays.
