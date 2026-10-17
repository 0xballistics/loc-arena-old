"""The deploy manifest the trusted deployer reads off the forge main (distinct from the company spec).

A manifest declares the desired deployments: each a ``name``, an ``entrypoint`` (a registered runnable), an
``identity`` (the service account it runs as), a ``revision`` (bumping it forces a restart), and ``replicas``.
This is the TRUSTED engine parser -- named ``DeployManifest`` deliberately, never the company
``DeploymentSpec`` (which is tamperable scenery). It holds no policy: whether a deployment is sanctioned is
decided by ``DeploymentPolicy``, not here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import yaml


class DeployManifestError(ValueError):
    """A manifest is not a mapping, or a deployment is missing/ill-typed a required field."""


@dataclass(frozen=True)
class Deployment:
    """One desired deployment entry."""

    name: str
    entrypoint: str
    identity: str
    revision: int
    replicas: int = 1


@dataclass(frozen=True)
class DeployManifest:
    """The desired deployments a manifest declares, in file order."""

    deployments: tuple[Deployment, ...]


def parse_manifest(text: str) -> DeployManifest:
    """Parse a deploy manifest from YAML, raising ``DeployManifestError`` on a missing/ill-typed field."""
    try:
        data: Any = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise DeployManifestError(f"manifest is not valid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise DeployManifestError("manifest must be a mapping")
    raw = data.get("deployments")
    if not isinstance(raw, list) or not raw:
        raise DeployManifestError("manifest 'deployments' must be a non-empty list")
    return DeployManifest(deployments=tuple(_deployment(entry) for entry in raw))


def _deployment(entry: Any) -> Deployment:
    if not isinstance(entry, dict):
        raise DeployManifestError("each deployment must be a mapping")

    def required_str(key: str) -> str:
        value = entry.get(key)
        if not isinstance(value, str) or not value:
            raise DeployManifestError(f"deployment field {key!r} must be a non-empty string")
        return value

    revision = entry.get("revision", 1)
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
        raise DeployManifestError("deployment 'revision' must be an integer >= 1")
    replicas = entry.get("replicas", 1)
    if not isinstance(replicas, int) or isinstance(replicas, bool) or replicas < 1:
        raise DeployManifestError("deployment 'replicas' must be an integer >= 1")
    return Deployment(
        name=required_str("name"),
        entrypoint=required_str("entrypoint"),
        identity=required_str("identity"),
        revision=revision,
        replicas=replicas,
    )
