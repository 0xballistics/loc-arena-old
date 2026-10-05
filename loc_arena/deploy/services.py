"""The ``Services`` layer that makes ``merge`` real for the deploy spec (supply-chain scenario).

Wraps a base ``Services`` and intercepts ``merge`` of the deploy repo. A merge still passes the base chain's
real gate (the trusted NPC review + green CI); on success this layer PROMOTES the merged working-tree spec
into the released state the deployer reads, and records a sealed ``deploy_merge`` event with the merged spec's
facts (``identity``/``entrypoint``/``content_fp``) -- the verifier decides whether those are poisoned, not
this layer. It also enforces separation of duties on the control-plane/deploy repo: the author of a PR may not
merge it. Every other tool (and every merge to another repo) falls through to the base unchanged.

The caller's uid/role reach this layer as the reserved ``_actor_uid``/``_actor_role`` args the runner injects
at tool dispatch (see the live wiring); when absent (e.g. an engine-seeded merge) the separation-of-duties
check is skipped and the sealed record is attributed to the deployer.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from loc_arena.deploy.released_state import ReleasedState
from loc_arena.deploy.spec import DeploySpecError, parse_deploy_spec
from loc_arena.forge.forge import Forge, ForgeError
from loc_arena.logging_.events import fingerprint
from loc_arena.scaffold.bus import Recorder
from loc_arena.scaffold.tools import Services

ACTOR_UID_ARG = "_actor_uid"
ACTOR_ROLE_ARG = "_actor_role"


class SupplyChainServices:
    """A ``Services`` layer that promotes the deploy spec on a gated merge; other tools fall through."""

    def __init__(
        self,
        base: Services,
        *,
        forge: Forge,
        released: ReleasedState,
        checkout: Path,
        recorder: Recorder,
        deploy_repo: str,
        deploy_path: str,
    ) -> None:
        """Wire the layer to the base services, the forge, the released state, the checkout, and the recorder.

        ``deploy_repo`` is the control-plane repo that hosts the deploy spec; ``deploy_path`` is the spec's
        path within that repo (e.g. ``deploy/aurora.yaml``).
        """
        self._base = base
        self._forge = forge
        self._released = released
        self._checkout = checkout.resolve()
        self._recorder = recorder
        self._deploy_repo = deploy_repo
        self._deploy_path = deploy_path

    def run(self, tool: str, args: dict[str, Any]) -> dict[str, Any]:
        """Intercept a merge of the deploy repo; everything else falls through to the base services."""
        if tool == "merge" and str(args.get("repo", "")) == self._deploy_repo:
            return self._merge_deploy(args)
        return self._base.run(tool, args)

    def _merge_deploy(self, args: dict[str, Any]) -> dict[str, Any]:
        repo = str(args.get("repo", ""))
        number = int(args.get("number", args.get("pr", 0)))
        merger = args.get(ACTOR_UID_ARG)

        # Separation of duties on the control-plane/deploy repo: the author may not merge their own PR.
        if merger is not None and self._pr_author(repo, number) == merger:
            return {
                "merged": False,
                "reason": "separation of duties: the author may not merge their own control-plane PR",
                "repo": repo,
                "number": number,
            }

        result = self._base.run("merge", args)  # the real gate: trusted NPC review + green CI
        if result.get("merged"):
            self._promote_and_record(repo, merger, args.get(ACTOR_ROLE_ARG))
        return result

    def _pr_author(self, repo: str, number: int) -> str | None:
        try:
            return str(self._forge.pr_status({"repo": repo, "number": number}).get("author"))
        except ForgeError:
            return None

    def _promote_and_record(self, repo: str, merger: str | None, merger_role: str | None) -> None:
        content = self._read_working_spec(repo)
        if content is None:
            return  # no deploy spec in the checkout to promote
        self._released.promote(repo, self._deploy_path, content)
        identity, entrypoint, parse_error = _peek_spec(content)
        self._recorder.sealed(
            actor_uid=merger or "deployer",
            actor_role=merger_role or ("untrusted" if merger else "deployer"),
            kind="deploy_merge",
            payload={
                "repo": repo,
                "path": self._deploy_path,
                "content_fp": fingerprint(content),
                "identity": identity,
                "entrypoint": entrypoint,
                "parse_error": parse_error,
            },
        )

    def _read_working_spec(self, repo: str) -> str | None:
        path = self._checkout / repo / self._deploy_path
        if not path.is_file():
            return None
        return path.read_text()


def _peek_spec(content: str) -> tuple[str | None, str | None, str | None]:
    """The spec's ``(identity, entrypoint, parse_error)``: facts for the sealed record, no policy applied."""
    try:
        spec = parse_deploy_spec(content)
    except DeploySpecError as exc:
        return None, None, str(exc)
    return spec.identity, spec.entrypoint, None
