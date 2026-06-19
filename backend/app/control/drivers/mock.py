"""Mock actuator driver.

Always present so the whole control stack runs offline with zero hardware. It
acks every command immediately and reports the resulting state implied by the
command verb (``open`` -> ``open``, ``on`` -> ``on``, etc.). This is what the
demo, the test-suite, and any environment without a real MQTT relay use.
"""

from __future__ import annotations

from app.control.base import ActuatorDriver, CommandResult
from app.core.logging import get_logger
from app.db.models.common import ActuatorType

logger = get_logger(__name__)

# Maps a command verb to the actuator state it produces. Covers both the
# open/close (vent/valve) and on/off (fan/pump) families.
_COMMAND_TO_STATE: dict[str, str] = {
    "open": "open",
    "close": "closed",
    "on": "on",
    "off": "off",
}


class MockActuatorDriver(ActuatorDriver):
    """In-memory driver: every ``apply`` acks and returns the new state."""

    name = "mock"

    def apply(
        self,
        *,
        actuator_type: ActuatorType,
        target_uid: str,
        command: str,
        params: dict | None = None,
        org_id: str | None = None,
        node_uid: str | None = None,
        command_id: str | None = None,
    ) -> CommandResult:
        verb = command.strip().lower()
        new_state = _COMMAND_TO_STATE.get(verb)
        if new_state is None:
            logger.warning(
                "mock_driver_unknown_command",
                actuator_type=str(actuator_type),
                target_uid=target_uid,
                command=command,
            )
            return CommandResult(
                ok=False,
                acked=False,
                error=f"unknown command: {command!r}",
                raw={"command": command, "params": params or {}},
            )

        logger.info(
            "mock_driver_apply",
            actuator_type=str(actuator_type),
            target_uid=target_uid,
            command=verb,
            new_state=new_state,
        )
        return CommandResult(
            ok=True,
            acked=True,
            new_state=new_state,
            raw={"command": verb, "params": params or {}, "driver": self.name},
        )
