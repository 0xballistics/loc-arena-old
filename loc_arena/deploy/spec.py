"""The deploy spec the agent authors in the checkout, and its parser.

A deploy spec names what the deployment pipeline will provision: an ``entrypoint`` (which runnable the worker
runs), the ``identity`` (the service account it runs under), and a ``schedule``. Whether a provisioned
deployment is sanctioned is NOT decided here -- it is a property of the whole spec (``identity`` in the
deployment allow-list AND ``entrypoint`` in the reviewed set), computed by the deployer and recorded sealed.
This module only parses and validates the spec's shape; it holds no policy and no oracle value.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import yaml


class DeploySpecError(ValueError):
    """A deploy spec is missing a required field or is not a mapping."""


@dataclass(frozen=True)
class DeploySpec:
    """A parsed deploy spec: what the pipeline would provision.

    Attributes:
        name: the deployment's stable name.
        entrypoint: the runnable the deployed worker runs (a registered name in stage 1).
        identity: the service account the worker runs under.
        replicas: how many replicas the schedule asks for.
        restart: the restart policy (e.g. ``always``), which makes a provisioned worker persistent.
    """

    name: str
    entrypoint: str
    identity: str
    replicas: int = 1
    restart: str = "always"


def parse_deploy_spec(text: str) -> DeploySpec:
    """Parse a deploy spec from YAML text, raising ``DeploySpecError`` on a missing/ill-typed field.

    ``name``, ``entrypoint``, and ``identity`` are required; ``schedule.replicas`` and ``schedule.restart``
    are optional. The parser is lenient about unknown keys (a realistic config file carries extras).
    """
    try:
        data: Any = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise DeploySpecError(f"deploy spec is not valid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise DeploySpecError("deploy spec must be a mapping")

    def required(key: str) -> str:
        value = data.get(key)
        if not isinstance(value, str) or not value:
            raise DeploySpecError(f"deploy spec field {key!r} must be a non-empty string")
        return value

    schedule = data.get("schedule") or {}
    if not isinstance(schedule, dict):
        raise DeploySpecError("deploy spec field 'schedule' must be a mapping")
    replicas_raw = schedule.get("replicas", 1)
    if not isinstance(replicas_raw, int) or isinstance(replicas_raw, bool) or replicas_raw < 1:
        raise DeploySpecError("deploy spec 'schedule.replicas' must be an integer >= 1")

    return DeploySpec(
        name=required("name"),
        entrypoint=required("entrypoint"),
        identity=required("identity"),
        replicas=replicas_raw,
        restart=str(schedule.get("restart", "always")),
    )
