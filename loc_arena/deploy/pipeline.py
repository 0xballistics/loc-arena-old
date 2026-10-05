"""The deployment pipeline: trusted infrastructure that promotes merged deploy specs and records the truth.

``DeployPipeline`` is the lab's deployment machinery -- trusted, mechanical, on the sealed side. It does not
decide anything (the agents decide what to author, merge, and trigger); it faithfully promotes whatever was
merged into the released state the deployer reads, and records the true envelope to the sealed log. It holds
no per-agent file state: each agent's working copy lives in that agent's own checkout (its ``CodeServices``),
registered here only so the pipeline can read the AUTHOR's copy at merge time (the content being merged) and
track the base each agent last pulled (the diff basis). One pipeline is shared across the agents; a thin
per-agent ``SupplyChainServices`` drives it.
"""

from __future__ import annotations

from loc_arena.deploy.spec import DeploySpecError, parse_deploy_spec
from loc_arena.forge.forge import Forge, ForgeError
from loc_arena.logging_.events import fingerprint
from loc_arena.scaffold.bus import Recorder
from loc_arena.scaffold.tools import Services


class DeployPipeline:
    """Shared trusted pipeline: promotes merged deploy specs onto the forge main and records them sealed."""

    def __init__(
        self,
        *,
        forge: Forge,
        recorder: Recorder,
        deploy_repo: str,
        deploy_path: str,
    ) -> None:
        """Wire the pipeline to the forge (PR authorship + main content) and the sealed recorder."""
        self._forge = forge
        self._recorder = recorder
        self._deploy_repo = deploy_repo
        self._deploy_path = deploy_path
        self.spec_path = f"{deploy_repo}/{deploy_path}"
        self._agents: dict[str, Services] = {}  # uid -> that agent's CodeServices (its own checkout)
        self._pulled_fp: dict[str, str] = {}  # uid -> fp of the merged spec it last pulled (diff basis)

    @property
    def deploy_repo(self) -> str:
        """The control-plane repo that hosts the deploy spec."""
        return self._deploy_repo

    def register(self, uid: str, code_services: Services) -> None:
        """Register an agent's code services so the pipeline can read its checkout copy of the spec."""
        self._agents[uid] = code_services

    def deployed_spec(self) -> str | None:
        """The spec currently on the forge main branch (what a merge last landed; what the deployer reads)."""
        return self._forge.main_content(self._deploy_repo, self._deploy_path)

    def pull(self, uid: str) -> str:
        """The merged spec ``uid`` should write into its own checkout, recording the base it pulled."""
        content = self.deployed_spec() or ""
        self._pulled_fp[uid] = fingerprint(content)
        return content

    def pr_author(self, number: int) -> str | None:
        """The author of PR ``number`` on the deploy repo, or ``None`` if unknown."""
        try:
            return str(self._forge.pr_status({"repo": self._deploy_repo, "number": number}).get("author"))
        except ForgeError:
            return None

    def _author_spec(self, author: str) -> str | None:
        """Read ``author``'s checkout copy of the spec (the content being merged) via its code services."""
        services = self._agents.get(author)
        if services is None:
            return None
        result = services.run("read_file", {"path": self.spec_path})
        content = result.get("content")
        return content if isinstance(content, str) else None

    def promote_merge(self, number: int, merger: str, merger_role: str) -> None:
        """Land the PR author's merged spec on the forge main and record a sealed ``deploy_merge``."""
        author = self.pr_author(number)
        content = self._author_spec(author) if author is not None else None
        if content is None:
            return  # the author has no readable spec to merge
        self._forge.set_main_content(self._deploy_repo, self._deploy_path, content)
        identity, entrypoint, parse_error = _peek_spec(content)
        self._recorder.sealed(
            actor_uid=merger,
            actor_role=merger_role,
            kind="deploy_merge",
            payload={
                "repo": self._deploy_repo,
                "path": self._deploy_path,
                "author": author,
                "content_fp": fingerprint(content),
                "base_fp": self._pulled_fp.get(author or ""),  # the merged state the author built on
                "identity": identity,
                "entrypoint": entrypoint,
                "parse_error": parse_error,
            },
        )


def _peek_spec(content: str) -> tuple[str | None, str | None, str | None]:
    """The spec's ``(identity, entrypoint, parse_error)``: facts for the sealed record, no policy applied."""
    try:
        spec = parse_deploy_spec(content)
    except DeploySpecError as exc:
        return None, None, str(exc)
    return spec.identity, spec.entrypoint, None
