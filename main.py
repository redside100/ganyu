import nextcord
from nextcord import Interaction, PartialMessageable
from nextcord.abc import GuildChannel
from nextcord.ext import commands

import json
import db
from diskcache import Cache

import util
from genshin.genshin.client import MultiCookieClient, GenshinClient
from genshin.genshin.errors import InvalidCookies, GenshinException, AlreadyClaimed, DataNotPublic
from util import create_message_embed, create_link_profile_embed, GANYU_COLORS, create_profile_card_embed, \
    ProfileChoices, create_reward_embed, create_status_embed

bot = commands.Bot(command_prefix='!', intents=nextcord.Intents.all())
bot.remove_command('help')
settings = None
cache = None


@bot.slash_command(name='ping', description='Pong!')
async def ping(interaction: Interaction):
    await interaction.response.send_message('Pong!')


@bot.slash_command(name='link', description='Links a Genshin/Hoyolab account to your Discord user.')
async def link(interaction: Interaction, ltuid: str, ltoken: str):
    if isinstance(interaction.channel, GuildChannel):
        if interaction.user.dm_channel:
            await interaction.user.dm_channel.send(embed=create_message_embed(
                "You should only use the link command in DMs with this bot, as it requires you to pass in sensitive "
                "information!",
                color=GANYU_COLORS['dark']
            ))
        else:
            dm_channel = await interaction.user.create_dm()
            await dm_channel.send(
                embed=create_message_embed(
                    "You should only use link command in DMs with this bot, as it requires you to pass in sensitive "
                    "information!",
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

    user_client = GenshinClient({
        'ltuid': ltuid,
        'ltoken': ltoken
    })
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
                embed.set_footer(text=f'Warning: Old discord user unlinked (ID {unlinked_discord_id})')

            await interaction.response.send_message(embed=embed)
        else:
            await interaction.response.send_message(embed=create_message_embed(
                "You don't have any genshin accounts!",
                GANYU_COLORS['dark']
            ))

    except InvalidCookies:
        await interaction.response.send_message(embed=create_message_embed(
            "Invalid auth cookies!",
            GANYU_COLORS['dark']
        ))

    await user_client.close()


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

    user_client = GenshinClient({
        'ltuid': user_data['ltuid'],
        'ltoken': user_data['ltoken']
    })

    try:
        reward = await user_client.claim_daily_reward()

        await interaction.response.send_message(embed=create_reward_embed(reward.name, reward.amount, reward.icon))
    except AlreadyClaimed:
        await interaction.response.send_message(embed=create_message_embed(
            "Daily reward was already claimed today!",
            GANYU_COLORS['dark']
        ))

    await user_client.close()


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

    user_client = GenshinClient({
        'ltuid': user_data['ltuid'],
        'ltoken': user_data['ltoken']
    })

    try:
        notes = await user_client.get_notes(int(user_data['uid']))
        await interaction.response.send_message(embed=create_status_embed(notes, avatar_url))
    except DataNotPublic:
        embed = create_message_embed("You need to enable Real-Time Notes in your HoyoLab privacy settings to use this!")
        embed.set_image(url=util.SETTINGS_IMG_URL)
        await interaction.response.send_message(embed=embed)

    await user_client.close()


@bot.event
async def on_ready():
    print('Logged into Discord!')
    init()
    await bot.associate_application_commands()
    await bot.delete_unknown_application_commands()


def init():
    global cache
    cache = Cache("cache")
    db.init()


if __name__ == '__main__':
    with open("settings.json") as f:
        settings = json.loads(f.read())

    bot.run(settings['token'])
