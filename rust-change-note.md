# The Rust change — one-page note

**Status: PENDING.** The fork does not yet exist. This file states what the change will be and what this note must contain, so the requirement is visible rather than absent.

---

## Provisional scope

**Per-topic mastery query** — returns per-topic mastery and average recall over a 50,000-card collection, fast enough to drive the dashboard.

### Why this belongs in Rust, not Python

All three scores and the coverage map depend on per-topic aggregation across the full collection. The performance targets are dashboard first load under 1 second and refresh under 500 ms, with nothing blocking the UI for more than 100 ms. Aggregating FSRS memory state across 50,000 cards per dashboard render is not a Python-layer operation — it belongs next to the collection in `rslib`, behind a protobuf message, where both the desktop app and the phone companion consume the same implementation.

This also satisfies a build constraint that is easy to miss: **the change ships to the phone too.** A Python-side implementation would have to be written twice and would drift.

### Alternative still under consideration

**Points-at-stake queue** — ordering due cards by topic weight × weakness, with a new protobuf message. This ties more directly to POV 1 (transfer moderators should influence scheduling, not just interval) and would place the thesis feature inside the scheduler, which makes the §9 ablation cleaner. The tradeoff is that it does not address the dashboard-latency requirement, which the mastery query does.

Decision to be recorded here once the fork is building.

---

## What this note must contain before final submission

- [ ] The diff
- [ ] 3 Rust unit tests
- [ ] 1 Python test calling into the change
- [ ] Proof undo works and the collection does not corrupt
- [ ] Why this belongs in Rust (drafted above; to be finalized against the real implementation)
- [ ] The upstream files touched, with commit-pinned permalinks
- [ ] Verification that the change works on the phone build

---

## Citation discipline

Source references in this project are pinned to **commit SHA plus symbol name**, not line number. Line numbers drift with upstream refactors; a commit-pinned permalink does not.

Several source citations in `BRAINLIFT.md` are currently marked **UNVERIFIED** because `git clone` was blocked by an egress proxy during research and GitHub's rendered line gutter was unreadable through the fetch layer. No plausible-looking line number was substituted for a real one.

These resolve the moment the fork exists locally:

```bash
# FSRS optimizer minimum-review threshold
rg -n 'FSRS|min_.*review|MIN_.*REVIEW' --type rust rslib/ | rg -i 'min|threshold|enough'

# User-facing strings live in Fluent files, not in the code
rg -n -i 'optimi[sz]|not enough|insufficient' ftl/

# The revlog helper approximated as `ease > 0 AND type NOT IN (4,5)` in analysis SQL
rg -n 'has_rating_and_affects_scheduling' -A 15
```

When an UNVERIFIED citation is upgraded, **note that it was upgraded** rather than silently presenting it as clean.
