"""The trusted deployment service: reads the manifest off the forge main and provisions real workers.

The agent edits and merges a deploy manifest (forge main); the trusted ``DeploymentService`` reconciles it --
revision-bump -> (re)start -- provisioning a ``DeployedWorker`` whose runnable is a bare self-feeding loop
(rogue) or a bounded sanctioned job (benign). It resolves ``sanctioned`` from a trusted allow-list +
reviewed-entrypoint set and records the sealed ``deploy`` record with the true envelope. Nothing here is
agent-editable: it lives in ``loc_arena/`` (engine), outside the checkout.
"""

from __future__ import annotations

from loc_arena.deploy.manifest import DeployManifest, DeployManifestError, Deployment, parse_manifest
from loc_arena.deploy.policy import DeploymentPolicy
from loc_arena.deploy.service import DeploymentService
from loc_arena.deploy.worker import DeployedWorker

__all__ = [
    "DeployManifest",
    "DeployManifestError",
    "DeployedWorker",
    "Deployment",
    "DeploymentPolicy",
    "DeploymentService",
    "parse_manifest",
]
