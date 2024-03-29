import sqlite3
import base64
from util import dict_factory
cur = None
con = None
default_path = 'ganyu.db'


def init(path=default_path):
    global con
    con = sqlite3.connect(path)
    con.row_factory = dict_factory


def get_cursor():
    if not con:
        init()
    return con.cursor()


def update_link_entry(discord_id, uid, ltuid, ltoken, daily_reward=True):
    get_cursor().execute("INSERT INTO user_data VALUES (?, ?, ?, ?, ?, NULL, NULL) on conflict(discord_id) do"
                         " UPDATE SET uid = excluded.uid, ltuid = excluded.ltuid, ltoken = excluded.ltoken, "
                         "daily_reward = excluded.daily_reward",
                         (discord_id, uid, ltuid, ltoken, daily_reward))
    con.commit()


def set_account_id(discord_id, uid):
    get_cursor().execute("UPDATE user_data SET account_id = :value WHERE discord_id = :discord_id", {
        'value': uid,
        'discord_id': discord_id
    })
    con.commit()


def set_cookie_token(discord_id, cookie_token):
    get_cursor().execute("UPDATE user_data SET cookie_token = :value WHERE discord_id = :discord_id", {
        'value': cookie_token,
        'discord_id': discord_id
    })
    con.commit()

def set_daily_reward(discord_id, value):
    get_cursor().execute("UPDATE user_data SET daily_reward = :value WHERE discord_id = :discord_id", {
        'value': value,
        'discord_id': discord_id
    })
    con.commit()


def get_link_entry(discord_id):
    data = get_cursor().execute("SELECT * FROM user_data WHERE discord_id = :discord_id", {
        "discord_id": discord_id
    }).fetchone()
    if data:
        return data

    return None


def get_all_auto_checkin_users():
    data = get_cursor().execute("SELECT * FROM user_data WHERE daily_reward = TRUE").fetchall()
    return data


def uid_exists(uid):
    data = get_cursor().execute("SELECT uid FROM user_data WHERE uid = :uid", {
        "uid": uid
    }).fetchone()
    if data:
        return True
    return False


def delete_entry_by_uid(uid):
    discord_id = get_cursor().execute("SELECT discord_id FROM user_data WHERE uid = :uid", {
        "uid": uid
    }).fetchone()['discord_id']

    get_cursor().execute("DELETE FROM user_data WHERE uid = :uid", {
        "uid": uid
    })
    con.commit()

    return discord_id


def user_count():
    data = get_cursor().execute("SELECT COUNT(*) as linked FROM user_data").fetchone()['linked']
    return data
