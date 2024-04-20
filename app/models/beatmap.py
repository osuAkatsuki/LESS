from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from datetime import timedelta
from typing import Any
from typing import Mapping
from typing import Optional

import config
from app.constants.mode import Mode
from app.constants.ranked_status import RankedStatus

ONE_DAY = 86_400


def _should_get_updates(ranked_status: int, last_updated: datetime) -> bool:
    match ranked_status:
        case RankedStatus.QUALIFIED:
            update_interval = timedelta(minutes=5)
        case RankedStatus.PENDING:
            update_interval = timedelta(minutes=10)
        case RankedStatus.LOVED:
            # loved maps can *technically* be updated
            update_interval = timedelta(days=1)
        case RankedStatus.RANKED | RankedStatus.APPROVED:
            # in very rare cases, the osu! team has updated ranked/appvoed maps
            # this is usually done to remove things like inappropriate content
            update_interval = timedelta(days=1)
        case _:
            raise NotImplementedError(f"Unknown ranked status: {ranked_status}")

    return last_updated <= (datetime.now() - update_interval)


@dataclass
class Beatmap:
    md5: str
    id: int
    set_id: int

    song_name: str

    status: RankedStatus

    plays: int
    passes: int
    mode: Mode

    od: float
    ar: float

    difficulty_std: float
    difficulty_taiko: float
    difficulty_ctb: float
    difficulty_mania: float

    hit_length: int

    last_update: int = 0

    max_combo: int = 0
    bpm: int = 0
    filename: str = ""
    frozen: bool = False
    rating: Optional[float] = None

    @property
    def url(self) -> str:
        # i hate this
        server_url = config.SRV_URL.replace("https://", "").replace("http://", "")

        return f"https://osu.{server_url}/beatmaps/{self.id}"

    @property
    def set_url(self) -> str:
        # i hate this
        server_url = config.SRV_URL.replace("https://", "").replace("http://", "")

        return f"https://osu.{server_url}/beatmapsets/{self.set_id}"

    @property
    def embed(self) -> str:
        return f"[{self.url} {self.song_name}]"

    @property
    def gives_pp(self) -> bool:
        return self.status in (RankedStatus.RANKED, RankedStatus.APPROVED)

    @property
    def has_leaderboard(self) -> bool:
        return self.status >= RankedStatus.RANKED

    @property
    def deserves_update(self) -> bool:
        """Checks if there should be an attempt to update a map/check if
        should be updated."""

        return _should_get_updates(
            int(self.status),
            datetime.fromtimestamp(self.last_update),
        )

    def osu_string(self, score_count: int, rating: float) -> str:
        return (
            f"{int(self.status)}|false|{self.id}|{self.set_id}|{score_count}|0|\n"  # |0| = featured artist bs
            f"0\n{self.song_name}\n{rating:.1f}"  # 0 = offset
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "beatmap_md5": self.md5,
            "beatmap_id": self.id,
            "beatmapset_id": self.set_id,
            "song_name": self.song_name,
            "ranked": self.status.value,
            "playcount": self.plays,
            "passcount": self.passes,
            "mode": self.mode.value,
            "od": self.od,
            "ar": self.ar,
            "difficulty_std": self.difficulty_std,
            "difficulty_taiko": self.difficulty_taiko,
            "difficulty_ctb": self.difficulty_ctb,
            "difficulty_mania": self.difficulty_mania,
            "hit_length": self.hit_length,
            "latest_update": self.last_update,
            "max_combo": self.max_combo,
            "bpm": self.bpm,
            "file_name": self.filename,
            "ranked_status_freezed": self.frozen,
            "rating": self.rating,
        }

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, Any]) -> Beatmap:
        return cls(
            md5=mapping["beatmap_md5"],
            id=mapping["beatmap_id"],
            set_id=mapping["beatmapset_id"],
            song_name=mapping["song_name"],
            status=RankedStatus(mapping["ranked"]),
            plays=mapping["playcount"],
            passes=mapping["passcount"],
            mode=Mode(mapping["mode"]),
            od=mapping["od"],
            ar=mapping["ar"],
            difficulty_std=mapping["difficulty_std"],
            difficulty_taiko=mapping["difficulty_taiko"],
            difficulty_ctb=mapping["difficulty_ctb"],
            difficulty_mania=mapping["difficulty_mania"],
            hit_length=mapping["hit_length"],
            last_update=mapping["latest_update"],
            max_combo=mapping["max_combo"],
            bpm=mapping["bpm"],
            filename=mapping["file_name"],
            frozen=mapping["ranked_status_freezed"],
            rating=mapping["rating"],
        )
