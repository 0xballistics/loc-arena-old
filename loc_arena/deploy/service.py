"""The deployment service: the trusted reconciler that deploys whatever is on the forge main.

Reads the manifest off the forge main (desired state), compares it to the running set (actual state), and
converges: a deployment that is new, or whose ``revision`` was bumped, is (re)started; the rest are left. It
enforces a configurable cap on how many deployments are active (default 1). It owns the ``deploy`` trigger (an
agent asks to reconcile now) and the deadline reconcile (a backstop); it does not write any tamperable state:
it reads the forge main and writes only the sealed ``deploy`` record (via the worker).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from loc_arena.deploy.manifest import DeployManifestError, parse_manifest
from loc_arena.deploy.policy import DeploymentPolicy
from loc_arena.deploy.worker import DeployedWorker
from loc_arena.forge.forge import Forge
from loc_arena.gateway.edge import GatewayEdge
from loc_arena.identity import IdentityService
from loc_arena.scaffold.bus import Recorder


class DeploymentService:
    """Trusted reconciler: converges the running deployments to the manifest on the forge main."""

    def __init__(
        self,
        edge: GatewayEdge,
        identity: IdentityService,
        recorder: Recorder,
        set_time: Callable[[float], None],
        *,
        forge: Forge,
        policy: DeploymentPolicy,
        deploy_repo: str,
        deploy_path: str,
        deadline_ts: float,
        loop_len_floor: int,
        cap: int = 1,
    ) -> None:
        """Wire the reconciler to the gateway, identity, recorder, forge, and the sanctioning policy."""
        self._edge = edge
        self._identity = identity
        self._recorder = recorder
        self._set_time = set_time
        self._forge = forge
        self._policy = policy
        self._deploy_repo = deploy_repo
        self._deploy_path = deploy_path
        self._deadline = deadline_ts
        self._loop_len_floor = loop_len_floor
        self._cap = max(1, cap)
        self._running: dict[str, int] = {}  # deployment name -> revision currently running

    def reconcile(self, now: float) -> dict[str, Any]:
        """Converge the running set to the manifest on the forge main; return what was (re)started."""
        content = self._forge.main_content(self._deploy_repo, self._deploy_path)
        if content is None:
            return {"reconciled": False, "reason": "no manifest on main"}
        try:
            manifest = parse_manifest(content)
        except DeployManifestError as exc:
            return {"reconciled": False, "error": str(exc)}

        desired = manifest.deployments[: self._cap]  # the platform runs at most `cap` deployments
        over_cap = [d.name for d in manifest.deployments[self._cap :]]
        started: list[str] = []
        for deployment in desired:
            running_revision = self._running.get(deployment.name)
            if running_revision is not None and deployment.revision <= running_revision:
                continue  # unchanged: no restart without a revision bump
            sanctioned = self._policy.sanctioned(deployment)
            worker = DeployedWorker(
                self._edge,
                self._identity,
                self._recorder,
                self._set_time,
                deployment=deployment,
                sanctioned=sanctioned,
            )
            worker.deploy(now=now, deadline=self._deadline, loop_len_floor=self._loop_len_floor)
            self._running[deployment.name] = deployment.revision
            started.append(deployment.name)
        return {"reconciled": True, "started": started, "cap": self._cap, "over_cap": over_cap}

    def deploy(self, now: float) -> dict[str, Any]:
        """The agent-facing ``deploy`` tool: reconcile the manifest now."""
        return self.reconcile(now)
