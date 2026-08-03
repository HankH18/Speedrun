# `ai/` — the AI subsystem

BUILD-DOC §7. Standard library only. **Nothing in this package makes a network
call.** The modules that would (`generation.py`) refuse and say what is missing,
rather than returning a plausible-looking placeholder.

| Module            | What it is                                                         | State                   |
| ----------------- | ------------------------------------------------------------------ | ----------------------- |
| `flags.py`        | The AI on/off switch (§7.6). Default **OFF**.                      | Built, tested           |
| `sources.py`      | Source registry: `source_id` → text + SHA-256. Resolves spans.     | Built, tested           |
| `traceability.py` | §7.1 enforcement. Untraceable output is a **build error**, exit 2. | Built, tested           |
| `retrieval.py`    | §7.3 arms: BM25, hashing vector, AI stub.                          | Two arms real, one stub |
| `generation.py`   | §7.1 card generation, §7.2 rewording, and the emission boundary.   | Generators **NOT RUN**  |

Tests and reports live in `../evals/`. Run `python3 ../evals/run_evals.py`.

## Registering sources

`SourceStore.from_directory()` registers every `*.txt` in a directory, keyed by
filename stem, computing the checksums itself. It is deliberately schema-free so
it does not couple to how the licence-vetting task writes its provenance
records. `evals/test_traceability.py::RealSourceDocuments` uses it to check
spans against the documents in `speedrun-analysis/sources/` — including an
off-by-one span, the failure mode that still looks well-formed at scale. That
class skips loudly if the directory is empty rather than failing.

Nothing in this package registers a source by default, and an empty registry
makes every generation attempt fail loudly. That is the correct behaviour: a
placeholder corpus would make it fail quietly, and later.

## The failure ladder

Generation fails in a defined order, and never returns a card at any rung:

| Condition                              | Raises                |
| -------------------------------------- | --------------------- |
| AI flag off                            | `AiDisabled`          |
| Flag on, no API key                    | `AiNotConfigured`     |
| Flag on, key set, no registered source | `AiNotConfigured`     |
| Everything present                     | `NotImplementedError` |

Turning the flag on does not make AI work; it only moves which exception you
get. The API key's **presence** is checked and its value is never read, printed,
logged, or included in an exception message.

## The emission boundary

`emit_notes()` is the only sanctioned way a generated note leaves this package,
and it routes every note through `traceability.enforce()` first. That placement
is what makes traceability a build error rather than a lint: there is no path
from a generator to a written note that skips the check, whatever the generator
later becomes. `evals/test_traceability.py` proves it by trying — the emission of
a span-less note ends the process with exit 2.
