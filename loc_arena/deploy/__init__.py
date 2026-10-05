"""The deployment pipeline: a real merge-to-release-to-provision path for the supply-chain scenario.

Agents are treated as NOT sharing a checkout: each edits its own copy of the deploy spec with ordinary code
tools, and the only way to get a teammate's change is to ``checkout`` (pull) the merged spec. A teammate
(not the author) performs the gated merge, which the trusted ``DeployPipeline`` promotes into a released state
the deployer reads, recording the true envelope on the sealed side. ``SupplyChainServices`` is the thin
per-agent layer that owns the pipeline tools; file I/O stays with ``CodeServices`` and ``open_pr`` with the
forge.
"""

from __future__ import annotations

from loc_arena.deploy.pipeline import DeployPipeline
from loc_arena.deploy.released_state import ReleasedState
from loc_arena.deploy.services import SupplyChainServices
from loc_arena.deploy.spec import DeploySpec, DeploySpecError, parse_deploy_spec

__all__ = [
    "DeployPipeline",
    "DeploySpec",
    "DeploySpecError",
    "ReleasedState",
    "SupplyChainServices",
    "parse_deploy_spec",
]
