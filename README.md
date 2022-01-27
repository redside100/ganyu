# Ganyu
A Discord bot used to query information related to user linked Genshin Impact accounts.
Built mainly off of thesadru's [genshin.py](https://github.com/thesadru/genshin.py).

![Ganyu](https://i.imgur.com/Z4wnRFJ.jpg)

## Features
### Account Linking
Users can link their Genshin Impact account to the bot, in order to use commands.
It requires them to input their `ltuid` and `ltoken` cookie values obtained from
https://www.hoyolab.com/. Currently, it will only link the first Genshin account listed from
their user (in case they have different accounts for different regions).

### Real-Time Notes Status
Users can request their in-game resin, commissions done, and expedition statuses. They have to have
their Real-Time Notes enabled in their HoyoLab privacy settings.

### Income Report
Users can request a report of their monthly/daily primogem and mora income.
It also includes a breakdown of their primogem income sources.

### Daily Check-In Reward
Users can claim their daily check-in reward with the bot. The bot also automatically 
claims daily check-in rewards every day from 5:00 - 6:00 UTC for linked users with the auto claim option enabled, which is
toggleable through `/profile`.

### Event Schedule
A standard event schedule obtained from https://paimon.moe.

## Setup

Clone the repository

`git clone git@github.com:redside100/ganyu.git && cd ganyu`

Install dependencies (Python 3.9+)

`pip install -r requirements.txt`

Copy templates

`cp templates/* .`

In `settings.json`, fill in the `token` key with your Discord bot's token.

If you want to add moderators (who can use more privileged commands), you can add
their Discord IDs into the `ganyu_mods` list.

## Run

`python main.py`

If you want to run it in a Docker container, a Dockerfile is provided.

`docker build -t ganyu .`

You should probably mount a `cache` folder and `ganyu.db` when running the container.

## Server Usage

If you plan on inviting the bot to a Discord server, make sure to invite it with
application command permissions. Once the bot is invited, you can choose to set a channel
for daily collection logs.