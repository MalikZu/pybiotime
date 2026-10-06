# Reading punches

BioTime calls punches *transactions*. Each one has an `id`, the person's `emp_code`, the
device's `terminal_sn`, a `punch_time` and an `upload_time`.

Identify people by `emp_code` and devices by `terminal_sn`. The `emp` and `terminal`
fields are usually empty.

## Filter

```python
from datetime import datetime

punches = bt.transactions.list(
    start=datetime(2026, 10, 1),
    end=datetime(2026, 10, 2),
    emp_code="1001",
    terminal_sn="CQUJ123456789",
    order_by="punch_time",
)
```

- `start` and `end` filter on **punch time**, in server time. A naive datetime is sent as
  is. An aware one is converted to the client's `timezone`, which must be set.
- `order_by` takes `"punch_time"`, `"upload_time"`, or either with a leading `-` for
  newest first. The server ignores any other sort, so pybiotime does not offer one.
  Without `order_by`, BioTime 9.5 returns punches by ascending id.

## Punch state and verification

`punch_state` and `verify_type` keep the raw code, because devices can send codes that
are not documented. Compare them with the enums:

```python
from pybiotime import PunchState, VerifyType

if punch.punch_state == PunchState.CHECK_IN and punch.verify_type == VerifyType.FACE:
    ...
```

`punch_state_display` and `verify_type_display` hold the server's own labels.

## Collect new punches without gaps

A device that was offline keeps its punches and uploads them later, sometimes months
later. A punch-time window such as "the last hour" misses them. Use `read_new`:

```python
import json

state = load_state()  # None on the first run
result = bt.transactions.read_new(state, start=datetime(2026, 10, 1))

for punch in result.transactions:
    save_punch(punch)  # key it on (server, punch.id)

save_state(json.dumps(result.state))
```

- **First run** (no state): returns every punch from `start`, or all punches if you leave
  `start` out.
- **Later runs**: returns punches that arrived since the previous run, however old their
  punch time.
- **The state** is a small dict. Store it as JSON and pass it back next time. Save it only
  after you saved the punches, so a crash repeats work instead of losing it.

How it works: it reads the newest arrivals first, back to just before the previous run's
newest arrival. It also re-reads punch times from the last day (`lookback=`) as a safety
net. It remembers the highest id and the recently seen ids, so each punch comes back once.

Each run checks that the server really sorts by arrival time. On a server that does not,
`read_new` relies on the punch-time window for that run, and `result.state["upload_order"]`
says `"unsupported"`.

A punch can still come back twice in rare cases. Store punches keyed on the server and
the `id`, and skip ones you already have.

### When the server's database is restored

A restored database hands out ids it already used, for new punches. `read_new` notices and
raises `ReadStateError`, so punches are not skipped as already seen:

- **It remembers a short fingerprint** (who punched, when, and on which device) for each
  recent id. When a known id comes back as a different punch, that is a restore. The same
  punch coming back is skipped as usual.
- **It also spots ids that start over from far below** what it has seen.
- **States saved by pybiotime 0.1.1 or older** have no fingerprints. They learn them as
  the scans see those punches again, and check them from then on.

After `ReadStateError`, start again without a state, from a known date, and let your
storage's `id` key drop the punches you already have.
