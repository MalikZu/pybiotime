# Command line

Installing pybiotime also installs a `pybiotime` command. It reads a BioTime server and
writes JSON Lines or CSV, so a scheduled job can feed punches to another system.

## Connect

Settings come from environment variables, so passwords stay out of your shell history:

```bash
export BIOTIME_URL=http://10.0.0.5:8090
export BIOTIME_TOKEN=your-api-token
```

Instead of a token, set `BIOTIME_USERNAME` and `BIOTIME_PASSWORD`. In a terminal, the
command asks for the password if it is not set. Set `BIOTIME_TIMEZONE`, for example
`Asia/Dubai`, to write times with their offset.

Check the connection:

```bash
pybiotime info
```

## Collect new punches on a schedule

`sync` prints the punches that arrived since its last run, then saves where it got to:

```bash
pybiotime sync --state /var/lib/biotime/state.json --start 2026-10-01 --output punches.jsonl
```

- **First run:** returns every punch from `--start`, or all punches without it.
- **Later runs:** return punches that arrived since the previous run, including old
  punches that offline devices upload late. See [Reading punches](punches.md#collect-new-punches-without-gaps).
- **`--output`** appends, so each run adds to the same file. Without it, punches go to
  standard output.
- **The state file** moves on only after the punches are written. If a run fails, the
  next one repeats it instead of losing punches. Key what you store on the punch `id`.

Run it from cron every few minutes, for example:

```text
*/5 * * * * pybiotime sync --state /var/lib/biotime/state.json --output /var/lib/biotime/punches.jsonl
```

## Export

```bash
pybiotime transactions --start 2026-10-01 --end "2026-10-31 23:59" --format csv -o october.csv
pybiotime employees --format csv
pybiotime terminals
```

- `transactions` filters on punch time and also takes `--emp-code` and `--terminal-sn`.
- `employees` never writes the device PIN, the card number or the password hash.
- `--format jsonl` (the default) writes every field; `--format csv` writes the main columns.

## Exit status

`0` when done, `1` when the server refused or failed, `2` for a wrong or missing setting.
Errors go to standard error.

Run `pybiotime --help` or `pybiotime <command> --help` for every option.
