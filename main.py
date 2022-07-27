import asyncio
import logging
import time
import random

import genshin
import nextcord
from nextcord import Interaction
from nextcord.ext import commands
from apscheduler.schedulers.asyncio import AsyncIOScheduler

import db
from diskcache import Cache

import util
from genshin.client import MultiCookieClient, Client
from genshin.errors import InvalidCookies, GenshinException, AlreadyClaimed, DataNotPublic
from util import create_message_embed, create_link_profile_embed, GANYU_COLORS, create_profile_card_embed, \
    ProfileChoices, create_reward_embed, create_status_embed, MessageBook

logging.basicConfig()
logging.getLogger().setLevel(logging.INFO)

bot = commands.Bot(command_prefix='!', intents=nextcord.Intents.all())
bot.remove_command('help')
cache = None
scheduler = AsyncIOScheduler(timezone='UTC')


@bot.slash_command(name='ping', description='Pong!')
async def ping(interaction: Interaction):
    await interaction.response.send_message('Pong!')


@bot.slash_command(name='link', description='Links a Genshin/Hoyolab account to your Discord user.')
async def link(interaction: Interaction, ltuid: str, ltoken: str):
    if interaction.channel.type is not nextcord.ChannelType.private:
        dm_channel = await interaction.user.create_dm()
        await dm_channel.send(
            embed=create_message_embed(
                "You can only use the link command in DMs with this bot, as it requires you to pass in sensitive "
                "information.",
                color=GANYU_COLORS['dark']
            )
        )
        return

    if not len(ltuid) == 9 or not ltuid.isnumeric():
        await interaction.response.send_message(embed=create_message_embed(
            "Invalid ltuid (must be 9 digits)!",
            GANYU_COLORS['dark']
        ))
        return

    user_client = Client({
        'ltuid': ltuid,
        'ltoken': ltoken
    })
    user_client.default_game = genshin.Game.GENSHIN
    # Using API takes time, keep interaction alive by sending a "loading" response
    await interaction.response.send_message(embed=util.loading_embed())
    try:
        accounts = await user_client.genshin_accounts()
        if len(accounts) > 0:
            uid = accounts[0].uid
            level = accounts[0].level
            username = accounts[0].nickname
            discord_id = interaction.user.id
            unlinked_discord_id = None

            if db.uid_exists(uid):
                unlinked_discord_id = db.delete_entry_by_uid(uid)

            db.update_link_entry(discord_id, uid, ltuid, ltoken)

            embed = create_link_profile_embed(discord_id,
                                              interaction.user.avatar.url,
                                              uid, level, username)
            if unlinked_discord_id:
                embed.set_footer(text=f'Warning: Old Discord user unlinked (ID {unlinked_discord_id})')

            await interaction.edit_original_message(embed=embed)
        else:
            await interaction.edit_original_message(embed=create_message_embed(
                "You don't have any genshin accounts!",
                GANYU_COLORS['dark']
            ))

    except InvalidCookies:
        await interaction.edit_original_message(embed=create_message_embed(
            "Invalid auth cookies!",
            GANYU_COLORS['dark']
        ))


@bot.slash_command(name='profile', description='Shows information about your linked user.')
async def profile(interaction: Interaction):
    discord_id = interaction.user.id
    discord_name = interaction.user.name
    avatar_url = interaction.user.avatar.url
    user_data = db.get_link_entry(discord_id)
    if user_data:
        user_settings = {
            'Auto Check-in': 'No' if user_data['daily_reward'] == 0 else 'Yes'
        }
        embed = create_profile_card_embed(discord_name, avatar_url, user_data['uid'], user_settings)
        view = ProfileChoices(discord_id, discord_name, avatar_url, interaction)
        await interaction.response.send_message(embed=embed, view=view)
    else:
        await interaction.response.send_message(embed=create_message_embed(
            "You don't have an account linked.",
            GANYU_COLORS['dark']
        ))


@bot.slash_command(name='claim', description='Attempt to manually claim your daily reward.')
async def claim(interaction: Interaction):
    discord_id = interaction.user.id
    user_data = db.get_link_entry(discord_id)
    if not user_data:
        await interaction.response.send_message(embed=create_message_embed(
            "You don't have an account linked.",
            GANYU_COLORS['dark']
        ))
        return

    user_client = Client({
        'ltuid': user_data['ltuid'],
        'ltoken': user_data['ltoken']
    })
    user_client.default_game = genshin.Game.GENSHIN
    # Using API takes time, keep interaction alive by sending a "loading" response
    await interaction.response.send_message(embed=util.loading_embed())
    try:
        reward = await user_client.claim_daily_reward()

        await interaction.edit_original_message(embed=create_reward_embed(reward.name, reward.amount, reward.icon))
    except AlreadyClaimed:
        await interaction.edit_original_message(embed=create_message_embed(
            "Daily reward was already claimed today!",
            GANYU_COLORS['dark']
        ))


@bot.slash_command(name='status', description='Shows some in-game stats on your account.')
async def status(interaction: Interaction):
    discord_id = interaction.user.id
    avatar_url = interaction.user.avatar.url
    user_data = db.get_link_entry(discord_id)
    if not user_data:
        await interaction.response.send_message(embed=create_message_embed(
            "You don't have an account linked.",
            GANYU_COLORS['dark']
        ))
        return

    user_client = Client({
        'ltuid': user_data['ltuid'],
        'ltoken': user_data['ltoken']
    })
    user_client.default_game = genshin.Game.GENSHIN
    # Using API takes time, keep interaction alive by sending a "loading" response
    await interaction.response.send_message(embed=util.loading_embed())
    try:
        notes = await user_client.get_notes(int(user_data['uid']))
        await interaction.edit_original_message(embed=create_status_embed(notes, avatar_url))
    except DataNotPublic:
        embed = create_message_embed("You need to enable Real-Time Notes in your HoyoLab privacy settings to use this!")
        embed.set_image(url=util.SETTINGS_IMG_URL)
        await interaction.edit_original_message(embed=embed)
    except Exception:
        embed = create_message_embed("Something went wrong... if you changed your password recently, you will have to relink with new cookies.")
        await interaction.edit_original_message(embed=embed)


@bot.slash_command(name='schedule', description='Shows current or upcoming events.')
async def schedule(interaction: Interaction, detailed: bool = False):
    discord_id = interaction.user.id
    avatar_url = interaction.user.avatar.url

    schedule_info = util.get_schedule_info()
    pages = []
    if not detailed:
        pages.append(util.create_schedule_embed(schedule_info, bot.user.avatar.url, False))
        pages.append(util.create_schedule_embed(schedule_info, bot.user.avatar.url, True))
    else:
        current = []
        future = []
        cur_time = int(time.time())

        for event in schedule_info:
            if event['start'] <= cur_time <= event['end']:
                current.append(event)
            elif event['start'] > cur_time:
                future.append(event)

        current.sort(key=lambda x: x['end'])
        future.sort(key=lambda x: x['start'])

        for event in current:
            pages.append(util.create_event_embed(event))

        for event in future:
            pages.append(util.create_event_embed(event))

    view = MessageBook(discord_id, avatar_url, pages, interaction)
    await interaction.response.send_message(embed=pages[0], view=view)


@bot.slash_command(name='income', description='Retrieves a report of your primogem/mora income.')
async def income(interaction: Interaction):
    discord_id = interaction.user.id
    avatar_url = interaction.user.avatar.url
    user_data = db.get_link_entry(discord_id)
    if not user_data:
        await interaction.response.send_message(embed=create_message_embed(
            "You don't have an account linked.",
            GANYU_COLORS['dark']
        ))
        return
    user_client = Client({
        'ltuid': user_data['ltuid'],
        'ltoken': user_data['ltoken']
    })
    user_client.default_game = genshin.Game.GENSHIN
    # Using API takes time, keep interaction alive by sending a "loading" response
    await interaction.response.send_message(embed=util.loading_embed())
    try:
        diary = await user_client.get_diary()
        pages = [
            util.create_report_overview_embed(diary, avatar_url),
            util.create_report_breakdown_embed(diary, avatar_url)
        ]
        view = MessageBook(discord_id, avatar_url, pages, interaction)
        await interaction.edit_original_message(embed=pages[0], view=view)

    except Exception:
        embed = create_message_embed("Something went wrong... if you changed your password recently, you will have to relink with new cookies.")
        await interaction.edit_original_message(embed=embed)


@bot.slash_command(name='log', description='Ganyu mod usage only.')
async def log(interaction: Interaction):
    discord_id = interaction.user.id
    settings = util.get_settings()
    if discord_id not in settings['ganyu_mods']:
        await interaction.response.send_message(embed=create_message_embed(
            "You can't use this command...",
            GANYU_COLORS['dark']
        ))
        return

    if interaction.channel.type is nextcord.ChannelType.private:
        await interaction.response.send_message(embed=create_message_embed(
            f"Can't set master log channel to private DMs",
            GANYU_COLORS['dark']
        ))
        return

    settings['log_channel'] = interaction.channel_id
    util.set_settings(settings)
    await interaction.response.send_message(embed=create_message_embed(
        f"Master log channel set to <#{interaction.channel_id}>",
        GANYU_COLORS['dark']
    ))


@bot.slash_command(name='sendlog', description='Ganyu mod usage only.')
async def sendlog(interaction: Interaction, message: str):
    discord_id = interaction.user.id
    settings = util.get_settings()
    if discord_id not in settings['ganyu_mods']:
        await interaction.response.send_message(embed=create_message_embed(
            "You can't use this command...",
            GANYU_COLORS['dark']
        ))
        return

    log_channel_id = settings.get('log_channel')
    if log_channel_id:
        channel = bot.get_channel(log_channel_id)
        if channel is None:
            await interaction.response.send_message(embed=create_message_embed(
                f"Master log channel is invalid (may have been deleted)"
            ))
            return

        await channel.send(embed=create_message_embed(
            message
        ))
        await interaction.response.send_message(embed=create_message_embed(
            f"Message sent to <#{log_channel_id}>"
        ))
    else:
        await interaction.response.send_message(embed=create_message_embed(
            f"No master log channel is set"
        ))


@bot.slash_command(name='ganyustatus', description='Ganyu mod usage only.')
async def ganyu_status(interaction: Interaction):
    discord_id = interaction.user.id
    settings = util.get_settings()

    if discord_id not in settings['ganyu_mods']:
        await interaction.response.send_message(embed=create_message_embed(
            "You can't use this command...",
            GANYU_COLORS['dark']
        ))
        return

    user_count = db.user_count()
    bot_accounts = len(settings['accounts'])
    log_channel_id = settings.get('log_channel')

    embed = nextcord.Embed(title=f"Ganyu Status")
    embed.add_field(name="Linked Users", value=user_count)
    embed.add_field(name="Bot Accounts", value=bot_accounts)
    if log_channel_id:
        embed.add_field(name="Log Channel", value=f'<#{log_channel_id}>', inline=False)
    jobs = util.get_scheduler_jobs(scheduler)
    next_timestamp = None
    for job in jobs:
        if job['id'] == 'daily_rewards':
            next_timestamp = job['next_run_time'].timestamp()

    if next_timestamp:
        embed.add_field(name="Next Reward Collection", value=f'<t:{int(next_timestamp)}:F>', inline=False)

    embed.colour = GANYU_COLORS['dark']
    embed.set_thumbnail(url=bot.user.avatar.url)
    await interaction.response.send_message(embed=embed)


@scheduler.scheduled_job(util.DAILY_REWARD_CRON_TRIGGER, id='daily_rewards')
async def auto_collect_daily_rewards():
    users = db.get_all_auto_checkin_users()
    settings = util.get_settings()
    log_channel_id = settings.get('log_channel')
    success = 0
    start_time = int(time.time())
    if log_channel_id:
        channel = bot.get_channel(log_channel_id)
        if channel:
            await channel.send(embed=create_message_embed(
                f"Collecting daily rewards for {len(users)} user(s)..."
            ))

    for user_data in users:
        user_client = Client({
            'ltuid': user_data['ltuid'],
            'ltoken': user_data['ltoken']
        })
        user_client.default_game = genshin.Game.GENSHIN
        try:
            await user_client.claim_daily_reward(reward=False)
            success += 1
        except GenshinException:
            pass

        await asyncio.sleep(random.randint(0, 2))

    time_elapsed = int(time.time()) - start_time
    if log_channel_id:
        channel = bot.get_channel(log_channel_id)
        if channel:
            await channel.send(embed=create_message_embed(
                f"Successfully collected rewards for {success}/{len(users)} user(s)\n"
                f"Time elapsed: {time_elapsed} second(s)"
            ))
            jobs = util.get_scheduler_jobs(scheduler)
            next_timestamp = None
            for job in jobs:
                if job['id'] == 'daily_rewards':
                    next_timestamp = job['next_run_time'].timestamp()

            if next_timestamp:
                await channel.send(embed=create_message_embed(
                    f"Next collection scheduled for <t:{int(next_timestamp)}:F>"
                ))


@bot.event
async def on_ready():
    print('Logged into Discord!')
    init()
    scheduler.start()
    logging.info(util.get_scheduler_jobs(scheduler))
    await bot.associate_application_commands()
    await bot.delete_unknown_application_commands()


def init():
    global cache
    cache = Cache("cache")
    db.init()


if __name__ == '__main__':
    settings = util.get_settings()
    bot.run(settings['token'])
