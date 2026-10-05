"""The released state: the deployable source of truth the deployer reads.

A ``ReleasedState`` maps ``(repo, path)`` to the released content of a file. The engine seeds it with the
sanctioned baseline at episode start; a gated ``merge`` of the deploy spec promotes the merged working-tree
content into it. The deployer reads ONLY from here, never the working tree -- so a bare ``edit_file`` deploys
nothing and ``merge`` is load-bearing. It holds no sealed state and no oracle value; it is ordinary deployable
state.
"""

from __future__ import annotations


class ReleasedState:
    """The released (merged) content of deployable files, keyed by ``(repo, path)``."""

    def __init__(self, baseline: dict[tuple[str, str], str] | None = None) -> None:
        """Start from a baseline mapping of ``(repo, path) -> content`` (copied, not aliased)."""
        self._store: dict[tuple[str, str], str] = dict(baseline or {})

    def get(self, repo: str, path: str) -> str | None:
        """The released content of ``(repo, path)``, or ``None`` if nothing has been released there."""
        return self._store.get((repo, path))

    def promote(self, repo: str, path: str, content: str) -> None:
        """Release ``content`` as the new deployable state of ``(repo, path)`` (a merge promotes to here)."""
        self._store[(repo, path)] = content
