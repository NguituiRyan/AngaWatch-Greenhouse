"""Simulator entry point — the publish loop.

Run it as ``python -m simulator.run`` (inside the ``simulator/`` package root,
which the Dockerfile sets up). It reads :class:`~simulator.config.SimulatorConfig`
from the environment and then ticks a set of :class:`~simulator.node.VirtualNode`
objects, applies the selected scenario, and publishes each reading to MQTT.

Time acceleration (``SIM_TIME_ACCEL``) advances the *simulated* clock faster
than wall-clock: at ``time_accel=3600`` one real second is one simulated hour,
so a 10-hour blight window forms in ~10 real seconds. The loop sleeps
``interval_seconds`` of wall-clock between ticks regardless.

Demo / test modes:

* ``--once``      : emit exactly one tick per node and exit.
* ``--count N``   : emit N ticks per node and exit.
* ``--dry-run``   : use the in-memory NullPublisher (never touch the network).
* ``--scenario S``: override ``SIM_SCENARIO``.
* ``--start ISO`` : set the simulated start time (default: now, UTC).
"""

from __future__ import annotations

import argparse
import logging
import time
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from simulator.config import SimulatorConfig
from simulator.node import VirtualNode, local_hour
from simulator.publisher import MqttPublisher, NullPublisher, Publisher
from simulator.scenarios import get_scenario

logger = logging.getLogger("simulator.run")


@dataclass(slots=True)
class Simulation:
    """A ready-to-run simulation: nodes + scenario + clock, no I/O.

    This is the testable core. :meth:`tick` advances the simulated clock by one
    interval and yields ``(topic, reading)`` for each node that emitted (a node
    can emit nothing, e.g. the ``offline`` scenario during its gap).
    """

    config: SimulatorConfig
    nodes: list[VirtualNode]
    sim_time: datetime

    @classmethod
    def from_config(
        cls, config: SimulatorConfig, *, start: datetime | None = None
    ) -> Simulation:
        nodes = [
            VirtualNode(device_id=config.device_uid(i), seed=i)
            for i in range(config.node_count)
        ]
        return cls(config=config, nodes=nodes, sim_time=start or datetime.now(UTC))

    def tick(self) -> list[tuple[str, dict[str, object]]]:
        """Advance the simulated clock one interval; return emitted messages."""
        scenario = get_scenario(self.config.scenario)
        hour = local_hour(self.sim_time)
        out: list[tuple[str, dict[str, object]]] = []
        for node in self.nodes:
            reading = node.baseline(self.sim_time)
            shaped = scenario(reading, hour=hour, node=node)
            if shaped is None:
                continue  # dropped (offline gap)
            topic = self.config.topic(node.device_id)
            out.append((topic, shaped))
        # Advance the *simulated* clock by interval * acceleration.
        sim_step = self.config.interval_seconds * self.config.time_accel
        self.sim_time = self.sim_time + timedelta(seconds=sim_step)
        return out

    def run_ticks(self, count: int) -> Iterator[list[tuple[str, dict[str, object]]]]:
        """Yield the emitted messages for each of ``count`` ticks."""
        for _ in range(count):
            yield self.tick()


def build_publisher(config: SimulatorConfig, *, dry_run: bool) -> Publisher:
    if dry_run:
        return NullPublisher()
    return MqttPublisher(
        config.mqtt_host,
        config.mqtt_port,
        username=config.mqtt_username,
        password=config.mqtt_password,
    )


def _print_message(topic: str, reading: dict[str, object]) -> None:
    """Print a compact human-readable line for what we publish."""
    ts = reading.get("ts")
    ts_str = ts.isoformat() if isinstance(ts, datetime) else str(ts)
    print(
        f"[{ts_str}] {topic} "
        f"air={reading.get('air_temp_c')}C rh={reading.get('rh_pct')}% "
        f"soil={reading.get('soil_moisture_pct')}% leaf={reading.get('leaf_wetness')} "
        f"pher={reading.get('pheromone_count')} flow={reading.get('water_flow_l_per_min')} "
        f"batt={reading.get('battery_v')}V",
        flush=True,
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="simulator.run",
        description="AngaWatch greenhouse device simulator.",
    )
    parser.add_argument("--once", action="store_true", help="emit one tick per node, then exit")
    parser.add_argument(
        "--count", type=int, default=None, metavar="N", help="emit N ticks per node, then exit"
    )
    parser.add_argument(
        "--scenario", default=None, help="override SIM_SCENARIO for this run"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="do not connect to MQTT; print only (uses NullPublisher)",
    )
    parser.add_argument(
        "--start",
        default=None,
        metavar="ISO8601",
        help="simulated start time (UTC). Default: now.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    args = parse_args(argv)
    config = SimulatorConfig.from_env()
    if args.scenario:
        config = config.model_copy(update={"scenario": args.scenario})

    start = None
    if args.start:
        start = datetime.fromisoformat(args.start)
        if start.tzinfo is None:
            start = start.replace(tzinfo=UTC)

    sim = Simulation.from_config(config, start=start)
    publisher = build_publisher(config, dry_run=args.dry_run)

    # Resolve how many ticks to run: --once == 1, --count N, else infinite.
    if args.once:
        total: int | None = 1
    elif args.count is not None:
        total = max(0, args.count)
    else:
        total = None

    logger.info(
        "simulator start: scenario=%s nodes=%d org=%s broker=%s:%s "
        "interval=%.1fs accel=%.1fx ticks=%s",
        config.scenario,
        config.node_count,
        config.org_id,
        config.mqtt_host,
        config.mqtt_port,
        config.interval_seconds,
        config.time_accel,
        "inf" if total is None else total,
    )

    publisher.connect()
    emitted = 0
    try:
        tick_index = 0
        while total is None or tick_index < total:
            for topic, reading in sim.tick():
                publisher.publish(topic, reading)
                _print_message(topic, reading)
                emitted += 1
            tick_index += 1
            # Finite runs publish back-to-back (no sleep) so demos/tests are fast.
            if total is None:
                time.sleep(config.interval_seconds)
    except KeyboardInterrupt:  # pragma: no cover - interactive only
        logger.info("interrupted; shutting down")
    finally:
        publisher.disconnect()

    logger.info("simulator done: %d messages published", emitted)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
