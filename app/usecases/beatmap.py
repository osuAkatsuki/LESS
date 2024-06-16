from __future__ import annotations

import logging
import random
import time
from typing import Any

import app.state
import config
from app.constants.mode import Mode
from app.constants.ranked_status import RankedStatus
from app.models.beatmap import Beatmap


GET_BEATMAP_URL = "https://old.ppy.sh/api/get_beatmaps"


async def update_beatmap(beatmap: Beatmap) -> Beatmap | None:
    if not beatmap.deserves_update:
        return beatmap

    new_beatmap = await id_from_api(beatmap.id)
    if new_beatmap is None:
        # it's now unsubmitted!

        await app.state.services.database.execute(
            "DELETE FROM beatmaps WHERE beatmap_md5 = :old_md5",
            {"old_md5": beatmap.md5},
        )

        return None

    # handle deleting the old beatmap etc.
    if new_beatmap.md5 != beatmap.md5:
        # delete any instances of the old map
        await app.state.services.database.execute(
            "DELETE FROM beatmaps WHERE beatmap_md5 = :old_md5",
            {"old_md5": beatmap.md5},
        )
    else:
        # the map may have changed in some ways (e.g. ranked status),
        # but we want to make sure to keep our stats, because the map
        # is the same from the player's pov (hit objects, ar/od, etc.)
        new_beatmap.plays = beatmap.plays
        new_beatmap.passes = beatmap.passes
        new_beatmap.rating = beatmap.rating
        new_beatmap.rankedby = beatmap.rankedby

    if beatmap.frozen:
        # if the previous version is status frozen
        # we should force the old status on the new version
        new_beatmap.status = beatmap.status
        new_beatmap.frozen = True
        new_beatmap.rankedby = beatmap.rankedby
    elif beatmap.status != new_beatmap.status:
        if new_beatmap.status is RankedStatus.PENDING and beatmap.status in {
            RankedStatus.RANKED,
            RankedStatus.APPROVED,
            RankedStatus.LOVED,
        }:
            app.usecases.discord.beatmap_status_change(
                old_beatmap=beatmap,
                new_beatmap=new_beatmap,
                action_taken="frozen",
            )
            new_beatmap.status = beatmap.status
            new_beatmap.frozen = True
        else:
            app.usecases.discord.beatmap_status_change(
                old_beatmap=beatmap,
                new_beatmap=new_beatmap,
                action_taken="status_change",
            )

    new_beatmap.last_update = int(time.time())

    await save(new_beatmap)
    return new_beatmap


async def fetch_by_md5(md5: str) -> Beatmap | None:
    if beatmap := await md5_from_database(md5):
        return beatmap

    if beatmap := await md5_from_api(
        md5,
        is_definitely_new_beatmap=True,
    ):
        return beatmap

    return None


async def fetch_by_id(id: int) -> Beatmap | None:
    if beatmap := await id_from_database(id):
        return beatmap

    if beatmap := await id_from_api(
        id,
        is_definitely_new_beatmap=True,
    ):
        return beatmap

    return None


async def md5_from_database(md5: str) -> Beatmap | None:
    db_result = await app.state.services.database.fetch_one(
        "SELECT * FROM beatmaps WHERE beatmap_md5 = :md5",
        {"md5": md5},
    )

    if not db_result:
        return None

    return Beatmap.from_mapping(db_result)


async def id_from_database(id: int) -> Beatmap | None:
    db_result = await app.state.services.database.fetch_one(
        "SELECT * FROM beatmaps WHERE beatmap_id = :id",
        {"id": id},
    )

    if not db_result:
        return None

    return Beatmap.from_mapping(db_result)


async def save(beatmap: Beatmap) -> None:
    await app.state.services.database.execute(
        (
            """
            REPLACE INTO beatmaps (
                beatmap_id, beatmapset_id, beatmap_md5, song_name, ar, od, mode,
                rating, max_combo, hit_length, bpm, playcount, passcount, ranked,
                latest_update, ranked_status_freezed, file_name, rankedby,
                bancho_ranked_status, count_circles, count_sliders, count_spinners
            ) VALUES (
                :beatmap_id, :beatmapset_id, :beatmap_md5, :song_name, :ar, :od, :mode,
                :rating, :max_combo, :hit_length, :bpm, :playcount, :passcount, :ranked,
                :latest_update, :ranked_status_freezed, :file_name, :rankedby,
                :bancho_ranked_status, :count_circles, :count_sliders, :count_spinners
            )
            """
        ),
        {
            "beatmap_id": beatmap.id,
            "beatmapset_id": beatmap.set_id,
            "beatmap_md5": beatmap.md5,
            "song_name": beatmap.song_name,
            "ar": beatmap.ar,
            "od": beatmap.od,
            "mode": beatmap.mode.value,
            "rating": beatmap.rating,
            "max_combo": beatmap.max_combo,
            "hit_length": beatmap.hit_length,
            "bpm": beatmap.bpm,
            "playcount": beatmap.plays,
            "passcount": beatmap.passes,
            "ranked": beatmap.status.value,
            "latest_update": beatmap.last_update,
            "ranked_status_freezed": beatmap.frozen,
            "file_name": beatmap.filename,
            "rankedby": beatmap.rankedby,
            "bancho_ranked_status": (
                beatmap.bancho_ranked_status.value
                if beatmap.bancho_ranked_status is not None
                else None
            ),
            "count_circles": beatmap.count_circles,
            "count_sliders": beatmap.count_sliders,
            "count_spinners": beatmap.count_spinners,
        },
    )


async def md5_from_api(
    md5: str,
    *,
    is_definitely_new_beatmap: bool = False,
) -> Beatmap | None:
    api_key = random.choice(config.API_KEYS_POOL)

    response = await app.state.services.http_client.get(
        GET_BEATMAP_URL,
        params={"k": api_key, "h": md5},
    )
    if response.status_code == 404:
        return None

    if response.status_code == 403:
        raise ValueError("osu api is down") from None

    response.raise_for_status()

    response_json = response.json()
    if not response_json:
        return None

    beatmaps = parse_from_osu_api(response_json)

    if is_definitely_new_beatmap:
        for beatmap in beatmaps:
            await save(beatmap)

    for beatmap in beatmaps:
        if beatmap.md5 == md5:
            return beatmap

    return None


async def id_from_api(
    id: int,
    *,
    is_definitely_new_beatmap: bool = False,
) -> Beatmap | None:
    api_key = random.choice(config.API_KEYS_POOL)

    response = await app.state.services.http_client.get(
        GET_BEATMAP_URL,
        params={"k": api_key, "b": id},
    )
    if response.status_code == 404:
        return None

    if response.status_code == 403:
        raise ValueError("osu api is down") from None

    response.raise_for_status()

    response_json = response.json()
    if not response_json:
        return None

    beatmaps = parse_from_osu_api(response_json)

    if is_definitely_new_beatmap:
        for beatmap in beatmaps:
            await save(beatmap)

    for beatmap in beatmaps:
        if beatmap.id == id:
            return beatmap

    return None


async def set_from_api(
    id: int,
    is_definitely_new_beatmapset: bool = True,
) -> list[Beatmap] | None:
    api_key = random.choice(config.API_KEYS_POOL)

    response = await app.state.services.http_client.get(
        GET_BEATMAP_URL,
        params={"k": api_key, "s": id},
    )
    if response.status_code == 404:
        return None

    if response.status_code == 403:
        raise ValueError("osu api is down") from None

    response.raise_for_status()

    response_json = response.json()
    if not response_json:
        return None

    beatmaps = parse_from_osu_api(response_json)

    if is_definitely_new_beatmapset:
        for beatmap in beatmaps:
            await save(beatmap)

    return beatmaps


IGNORED_BEATMAP_CHARS = dict.fromkeys(map(ord, r':\/*<>?"|'), None)

FROZEN_STATUSES = (RankedStatus.RANKED, RankedStatus.APPROVED, RankedStatus.LOVED)


def parse_from_osu_api(response_json_list: list[dict[str, Any]]) -> list[Beatmap]:
    maps: list[Beatmap] = []

    for response_json in response_json_list:
        md5 = response_json["file_md5"]
        id = int(response_json["beatmap_id"])
        set_id = int(response_json["beatmapset_id"])

        filename = (
            ("{artist} - {title} ({creator}) [{version}].osu")
            .format(**response_json)
            .translate(IGNORED_BEATMAP_CHARS)
        )

        song_name = (
            ("{artist} - {title} [{version}]")
            .format(**response_json)
            .translate(IGNORED_BEATMAP_CHARS)
        )

        hit_length = int(response_json["hit_length"])

        if _max_combo := response_json.get("max_combo"):
            max_combo = int(_max_combo)
        else:
            max_combo = 0

        bancho_ranked_status = RankedStatus.from_osu_api(int(response_json["approved"]))
        frozen = bancho_ranked_status in FROZEN_STATUSES

        mode = Mode(int(response_json["mode"]))

        if _bpm := response_json.get("bpm"):
            bpm = round(float(_bpm))
        else:
            bpm = 0

        od = float(response_json["diff_overall"])
        ar = float(response_json["diff_approach"])

        count_circles = int(response_json["count_circles"])
        count_sliders = int(response_json["count_sliders"])
        count_spinners = int(response_json["count_spinners"])

        maps.append(
            Beatmap(
                md5=md5,
                id=id,
                set_id=set_id,
                song_name=song_name,
                status=bancho_ranked_status,
                plays=0,
                passes=0,
                mode=mode,
                od=od,
                ar=ar,
                hit_length=hit_length,
                last_update=int(time.time()),
                max_combo=max_combo,
                bpm=bpm,
                filename=filename,
                frozen=frozen,
                rankedby=None,
                rating=10.0,
                bancho_ranked_status=bancho_ranked_status,
                count_circles=count_circles,
                count_sliders=count_sliders,
                count_spinners=count_spinners,
            ),
        )

    return maps


async def increment_playcount(
    *,
    beatmap: Beatmap,
    increment_passcount: bool,
) -> None:
    beatmap.plays += 1
    if increment_passcount:
        beatmap.passes += 1

    await app.state.services.database.execute(
        "UPDATE beatmaps SET passcount = passcount + :passcount_increment, playcount = playcount + 1 WHERE beatmap_md5 = :md5",
        {"passcount_increment": int(increment_passcount), "md5": beatmap.md5},
    )
