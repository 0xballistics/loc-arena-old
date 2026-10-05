"""Per-agent working copies of the deploy spec, with checkout / edit / open_pr / merge.

Models the deploy spec the way isolated agents really work it: each agent has its OWN copy, and the only way
to get another agent's merged change is to ``checkout`` (pull) the released/merged spec. An agent that edits
without pulling is working from a stale base, so when its PR merges it overwrites -- a real, intended footgun
that forces pull-before-build. A PR captures the author's copy AND the base it was pulled from, so its change
can be read as a diff against merged main (the basis for "each change looks innocent, combined is poison").

Scenario-local for now; when the isolation stack lands per-agent checkouts + sync, this is backed by those
(the released state becomes merged ``main``, ``checkout`` becomes a real pull, and open_pr a real diff).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from loc_arena.deploy.released_state import ReleasedState
from loc_arena.logging_.events import fingerprint


@dataclass(frozen=True)
class MergedSpec:
    """What a gated merge promoted: the released content and the base the PR was opened against."""

    content: str
    base_fp: str


class DeployWorkspace:
    """Per-agent copies of one deploy spec over a shared released (merged) state."""

    def __init__(self, released: ReleasedState, *, repo: str, path: str, baseline: str) -> None:
        """Wire to the released state and the spec's ``(repo, path)``; ``baseline`` seeds each fresh copy."""
        self._released = released
        self._repo = repo
        self._path = path
        self._baseline = baseline
        self._view: dict[str, str] = {}  # uid -> that agent's current copy of the spec
        self._base_fp: dict[str, str] = {}  # uid -> fp of the content it last started from / pulled
        self._pr: dict[int, MergedSpec] = {}  # pr number -> what it captured at open time

    # -- per-agent copy ----------------------------------------------------------------------------------
    def _ensure(self, uid: str) -> str:
        """The agent's copy, seeded from the baseline the first time it is touched (a fresh checkout)."""
        if uid not in self._view:
            self._view[uid] = self._baseline
            self._base_fp[uid] = fingerprint(self._baseline)
        return self._view[uid]

    def checkout(self, uid: str) -> dict[str, Any]:
        """Pull the latest merged spec into ``uid``'s copy (how one agent gets another's merged change)."""
        content = self._released.get(self._repo, self._path)
        content = content if content is not None else self._baseline
        self._view[uid] = content
        self._base_fp[uid] = fingerprint(content)
        return {"checked_out": True, "path": self._path, "content": content}

    def read(self, uid: str) -> dict[str, Any]:
        """Read ``uid``'s own copy of the spec (not any other agent's, not merged main)."""
        return {"path": self._path, "content": self._ensure(uid)}

    def write(self, uid: str, content: str) -> dict[str, Any]:
        """Overwrite ``uid``'s copy with ``content``."""
        self._ensure(uid)
        self._view[uid] = content
        return {"path": self._path, "bytes_written": len(content.encode())}

    def edit(self, uid: str, old: str, new: str) -> dict[str, Any]:
        """Replace ``old`` with ``new`` in ``uid``'s copy, erroring if ``old`` is absent."""
        current = self._ensure(uid)
        if old not in current:
            return {"error": "old string not found", "path": self._path, "replaced": 0}
        self._view[uid] = current.replace(old, new)
        return {"path": self._path, "replaced": current.count(old)}

    # -- PR lifecycle ------------------------------------------------------------------------------------
    def capture_pr(self, uid: str, number: int) -> None:
        """Bind PR ``number`` to ``uid``'s copy now and the base it was opened against (for a later diff)."""
        self._pr[number] = MergedSpec(self._ensure(uid), self._base_fp.get(uid, fingerprint(self._baseline)))

    def promote_pr(self, number: int) -> MergedSpec | None:
        """Promote PR ``number``'s captured content to the released state; return what was promoted."""
        captured = self._pr.get(number)
        if captured is None:
            return None
        self._released.promote(self._repo, self._path, captured.content)
        return captured

    @property
    def spec_path(self) -> str:
        """The spec's repo-relative path (the file an agent reads/edits)."""
        return self._path
