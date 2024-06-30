import ast
import asyncio
import json
import sys
import time
from datetime import datetime, timezone
from typing import List

import genshin
import requests
import pytz
from apscheduler.triggers.cron import CronTrigger
from genshin import (
    Client,
    RedemptionInvalid,
    RedemptionClaimed,
    InvalidCookies,
    RedemptionCooldown,
)
from genshin.models import Notes
from genshin.models.genshin.diary import Diary
from nextcord import Interaction, Embed
from nextcord.ui.view import View
import nextcord
import db
import re
import demjson
from diskcache import Cache

GANYU_COLORS = {"light": 0xB5C5D7, "dark": 0x505EA9}
SETTINGS_IMG_URL = "https://i.imgur.com/cOvCeqF.png"
PRIMO_IMG_URL = "https://i.imgur.com/6NhUURa.png"
PAIMON_MOE_URL_BASE = "https://paimon.moe"
PAIMON_MOE_EVENT_IMG_BASE = "https://paimon.moe/images/events"
# Subject to change (if paimon.moe updates its location)
TIMELINE_REGEX = "/_app/immutable/chunks/timeline-\\w+.js"

PRIMO_EMOJI = "<:primogem:935934046029115462>"
MORA_EMOJI = "<:mora:935934436594286652>"
AEP_EMOJI = "<:aep:1249814893897449492>"
ACHIEVEMENT_EMOJI = "<:achievement:1249814725454467081>"
ABYSS_EMOJI = "<:abyss:1249817258856026273>"

# Daily reward becomes available at 5 pm UTC
DAILY_REWARD_CRON_TRIGGER = CronTrigger(
    hour="17", timezone=pytz.UTC, jitter=3600  # anytime within that hour
)

DAILY_HSR_REWARD_CRON_TRIGGER = CronTrigger(
    hour="18", timezone=pytz.UTC, jitter=3600  # anytime within that hour
)

CODE_POLLER_CRON_TRIGGER = CronTrigger(
    hour="*/2", timezone=pytz.UTC, jitter=600  # 10 min jitter
)

ACTIVITY_FEED_CRON_TRIGGER = CronTrigger(minute="*/5", timezone=pytz.UTC)  # every 5 min
ACTIVITY_FEED_CLEANUP_TRIGGER = CronTrigger(hour="0", timezone=pytz.UTC)  # once a day

cache = Cache("cache")


def get_scheduler_jobs(scheduler):
    jobs = scheduler.get_jobs()
    detailed_jobs = []
    for job in jobs:
        detailed_jobs.append(
            {"id": job.id, "name": job.name, "next_run_time": job.next_run_time}
        )

    return detailed_jobs


def get_schedule_info():
    cache_key = "timeline"
    if cache_key in cache:
        return cache[cache_key]

    timeline_js = get_paimon_moe_timeline_js()
    if timeline_js:
        res = requests.get(f"{PAIMON_MOE_URL_BASE}{timeline_js}")
        raw = res.text
        info = demjson.decode(
            raw[raw.index("[") : raw.index("];") + 1].replace("!0", "1")
        )
        # unpack stuff and format dates
        consolidated_event_list = []
        for event_list in info:
            for event in event_list:
                try:
                    if event.get("timezoneDependent"):
                        # Asia time conversion
                        event["start"] = int(
                            datetime.strptime(event["start"], "%Y-%m-%d %H:%M:%S")
                            .replace(tzinfo=pytz.timezone("Etc/GMT-8"))
                            .timestamp()
                        )
                    else:
                        # GMT+5 Conversion
                        event["start"] = int(
                            datetime.strptime(event["start"], "%Y-%m-%d %H:%M:%S")
                            .replace(tzinfo=pytz.timezone("Etc/GMT+5"))
                            .timestamp()
                        )

                    event["end"] = int(
                        datetime.strptime(event["end"], "%Y-%m-%d %H:%M:%S")
                        .replace(tzinfo=pytz.timezone("Etc/GMT+5"))
                        .timestamp()
                    )
                    consolidated_event_list.append(event)
                except:
                    print(
                        f"Ignoring event (maybe invalid date): start {event['start']} end {event['end']}"
                    )

        cache.set(cache_key, consolidated_event_list, expire=3600)  # 1 hr cache
        return consolidated_event_list

    return None


def get_paimon_moe_timeline_js():
    res = requests.get(f"{PAIMON_MOE_URL_BASE}/timeline/")
    matches = re.findall(TIMELINE_REGEX, res.text)
    if len(matches) > 0:
        return matches[0]
    else:
        return None


def dict_factory(cursor, row):
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d


def get_settings():
    with open("settings.json") as f:
        settings = json.loads(f.read())
        return settings


def set_settings(settings):
    with open("settings.json", "w+") as f:
        f.write(json.dumps(settings, indent=4, sort_keys=True))


def create_link_profile_embed(
    discord_id, discord_avatar_url, uid, level, username, is_hsr=False
):
    embed = nextcord.Embed(
        title=f"Successfully linked! ({'Genshin' if not is_hsr else 'HSR'})"
    )
    embed.add_field(name="UID", value=uid)
    embed.add_field(name="Name", value=username)
    embed.add_field(
        name="Adventure Rank" if not is_hsr else "Trailblaze Level", value=level
    )
    embed.add_field(name="Discord User", value=f"<@{discord_id}>")
    embed.set_thumbnail(url=discord_avatar_url)
    embed.colour = GANYU_COLORS["dark"]

    return embed


def create_profile_card_embed(discord_name, discord_avatar_url, uid, user_settings):
    embed = nextcord.Embed(title=discord_name)
    embed.add_field(name="UID", value=uid)
    for setting in user_settings:
        embed.add_field(name=setting, value=user_settings[setting])

    embed.set_thumbnail(url=discord_avatar_url)
    embed.colour = GANYU_COLORS["dark"]

    return embed


def create_reward_embed(name, amount, icon_url):
    embed = nextcord.Embed(title="Reward Claimed", description=f"Got {amount}x {name}")
    embed.set_thumbnail(url=icon_url)
    embed.colour = GANYU_COLORS["dark"]
    return embed


def create_status_embed(notes: Notes, avatar_url):
    embed = nextcord.Embed(title="Status")
    embed.set_thumbnail(url=avatar_url)
    embed.add_field(
        name="Commissions",
        value=f"{notes.completed_commissions}/{notes.max_commissions} Finished",
        inline=False,
    )
    cur_time = time.time()
    recover_time = int(cur_time + notes.remaining_resin_recovery_time.total_seconds())
    embed.add_field(
        name="Resin",
        value=f"{notes.current_resin}/{notes.max_resin}\nFull <t:{recover_time}:R>",
    )
    realm_currency_time = int(
        cur_time + notes.remaining_realm_currency_recovery_time.total_seconds()
    )
    embed.add_field(
        name="Realm Currency",
        value=f"{notes.current_realm_currency}/{notes.max_realm_currency}"
        f"\nFull <t:{realm_currency_time}:R>",
    )
    expeditions = []
    for i, expedition in enumerate(notes.expeditions):
        exp_str = f"Expedition {i + 1} - `{str(expedition.status)}`"
        if not expedition.finished:
            exp_str += f" (Finishing <t:{int(cur_time + expedition.remaining_time.total_seconds())}:R>)"

        expeditions.append(exp_str)

    embed.add_field(name="Expeditions", value="\n".join(expeditions), inline=False)
    embed.colour = GANYU_COLORS["dark"]
    return embed


def create_schedule_embed(event_list, avatar_url, future=False):
    schedule = []

    current_time = int(time.time())

    if future:
        title = "Upcoming Events"
    else:
        title = "Current Events"

    if future:
        event_list.sort(key=lambda x: x["start"])
    else:
        event_list.sort(key=lambda x: x["end"])

    for event in event_list:
        name = event["name"]
        url = event.get("url")
        start_time = event["start"]
        end_time = event["end"]

        if start_time <= current_time <= end_time and not future:
            if url:
                schedule.append(f"[{name}]({url}) ends <t:{end_time}:R>")
            else:
                schedule.append(f"{name} ends <t:{end_time}:R>")
        elif start_time > current_time and future:
            if url:
                schedule.append(f"[{name}]({url}) starts <t:{start_time}:R>")
            else:
                schedule.append(f"{name} starts <t:{start_time}:R>")

    embed = nextcord.Embed(title=title, description="\n".join(schedule))
    embed.set_thumbnail(url=avatar_url)
    embed.colour = GANYU_COLORS["dark"]
    return embed


def create_event_embed(event):
    # wtf is this man
    current_time = int(time.time())
    start_time = event["start"]
    end_time = event["end"]

    if start_time <= current_time <= end_time:
        desc = f"Ends <t:{end_time}:R>"
    elif start_time > current_time:
        desc = f"Starts <t:{start_time}:R>"

    embed = nextcord.Embed(title=event["name"], description=desc)
    if event.get("url"):
        embed.url = event["url"]

    if event.get("description"):
        embed.description += "\n\n" + event["description"]

    if event.get("image"):
        image = event["image"]
        embed.set_image(url=f"{PAIMON_MOE_EVENT_IMG_BASE}/{image}")
    if event.get("color"):
        embed.colour = int("0x" + event["color"][1:], base=16)
    else:
        embed.colour = GANYU_COLORS["dark"]

    return embed


def create_report_overview_embed(data: Diary, avatar_url):
    embed = nextcord.Embed(
        title="Income Overview",
        description="Does not include Welkins or top-up income.",
    )
    primo_percent = data.data.primogems_rate
    mora_percent = data.data.mora_rate
    if primo_percent > 0:
        primo_percent = f"+{primo_percent}"
    if mora_percent > 0:
        mora_percent = f"+{mora_percent}"

    embed.add_field(
        name="Current Month",
        value=f"{PRIMO_EMOJI} {data.data.current_primogems}"
        f" `({primo_percent}%)`\n{MORA_EMOJI}"
        f" {data.data.current_mora} `({mora_percent}%)`",
    )
    embed.add_field(
        name="Last Month",
        value=f"{PRIMO_EMOJI} {data.data.last_primogems}\n{MORA_EMOJI}"
        f" {data.data.last_mora}",
    )
    embed.add_field(
        name="Today",
        value=f"{PRIMO_EMOJI} {data.day_data.current_primogems}\n{MORA_EMOJI}"
        f" {data.day_data.current_mora}",
    )
    embed.set_thumbnail(url=avatar_url)
    embed.colour = GANYU_COLORS["dark"]
    return embed


def create_report_breakdown_embed(data: Diary, avatar_url):
    embed = nextcord.Embed(
        title="Income Breakdown",
        description="Does not include Welkins or top-up income.",
    )
    for category in data.data.categories:
        embed.add_field(
            name=category.name,
            value=f"{PRIMO_EMOJI} {category.amount} `({category.percentage}%)`",
        )

    embed.set_thumbnail(url=avatar_url)
    embed.colour = GANYU_COLORS["dark"]
    return embed


def create_code_announcement_embed(code: str):
    embed = nextcord.Embed(
        title=f"Redemption Code",
        description=f"Code: `{code}`\nClick below to automatically redeem!",
    )
    embed.set_thumbnail(url=PRIMO_IMG_URL)
    embed.colour = GANYU_COLORS["dark"]
    embed.set_footer(text="The redeem button will stop working after 48 hours.")
    return embed


def create_code_discovery_embed(code: str):
    embed = nextcord.Embed(
        title=f"New Code Discovered",
        description=f"Code: `{code}`\nCan attempt to redeem with the buttons below!",
    )
    embed.set_thumbnail(url=PRIMO_IMG_URL)
    embed.colour = GANYU_COLORS["dark"]
    embed.set_footer(text="The redeem button will stop working after 48 hours.")
    return embed


def create_message_embed(message, color=GANYU_COLORS["dark"], thumbnail=None):
    embed = nextcord.Embed(description=message)
    embed.colour = color
    if thumbnail:
        embed.set_thumbnail(url=thumbnail)

    return embed


def loading_embed():
    embed = nextcord.Embed(description="Working on it...")
    embed.colour = GANYU_COLORS["light"]
    return embed


def create_activity_update_embed(discord_id, uid, db_data, new_data):
    embed = nextcord.Embed(title="🔵 Activity Update", description=f"<@{discord_id}>")
    fields = [
        ("level", "level", AEP_EMOJI, "Adventure Rank"),
        ("world_level", "worldLevel", "🌎", "World Level"),
        (
            "finish_achievement_num",
            "finishAchievementNum",
            ACHIEVEMENT_EMOJI,
            "Achievements",
        ),
    ]

    for field in fields:
        if db_data[field[0]] != new_data[field[1]]:
            diff = new_data[field[1]] - db_data[field[0]]
            embed.add_field(
                name=field[3],
                value=f"{field[2]} {new_data[field[1]]} *({'+' if diff > 0 else ''}{diff})*",
            )

    if (
        db_data["tower_floor_index"] != new_data["towerFloorIndex"]
        or db_data["tower_level_index"] != new_data["towerLevelIndex"]
    ):
        embed.add_field(
            name="Spiral Abyss",
            value=f"{ABYSS_EMOJI} {new_data['towerFloorIndex']}-{new_data['towerLevelIndex']} *(from {db_data['tower_floor_index']}-{db_data['tower_level_index']})*",
        )

    embed.colour = GANYU_COLORS["dark"]
    embed.set_footer(text=f"UID {uid}")
    return embed


class ProfileChoices(View):
    def __init__(
        self,
        user_id,
        user_name,
        user_avatar,
        need_code_setup,
        base_interaction: Interaction,
        probe=False,
        is_hsr=False,
    ):
        super().__init__(timeout=120)
        self.base_interaction: Interaction = base_interaction
        self.user_avatar = user_avatar
        self.user_name = user_name
        self.user_id = user_id
        self.user_data = (
            db.get_link_entry(self.user_id)
            if not is_hsr
            else db.get_hsr_link_entry(self.user_id)
        )
        self.is_hsr = is_hsr

        toggle_check_in_button = nextcord.ui.Button(
            label="Toggle Check-in", style=nextcord.ButtonStyle.blurple
        )
        toggle_check_in_button.callback = self.toggle_check_in
        if not probe:
            self.add_item(toggle_check_in_button)

        if not is_hsr:
            toggle_activity_button = nextcord.ui.Button(
                label="Toggle Activity Tracking", style=nextcord.ButtonStyle.blurple
            )
            toggle_activity_button.callback = self.toggle_activity
            enka_network_button = nextcord.ui.Button(
                label="Enka Network",
                style=nextcord.ButtonStyle.link,
                url=f"https://enka.network/u/{self.user_data['uid']}",
            )
            akasha_cv_button = nextcord.ui.Button(
                label="Akasha",
                style=nextcord.ButtonStyle.link,
                url=f"https://akasha.cv/profile/{self.user_data['uid']}",
            )
            if not probe:
                self.add_item(toggle_activity_button)

            self.add_item(enka_network_button)
            self.add_item(akasha_cv_button)

    async def toggle_check_in(self, interaction: nextcord.Interaction):
        if not interaction.user.id == self.user_id:
            return

        if not self.user_data:
            self.stop()

        if self.is_hsr:
            db.set_hsr_daily_reward(self.user_id, not self.user_data["daily_reward"])
            self.user_data["daily_reward"] = not self.user_data["daily_reward"]
            user_settings = {
                "HSR Auto Check-in": "No"
                if self.user_data["daily_reward"] == 0
                else "Yes",
            }
            embed = create_profile_card_embed(
                self.user_name, self.user_avatar, self.user_data["uid"], user_settings
            )
            await self.base_interaction.edit_original_message(embed=embed)
            return

        need_code_setup = (
            self.user_data["account_id"] is None
            or self.user_data["cookie_token"] is None
        )

        db.set_daily_reward(self.user_id, not self.user_data["daily_reward"])
        self.user_data["daily_reward"] = not self.user_data["daily_reward"]

        user_settings = {
            "Auto Check-in": "No" if self.user_data["daily_reward"] == 0 else "Yes",
            "Can Redeem Codes": "No" if need_code_setup else "Yes",
            "Track Activity": "No" if self.user_data["track"] == 0 else "Yes",
        }
        embed = create_profile_card_embed(
            self.user_name, self.user_avatar, self.user_data["uid"], user_settings
        )
        await self.base_interaction.edit_original_message(embed=embed)

    async def toggle_activity(self, interaction: nextcord.Interaction):
        if not interaction.user.id == self.user_id:
            return

        if not self.user_data:
            self.stop()

        need_code_setup = (
            self.user_data["account_id"] is None
            or self.user_data["cookie_token"] is None
        )

        db.set_activity_tracking(self.user_id, not self.user_data["track"])
        self.user_data["track"] = not self.user_data["track"]

        user_settings = {
            "Auto Check-in": "No" if self.user_data["daily_reward"] == 0 else "Yes",
            "Can Redeem Codes": "No" if need_code_setup else "Yes",
            "Track Activity": "No" if self.user_data["track"] == 0 else "Yes",
        }
        embed = create_profile_card_embed(
            self.user_name, self.user_avatar, self.user_data["uid"], user_settings
        )
        await self.base_interaction.edit_original_message(embed=embed)


class MessageBook(View):
    def __init__(
        self,
        user_id: int,
        user_avatar_url: str,
        pages: List[Embed],
        base_interaction: Interaction,
    ):
        super().__init__(timeout=120)
        self.page_count = len(pages)

        for i, page in enumerate(pages):
            page.set_footer(
                text=f"Page {i + 1} of {self.page_count}", icon_url=user_avatar_url
            )

        self.base_interaction = base_interaction
        self.pages = pages
        self.user_id = user_id
        self.current_page = 0

    @nextcord.ui.button(label="Prev", style=nextcord.ButtonStyle.blurple)
    async def prev_button(
        self, button: nextcord.ui.Button, interaction: nextcord.Interaction
    ):
        if not interaction.user.id == self.user_id:
            return

        await self.prev_page()

    @nextcord.ui.button(label="Next", style=nextcord.ButtonStyle.blurple)
    async def next_button(
        self, button: nextcord.ui.Button, interaction: nextcord.Interaction
    ):
        if not interaction.user.id == self.user_id:
            return

        await self.next_page()

    async def next_page(self):
        self.current_page += 1
        if self.current_page > len(self.pages) - 1:
            self.current_page = 0

        await self.update_page()

    async def prev_page(self):
        self.current_page -= 1
        if self.current_page < 0:
            self.current_page = len(self.pages) - 1

        await self.update_page()

    async def update_page(self):
        await self.base_interaction.edit_original_message(
            embed=self.pages[self.current_page]
        )


class CodeAnnouncement(View):
    def __init__(self, code: str):
        super().__init__(timeout=86400 * 2)
        self.code = code
        redeem_button = nextcord.ui.Button(
            label="Redeem", style=nextcord.ButtonStyle.blurple
        )
        redeem_button.callback = self.redeem
        manual_redeem_button = nextcord.ui.Button(
            label="Redeem Manually",
            style=nextcord.ButtonStyle.link,
            url=f"https://genshin.hoyoverse.com/en/gift?code={code}",
        )
        self.add_item(redeem_button)
        self.add_item(manual_redeem_button)

    async def redeem(self, interaction: nextcord.Interaction):
        discord_id = interaction.user.id
        user_data = db.get_link_entry(discord_id)
        if not user_data:
            await interaction.response.send_message(
                embed=create_message_embed(
                    "You don't have an account linked.", GANYU_COLORS["dark"]
                ),
                ephemeral=True,
            )
            return

        need_code_setup = (
            user_data["account_id"] is None or user_data["cookie_token"] is None
        )
        if need_code_setup:
            await interaction.response.send_message(
                embed=create_message_embed(
                    "You need to add additional authentication cookies to redeem codes.\n"
                    "Log into https://genshin.hoyoverse.com/en/gift, find `account_id` and `cookie_token`,"
                    " then use `/linkcode`.",
                    color=GANYU_COLORS["dark"],
                ),
                ephemeral=True,
            )
            return

        user_client = Client(
            {
                "ltuid": user_data["ltuid"],
                "ltoken": user_data["ltoken"],
                "account_id": user_data["account_id"],
                "cookie_token": user_data["cookie_token"],
            }
        )

        user_client.default_game = genshin.Game.GENSHIN
        # Using API takes time, keep interaction alive by sending a "loading" response
        await interaction.response.send_message(embed=loading_embed(), ephemeral=True)
        try:
            await user_client.redeem_code(self.code)
            await interaction.edit_original_message(
                embed=create_message_embed(f"Successfully claimed code `{self.code}`!")
            )
        except RedemptionInvalid:
            await interaction.edit_original_message(
                embed=create_message_embed(
                    f"Invalid code `{self.code}`!", color=GANYU_COLORS["dark"]
                )
            )
        except RedemptionClaimed:
            await interaction.edit_original_message(
                embed=create_message_embed(
                    f"You've already redeemed `{self.code}`!",
                    color=GANYU_COLORS["dark"],
                )
            )
        except RedemptionCooldown:
            await interaction.edit_original_message(
                embed=create_message_embed("Please wait a bit before redeeming again.")
            )
        except InvalidCookies:
            embed = create_message_embed(
                "Something went wrong... if you changed your password recently,"
                " you will have to relink with new cookies."
            )
            await interaction.edit_original_message(embed=embed)


def get_client(ltuid: str, ltoken: str, is_genshin=True) -> Client:
    if ltoken.startswith("v2"):
        client = Client({"ltuid_v2": ltuid, "ltoken_v2": ltoken})
    else:
        client = Client({"ltuid": ltuid, "ltoken": ltoken})

    if is_genshin:
        client.default_game = genshin.Game.GENSHIN

    return client


def get_hsr_client(
    ltuid: str, ltoken: str, account_mid: str, cookie_token: str
) -> Client:
    params = {}
    if ltoken.startswith("v2"):
        params["ltuid_v2"] = ltuid
        params["ltoken_v2"] = ltoken
    else:
        params["ltuid"] = ltuid
        params["ltoken"] = ltoken

    if cookie_token.startswith("v2"):
        params["account_mid_v2"] = account_mid
        params["cookie_token_v2"] = cookie_token
    else:
        params["account_mid"] = account_mid
        params["cookie_token"] = cookie_token

    client = Client(params)
    client.default_game = genshin.Game.STARRAIL

    return client
