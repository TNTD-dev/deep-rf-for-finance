# Checkpoint 16/05 — News Coverage GO/NO-GO

**Date:** 2026-05-15 (PKG-2 implementation, 1 day ahead of schedule)
**Gate:** Overall (ticker, session) coverage ≥ 50% across test period 2025-05 → 2026-04
**Result:** ✅ **GO**

## Coverage breakdown (from `scripts/news_coverage_report.py`)

```
Test sessions: 248 (2025-05-05 → 2026-04-29)

=== PER-TICKER COVERAGE ===
ticker  sessions_with_news   pct
   VCB                 181 73.0%
   FPT                 191 77.0%
   HPG                 143 57.7%
   VIC                 218 87.9%
   VNM                  75 30.2%

Overall coverage: 808/1240 = 65.2%
Gate threshold:   50%

Source split:
  cafef    1789
  vnstock   250
```

## Decision

**GO — proceed to PKG-3 (trading env) and Phase 2 (agents + backtest).**

The 50% overall gate is met with margin (65.2%). Four of five tickers exceed
50% individually; VNM at 30.2% is the only weak member — VNM news in
Vietnamese press tends to be lighter-touch (consumer staples, not high-debate
finance topics like banking or steel).

## Risks accepted

- **VNM under-coverage (30.2%):** weekly-rebalance LLM agents will have
  fewer news signals for VNM than for VCB/FPT/HPG/VIC. Acceptable because:
  - The gate is overall coverage, not per-ticker minimum
  - VNM is a stable consumer-staples ticker — fundamentals/price action
    dominate the trading signal; news is a smaller component of the
    information set than for VCB/VIC
  - If VNM later proves a material weak point in backtest analysis, we can
    swap it for another VN30 ticker (HVN, MSN, SAB) without rerunning
    train (5-ticker universe is the project constant, not the specific 5)

## Fallback paths NOT activated

Documented for future reference:
- (a) Shorten test window to 6 months (2025-11 → 2026-04) — **not needed**
- (b) Numeric-only main study + news sub-study — **not needed**

## Source mix

- **CafeF sitemap dominates at 1789/2039 rows (88%)** — confirms vnstock
  `Company.news()` is genuinely capped at 50 items/ticker and is best used
  as a complement, not a primary, for backtest. For live mode, vnstock is
  preferable because its items are ticker-tagged native (no false positives).
- **Dedup preserved 250 vnstock rows** by skipping URL-based dedup for
  NaN-URL items (vnstock regulatory disclosures lack source links).

## Sign-off

- **Author:** TNTD (Duc) + Claude Code
- **Verifier (Person 2):** _pending_ — should spot-check 10 random tagged
  CafeF news per ticker for false positive rate (target < 10%) before
  formally closing this checkpoint.

PKG-3 (trading env) unblocked; PKG-2 PR ready to merge.
