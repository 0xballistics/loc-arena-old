"""The deployment pipeline: a real merge-to-main-to-provision path for the supply-chain scenario.

Agents are treated as NOT sharing a checkout: each edits its own copy of the deploy spec with ordinary code
tools, and the only way to get a teammate's change is to ``checkout`` (pull) the merged spec from the forge
main. A teammate (not the author) performs the gated merge, which the trusted ``DeployPipeline`` lands on the
forge main and records on the sealed side. ``SupplyChainServices`` is the thin per-agent layer that owns the
pipeline tools; file I/O stays with ``CodeServices``, ``open_pr`` with the forge, and the merged main content
lives on the forge.
"""

from __future__ import annotations

from loc_arena.deploy.pipeline import DeployPipeline
from loc_arena.deploy.services import SupplyChainServices
from loc_arena.deploy.spec import DeploySpec, DeploySpecError, parse_deploy_spec

__all__ = [
    "DeployPipeline",
    "DeploySpec",
    "DeploySpecError",
    "SupplyChainServices",
    "parse_deploy_spec",
]
