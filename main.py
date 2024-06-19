import asyncio
import logging
import re
import time
import random

import genshin
import nextcord
import requests
from nextcord import Interaction
from nextcord.ext import commands
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import traceback
import db
from diskcache import Cache

import util
from genshin.client import MultiCookieClient, Client
from genshin.errors import (
    InvalidCookies,
    GenshinException,
    AlreadyClaimed,
    DataNotPublic,
    RedemptionInvalid,
    RedemptionClaimed,
    RedemptionCooldown,
)
from util import (
    create_activity_update_embed,
    create_message_embed,
    create_link_profile_embed,
    GANYU_COLORS,
    create_profile_card_embed,
    ProfileChoices,
    create_reward_embed,
    create_status_embed,
    MessageBook,
    get_client,
)

logging.basicConfig()
logging.getLogger().setLevel(logging.INFO)

bot = commands.Bot(command_prefix="!", intents=nextcord.Intents.all())
bot.remove_command("help")
cache = None
scheduler = AsyncIOScheduler(timezone="UTC")


@bot.slash_command(name="ping", description="Pong!")
async def ping(interaction: Interaction):
    await interaction.response.send_message("Pong!")


@bot.slash_command(
    name="link", description="Links a Genshin/Hoyolab account to your Discord user."
)
async def link(interaction: Interaction, ltuid: str, ltoken: str):
    if not ltuid.isnumeric():
        await interaction.response.send_message(
            embed=create_message_embed(
                "Invalid ltuid (must a number)!", GANYU_COLORS["dark"]
            ),
            ephemeral=True,
        )
        return

    user_client = get_client(ltuid, ltoken)
    # Using API takes time, keep interaction alive by sending a "loading" response
    await interaction.response.send_message(embed=util.loading_embed(), ephemeral=True)
    try:
        accounts = await user_client.genshin_accounts()
        if len(accounts) > 0:

            no_na_warning = False
            na_account = None
            for account in accounts:
                if account.server_name == "America Server":
                    na_account = account

            if na_account is None:
                na_account = accounts[0]
                no_na_warning = True

            uid = na_account.uid
            level = na_account.level
            username = na_account.nickname
            discord_id = interaction.user.id
            unlinked_discord_id = None

            existing_alt_uuid = db.alt_uid_exists(uid)
            if existing_alt_uuid:
                await interaction.edit_original_message(
                    embed=create_message_embed(
                        f"UID {uid} already exists as an alt account (uuid {existing_alt_uuid})."
                    )
                )
                return

            if db.uid_exists(uid):
                unlinked_discord_id = db.delete_entry_by_uid(uid)

            db.update_link_entry(discord_id, uid, ltuid, ltoken)

            embed = create_link_profile_embed(
                discord_id, interaction.user.avatar.url, uid, level, username
            )

            if unlinked_discord_id:
                embed.add_field(
                    name="Old Discord User", value=f"<@{unlinked_discord_id}>"
                )

            if no_na_warning:
                embed.set_footer(
                    text="Warning: No NA account was found, the UID may be incorrect."
                )

            await interaction.edit_original_message(embed=embed)
        else:
            await interaction.edit_original_message(
                embed=create_message_embed(
                    "You don't have any genshin accounts!", GANYU_COLORS["dark"]
                )
            )

    except InvalidCookies:
        await interaction.edit_original_message(
            embed=create_message_embed("Invalid auth cookies!", GANYU_COLORS["dark"])
        )


@bot.slash_command(name="linkalt", description="Ganyu mod usage only.")
async def link_alt(interaction: Interaction, ltuid: str, ltoken: str, name: str):

    discord_id = interaction.user.id
    settings = util.get_settings()

    if discord_id not in settings["ganyu_mods"]:
        await interaction.response.send_message(
            embed=create_message_embed(
                "You can't use this command...", GANYU_COLORS["dark"]
            )
        )
        return

    if not ltuid.isnumeric():
        await interaction.response.send_message(
            embed=create_message_embed(
                "Invalid ltuid (must a number)!", GANYU_COLORS["dark"]
            ),
            ephemeral=True,
        )
        return

    user_client = get_client(ltuid, ltoken)
    # Using API takes time, keep interaction alive by sending a "loading" response
    await interaction.response.send_message(embed=util.loading_embed(), ephemeral=True)
    try:
        accounts = await user_client.genshin_accounts()
        if len(accounts) > 0:

            no_na_warning = False
            na_account = None
            for account in accounts:
                if account.server_name == "America Server":
                    na_account = account

            if na_account is None:
                na_account = accounts[0]
                no_na_warning = True

            uid = na_account.uid
            level = na_account.level
            username = na_account.nickname
            discord_id = interaction.user.id

            if db.uid_exists(uid):
                await interaction.edit_original_message(
                    embed=create_message_embed(
                        f"UID {uid} already exists as a linked main account."
                    )
                )
                return

            existing_alt_uuid = db.alt_uid_exists(uid)

            if existing_alt_uuid:
                db.delete_alt_entry(existing_alt_uuid)

            db.create_alt_entry(name, uid, ltuid, ltoken)

            embed = create_link_profile_embed(
                discord_id, interaction.user.avatar.url, uid, level, username
            )

            footer = "Alt account linked!"

            if no_na_warning:
                footer += " Warning: No NA account was found, the UID may be incorrect."

            embed.set_footer(text=footer)

            await interaction.edit_original_message(embed=embed)
        else:
            await interaction.edit_original_message(
                embed=create_message_embed(
                    "Alt account has no genshin accounts!", GANYU_COLORS["dark"]
                )
            )

    except InvalidCookies:
        await interaction.edit_original_message(
            embed=create_message_embed("Invalid auth cookies!", GANYU_COLORS["dark"])
        )


@bot.slash_command(name="deletealt", description="Ganyu mod usage only.")
async def delete_alt(interaction: Interaction, uuid: str):
    discord_id = interaction.user.id
    settings = util.get_settings()

    if discord_id not in settings["ganyu_mods"]:
        await interaction.response.send_message(
            embed=create_message_embed(
                "You can't use this command...", GANYU_COLORS["dark"]
            )
        )
        return

    if not db.get_alt_data(uuid):
        await interaction.response.send_message(
            embed=create_message_embed("Alt with that UUID doesn't exist.")
        )
        return

    db.delete_alt_entry(uuid)
    await interaction.response.send_message(
        embed=create_message_embed(f"Deleted alt with UUID {uuid}.")
    )


@bot.slash_command(
    name="linkcode",
    description="Adds additional authentication cookies in order to redeem codes.",
)
async def link_code(interaction: Interaction, account_id: str, cookie_token: str):
    discord_id = interaction.user.id
    user_data = db.get_link_entry(discord_id)
    if user_data:
        if not account_id.isnumeric():
            await interaction.response.send_message(
                embed=create_message_embed(
                    "Invalid account id (must be a number)!", GANYU_COLORS["dark"]
                ),
                ephemeral=True,
            )
            return

        user_client = get_client(user_data["ltuid"], user_data["ltoken"])
        user_client.set_cookies(account_id=account_id, cookie_token=cookie_token)

        # Using API takes time, keep interaction alive by sending a "loading" response
        await interaction.response.send_message(
            embed=util.loading_embed(), ephemeral=True
        )
        try:
            await user_client.redeem_code("TestCode")
        except RedemptionInvalid:
            db.set_account_id(discord_id, account_id)
            db.set_cookie_token(discord_id, cookie_token)
            await interaction.edit_original_message(
                embed=create_message_embed(
                    "Successfully added extra authentication cookies.\nYou can now redeem codes!"
                )
            )
        except RedemptionCooldown:
            await interaction.edit_original_message(
                embed=create_message_embed("Please wait a bit before trying again.")
            )
        except InvalidCookies:
            await interaction.edit_original_message(
                embed=create_message_embed(
                    "Invalid auth cookies!", GANYU_COLORS["dark"]
                )
            )

    else:
        await interaction.response.send_message(
            embed=create_message_embed(
                "You don't have an account linked.", GANYU_COLORS["dark"]
            )
        )


@bot.slash_command(
    name="profile", description="Shows information about your linked user."
)
async def profile(interaction: Interaction):
    discord_id = interaction.user.id
    discord_name = interaction.user.name
    avatar_url = interaction.user.avatar.url
    user_data = db.get_link_entry(discord_id)
    if user_data:
        need_code_setup = (
            user_data["account_id"] is None or user_data["cookie_token"] is None
        )
        user_settings = {
            "Auto Check-in": "No" if user_data["daily_reward"] == 0 else "Yes",
            "Can Redeem Codes": "No" if need_code_setup else "Yes",
            "Track Activity": "No" if user_data["track"] == 0 else "Yes",
        }
        embed = create_profile_card_embed(
            discord_name, avatar_url, user_data["uid"], user_settings
        )
        view = ProfileChoices(
            discord_id, discord_name, avatar_url, need_code_setup, interaction
        )
        await interaction.response.send_message(embed=embed, view=view)
    else:
        await interaction.response.send_message(
            embed=create_message_embed(
                "You don't have an account linked.", GANYU_COLORS["dark"]
            )
        )


@bot.user_command(name="Get Profile")
async def get_profile(interaction: Interaction, member: nextcord.Member):
    target_data = db.get_link_entry(member.id)
    if not target_data:
        embed = create_message_embed(f"{member.name} does not have an account linked!")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    need_code_setup = (
        target_data["account_id"] is None or target_data["cookie_token"] is None
    )
    user_settings = {
        "Auto Check-in": "No" if target_data["daily_reward"] == 0 else "Yes",
        "Can Redeem Codes": "No" if need_code_setup else "Yes",
    }

    embed = create_profile_card_embed(
        member.name, member.avatar, target_data["uid"], user_settings
    )
    view = ProfileChoices(
        member.id, member.name, member.avatar, need_code_setup, interaction, probe=True
    )
    await interaction.response.send_message(embed=embed, view=view)


@bot.slash_command(
    name="claim", description="Attempt to manually claim your daily reward."
)
async def claim(interaction: Interaction):
    discord_id = interaction.user.id
    user_data = db.get_link_entry(discord_id)
    if not user_data:
        await interaction.response.send_message(
            embed=create_message_embed(
                "You don't have an account linked.", GANYU_COLORS["dark"]
            )
        )
        return

    user_client = get_client(user_data["ltuid"], user_data["ltoken"])
    # Using API takes time, keep interaction alive by sending a "loading" response
    await interaction.response.send_message(embed=util.loading_embed())
    try:
        reward = await user_client.claim_daily_reward()

        await interaction.edit_original_message(
            embed=create_reward_embed(reward.name, reward.amount, reward.icon)
        )
    except AlreadyClaimed:
        await interaction.edit_original_message(
            embed=create_message_embed(
                "Daily reward was already claimed today!", GANYU_COLORS["dark"]
            )
        )


@bot.slash_command(
    name="status", description="Shows some in-game stats on your account."
)
async def status(interaction: Interaction):
    discord_id = interaction.user.id
    avatar_url = interaction.user.avatar.url
    user_data = db.get_link_entry(discord_id)
    if not user_data:
        await interaction.response.send_message(
            embed=create_message_embed(
                "You don't have an account linked.", GANYU_COLORS["dark"]
            )
        )
        return

    user_client = get_client(user_data["ltuid"], user_data["ltoken"])
    # Using API takes time, keep interaction alive by sending a "loading" response
    await interaction.response.send_message(embed=util.loading_embed())
    try:
        notes = await user_client.get_notes(int(user_data["uid"]))
        await interaction.edit_original_message(
            embed=create_status_embed(notes, avatar_url)
        )
    except DataNotPublic:
        embed = create_message_embed(
            "You need to enable Real-Time Notes in your HoyoLab privacy settings to use this!"
        )
        embed.set_image(url=util.SETTINGS_IMG_URL)
        await interaction.edit_original_message(embed=embed)
    except Exception:
        traceback.print_exc()
        embed = create_message_embed(
            "Something went wrong... if you changed your password recently, you will have to relink with new cookies."
        )
        await interaction.edit_original_message(embed=embed)


@bot.slash_command(name="schedule", description="Shows current or upcoming events.")
async def schedule(interaction: Interaction, detailed: bool = False):
    discord_id = interaction.user.id
    avatar_url = interaction.user.avatar.url

    schedule_info = util.get_schedule_info()
    pages = []
    if not detailed:
        pages.append(
            util.create_schedule_embed(schedule_info, bot.user.avatar.url, False)
        )
        pages.append(
            util.create_schedule_embed(schedule_info, bot.user.avatar.url, True)
        )
    else:
        current = []
        future = []
        cur_time = int(time.time())

        for event in schedule_info:
            if event["start"] <= cur_time <= event["end"]:
                current.append(event)
            elif event["start"] > cur_time:
                future.append(event)

        current.sort(key=lambda x: x["end"])
        future.sort(key=lambda x: x["start"])

        for event in current:
            pages.append(util.create_event_embed(event))

        for event in future:
            pages.append(util.create_event_embed(event))

    view = MessageBook(discord_id, avatar_url, pages, interaction)
    await interaction.response.send_message(embed=pages[0], view=view)


@bot.slash_command(
    name="income", description="Retrieves a report of your primogem/mora income."
)
async def income(interaction: Interaction):
    discord_id = interaction.user.id
    avatar_url = interaction.user.avatar.url
    user_data = db.get_link_entry(discord_id)
    if not user_data:
        await interaction.response.send_message(
            embed=create_message_embed(
                "You don't have an account linked.", GANYU_COLORS["dark"]
            )
        )
        return
    user_client = get_client(user_data["ltuid"], user_data["ltoken"])
    # Using API takes time, keep interaction alive by sending a "loading" response
    await interaction.response.send_message(embed=util.loading_embed())
    try:
        diary = await user_client.get_genshin_diary()
        pages = [
            util.create_report_overview_embed(diary, avatar_url),
            util.create_report_breakdown_embed(diary, avatar_url),
        ]
        view = MessageBook(discord_id, avatar_url, pages, interaction)
        await interaction.edit_original_message(embed=pages[0], view=view)

    except Exception:
        traceback.print_exc()
        embed = create_message_embed(
            "Something went wrong... if you changed your password recently, you will have to relink with new cookies."
        )
        await interaction.edit_original_message(embed=embed)


@bot.slash_command(name="redeem", description="Attempts to redeem a code.")
async def redeem(interaction: Interaction, code: str):
    discord_id = interaction.user.id
    user_data = db.get_link_entry(discord_id)
    if not user_data:
        await interaction.response.send_message(
            embed=create_message_embed(
                "You don't have an account linked.", GANYU_COLORS["dark"]
            )
        )
        return

    need_code_setup = (
        user_data["account_id"] is None or user_data["cookie_token"] is None
    )
    if need_code_setup:
        await interaction.response.send_message(
            embed=util.create_message_embed(
                "You need to add additional authentication cookies to redeem codes.\n"
                "Log into https://genshin.hoyoverse.com/en/gift, find `account_id` and `cookie_token`,"
                " then use `/linkcode`.",
                color=GANYU_COLORS["dark"],
            )
        )
        return

    user_client = get_client(user_data["ltuid"], user_data["ltoken"])
    user_client.set_browser_cookies(
        account_id=user_data["account_id"], cookie_token=user_data["cookie_token"]
    )

    # Using API takes time, keep interaction alive by sending a "loading" response
    await interaction.response.send_message(embed=util.loading_embed())
    try:
        await user_client.redeem_code(code)
        await interaction.edit_original_message(
            embed=util.create_message_embed(f"Successfully claimed code `{code}`!")
        )
    except RedemptionInvalid:
        await interaction.edit_original_message(
            embed=util.create_message_embed(
                f"Invalid code `{code}`!", color=GANYU_COLORS["dark"]
            )
        )
    except RedemptionClaimed:
        await interaction.edit_original_message(
            embed=util.create_message_embed(
                f"You've already redeemed `{code}`!", color=GANYU_COLORS["dark"]
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


@bot.slash_command(
    name="announcecode", description="Announces a code for easy redemption."
)
async def announce_code(interaction: Interaction, code: str):
    if interaction.channel.type is nextcord.ChannelType.private:
        await interaction.response.send_message(
            embed=util.create_message_embed(
                "This can only be used in servers.", color=GANYU_COLORS["dark"]
            )
        )
        return

    if not interaction.user.guild_permissions.manage_messages:
        await interaction.response.send_message(
            embed=util.create_message_embed(
                "You need the `Manage Messages` " "permission to use this command!",
                color=GANYU_COLORS["dark"],
            )
        )
        return

    if len(code.split(" ")) > 1:
        await interaction.response.send_message(
            embed=util.create_message_embed(
                "The code needs to be one continuous string."
            ),
            ephemeral=True,
        )
        return

    await interaction.response.send_message(
        view=util.CodeAnnouncement(code),
        embed=util.create_code_announcement_embed(code),
    )


@bot.slash_command(name="log", description="Ganyu mod usage only.")
async def log(interaction: Interaction):
    discord_id = interaction.user.id
    settings = util.get_settings()
    if discord_id not in settings["ganyu_mods"]:
        await interaction.response.send_message(
            embed=create_message_embed(
                "You can't use this command...", GANYU_COLORS["dark"]
            )
        )
        return

    if interaction.channel.type is nextcord.ChannelType.private:
        await interaction.response.send_message(
            embed=create_message_embed(
                f"Can't set master log channel to private DMs", GANYU_COLORS["dark"]
            )
        )
        return

    settings["log_channel"] = interaction.channel_id
    util.set_settings(settings)
    await interaction.response.send_message(
        embed=create_message_embed(
            f"Master log channel set to <#{interaction.channel_id}>",
            GANYU_COLORS["dark"],
        )
    )


@bot.slash_command(name="sendlog", description="Ganyu mod usage only.")
async def sendlog(interaction: Interaction, message: str):
    discord_id = interaction.user.id
    settings = util.get_settings()
    if discord_id not in settings["ganyu_mods"]:
        await interaction.response.send_message(
            embed=create_message_embed(
                "You can't use this command...", GANYU_COLORS["dark"]
            )
        )
        return

    log_channel_id = settings.get("log_channel")
    if log_channel_id:
        channel = bot.get_channel(log_channel_id)
        if channel is None:
            await interaction.response.send_message(
                embed=create_message_embed(
                    f"Master log channel is invalid (may have been deleted)"
                )
            )
            return

        await channel.send(embed=create_message_embed(message))
        await interaction.response.send_message(
            embed=create_message_embed(f"Message sent to <#{log_channel_id}>")
        )
    else:
        await interaction.response.send_message(
            embed=create_message_embed(f"No master log channel is set")
        )


@bot.slash_command(name="ganyustatus", description="Ganyu mod usage only.")
async def ganyu_status(interaction: Interaction):
    discord_id = interaction.user.id
    settings = util.get_settings()

    if discord_id not in settings["ganyu_mods"]:
        await interaction.response.send_message(
            embed=create_message_embed(
                "You can't use this command...", GANYU_COLORS["dark"]
            )
        )
        return

    user_count = db.user_count()
    bot_accounts = len(settings["accounts"])
    log_channel_id = settings.get("log_channel")

    embed = nextcord.Embed(title=f"Ganyu Status")
    embed.add_field(name="Linked Users", value=user_count)
    embed.add_field(name="Bot Accounts", value=bot_accounts)
    if log_channel_id:
        embed.add_field(name="Log Channel", value=f"<#{log_channel_id}>", inline=False)
    jobs = util.get_scheduler_jobs(scheduler)
    next_timestamp = None
    next_code_timestamp = None
    next_activity_feed_timestamp = None
    for job in jobs:
        if job["id"] == "daily_rewards":
            next_timestamp = job["next_run_time"].timestamp()
        if job["id"] == "code_poller":
            next_code_timestamp = job["next_run_time"].timestamp()
        if job["id"] == "activity_feed_update":
            next_activity_feed_timestamp = job["next_run_time"].timestamp()

    if next_timestamp:
        embed.add_field(
            name="Next Reward Collection",
            value=f"<t:{int(next_timestamp)}:F>",
            inline=False,
        )
    if next_code_timestamp:
        embed.add_field(
            name="Next Code Poll Time",
            value=f"<t:{int(next_code_timestamp)}:F>",
            inline=False,
        )
    if next_activity_feed_timestamp:
        embed.add_field(
            name="Next Activity Feed Update",
            value=f"<t:{int(next_activity_feed_timestamp)}:F>",
            inline=False,
        )

    embed.colour = GANYU_COLORS["dark"]
    embed.set_thumbnail(url=bot.user.avatar.url)
    await interaction.response.send_message(embed=embed)


@bot.slash_command(name="listalts", description="Ganyu mod usage only.")
async def list_alts(interaction: Interaction):
    discord_id = interaction.user.id
    settings = util.get_settings()

    if discord_id not in settings["ganyu_mods"]:
        await interaction.response.send_message(
            embed=create_message_embed(
                "You can't use this command...", GANYU_COLORS["dark"]
            )
        )
        return

    alt_accounts = db.get_all_alts()
    description_lines = []
    for alt in alt_accounts:
        description_lines.append(f"{alt['id']} ({alt['name']}): **{alt['uid']}**")

    embed = nextcord.Embed(
        title=f"Linked Alts", description="\n".join(description_lines)
    )
    embed.colour = GANYU_COLORS["dark"]
    embed.set_thumbnail(url=bot.user.avatar.url)
    await interaction.response.send_message(embed=embed)


@scheduler.scheduled_job(util.DAILY_REWARD_CRON_TRIGGER, id="daily_rewards")
async def auto_collect_daily_rewards():

    users = db.get_all_auto_checkin_users()
    alt_users = db.get_all_alts()

    settings = util.get_settings()
    log_channel_id = settings.get("log_channel")
    success = 0
    start_time = int(time.time())
    if log_channel_id:
        channel = bot.get_channel(log_channel_id)
        if channel:
            # Seems like geetests are gone for the time being
            # await channel.send(embed=create_message_embed(
            #     "Autoclaiming is disabled due to Geetests.\nManually claim your daily reward [here](https://act.hoyolab.com/ys/event/signin-sea-v3/index.html?act_id=e202102251931481)."
            # ))
            # return
            await channel.send(
                embed=create_message_embed(
                    f"Collecting daily rewards for **{len(users)}** user(s), **{len(alt_users)}** alt(s)..."
                )
            )

    failed_users = []
    for user_data in users:
        user_client = get_client(user_data["ltuid"], user_data["ltoken"])
        try:
            await user_client.claim_daily_reward(reward=False)
            success += 1
        except GenshinException:
            failed_users.append(user_data["discord_id"])

        await asyncio.sleep(random.randint(0, 2))

    failed_alt_users = []
    for user_data in alt_users:
        user_client = get_client(user_data["ltuid"], user_data["ltoken"])
        try:
            await user_client.claim_daily_reward(reward=False)
            success += 1
        except GenshinException:
            failed_alt_users.append(user_data["name"])

        await asyncio.sleep(random.randint(0, 2))

    time_elapsed = int(time.time()) - start_time
    if log_channel_id:
        channel = bot.get_channel(log_channel_id)
        if channel:
            await channel.send(
                embed=create_message_embed(
                    f"Successfully collected rewards for {success}/{len(users) + len(alt_users)} user(s)\n"
                    f"Time elapsed: {time_elapsed} second(s)"
                )
            )
            if failed_users:
                fails = [f"<@{user_id}>" for user_id in failed_users]
                for name in failed_alt_users:
                    fails.append(f"**{name}**")

                failed_text = " ".join(fails[:20])
                if len(fails) > 20:
                    failed_text += f" and {len(fails) - 20} more..."

                await channel.send(
                    embed=create_message_embed(f"Failed users: {failed_text}")
                )

            jobs = util.get_scheduler_jobs(scheduler)
            next_timestamp = None
            for job in jobs:
                if job["id"] == "daily_rewards":
                    next_timestamp = job["next_run_time"].timestamp()

            if next_timestamp:
                await channel.send(
                    embed=create_message_embed(
                        f"Next collection scheduled for <t:{int(next_timestamp)}:F>"
                    )
                )


# @scheduler.scheduled_job(util.CODE_POLLER_CRON_TRIGGER, id="code_poller")
async def poll_for_reddit_codes():
    headers = {"User-Agent": "GanyuBot 3.0"}

    QUERY_URL = (
        "https://old.reddit.com/r/Genshin_Impact/search.json?q=code&restrict_sr=1&t=day"
    )
    TEST_URL = "https://old.reddit.com/r/Genshin_Impact/search.json?q=code&restrict_sr=1&t=week"
    res = requests.get(QUERY_URL, headers=headers)
    search_data = res.json()

    code_regex = re.compile(r" *[A-Z0-9]{12} *")
    code_link_regex = re.compile(
        r" *https:\/\/genshin\.hoyoverse\.com\/en\/gift\?code=[A-Z0-9]{12} *"
    )
    code_keyword_regex = re.compile(r"(\w+ )?codes?", re.IGNORECASE)

    codes = set()
    for post in search_data["data"]["children"]:
        title = post["data"]["title"]
        body = post["data"]["selftext"]
        id = post["data"]["id"]
        # cache_key = f"reddit_{id}"
        # if cache_key in cache:
        #     continue

        if (
            code_regex.search(title + "\n" + body)
            or code_keyword_regex.search(title + "\n" + body)
            or code_link_regex.search(title + "\n" + body)
        ):
            raw_codes = code_regex.findall(title + "\n" + body)
            code_links = code_link_regex.findall(title + "\n" + body)
            comment_codes = []
            # search comments
            post_url = f"https://www.reddit.com{post['data']['permalink'][:-1]}.json"
            post_res = requests.get(post_url, headers=headers)
            post_data = post_res.json()
            if len(post_data) > 1:
                comments = post_data[1]
                for comment in comments["data"]["children"]:
                    comment_body = comment["data"].get("body", "")
                    comment_codes = code_regex.findall(
                        comment_body
                    ) + code_link_regex.findall(comment_body)

            # add codes from title, body, and comments
            for code in list(dict.fromkeys(raw_codes + code_links + comment_codes)):
                code = code.strip()[-12:]
                if f"code_{code}" not in cache:
                    codes.add(code)
                    cache.set(
                        f"code_{code}", code, expire=604800
                    )  # 1 wk cache for codes (codes shouldn't be reposted though)

        # cache.set(cache_key, cache_key, expire=86400) # 24 hr cache

    logging.info(f"Found new reddit codes {codes}")

    settings = util.get_settings()
    log_channel_id = settings.get("log_channel")

    if log_channel_id:
        channel = bot.get_channel(log_channel_id)
        if channel:
            for code in codes:
                await channel.send(
                    view=util.CodeAnnouncement(code),
                    embed=util.create_code_discovery_embed(code),
                )


@scheduler.scheduled_job(util.ACTIVITY_FEED_CRON_TRIGGER, id="activity_feed_update")
async def poll_enka():

    users = db.get_all_tracked_users()

    settings = util.get_settings()
    log_channel_id = settings.get("log_channel")
    channel = None
    if log_channel_id:
        channel = bot.get_channel(log_channel_id)

    for user in users:

        uid = user["uid"]
        last_activity = db.get_latest_activity(user["discord_id"])

        headers = {"User-Agent": "GanyuBot 3.0"}

        try:
            res = requests.get(
                f"https://enka.network/api/uid/{uid}?info", headers=headers
            )
            enka_data = res.json()
            db.log_activity(user["discord_id"], enka_data)
            if last_activity and channel:
                player_info = enka_data["playerInfo"]
                if (
                    last_activity["level"] != player_info["level"]
                    or last_activity["world_level"] != player_info["worldLevel"]
                    or last_activity["finish_achievement_num"]
                    != player_info["finishAchievementNum"]
                    or last_activity["tower_floor_index"]
                    != player_info["towerFloorIndex"]
                    or last_activity["tower_level_index"]
                    != player_info["towerLevelIndex"]
                ):
                    embed = create_activity_update_embed(
                        user["discord_id"], uid, last_activity, player_info
                    )
                    await channel.send(embed=embed)
        except Exception:
            import traceback

            logging.info(f"Error while fetching enka data for uid {uid}; skipping")
            traceback.print_exc()

        # sleep to not spam enka api and get rate limited
        await asyncio.sleep(2)


@scheduler.scheduled_job(util.ACTIVITY_FEED_CLEANUP_TRIGGER, id="activity_feed_cleanup")
async def cleanup_activities():
    db.purge_activities()


@bot.event
async def on_ready():
    print("Logged into Discord!")
    init()
    scheduler.start()
    logging.info(util.get_scheduler_jobs(scheduler))
    await bot.discover_application_commands()
    await bot.sync_all_application_commands()


def init():
    global cache
    cache = Cache("cache")
    db.init()


if __name__ == "__main__":
    settings = util.get_settings()
    bot.run(settings["token"])
