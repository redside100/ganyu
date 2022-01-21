import json

from nextcord import Interaction
from nextcord.ui.view import View
import nextcord
import db

GANYU_COLORS = {
    'light': 0xb5c5d7,
    'dark': 0x505ea9
}


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


def create_link_profile_embed(discord_id, discord_avatar_url, uid, level, username):
    embed = nextcord.Embed(title=f"Successfully linked!")
    embed.add_field(name="UID", value=uid)
    embed.add_field(name="Name", value=username)
    embed.add_field(name="Adventure Rank", value=level)
    embed.add_field(name="Discord User", value=f"<@{discord_id}>")
    embed.set_thumbnail(url=discord_avatar_url)
    embed.colour = GANYU_COLORS['dark']

    return embed


def create_profile_card_embed(discord_name, discord_id, discord_avatar_url, uid, user_settings):
    embed = nextcord.Embed(title=discord_name)
    embed.add_field(name="UID", value=uid)
    for setting in user_settings:
        embed.add_field(name=setting, value=user_settings[setting])

    embed.set_thumbnail(url=discord_avatar_url)
    embed.colour = GANYU_COLORS['dark']

    return embed


def create_reward_embed(name, amount, icon_url):
    embed = nextcord.Embed(title="Reward Claimed", description=f"Got {amount}x {name}")
    embed.set_thumbnail(url=icon_url)
    return embed


def create_message_embed(message, color=GANYU_COLORS['dark'], thumbnail=None):
    embed = nextcord.Embed(description=message)
    embed.colour = color
    if thumbnail:
        embed.set_thumbnail(url=thumbnail)

    return embed


class ProfileChoices(View):
    def __init__(self, user_id, user_name, user_avatar, base_interaction):
        super().__init__(timeout=120)
        self.base_interaction: Interaction = base_interaction
        self.user_avatar = user_avatar
        self.user_name = user_name
        self.user_id = user_id

    @nextcord.ui.button(label="Toggle Check-in", style=nextcord.ButtonStyle.blurple)
    async def toggle_check_in(self, button: nextcord.ui.Button, interaction: nextcord.Interaction):
        if not interaction.user.id == self.user_id:
            return

        user_data = db.get_link_entry(self.user_id)
        if not user_data:
            self.stop()

        db.set_daily_reward(self.user_id, not user_data['daily_reward'])
        user_settings = {
            'Auto Check-in': 'No' if not user_data['daily_reward'] == 0 else 'Yes'
        }
        embed = create_profile_card_embed(self.user_name, self.user_id, self.user_avatar, user_data['uid'], user_settings)
        await self.base_interaction.edit_original_message(embed=embed)


