import discord
from discord.ext import commands, tasks
import os
from dotenv import load_dotenv
from datetime import datetime
from collections import defaultdict
import json
import re
import random
import asyncio

# -----------------------------
# Load Environment
# -----------------------------
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# -----------------------------
# Configuration Files
# -----------------------------
OFFENSES_FILE = "offenses.json"
PREFIXES_FILE = "prefixes.json"
USERDATA_FILE = "userdata.json"

# Load offenses
if os.path.exists(OFFENSES_FILE):
    with open(OFFENSES_FILE, "r") as f:
        user_offenses = defaultdict(list, json.load(f))
else:
    user_offenses = defaultdict(list)

# Load prefixes
if os.path.exists(PREFIXES_FILE):
    with open(PREFIXES_FILE, "r") as f:
        prefixes = json.load(f)
else:
    prefixes = {}

# Load user data
if os.path.exists(USERDATA_FILE):
    with open(USERDATA_FILE, "r") as f:
        data = json.load(f)
        user_points = defaultdict(int, {int(k): v["points"] for k, v in data.items()})
        user_xp = defaultdict(int, {int(k): v["xp"] for k, v in data.items()})
        user_level = defaultdict(int, {int(k): v["level"] for k, v in data.items()})
else:
    user_points = defaultdict(int)
    user_xp = defaultdict(int)
    user_level = defaultdict(int)

def save_userdata():
    data = {str(k): {"points": user_points[k], "xp": user_xp[k], "level": user_level[k]} for k in user_points}
    with open(USERDATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

# -----------------------------
# Bot Setup
# -----------------------------
intents = discord.Intents.all()
intents.message_content = True
intents.members = True

def get_prefix(bot, message):
    return prefixes.get(str(message.guild.id), "!")

bot = commands.Bot(command_prefix=get_prefix, intents=intents)
bot.remove_command("help")

# -----------------------------
# Configuration
# -----------------------------
illegalWords = ["egg", "exampleword1", "exampleword2"]
logChannelID = 1429033263699071057
userWarningChannelID = None

# Auto-moderation thresholds
WARN_THRESHOLD = 1
MUTE_THRESHOLD = 4
MUTE_DURATION = 60*5
MUTE_ROLE_NAME = "Muted"
KICK_THRESHOLD = 3
BAN_THRESHOLD = 5

# Anti-spam
SPAM_THRESHOLD = 5
SPAM_INTERVAL = 10
user_message_times = defaultdict(list)

# Economy and leveling
XP_PER_MESSAGE = 5
LEVEL_UP_BASE = 100
LEVEL_MULTIPLIER = 1.5

# Welcome messages
welcome_messages = {}

# Reaction roles
reaction_roles = {
    "👍": "Member",
    "🎮": "Gamer",
    "🎨": "Artist"
}

# -----------------------------
# Helper Functions
# -----------------------------
def save_offenses():
    with open(OFFENSES_FILE, "w") as f:
        json.dump(user_offenses, f, indent=4)

def contains_illegal_word(message_content):
    content = re.sub(r"[^\w\s]", "", message_content.lower())
    return any(word.lower() in content for word in illegalWords)

def record_offense(user_id, content, channel_name, message_link):
    offense = {
        "time": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
        "content": content,
        "channel": channel_name,
        "link": message_link
    }
    user_offenses[str(user_id)].append(offense)
    save_offenses()
    return len(user_offenses[str(user_id)])

def add_xp(user_id):
    user_xp[user_id] += XP_PER_MESSAGE
    next_level_xp = int(LEVEL_UP_BASE * (LEVEL_MULTIPLIER ** user_level[user_id]))
    leveled_up = False
    while user_xp[user_id] >= next_level_xp:
        user_xp[user_id] -= next_level_xp
        user_level[user_id] += 1
        leveled_up = True
        next_level_xp = int(LEVEL_UP_BASE * (LEVEL_MULTIPLIER ** user_level[user_id]))
    save_userdata()
    return leveled_up

async def handle_auto_moderation(message, offenses_count):
    author = message.author
    mod_channel = bot.get_channel(logChannelID)
    try:
        if offenses_count == KICK_THRESHOLD:
            await author.kick(reason=f"Reached {KICK_THRESHOLD} offenses.")
            if mod_channel:
                await mod_channel.send(f"⚠️ {author.mention} has been **kicked** automatically.")
        elif offenses_count == BAN_THRESHOLD:
            await author.ban(reason=f"Reached {BAN_THRESHOLD} offenses.")
            if mod_channel:
                await mod_channel.send(f"⛔ {author.mention} has been **banned** automatically.")
        elif offenses_count == MUTE_THRESHOLD:
            guild = message.guild
            mute_role = discord.utils.get(guild.roles, name=MUTE_ROLE_NAME)
            if mute_role:
                await author.add_roles(mute_role, reason=f"Reached {MUTE_THRESHOLD} offenses")
                if mod_channel:
                    await mod_channel.send(f"🔇 {author.mention} has been **muted** for {MUTE_DURATION//60} minutes.")
                await asyncio.sleep(MUTE_DURATION)
                await author.remove_roles(mute_role, reason="Mute duration expired")
                if mod_channel:
                    await mod_channel.send(f"✅ {author.mention} has been **unmuted** after mute duration.")
    except Exception as e:
        if mod_channel:
            await mod_channel.send(f"❌ Failed auto-moderation action on {author.mention}: {e}")

# -----------------------------
# Events
# -----------------------------
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user} (ID: {bot.user.id})")

@bot.event
async def on_member_join(member):
    channel = member.guild.system_channel
    msg = welcome_messages.get(member.guild.id)
    if channel:
        if msg:
            await channel.send(msg.replace("{user}", member.mention))
        else:
            await channel.send(f"👋 Welcome {member.mention} to {member.guild.name}!")
    role = discord.utils.get(member.guild.roles, name="Member")
    if role:
        await member.add_roles(role)

@bot.event
async def on_message_edit(before, after):
    if before.author.bot or before.content == after.content:
        return
    mod_channel = bot.get_channel(logChannelID)
    if mod_channel:
        await mod_channel.send(
            f"✏️ **Message Edited**\n"
            f"**Author:** {before.author.mention}\n"
            f"**Channel:** #{before.channel.name}\n"
            f"**Before:** {before.content}\n"
            f"**After:** {after.content}"
        )

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    # Anti-spam
    now = datetime.utcnow().timestamp()
    times = user_message_times[message.author.id]
    times.append(now)
    user_message_times[message.author.id] = [t for t in times if now - t <= SPAM_INTERVAL]
    if len(user_message_times[message.author.id]) > SPAM_THRESHOLD:
        await message.channel.send(f"{message.author.mention}, please stop spamming!")
        await message.delete()
        return

    # Economy and leveling
    user_points[message.author.id] += 1
    leveled_up = add_xp(message.author.id)
    if leveled_up:
        await message.channel.send(f"🎉 {message.author.mention} has leveled up to **Level {user_level[message.author.id]}**!")

    # Moderation
    if contains_illegal_word(message.content):
        message_link = message.jump_url
        author = message.author
        content = message.content
        channel_name = message.channel.name

        await message.delete()
        offenses_count = record_offense(author.id, content, channel_name, message_link)

        mod_channel = bot.get_channel(logChannelID)
        if mod_channel:
            await mod_channel.send(
                f"🚨 **Message Deleted**\n"
                f"**Author:** {author.mention} ({author.id})\n"
                f"**Channel:** #{channel_name}\n"
                f"**Time:** {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}\n"
                f"**Content:** {content}\n"
                f"[Jump to message]({message_link})\n"
                f"**Total Offenses:** {offenses_count}"
            )

        if userWarningChannelID:
            warning_channel = bot.get_channel(userWarningChannelID)
            if warning_channel:
                await warning_channel.send(
                    f"{author.mention}, your message was deleted for prohibited content. "
                    f"This is offense #{offenses_count}."
                )

        await handle_auto_moderation(message, offenses_count)

    await bot.process_commands(message)

@bot.event
async def on_raw_reaction_add(payload):
    guild = bot.get_guild(payload.guild_id)
    member = guild.get_member(payload.user_id)
    if member.bot:
        return
    role_name = reaction_roles.get(str(payload.emoji))
    if role_name:
        role = discord.utils.get(guild.roles, name=role_name)
        if role:
            await member.add_roles(role)
            channel = guild.get_channel(payload.channel_id)
            await channel.send(f"{member.mention} got the role **{role_name}**!")

@bot.event
async def on_raw_reaction_remove(payload):
    guild = bot.get_guild(payload.guild_id)
    member = guild.get_member(payload.user_id)
    role_name = reaction_roles.get(str(payload.emoji))
    if role_name:
        role = discord.utils.get(guild.roles, name=role_name)
        if role:
            await member.remove_roles(role)

# -----------------------------
# Moderation Commands
# -----------------------------
@bot.command()
async def ping(ctx):
    await ctx.send("Pong!")

@bot.command()
@commands.has_permissions(manage_messages=True)
async def purge(ctx, amount: int):
    deleted = await ctx.channel.purge(limit=amount)
    log_channel = bot.get_channel(logChannelID)

    # Collect messages data
    lines = []
    for msg in deleted:
        timestamp = msg.created_at.strftime("%Y-%m-%d %H:%M:%S UTC")
        author = f"{msg.author} ({msg.author.id})"
        content = msg.content
        lines.append(f"[{timestamp}] {author}: {content}")

    # Save to txt
    if lines and log_channel:
        filename = f"purge_{ctx.channel.id}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.txt"
        with open(filename, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        await log_channel.send(f"🗑️ {len(deleted)} messages deleted in #{ctx.channel.name}:", file=discord.File(filename))
        os.remove(filename)

    await ctx.send(f"🗑️ Deleted {len(deleted)} messages.", delete_after=5)

# -----------------------------
# Fun Commands
# -----------------------------
@bot.command()
async def roll(ctx, sides: int = 6):
    await ctx.send(f"🎲 {ctx.author.mention} rolled a {random.randint(1, sides)} (1-{sides})")

@bot.command()
async def coinflip(ctx):
    await ctx.send(f"🪙 {ctx.author.mention} flipped a coin: {'Heads' if random.random() < 0.5 else 'Tails'}")

@bot.command()
async def eightball(ctx, *, question):
    responses = ["Yes.", "No.", "Maybe.", "Definitely!", "Absolutely not.", "Ask again later.", "It is certain.", "I have my doubts."]
    await ctx.send(f"🎱 {ctx.author.mention} asked: {question}\nAnswer: {random.choice(responses)}")

# -----------------------------
# Economy & Leveling Commands
# -----------------------------
@bot.command()
async def points(ctx, member: commands.MemberConverter = None):
    member = member or ctx.author
    pts = user_points.get(member.id, 0)
    await ctx.send(f"{member.mention} has {pts} points.")

@bot.command()
async def level(ctx, member: commands.MemberConverter = None):
    member = member or ctx.author
    lvl = user_level.get(member.id, 0)
    xp = user_xp.get(member.id, 0)
    next_xp = int(LEVEL_UP_BASE * (LEVEL_MULTIPLIER ** lvl))
    await ctx.send(f"{member.mention} is **Level {lvl}** with **{xp}/{next_xp} XP**.")

@bot.command()
async def leaderboard(ctx, limit: int = 10):
    if not user_level:
        await ctx.send("No users have leveled up yet.")
        return
    top = sorted(user_level.items(), key=lambda x: x[1], reverse=True)[:limit]
    msg = "**Top Levels:**\n"
    for user_id, lvl in top:
        user = ctx.guild.get_member(user_id)
        name = user.mention if user else f"User ID {user_id}"
        msg += f"{name}: Level {lvl} ({user_xp.get(user_id,0)} XP)\n"
    await ctx.send(msg)

@bot.command()
async def remindme(ctx, time: int, *, message):
    await ctx.send(f"⏰ {ctx.author.mention}, I will remind you in {time} seconds.")
    await asyncio.sleep(time)
    await ctx.send(f"💡 {ctx.author.mention}, reminder: {message}")

# -----------------------------
# Info Commands
# -----------------------------
@bot.command()
async def userinfo(ctx, member: commands.MemberConverter = None):
    member = member or ctx.author
    roles = ", ".join([r.name for r in member.roles if r.name != "@everyone"])
    await ctx.send(f"**User Info:**\nName: {member}\nID: {member.id}\nJoined: {member.joined_at}\nRoles: {roles}")

@bot.command()
async def serverinfo(ctx):
    guild = ctx.guild
    await ctx.send(f"**Server Info:**\nName: {guild.name}\nID: {guild.id}\nMembers: {guild.member_count}\nCreated: {guild.created_at}")

@bot.command()
async def avatar(ctx, member: commands.MemberConverter = None):
    member = member or ctx.author
    await ctx.send(f"{member.mention}'s avatar: {member.avatar.url}")

# -----------------------------
# Help Command
# -----------------------------
@bot.command(name="help")
async def help_command(ctx):
    msg = (
        "**Mega Bot Help**\n\n"
        "📌 **Moderation Commands:**\n"
        "`!purge <number>` - Delete messages (mod)\n"
        "`!offenses [@user]` - Show offenses\n"
        "`!offenses_detail @user` - Show detailed offenses (mod)\n"
        "`!reset_offenses @user` - Reset offenses (mod)\n"
        "`!top_offenders [limit]` - Show top offenders (mod)\n\n"
        "🎲 **Fun Commands:**\n"
        "`!roll [sides]` - Roll a dice\n"
        "`!coinflip` - Flip a coin\n"
        "`!eightball <question>` - Ask the magic 8-ball\n\n"
        "💰 **Economy & Leveling:**\n"
        "`!points [@user]` - Show points\n"
        "`!level [@user]` - Show level and XP\n"
        "`!leaderboard [limit]` - Top levels\n"
        "`!remindme <seconds> <message>` - Set a reminder\n\n"
        "ℹ️ **Info Commands:**\n"
        "`!userinfo [@user]` - Show user info\n"
        "`!serverinfo` - Show server info\n"
        "`!avatar [@user]` - Show avatar\n"
        "`!ping` - Pong!"
    )
    await ctx.send(msg)

# -----------------------------
# Run Bot
# -----------------------------
bot.run(TOKEN)
