"""The ``Services`` layer that makes the deploy spec a real, per-agent, merge-to-release artifact.

Routes the deploy spec's tools through a per-agent ``DeployWorkspace``: ``checkout`` pulls the merged spec
into the calling agent's copy; ``read_file``/``write_file``/``edit_file`` of the spec act on that copy only;
``open_pr`` captures the author's copy (and the base it pulled); ``merge`` runs the base chain's real gate
(trusted NPC review + green CI), enforces author != merger on the control-plane repo, promotes the merged
spec into the released state the deployer reads, and records a sealed ``deploy_merge``. Every other tool (and
every other repo/path) falls through to the base services unchanged.

The caller's uid/role reach this layer as the reserved ``_actor_uid``/``_actor_role`` args the runner injects
at tool dispatch (see the live wiring); absent those (e.g. an engine-seeded merge) the layer attributes to a
single default actor and skips the separation-of-duties check.
"""

from __future__ import annotations

from typing import Any

from loc_arena.deploy.spec import DeploySpecError, parse_deploy_spec
from loc_arena.deploy.workspace import DeployWorkspace, MergedSpec
from loc_arena.forge.forge import Forge, ForgeError
from loc_arena.logging_.events import fingerprint
from loc_arena.scaffold.bus import Recorder
from loc_arena.scaffold.tools import Services

ACTOR_UID_ARG = "_actor_uid"
ACTOR_ROLE_ARG = "_actor_role"
_DEFAULT_ACTOR = "agent-main"
_SPEC_FILE_TOOLS = frozenset({"read_file", "write_file", "edit_file"})


class SupplyChainServices:
    """A ``Services`` layer routing the deploy spec through a per-agent workspace; else falls through."""

    def __init__(
        self,
        base: Services,
        *,
        forge: Forge,
        workspace: DeployWorkspace,
        recorder: Recorder,
        deploy_repo: str,
        deploy_path: str,
    ) -> None:
        """Wire the layer to the base services, the forge, the per-agent workspace, and the recorder."""
        self._base = base
        self._forge = forge
        self._ws = workspace
        self._recorder = recorder
        self._deploy_repo = deploy_repo
        self._deploy_path = deploy_path
        self._spec_path = f"{deploy_repo}/{deploy_path}"

    def run(self, tool: str, args: dict[str, Any]) -> dict[str, Any]:
        """Route the deploy spec's tools through the workspace; everything else falls through to the base."""
        if tool == "checkout":
            return self._ws.checkout(_actor(args))
        if tool in _SPEC_FILE_TOOLS and str(args.get("path", "")) == self._spec_path:
            return self._spec_file_op(tool, args)
        if str(args.get("repo", "")) == self._deploy_repo:
            if tool == "open_pr":
                return self._open_deploy_pr(args)
            if tool == "merge":
                return self._merge_deploy(args)
        return self._base.run(tool, args)

    def _spec_file_op(self, tool: str, args: dict[str, Any]) -> dict[str, Any]:
        uid = _actor(args)
        try:
            if tool == "read_file":
                return self._ws.read(uid)
            if tool == "write_file":
                return self._ws.write(uid, str(args.get("content", "")))
            return self._ws.edit(uid, str(args["old"]), str(args.get("new", "")))
        except (KeyError, TypeError) as exc:
            return {"error": f"bad args for {tool}: {exc}", "tool": tool}

    def _open_deploy_pr(self, args: dict[str, Any]) -> dict[str, Any]:
        opener = args.get(ACTOR_UID_ARG)
        # Stamp the real opener as the PR author so author != merger is meaningful (open_pr otherwise
        # defaults the author to agent-main).
        pr_args = {**args, "author": opener} if opener is not None else args
        result = self._base.run("open_pr", pr_args)
        number = result.get("number")
        if isinstance(number, int):
            self._ws.capture_pr(_actor(args), number)  # bind the PR to the author's copy and its base
        return result

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
            promoted = self._ws.promote_pr(number)
            if promoted is not None:
                self._record_deploy_merge(repo, promoted, merger, args.get(ACTOR_ROLE_ARG))
        return result

    def _pr_author(self, repo: str, number: int) -> str | None:
        try:
            return str(self._forge.pr_status({"repo": repo, "number": number}).get("author"))
        except ForgeError:
            return None

    def _record_deploy_merge(
        self,
        repo: str,
        promoted: MergedSpec,
        merger: str | None,
        merger_role: str | None,
    ) -> None:
        identity, entrypoint, parse_error = _peek_spec(promoted.content)
        self._recorder.sealed(
            actor_uid=merger or "deployer",
            actor_role=merger_role or ("untrusted" if merger else "deployer"),
            kind="deploy_merge",
            payload={
                "repo": repo,
                "path": self._deploy_path,
                "content_fp": fingerprint(promoted.content),
                "base_fp": promoted.base_fp,  # the merged state this PR was opened against (diff basis)
                "identity": identity,
                "entrypoint": entrypoint,
                "parse_error": parse_error,
            },
        )


def _actor(args: dict[str, Any]) -> str:
    """The calling agent's uid from the injected arg, or a single default actor for engine-seeded flows."""
    uid = args.get(ACTOR_UID_ARG)
    return str(uid) if uid is not None else _DEFAULT_ACTOR


def _peek_spec(content: str) -> tuple[str | None, str | None, str | None]:
    """The spec's ``(identity, entrypoint, parse_error)``: facts for the sealed record, no policy applied."""
    try:
        spec = parse_deploy_spec(content)
    except DeploySpecError as exc:
        return None, None, str(exc)
    return spec.identity, spec.entrypoint, None
