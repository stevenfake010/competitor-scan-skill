# Maintenance

## Add A Platform

Edit `scripts/scan.py`:

1. Add a new entry in `PLATFORM_CONFIG`
2. Include:
   - `aliases`
   - `official_domains`
   - `focus_keywords`
   - `queries`
3. Run syntax checks and offline tests
4. Run a low-budget live scan if credentials exist

## Add A Channel

1. Implement `search_<channel>()`
2. Register the label in `CHANNEL_LABELS`
3. Add the call in `search_all_channels()`
4. On dependency/auth/quota failure, call `mark_channel(ok=False, ...)`
5. Keep the scan running even when the channel is unavailable

## Normalized Signal Schema

Every signal should preserve the base fields:

- `platform`
- `dimension`
- `title`
- `date`
- `raw_date`
- `source`
- `source_label`
- `url`
- `author`
- `content`
- `query`

The analyst layer additionally uses:

- `domain`
- `action_type`
- `source_tier`
- `credibility_score`
- `credibility_label`
- `relevance_score`
- `total_score`
- `priority`
- `matched_aliases`
- `matched_keywords`
- `judgement`
- `implication`
- `evidence_summary`

## Scoring Integrity

- Do not silently promote low-credibility SEO pages to high-priority evidence
- Keep `credibility_score` and `relevance_score` separate
- Use `total_score` only after both axes are computed
- Treat “no result” and “channel unavailable” differently

## Parser Safety

- Parse structured JSON before text extraction
- Decode subprocess output as UTF-8 with replacement
- Preserve `raw_date`
- Use dynamic dates; never hard-code year/month in queries
- Never hard-code API keys

## Validation

Run after changing the skill:

```bash
python3 -m py_compile scripts/scan.py
python3 tests/offline_scan_tests.py
python3 /path/to/skill-creator/scripts/quick_validate.py /path/to/competitor-scan
```

When live dependencies are available, also run:

```bash
COMPETITOR_SCAN_MAX_QUERIES_PER_PLATFORM=1 python3 scripts/scan.py
```

For Windows PowerShell:

```powershell
$env:COMPETITOR_SCAN_MAX_QUERIES_PER_PLATFORM = "1"
python .\scripts\scan.py
```
