"""
Mock data that mirrors the real MOSAIC responses.
Used when MOCK_MODE=true for offline development.
"""

import random
import time
from datetime import datetime, timezone


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _cpu() -> float:
    return round(random.uniform(20, 92), 1)


def _mem_used() -> int:
    return random.randint(1_000_000_000, 6_000_000_000)


# ── Orchestrator endpoints ────────────────────────────────────────────────────

MOCK_STATUS = {
    "nodes": {
        "fog1": {
            "online": True,
            "host": "192.168.1.10",
            "runtime_port": 7000,
            "active_steps": 2,
            "queued_steps": 1,
        },
        "fog2": {
            "online": True,
            "host": "192.168.1.11",
            "runtime_port": 7001,
            "active_steps": 0,
            "queued_steps": 0,
        },
        "server": {
            "online": True,
            "host": "192.168.1.12",
            "runtime_port": 7002,
            "active_steps": 1,
            "queued_steps": 3,
        },
    },
    "total_nodes": 3,
    "online_nodes": 3,
    "total_active": 3,
    "total_queued": 4,
}


def mock_metrics() -> dict:
    return {
        "fog1": {
            "cpu_pct": _cpu(),
            "cpu_states": {"user": 45.2, "system": 12.1, "idle": 42.7},
            "mem_used": _mem_used(),
            "mem_free": 2_000_000_000,
            "mem_total": 8_000_000_000,
        },
        "fog2": {
            "cpu_pct": _cpu(),
            "cpu_states": {"user": 22.1, "system": 8.3, "idle": 69.6},
            "mem_used": _mem_used(),
            "mem_free": 4_000_000_000,
            "mem_total": 8_000_000_000,
        },
        "server": {
            "cpu_pct": _cpu(),
            "cpu_states": {"user": 55.0, "system": 15.0, "idle": 30.0},
            "mem_used": _mem_used(),
            "mem_free": 8_000_000_000,
            "mem_total": 16_000_000_000,
        },
    }


MOCK_NODES_CONFIG = {
    "service_name": "mosaic-runtime.service",
    "nodes": {
        "fog1": {
            "host": "192.168.1.10",
            "ssh_port": 22,
            "ssh_user": "pi",
            "runtime_port": 7000,
            "listen_host": "0.0.0.0",
            "listen_port": 7000,
            "step_timeout": 60,
            "runtime_dir": "/home/pi/mosaic",
        },
        "fog2": {
            "host": "192.168.1.11",
            "ssh_port": 22,
            "ssh_user": "pi",
            "runtime_port": 7001,
            "listen_host": "0.0.0.0",
            "listen_port": 7001,
            "step_timeout": 60,
            "runtime_dir": "/home/pi/mosaic",
        },
        "server": {
            "host": "192.168.1.12",
            "ssh_port": 22,
            "ssh_user": "admin",
            "runtime_port": 7002,
            "listen_host": "0.0.0.0",
            "listen_port": 7002,
            "step_timeout": 120,
            "runtime_dir": "/home/admin/mosaic",
        },
    },
    "service_catalogs": {
        "fog1": {
            "inference_svc": {"mode": "docker", "image": "inference:latest"},
            "preprocess_svc": {"mode": "docker", "image": "preprocess:latest"},
        },
        "fog2": {
            "inference_svc": {"mode": "docker", "image": "inference:latest"},
        },
        "server": {
            "inference_svc": {"mode": "docker", "image": "inference:latest"},
            "aggregator_svc": {"mode": "docker", "image": "aggregator:latest"},
        },
    },
}

MOCK_APPLICATIONS = {
    "applications": {
        "inference_pipeline": {
            "steps": [
                {
                    "counter": 0,
                    "node_id": "fog1",
                    "is_traffic_generator": True,
                    "forward_to": [{"node_id": "fog1"}],
                },
                {
                    "counter": 1,
                    "node_id": "fog1",
                    "service_ref": "preprocess_svc",
                    "forward_to": [{"node_id": "fog1"}],
                },
                {
                    "counter": 2,
                    "node_id": "fog1",
                    "service_ref": "inference_svc",
                    "forward_to": [{"node_id": "server"}],
                },
                {
                    "counter": 3,
                    "node_id": "server",
                    "service_ref": "aggregator_svc",
                    "forward_to": [],
                },
            ]
        }
    }
}


def mock_jobs(label: str = "inference_pipeline") -> list[dict]:
    return [
        {
            "label": label,
            "job_id": f"job-{label}-001-00{i}",
            "status": random.choice(["done", "done", "done", "running", "queued"]),
            "created_at": _ts(),
            "steps_total": 4,
            "steps_done": random.randint(1, 4),
        }
        for i in range(1, 8)
    ]


def mock_job_detail(label: str, job_id: str) -> dict:
    return {
        "label": label,
        "job_id": job_id,
        "status": "done",
        "created_at": _ts(),
        "lifetime_ms": random.randint(800, 5000),
        "steps": [
            {
                "counter": i,
                "node_id": ["fog1", "fog1", "fog1", "server"][i],
                "service_ref": [None, "preprocess_svc", "inference_svc", "aggregator_svc"][i],
                "status": "done",
                "queue_ms": random.randint(5, 200),
                "exec_ms": random.randint(100, 2000),
                "transmission_ms": random.randint(1, 50),
                "overhead_ms": random.randint(1, 20),
            }
            for i in range(4)
        ],
        "output": {"result": "mock_inference_result", "confidence": 0.92},
    }


# ── Runtime endpoints ─────────────────────────────────────────────────────────

def mock_runtime_health() -> dict:
    return {"ok": True}


def mock_runtime_status(node_id: str) -> dict:
    return {
        "node_id": node_id,
        "active_step": {
            "label": "inference_pipeline",
            "job_id": "job-inference_pipeline-001-001",
            "counter": 2,
            "service": "inference_svc",
            "started_at": _ts(),
        },
        "queue_depth": random.randint(0, 5),
        "queue": [],
    }


def mock_node_info(node_id: str) -> dict:
    return {
        "node_id": node_id,
        "host": "192.168.1.10",
        "port": 7000,
        "service_catalog": {
            "inference_svc": {"mode": "docker", "image": "inference:latest"},
            "preprocess_svc": {"mode": "docker", "image": "preprocess:latest"},
        },
        "capabilities": {
            "docker": True,
            "gpu": node_id == "server",
            "cpu_cores": 4 if "fog" in node_id else 16,
            "ram_gb": 8 if "fog" in node_id else 32,
        },
    }


def mock_runtime_metrics(node_id: str) -> dict:
    used = _mem_used()
    total = 8_000_000_000
    return {
        "cpu_pct": _cpu(),
        "cpu_states": {"user": 40.0, "system": 10.0, "idle": 50.0},
        "mem_used": used,
        "mem_free": total - used,
        "mem_total": total,
    }


def mock_tg_status(label: str | None = None) -> dict:
    return {
        "label": label,
        "status": "running",
        "jobs_sent": random.randint(10, 100),
        "iterations_done": random.randint(5, 50),
        "interval_s": 1.0,
    }


def mock_logs(node_id: str | None = None, lines: int = 50) -> list[dict]:
    events = [
        "step_queued", "step_started", "service_finished",
        "step_done", "forwarding_started", "forwarding_succeeded",
        "output_validated",
    ]
    return [
        {
            "ts": _ts(),
            "level": "info",
            "event": random.choice(events),
            "job_id": f"job-inference_pipeline-001-00{random.randint(1,9)}",
            "details": {"node": node_id, "counter": random.randint(0, 3)},
        }
        for _ in range(min(lines, 50))
    ]
