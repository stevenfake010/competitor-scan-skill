# Maintenance

## Add A Platform

Edit `scripts/scan.py`:

1. Add a new entry in `PLATFORM_CONFIG`
2. Include:
   - `aliases`
   - `official_domains`
   - `content_url_markers` or `content_url_regexes` when official domains also
     host user posts, videos, notes, or profile pages
   - `focus_keywords`
   - `queries`
3. Run syntax checks and offline tests
4. Run a low-budget live scan if credentials exist

## Multi-Platform Portability

- Treat platform names as configuration, not as the report viewpoint.
- Keep `PLATFORM_CONFIG` as the source of truth for aliases, official domains,
  query templates, content-page URL patterns, and platform-specific focus
  keywords.
- Add event phrases only for recurring concrete actions that help clustering;
  avoid turning one platform's current examples into universal rules.
- When a platform's official domain also hosts user content, add URL markers or
  regexes so user videos/posts are not promoted as official rule evidence.
- Keep report language neutral by default. Do not add audience-specific response
  framing unless the user explicitly asks for a response memo.

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
- `growth_lever`
- `growth_score`
- `date_confidence`
- `source_tier`
- `credibility_score`
- `credibility_label`
- `relevance_score`
- `total_score`
- `priority`
- `matched_aliases`
- `matched_keywords`
- `judgement`
- `evidence_summary`

## Normalized Event Schema

The text report is event-based. `build_payload()` should preserve:

- `by_platform` for retained raw signals
- `by_platform_events` for clustered user-growth events
- `platform_analysis.<platform>.events`

Every event should preserve:

- `platform`
- `title`
- `growth_lever`
- `action_type`
- `date`
- `status`
- `priority`
- `total_score`
- `evidence_strength`
- `evidence_count`
- `evidence_buckets`
- `fact_summary`
- `sources`
- `uncertainty`
- `signals`

The user-facing report should render events, not raw signals.

## Scoring Integrity

- Do not silently promote low-credibility SEO pages to high-priority evidence
- Keep `credibility_score` and `relevance_score` separate
- Use `total_score` only after both axes are computed
- Treat “no result” and “channel unavailable” differently
- Treat undated evidence as support, not P1 event evidence
- Do not treat platform content pages as official rule evidence
- Keep user-growth filtering strict; generic product news should not enter the
  body unless it maps to a clear growth lever

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
