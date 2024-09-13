from __future__ import annotations

from typing import TypedDict

from tenacity import retry
from tenacity import stop_after_attempt
from tenacity import wait_exponential

import app.state
import config
from app.constants.mode import Mode
from app.reliability import retry_if_exception_network_related


class PerformanceScore(TypedDict):
    beatmap_id: int
    beatmap_md5: str
    mode: int
    mods: int
    max_combo: int
    accuracy: float
    miss_count: int


@retry(
    retry=retry_if_exception_network_related(),
    wait=wait_exponential(),
    stop=stop_after_attempt(10),
    reraise=True,
)
async def calculate_performances(
    scores: list[PerformanceScore],
) -> list[tuple[float, float]]:
    response = await app.state.services.http_client.post(
        f"{config.PERFORMANCE_SERVICE_URL}/api/v1/calculate",
        json=scores,
    )
    response.raise_for_status()

    data = response.json()
    return [(result["pp"], result["stars"]) for result in data]


@retry(
    retry=retry_if_exception_network_related(),
    wait=wait_exponential(),
    stop=stop_after_attempt(10),
    reraise=True,
)
async def calculate_performance(
    *,
    beatmap_id: int,
    beatmap_md5: str,
    mode: Mode,
    mods: int,
    max_combo: int,
    accuracy: float,
    miss_count: int,
) -> tuple[float, float]:
    response = await app.state.services.http_client.post(
        f"{config.PERFORMANCE_SERVICE_URL}/api/v1/calculate",
        json=[
            {
                "beatmap_id": beatmap_id,
                "beatmap_md5": beatmap_md5,
                "mode": mode.as_vn,
                "mods": mods,
                "max_combo": max_combo,
                "accuracy": accuracy,
                "miss_count": miss_count,
            },
        ],
    )
    response.raise_for_status()

    data = response.json()[0]
    return data["pp"], data["stars"]
