// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

//! Speedrun's prediction layer.
//!
//! Everything in this module is **read-only**: it issues no writes of its own,
//! produces no `OpChanges`, and records no undo entry, which is what makes the
//! required "undo still works and the collection does not corrupt" proof
//! demonstrable rather than perilous.
//!
//! One caveat, stated rather than glossed, because "read-only" is otherwise
//! stronger than the truth: the first call on a collection that has never been
//! scheduled will persist Anki's `rollover` and `localOffset` config keys, via
//! `Collection::timing_today`. Those are upstream's one-time backfill, written
//! outside any transaction and so carrying no undo entry. See
//! `mastery::test::topic_mastery_itself_triggers_the_backfill_on_a_cold_collection`.

mod bench;
pub mod mastery;
