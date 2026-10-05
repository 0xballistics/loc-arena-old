"""The deployment pipeline: a real merge-to-release-to-provision path for the supply-chain scenario.

The agent authors a deploy spec in the checkout and merges it (separation of duties: a teammate, not the
author, performs the gated merge). The merge PROMOTES the merged spec into a released state the deployer
reads -- so a bare ``edit_file`` deploys nothing; only a merge lands the change. The deployer (later
increment) reads the released spec and provisions a worker, recording the true deploy envelope on the sealed
side.
"""

from __future__ import annotations

from loc_arena.deploy.released_state import ReleasedState
from loc_arena.deploy.spec import DeploySpec, DeploySpecError, parse_deploy_spec

__all__ = ["DeploySpec", "DeploySpecError", "ReleasedState", "parse_deploy_spec"]
