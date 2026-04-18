# Maintenance

## Add A Platform

Edit `scripts/scan.py`:

1. Add the display name to `PLATFORM_ORDER`.
2. Add aliases to `PLATFORM_ALIASES`.
3. If needed, add special query hints to `PLATFORM_HINTS`.
4. Run a syntax check and a small scan with a low query budget.

## Add A Channel

1. Implement a `search_<channel>()` function that returns normalized signal
   dictionaries through `make_signal()`.
2. Register the channel in `CHANNEL_LABELS`.
3. Add the channel call inside `search_all_channels()`.
4. On dependency or quota failure, call `mark_channel()` with `ok=False` and
   return an empty list.

## Normalized Signal Schema

Every result should preserve these fields:

- `platform`
- `dimension`
- `title`
- `date`
- `source`
- `source_label`
- `url`
- `author`
- `content`
- `query`

Avoid overloading fields. In particular, do not place URLs and authors in the
same field.

## Parser Safety

- Keep parser functions pure where possible so they can be tested without live
  network access.
- Parse structured JSON before falling back to text extraction.
- For relative dates, keep the original raw date in `raw_date` and also produce
  a normalized `date` when possible.
- Use the current year dynamically. Do not hard-code a calendar month or year in
  query strings or date parsing.

## Validation

Run these checks after changing the skill:

```bash
python3 -m py_compile scripts/scan.py
python3 /path/to/skill-creator/scripts/quick_validate.py /path/to/competitor-scan
```

When live dependencies are available, also run:

```bash
COMPETITOR_SCAN_MAX_QUERIES_PER_PLATFORM=1 python3 scripts/scan.py
```
