# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Speedrun's AI subsystem (BUILD-DOC 7).

Standard library only. Nothing in this package calls a network service; the
modules that WOULD call one (``generation``) refuse to run and say why, rather
than returning a plausible-looking placeholder.

Import from a script by putting ``speedrun-analysis/`` on ``sys.path``::

    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from ai import traceability
"""
