# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Python-side tests for the per-topic mastery query.

These mirror the topology of the Rust fixture in
``rslib/src/speedrun/mastery.rs``: three cards over two topics, one of which
carries both tags. FSRS memory state cannot be set from pylib, so the
assertions here cover the counts and the filter; the means are asserted on the
Rust side where a memory state can be constructed.
"""

# Load-bearing, not cosmetic: without it the generated backend method raises
# AttributeError: module 'anki' has no attribute 'speedrun_pb2'.
import anki.speedrun_pb2  # noqa: F401
from tests.shared import getEmptyCol

# rslib/src/speedrun/mastery.rs — pub const TOPIC_TAG_PREFIX
CARDIO = "speedrun::topic::cardio"
RENAL = "speedrun::topic::renal"


def _add(col, front: str, tags: list[str]) -> None:
    note = col.newNote()
    note["Front"] = front
    note["Back"] = "back"
    for tag in tags:
        note.tags.append(tag)
    col.add_note(note, col.decks.selected())


def _topic(resp, tag: str):
    return next(t for t in resp.topics if t.topic_tag == tag)


def test_empty_collection_returns_no_topics() -> None:
    col = getEmptyCol()
    resp = col._backend.topic_mastery(topic_tags=[], as_of_unix_secs=0)
    assert list(resp.topics) == []
    assert resp.cards_without_memory_state == 0


def test_aggregates_match_the_rust_fixture_topology() -> None:
    col = getEmptyCol()
    _add(col, "a", [CARDIO])
    _add(col, "b", [CARDIO, RENAL])
    _add(col, "c", [RENAL])

    resp = col._backend.topic_mastery(topic_tags=[], as_of_unix_secs=0)

    # Sorted, and only tagged cards appear.
    assert [t.topic_tag for t in resp.topics] == [CARDIO, RENAL]

    # The card carrying both tags is counted under each.
    assert _topic(resp, CARDIO).card_count == 2
    assert _topic(resp, RENAL).card_count == 2
    assert sum(t.card_count for t in resp.topics) == 4, "3 cards, 4 memberships"

    # None have been answered, so none are reviewed or mature, and every
    # distinct card is reported as lacking a memory state exactly once.
    for topic in resp.topics:
        assert topic.reviewed_count == 0
        assert topic.mature_count == 0
        assert topic.review_count == 0
        assert topic.fsrs_item_count == 0
    assert resp.cards_without_memory_state == 3


def test_topic_filter_restricts_results() -> None:
    col = getEmptyCol()
    _add(col, "a", [CARDIO])
    _add(col, "b", [CARDIO, RENAL])

    resp = col._backend.topic_mastery(topic_tags=[RENAL], as_of_unix_secs=0)
    assert [t.topic_tag for t in resp.topics] == [RENAL]
    assert resp.topics[0].card_count == 1

    # An untagged topic yields nothing rather than an error.
    empty = col._backend.topic_mastery(
        topic_tags=["speedrun::topic::nonexistent"], as_of_unix_secs=0
    )
    assert list(empty.topics) == []


def test_untagged_cards_are_ignored() -> None:
    col = getEmptyCol()
    _add(col, "tagged", [CARDIO])
    _add(col, "untagged", [])
    _add(col, "other-tag", ["not-a-speedrun-topic"])

    resp = col._backend.topic_mastery(topic_tags=[], as_of_unix_secs=0)
    assert [t.topic_tag for t in resp.topics] == [CARDIO]
    assert _topic(resp, CARDIO).card_count == 1
    assert resp.cards_without_memory_state == 1, "only the tagged card counts"
