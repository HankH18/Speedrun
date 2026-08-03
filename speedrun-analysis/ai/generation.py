# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Card generation and item rewording (BUILD-DOC 7.1, 7.2).

**Neither generator has ever run.** Both need a real source document and an API
key; this tree has neither. They therefore raise, in a defined order, with a
message naming what is missing:

    AI flag off  -> AiDisabled
    flag on, no key -> AiNotConfigured
    flag on, key set, no registered source -> AiNotConfigured
    everything present -> NotImplementedError (the request is not written)

At no point does either function return a card. A stub that returns
plausible-looking output is worse than an absent one, so there is none.

What IS built and tested here is the emission boundary, `emit_notes()`. It is
the only sanctioned way a generated note leaves this module, and it routes
every note through `traceability.enforce()` first. That is what makes
traceability a build error rather than a lint (BUILD-DOC 7.1): there is no code
path from a generator to a written note that skips the check, so an untraceable
note cannot come into existence, however the generator is later implemented.
`evals/test_traceability.py` proves it by trying.
"""

from __future__ import annotations

import sys
from typing import Iterable
from typing import List
from typing import Mapping
from typing import Optional
from typing import Sequence
from typing import TextIO

from ai.flags import AiNotConfigured
from ai.flags import require_ai
from ai.flags import require_api_key
from ai.sources import SourceStore
from ai.traceability import GeneratedNote
from ai.traceability import TraceabilityError
from ai.traceability import enforce
from ai.traceability import fail_build

#: Printed by anything that reports on the AI subsystem's readiness.
GENERATION_STATUS = (
    "NOT RUNNABLE. Card generation (BUILD-DOC 7.1) and item rewording (7.2) "
    "require a registered real source document and an API key. This tree has "
    "neither, no card has been generated, and no eval number exists for them."
)


def _require_generation_prerequisites(
    what: str,
    store: SourceStore,
    env: Optional[Mapping[str, str]] = None,
) -> None:
    require_ai(what, env)
    require_api_key(what, env)
    if len(store) == 0:
        raise AiNotConfigured(
            "{} requires at least one registered source document; the source "
            "store is empty. Generating from no source would produce notes "
            "with no resolvable span, which is a build error "
            "(BUILD-DOC 7.1).".format(what)
        )


def generate_cards(
    source_id: str,
    store: SourceStore,
    count: int = 1,
    env: Optional[Mapping[str, str]] = None,
) -> List[GeneratedNote]:
    """Generate cards from one source document. **Never has been run.**

    Raises before any request would be made. See the module docstring for the
    order of the failures.
    """
    _require_generation_prerequisites("card generation", store, env)
    store.get(source_id)  # raises UnknownSource if the citation is unresolvable
    raise NotImplementedError(
        "card generation is not implemented: no request is written, no card "
        "has ever been produced, and no eval number for it exists. The "
        "pre-registered cutoff in speedrun-analysis/evals/ai_card_cutoff.json "
        "is unmeasured against."
    )


def reword_items(
    note: GeneratedNote,
    store: SourceStore,
    variants: int = 2,
    env: Optional[Mapping[str, str]] = None,
) -> List[str]:
    """Two reworded exam-style items per card (BUILD-DOC 7.2). **Never run.**

    Feeds the paraphrase test (BUILD-DOC 11, test 4), which reports the gap
    between card recall and rewording accuracy. There is no gap to report,
    because no rewording has been produced.
    """
    _require_generation_prerequisites("item rewording", store, env)
    raise NotImplementedError(
        "item rewording is not implemented; the paraphrase test has no inputs "
        "and its gap is UNMEASURED, not zero."
    )


def emit_notes(
    notes: Iterable[GeneratedNote],
    store: SourceStore,
    stream: Optional[TextIO] = None,
) -> List[GeneratedNote]:
    """The only sanctioned exit from generation. Enforces traceability first.

    On any violation this prints the build-error banner and exits the process
    with code 2. It does not return a partial list, does not drop the offending
    notes and continue, and has no parameter that would let it.
    """
    try:
        return enforce(notes, store)
    except TraceabilityError as exc:
        fail_build(exc.violations, stream or sys.stderr)


def readiness_report(
    store: SourceStore, env: Optional[Mapping[str, str]] = None
) -> Sequence[str]:
    """Human-readable statement of what the AI subsystem can and cannot do."""
    from ai.flags import flag_state

    return (
        "AI subsystem status",
        "  flag:              {}".format(flag_state(env)),
        "  registered sources: {} ({})".format(
            len(store), ", ".join(store.ids()) or "none"
        ),
        "  generation:        {}".format(GENERATION_STATUS),
        "  emission boundary: BUILT and TESTED -- traceability is enforced at "
        "emit_notes() and fails the process with exit 2.",
    )
