# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""The AI feature flag (BUILD-DOC 7.6).

One switch, read from the environment, consulted by every AI entry point.

    SPEEDRUN_AI=1    AI paths may run
    unset / anything else   AI paths refuse

**The default is OFF, deliberately.** `speedrun-analysis/evals/ai_card_cutoff.json`
pre-registers the acceptance cutoff and states that the feature is not shipped
enabled by default unless the eval passes. That eval has not been run -- no
source document and no generated cards exist yet -- so the honest default is
the one that cannot produce an unevaluated card.

Turning the flag on does not make AI work. It only moves the failure from
`AiDisabled` to `AiNotConfigured`, which is the point: neither state ever
returns a fabricated result.
"""

from __future__ import annotations

import os
from typing import Mapping
from typing import Optional

AI_FLAG_ENV = "SPEEDRUN_AI"

#: Values that turn the flag on. Everything else -- including "0", "off",
#: the empty string, and the variable being unset -- leaves it off.
_TRUTHY = frozenset({"1", "true", "t", "yes", "y", "on"})

#: The key generation would need. Presence is checked; the VALUE is never read,
#: logged, echoed, or included in an exception message.
API_KEY_ENV = "ANTHROPIC_API_KEY"


class AiDisabled(RuntimeError):
    """Raised when an AI path is reached while the feature flag is off.

    This is the expected, tested state -- see `evals/test_ai_off.py`. It is an
    exception rather than a silent no-op so that a caller cannot mistake
    "returned nothing because AI is off" for "returned nothing because there
    was nothing to return".
    """


class AiNotConfigured(RuntimeError):
    """Raised when the flag is on but the prerequisites are absent.

    Distinct from `AiDisabled` on purpose: "you turned it on and it still
    cannot run, here is what is missing" is a different fact from "it is off".
    """


def _env(env: Optional[Mapping[str, str]] = None) -> Mapping[str, str]:
    return os.environ if env is None else env


def ai_enabled(env: Optional[Mapping[str, str]] = None) -> bool:
    """True only if the flag is explicitly set to a truthy value."""
    return _env(env).get(AI_FLAG_ENV, "").strip().lower() in _TRUTHY


def api_key_present(env: Optional[Mapping[str, str]] = None) -> bool:
    """Whether an API key is set. Never returns or logs the key itself."""
    return bool(_env(env).get(API_KEY_ENV, "").strip())


def require_ai(what: str, env: Optional[Mapping[str, str]] = None) -> None:
    """Gate an AI path. Raises `AiDisabled` when the flag is off."""
    if not ai_enabled(env):
        raise AiDisabled(
            "{} requires the AI feature flag. It is OFF ({} is unset or not "
            "truthy). With AI off there is no generation and no AI retrieval, "
            "by design (BUILD-DOC 7.6).".format(what, AI_FLAG_ENV)
        )


def require_api_key(what: str, env: Optional[Mapping[str, str]] = None) -> None:
    """Gate on key presence. The key value never appears in the message."""
    if not api_key_present(env):
        raise AiNotConfigured(
            "{} requires {} to be set in the environment. It is not set. "
            "(The value is never read, printed, or logged by this code -- only "
            "its presence is checked.)".format(what, API_KEY_ENV)
        )


def flag_state(env: Optional[Mapping[str, str]] = None) -> str:
    """One line describing the flag state, safe to print anywhere."""
    return "{}={}  api_key_present={}".format(
        AI_FLAG_ENV,
        "ON" if ai_enabled(env) else "OFF",
        api_key_present(env),
    )
