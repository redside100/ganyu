import sqlite3
import uuid
import time
from util import dict_factory

cur = None
con = None
default_path = "ganyu.db"


def init(path=default_path):
    global con
    con = sqlite3.connect(path)
    con.row_factory = dict_factory


def get_cursor():
    if not con:
        init()
    return con.cursor()


def update_link_entry(discord_id, uid, ltuid, ltoken, daily_reward=True):
    get_cursor().execute(
        "INSERT INTO user_data VALUES (?, ?, ?, ?, ?, NULL, NULL, TRUE) on conflict(discord_id) do"
        " UPDATE SET uid = excluded.uid, ltuid = excluded.ltuid, ltoken = excluded.ltoken, "
        "daily_reward = excluded.daily_reward",
        (discord_id, uid, ltuid, ltoken, daily_reward),
    )
    con.commit()


def update_hsr_link_entry(
    discord_id, uid, ltuid, ltoken, account_mid, cookie_token, daily_reward=True
):
    get_cursor().execute(
        "INSERT INTO hsr_user_data VALUES (?, ?, ?, ?, ?, ?, ?) on conflict(discord_id) do"
        " UPDATE SET uid = excluded.uid, ltuid = excluded.ltuid, ltoken = excluded.ltoken, account_mid = excluded.account_mid, cookie_token = excluded.cookie_token, "
        "daily_reward = excluded.daily_reward",
        (discord_id, uid, ltuid, ltoken, account_mid, cookie_token, daily_reward),
    )
    con.commit()


def create_alt_entry(name, uid, ltuid, ltoken):
    get_cursor().execute(
        "INSERT INTO alt_data VALUES (?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), name, uid, ltuid, ltoken),
    )
    con.commit()


def delete_alt_entry(uuid):
    get_cursor().execute("DELETE FROM alt_data WHERE id = :id", {"id": uuid})
    con.commit()


def get_alt_data(uuid):
    data = (
        get_cursor()
        .execute("SELECT * FROM alt_data WHERE id = :id", {"id": uuid},)
        .fetchone()
    )
    if data:
        return data

    return None


def get_all_alts():
    data = get_cursor().execute("SELECT * FROM alt_data").fetchall()
    return data


def alt_uid_exists(uid):
    data = (
        get_cursor()
        .execute("SELECT * FROM alt_data WHERE uid = :uid", {"uid": uid},)
        .fetchone()
    )
    if data:
        return data["id"]
    else:
        return False


def set_account_id(discord_id, uid):
    get_cursor().execute(
        "UPDATE user_data SET account_id = :value WHERE discord_id = :discord_id",
        {"value": uid, "discord_id": discord_id},
    )
    con.commit()


def set_cookie_token(discord_id, cookie_token):
    get_cursor().execute(
        "UPDATE user_data SET cookie_token = :value WHERE discord_id = :discord_id",
        {"value": cookie_token, "discord_id": discord_id},
    )
    con.commit()


def set_daily_reward(discord_id, value):
    get_cursor().execute(
        "UPDATE user_data SET daily_reward = :value WHERE discord_id = :discord_id",
        {"value": value, "discord_id": discord_id},
    )
    con.commit()


def set_hsr_daily_reward(discord_id, value):
    get_cursor().execute(
        "UPDATE user_data SET daily_reward = :value WHERE discord_id = :discord_id",
        {"value": value, "discord_id": discord_id},
    )
    con.commit()


def set_activity_tracking(discord_id, value):
    get_cursor().execute(
        "UPDATE user_data SET track = :value WHERE discord_id = :discord_id",
        {"value": value, "discord_id": discord_id},
    )
    con.commit()


def get_link_entry(discord_id):
    data = (
        get_cursor()
        .execute(
            "SELECT * FROM user_data WHERE discord_id = :discord_id",
            {"discord_id": discord_id},
        )
        .fetchone()
    )
    if data:
        return data

    return None


def get_hsr_link_entry(discord_id):
    data = (
        get_cursor()
        .execute(
            "SELECT * FROM hsr_user_data WHERE discord_id = :discord_id",
            {"discord_id": discord_id},
        )
        .fetchone()
    )
    if data:
        return data

    return None


def get_all_auto_checkin_users():
    data = (
        get_cursor()
        .execute("SELECT * FROM user_data WHERE daily_reward = TRUE")
        .fetchall()
    )
    return data


def get_all_hsr_auto_checkin_users():
    data = (
        get_cursor()
        .execute("SELECT * FROM hsr_user_data WHERE daily_reward = TRUE")
        .fetchall()
    )
    return data


def get_all_tracked_users():
    data = get_cursor().execute("SELECT * FROM user_data WHERE track = TRUE").fetchall()
    return data


def get_latest_activity(discord_id):
    data = (
        get_cursor()
        .execute(
            "SELECT * FROM user_activity WHERE discord_id = :discord_id ORDER BY timestamp DESC limit 1",
            {"discord_id": discord_id},
        )
        .fetchone()
    )
    return data


def uid_exists(uid):
    data = (
        get_cursor()
        .execute("SELECT uid FROM user_data WHERE uid = :uid", {"uid": uid})
        .fetchone()
    )
    if data:
        return True
    return False


def hsr_uid_exists(uid):
    data = (
        get_cursor()
        .execute("SELECT uid FROM hsr_user_data WHERE uid = :uid", {"uid": uid})
        .fetchone()
    )
    if data:
        return True
    return False


def delete_entry_by_uid(uid):
    discord_id = (
        get_cursor()
        .execute("SELECT discord_id FROM user_data WHERE uid = :uid", {"uid": uid})
        .fetchone()["discord_id"]
    )

    get_cursor().execute("DELETE FROM user_data WHERE uid = :uid", {"uid": uid})
    con.commit()

    return discord_id


def hsr_delete_entry_by_uid(uid):
    discord_id = (
        get_cursor()
        .execute("SELECT discord_id FROM hsr_user_data WHERE uid = :uid", {"uid": uid})
        .fetchone()["discord_id"]
    )

    get_cursor().execute("DELETE FROM hsr_user_data WHERE uid = :uid", {"uid": uid})
    con.commit()

    return discord_id


def user_count():
    data = (
        get_cursor()
        .execute("SELECT COUNT(*) as linked FROM user_data")
        .fetchone()["linked"]
    )
    return data


def log_activity(discord_id, enka_response):
    player_info = enka_response["playerInfo"]
    get_cursor().execute(
        "INSERT INTO user_activity VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            discord_id,
            player_info["level"],
            player_info["worldLevel"],
            player_info["finishAchievementNum"],
            player_info["towerFloorIndex"],
            player_info["towerLevelIndex"],
            int(time.time()),
        ),
    )
    con.commit()


def purge_activities():
    time_thres = int(time.time()) - (86400 * 30)
    get_cursor().execute(f"DELETE FROM user_activity WHERE timestamp < {time_thres}")
    con.commit()
