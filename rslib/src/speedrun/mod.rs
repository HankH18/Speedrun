// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

//! Speedrun's prediction layer.
//!
//! Everything in this module is **read-only**. Nothing here writes to the
//! collection, produces `OpChanges`, or records an undo entry, which is what
//! makes the required "undo still works and the collection does not corrupt"
//! proof demonstrable rather than perilous.

pub mod mastery;
