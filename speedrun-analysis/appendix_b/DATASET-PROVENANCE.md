# Appendix B — the real review dataset

**No byte of this dataset is in this repository, and none may be.** This file
records what the dataset is, what it costs to get at it, what its licence
actually says, and precisely which of those things are verified rather than
assumed. `fetch_dataset.py` beside it is the only thing that talks to the
network; it downloads into a gitignored path and refuses to write anywhere
`git check-ignore` does not already cover.

Everything below was read on **2026-08-02** from public endpoints at the pinned
revision. Each claim names the endpoint or file it came from. Where something is
still unknown it says UNKNOWN and why.

---

## Identity and pin

| Field        | Value                                                            |
| ------------ | ---------------------------------------------------------------- |
| Dataset      | `open-spaced-repetition/anki-revlogs-10k` (HuggingFace Datasets) |
| Revision     | `75299740cff05894ef42d7ad990666691efdd2da`                       |
| lastModified | `2025-08-22T06:42:25.000Z`                                       |
| DOI          | `10.57967/hf/3435`                                               |
| Gating       | `gated: auto`                                                    |
| Licence tag  | `license: other`, `license_name: anki-revlogs-10k`               |
| Payload size | 15.7 GB (dataset page), 29,937 files                             |

Source: `GET https://huggingface.co/api/datasets/open-spaced-repetition/anki-revlogs-10k`
(HTTP 200, unauthenticated). The `sha` field of that response is the revision
above, so at the time of reading the pin **is** the repository head — it is
pinned anyway, because a head moves and a derived number must not.

Row counts, from the same response's `cardData.dataset_info`:

| Table     | Rows        |
| --------- | ----------- |
| `revlogs` | 727,738,650 |
| `cards`   | 208,432,491 |
| `decks`   | 2,066,838   |

`fetch_dataset.py` pins `REVISION` on every request **and checks the
`X-Repo-Commit` header of every response against it**. A response served from any
other revision is refused rather than warned about: a threshold derived from a
different snapshot than the one this file names is a number with false
provenance, which is worse than no number at all.

---

## It is gated, and here is exactly what that costs

The payload is gated; the repository's _text_ files are not. Measured, not
assumed:

| Endpoint at the pinned revision                 | Unauthenticated result             |
| ----------------------------------------------- | ---------------------------------- |
| `/resolve/<rev>/README.md`                      | **200**                            |
| `/resolve/<rev>/LICENSE`                        | **200**                            |
| `/api/.../tree/<rev>?recursive=1`               | **200**                            |
| `/resolve/<rev>/revlogs/user_id=1/data.parquet` | **401**, `x-error-code: GatedRepo` |

So the metadata, the file listing and the licence can all be read by anyone. Only
the parquet payload requires access.

**To unblock the download a user must:**

1. Have (or create) a HuggingFace account.
2. Visit <https://huggingface.co/datasets/open-spaced-repetition/anki-revlogs-10k>
   while signed in and accept the access request. Because the gate is
   `gated: auto`, approval is immediate and no human reviews it.
3. Create a token with `read` scope at <https://huggingface.co/settings/tokens>,
   and expose it as `HF_TOKEN` (or log in with `hf auth login`, which writes
   `~/.cache/huggingface/token`).

**What accepting the gate commits them to.** HuggingFace's default gate asks the
user to agree to share their account's contact information — username and email —
with the repository's authors. Additional gate terms, when a repository has any,
are declared as `extra_gated_prompt` / `extra_gated_fields` /
`extra_gated_heading` / `extra_gated_button_content` in the dataset card's YAML
front matter. **The front matter at this revision contains none of those keys**
(read directly from `/resolve/<rev>/README.md`), so the gate carries no custom
terms beyond the default contact-sharing agreement and the repository's own
`LICENSE`. HuggingFace's own site terms apply independently and are not
enumerated here.

---

## The licence — read, quoted, and assessed

### Correction to this project's earlier position

This project previously recorded that the licence was "custom and **NOT readable
without access**", and that derived-use permission was therefore **UNVERIFIED
pending access**. **That was wrong, and it is corrected here.** The gate covers
the parquet payload only; `LICENSE` resolves with HTTP 200 to an unauthenticated
client at the pinned revision. The claim was never tested before it was written
down, which is the same defect `BRAINLIFT.md` §8 records for the retired
thresholds: an assertion made first and sent looking for authority afterwards.

### The text, verbatim and complete

Fetched from
`https://huggingface.co/datasets/open-spaced-repetition/anki-revlogs-10k/resolve/75299740cff05894ef42d7ad990666691efdd2da/LICENSE`
— 326 bytes, `sha256 = b9b802ee74d65b448d8e522bb8d8a020b822700ec03f51ad10517246170cdca7`.
This is the whole file; nothing is elided, and the line breaks are the file's own:

```text
This data was provided to the FSRS project for use in memory research.
University students and individuals may also use it for their own research.
Please do not redistribute the data publicly (other than linking here).
If you wish to use the data in other contexts, please request permission on
https://anki.tenderapp.com.
```

### What that does and does not license

It is **not** a standard open licence. It grants no redistribution right, names
no warranty position, and has no versioned text to cite. Reading it plainly:

| Question                                                           | Answer                                                                              | Basis                |
| ------------------------------------------------------------------ | ----------------------------------------------------------------------------------- | -------------------- |
| May a student use it for their own research?                       | **Yes**                                                                             | sentence 2, verbatim |
| May derived numbers (thresholds, calibration curves) be published? | **Not addressed** — the text restricts redistribution of _the data_, not of results | sentence 3           |
| May the data be redistributed, committed, or vendored?             | **No**                                                                              | sentence 3           |
| May it be used in a product or any other context?                  | **Only with permission**, requested at anki.tenderapp.com                           | sentences 4–5        |

So the earlier blanket "derived-use permission is UNVERIFIED" is replaced by
something narrower and more useful:

- **Research use by an individual student: permitted by the licence text.**
- **Redistribution in any form: prohibited.** This is why `.gitignore` carries
  the download path, why `fetch_dataset.py` calls `git check-ignore` before it
  writes, and why the download manifest is written _inside_ the ignored
  directory rather than beside the code.
- **Product use: UNKNOWN and not assumed.** Speedrun is a graded course project
  that also ships a feature. Whether that is "their own research" or an "other
  context" is a judgement about intent that the text does not settle, and this
  project has not asked. If any Speedrun _shipped behaviour_ is ever fitted on
  this data — as opposed to a threshold reported in Appendix B — permission must
  be requested first. That request has **not** been made.

### What is still unverified

- The gate's click-through UI itself. The front matter shows no custom gate
  terms, which is strong evidence there are none, but nobody here has an account
  and so nobody here has seen the form.
- Whether the upstream permission the LICENSE alludes to ("provided to the FSRS
  project") imposes conditions not restated in it. Unknowable from outside.

---

## Schema

From the dataset card at the pinned revision, verbatim:

**`revlogs`** — pre-sorted in chronological order.

| Field             | Meaning (card's own words)                                            |
| ----------------- | --------------------------------------------------------------------- |
| `card_id`         | Unique identifier for each flashcard                                  |
| `day_offset`      | Number of days since the start of user's first review                 |
| `rating`          | User's rating (1: again, 2: hard, 3: good, 4: easy)                   |
| `state`           | Card's learning state (0: new, 1: learning, 2: review, 3: relearning) |
| `duration`        | Time spent on the card review in ms (range: 0–60000)                  |
| `elapsed_days`    | Days since the last review (−1 for new cards)                         |
| `elapsed_seconds` | Seconds since the last review (−1 for new cards)                      |

**`cards`**: `card_id`, `note_id`, `deck_id`.
**`decks`**: `deck_id`, `parent_id`, `preset_id`.

No card content, no deck names, no note text, by design. All ids are re-indexed
per user by `IdMapper.factorize` in the builder, so they are dense small integers
and carry nothing back to a real collection.

Layout on disk, from the card's `configs` block: `revlogs/user_id=*/data.parquet`,
`cards/user_id=*/data.parquet`, `decks/user_id=*/data.parquet` — a hive
partition, one file per user per table.

Counted from the `siblings` list of the public API response (29,937 files, none
of which required a token to enumerate):

| Table                                           | Partitions |
| ----------------------------------------------- | ---------- |
| `revlogs`                                       | 10,000     |
| `decks`                                         | 10,000     |
| `cards`                                         | **9,934**  |
| root (`.gitattributes`, `LICENSE`, `README.md`) | 3          |

User ids run 1–10,000 with no gaps. **66 users have `revlogs` and `decks` but no
`cards` partition** — so any join onto `cards` silently drops 0.66% of users
unless it is written to expect the miss. srs-benchmark handles this
(`data_loader.py::_read_user_partition` falls back to a filtered read "for users
with no partition directory (e.g. revlogs but no cards)"), and anything this
project writes must too. `--users all` in `fetch_dataset.py` selects from the
live tree listing rather than a generated path list for exactly this reason.

### The card's `state` column is incomplete — read the builder, not the card

The card documents four values. The builder emits **five**. From
[`anki-revlogs-dataset-builder/build_parquet.py`](https://github.com/open-spaced-repetition/anki-revlogs-dataset-builder/blob/main/build_parquet.py),
`process_revlogs` does `df.loc[:, "state"] += 1` and then sets the first entry of
each card's last learning run back to `0`. Against Anki's own
`RevlogReviewKind` (`Learning=0, Review=1, Relearning=2, Filtered=3, Manual=4,
Rescheduled=5` — `rslib/src/revlog/mod.rs`), the published values are:

| Published `state` | Actually means                                                                                       |
| ----------------- | ---------------------------------------------------------------------------------------------------- |
| 0                 | first entry of the card's **last learning run** (the dataset card calls this "new")                  |
| 1                 | `Learning`                                                                                           |
| 2                 | `Review`                                                                                             |
| 3                 | `Relearning`                                                                                         |
| **4**             | **`Filtered`** — a filtered-deck/cram review that _did_ affect scheduling. Undocumented on the card. |

`Manual` and `Rescheduled` cannot appear: they are always written with
`button_chosen: 0` (`Collection::log_scheduled_review`, `rslib/src/revlog/mod.rs`)
and the builder's `filter_revlog` keeps only `button_chosen >= 1`.

Anything that treats `state` as a four-valued enum will silently mis-handle
filtered-deck reviews. This is a finding about the dataset card, not about the
data.

---

## `FSRS-Anki-20k` is deprecated — do not use it

`open-spaced-repetition/FSRS-Anki-20k` (20k collections, ~1.7 billion reviews) is
superseded. The srs-benchmark README strikes its own description of it through
(`~~...~~`) and replaces it with `anki-revlogs-10k`. Nothing in this project may
cite the 20k dataset, and no figure derived from it may be carried forward.

---

## Nothing here is committed

- `.gitignore` carries `/speedrun-analysis/appendix_b/data/` and `*.parquet`.
- `fetch_dataset.py` runs `git check-ignore` on its destination **before writing
  a byte** and aborts if the answer is anything but "ignored". The `.gitignore`
  entry can be deleted by someone who does not know why it is there; that check
  is what actually holds the line.
- The download manifest (`download-manifest.json`: per-file size, sha256, and
  every verification outcome) is written _inside_ the ignored directory. It
  describes a payload this repository may not keep, so it is not evidence this
  repository may carry either.
- The token is never printed, never logged, never written to the manifest. Every
  string the script emits — including exception text — goes through `_scrub()`
  first.

## What `fetch_dataset.py` verifies

Per file, recorded in the manifest as PASS / FAIL / SKIP with a reason:

| Check     | How                                                                                                                                                       |
| --------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| revision  | `X-Repo-Commit` on the response equals the pinned sha (hard failure on mismatch)                                                                          |
| non-empty | size > 0                                                                                                                                                  |
| size      | matches the server's `X-Linked-Size`                                                                                                                      |
| sha256    | matches the server's LFS `X-Linked-Etag` oid                                                                                                              |
| format    | `PAR1` magic at both ends of the file — the cheapest honest answer to "is this a parquet file or an HTML error page?", and it needs no third-party reader |

`SKIP` is used where the server did not supply something to compare against, and
says so. It is never used to make a failure look like a pass.

## Reproducing the public reads above

```bash
B=https://huggingface.co/datasets/open-spaced-repetition/anki-revlogs-10k
R=75299740cff05894ef42d7ad990666691efdd2da

curl -s  https://huggingface.co/api/datasets/open-spaced-repetition/anki-revlogs-10k | python3 -m json.tool
curl -sL "$B/resolve/$R/LICENSE" | shasum -a 256   # b9b802ee74d6...
curl -sL "$B/resolve/$R/README.md"
curl -s -o /dev/null -w '%{http_code}\n' "$B/resolve/$R/revlogs/user_id=1/data.parquet"   # 401
```

Then, once a token exists:

```bash
python3 speedrun-analysis/appendix_b/fetch_dataset.py --preflight   # proves access, fetches nothing
python3 speedrun-analysis/appendix_b/fetch_dataset.py --list        # the repo's own listing
python3 speedrun-analysis/appendix_b/fetch_dataset.py --users 1-3   # ~3 users, all three tables
```

## What this does not discharge

Having the data is not having a threshold. `thresholds.json` reports eight
thresholds, all `UNKNOWN`, all `value: null`, and it will keep doing so until
`derive_thresholds.py` runs against a manifest whose `"synthetic"` is `false`
**and** the crossover each search looks for is actually present. Downloading a
dataset changes none of that on its own, and `Derivation.to_json` will not let it
pretend otherwise.

## The unit does not currently match ours — read this before deriving anything

A threshold expressed in "fsrs_items" is only transferable if this dataset's
scored review and `rslib/src/speedrun/mastery.rs`'s `fsrs_item_count` are the same
thing. They are not. Three of the four filters agree exactly; the fourth is
missing from our side, and it is missing from the _earliest_ stage, so ours is
the wrong one.

| Filter                                                 | Anki `params.rs`                                                                                                 | dataset + srs-benchmark                                                  | our `mastery.rs`                             |
| ------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------ | -------------------------------------------- |
| manual due-date changes / resets / reschedules removed | `has_rating()` (`button_chosen > 0`)                                                                             | `filter_revlog`: `button_chosen >= 1`                                    | same — `has_rating_and_affects_scheduling()` |
| cram with rescheduling disabled removed                | `is_cramming()` (`Filtered && ease_factor==0`)                                                                   | `filter_revlog`: `review_kind != 3 or ease_factor != 0`                  | same call, same rule                         |
| same-day reviews excluded from the item count          | item emitted only when `delta_t > 0`                                                                             | evaluation rows are `delta_t > 0`                                        | same — `idx_in_card >= 1 && delta_t > 0`     |
| **history truncated at the last learning run**         | `first_of_last_learn_entries` + `drain(..idx)`; card dropped entirely when training and it has no learning steps | `process_revlogs` mask + `groupby("card_id").filter(state.iloc[0] == 0)` | **absent**                                   |

`mastery.rs` implements exactly two stages — the `has_rating_and_affects_scheduling()`
retain (`mastery.rs:199`) and the `idx_in_card >= 1 && delta_t > 0` emit
(`mastery.rs:209`). It never
mentions `Learning`, `is_reset`, `first_of_last_learn_entries` or `drain`, so the
stage is not merely wrong, it is not present.

The consequence is one-directional: `fsrs_item_count` here **over-counts**. Two
worked cases, both taken from upstream's own tests so the expected values are
not this project's opinion:

| Card history                                                       | Anki (`params.rs` tests)                                                | `mastery.rs` |
| ------------------------------------------------------------------ | ----------------------------------------------------------------------- | ------------ |
| `Learning@10, Reset@7, Learning@4, Review@0`                       | **1** item — `card_reset_drops_all_previous_history`                    | **2**        |
| `Review@10, Review@5` (no learning entry — imported / shared deck) | **0** items — same rule as `single_learning_step_skipped_when_training` | **1**        |

In the first, the `Reset` is dropped by stage 1 as an unrated entry, so nothing
downstream can see that it was ever there; upstream uses it _before_ that filter
to cut the history. Cards imported from another collection, cards re-learnt after
`Forget`, and shared-deck cards with truncated histories are all in this class.

srs-benchmark additionally applies an outlier filter (`remove_outliers` +
`remove_non_continuous_rows`, borrowed from fsrs-optimizer) and truncates each
card at 128 reviews. **Neither Anki nor this project has any equivalent**, and
that divergence is theirs, not ours — but it means an `fsrs_items` figure read
off the published benchmark is not the same quantity as an `fsrs_items` figure
computed by Anki, either.

Until the truncation stage exists in `mastery.rs`, no floor derived on this
dataset may be applied to `fsrs_item_count` without restating which of the two
units it is in.
