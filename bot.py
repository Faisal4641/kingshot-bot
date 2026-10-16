import discord
from discord.ext import commands, tasks
import aiohttp
from bs4 import BeautifulSoup
import json
import os
import logging
from datetime import datetime, timezone, timedelta
import random

# ─────────────────────────────────────────────
BOT_TOKEN        = os.getenv("DISCORD_TOKEN")
CHECK_INTERVAL   = 5       # check every 5 minutes
ALERT_INTERVAL_H = 12      # reminder every 12 hours
OWNER_NAME       = "DEADPOOL"
OWNER_USERNAME   = "faysal4641"
REDEEM_URL       = "https://kingshot.me/gift-code"
BOT_COLOR        = 0xFFD700
BOT_COLOR_GREEN  = 0x2ECC71
BOT_COLOR_BLUE   = 0x3498DB
BOT_COLOR_RED    = 0xE74C3C
# ─────────────────────────────────────────────

CODES_FILE       = "known_codes.json"
CODES_TIME_FILE  = "codes_time.json"
SETTINGS_FILE    = "server_settings.json"

SOURCES = [
    {
        "name": "Pocket Tactics",
        "url": "https://www.pockettactics.com/kingshot/codes",
        "selector": "code, strong, li strong, p strong",
    },
    {
        "name": "Kingshot Official",
        "url": "https://kingshot.me/gift-code",
        "selector": "code, .gift-code, .redeem-code, span[class*='code'], input[type='text']",
    },
]

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)


# ── settings ──────────────────────────────────

def load_settings() -> dict:
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE) as f:
            return json.load(f)
    return {}

def save_settings(s: dict):
    with open(SETTINGS_FILE, "w") as f:
        json.dump(s, f, indent=2)

def get_server(guild_id: int) -> dict:
    return load_settings().get(str(guild_id), {})

def save_server(guild_id: int, data: dict):
    s = load_settings()
    s[str(guild_id)] = data
    save_settings(s)


# ── codes ─────────────────────────────────────

def load_known_codes() -> set:
    if os.path.exists(CODES_FILE):
        with open(CODES_FILE) as f:
            return set(json.load(f))
    return set()

def save_known_codes(codes: set):
    with open(CODES_FILE, "w") as f:
        json.dump(list(codes), f, indent=2)

def load_codes_time() -> dict:
    if os.path.exists(CODES_TIME_FILE):
        with open(CODES_TIME_FILE) as f:
            return json.load(f)
    return {}

def save_codes_time(data: dict):
    with open(CODES_TIME_FILE, "w") as f:
        json.dump(data, f, indent=2)

def record_code_time(codes: set):
    times = load_codes_time()
    now = datetime.now(timezone.utc).isoformat()
    for c in codes:
        if c not in times:
            times[c] = now
    save_codes_time(times)

def get_code_age(code: str) -> str:
    times = load_codes_time()
    if code not in times:
        return "recently"
    found_at = datetime.fromisoformat(times[code])
    if found_at.tzinfo is None:
        found_at = found_at.replace(tzinfo=timezone.utc)
    diff = datetime.now(timezone.utc) - found_at
    mins = int(diff.total_seconds() / 60)
    if mins < 60:
        return f"{mins}m ago" if mins > 1 else "just now"
    hours = mins // 60
    if hours < 24:
        return f"{hours}h ago"
    days = hours // 24
    return f"{days}d ago"

SKIP_WORDS = {
    "kingshot", "kingshot2", "download", "redeem", "click", "here",
    "code", "codes", "gift", "free", "expired", "active", "working",
    "valid", "new", "latest", "all", "game", "mobile", "play", "store"
}

def looks_like_code(text: str) -> bool:
    t = text.strip()
    if not (5 <= len(t) <= 25):
        return False
    if " " in t:
        return False
    cleaned = t.replace("-", "").replace("_", "")
    if not cleaned.isalnum():
        return False
    if t.lower() in SKIP_WORDS:
        return False
    has_digit = any(c.isdigit() for c in t)
    has_letter = any(c.isalpha() for c in t)
    return has_digit and has_letter

async def fetch_codes_from_source(session, source) -> set:
    codes = set()
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        async with session.get(source["url"], headers=headers, timeout=aiohttp.ClientTimeout(total=20)) as resp:
            if resp.status != 200:
                return codes
            html = await resp.text()
        soup = BeautifulSoup(html, "html.parser")
        for el in soup.select(source["selector"]):
            text = el.get_text(strip=True)
            if looks_like_code(text):
                codes.add(text.upper())
    except Exception as e:
        log.error(f"[{source['name']}] error: {e}")
    return codes

async def scrape_all_codes() -> set:
    all_codes = set()
    async with aiohttp.ClientSession() as session:
        for src in SOURCES:
            found = await fetch_codes_from_source(session, src)
            log.info(f"[{src['name']}] found: {found}")
            all_codes |= found
    return all_codes


# ── embeds ────────────────────────────────────

def footer():
    return f"Powered by {OWNER_NAME} • {OWNER_USERNAME}"

def format_codes_list(codes: list) -> str:
    """Each code on its own line in a copyable inline code block with age"""
    lines = []
    for c in codes:
        age = get_code_age(c)
        lines.append(f"`{c}`  —  ⏱ {age}")
    return "\n\n".join(lines)

def build_codes_embed(codes: list, username: str = None) -> discord.Embed:
    greeting = f"Hey **{username}**! 👋\n\n" if username else ""

    if codes:
        count = len(codes)
        desc = (
            f"{greeting}"
            f"🎮 Currently **{count} active code{'s' if count > 1 else ''}** for Kingshot:\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"{format_codes_list(codes)}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"💡 *Tap any code to select it, then copy!*"
        )
        title = f"🎁 Kingshot Active Codes ({count} found)"
        color = BOT_COLOR_GREEN
    else:
        desc = (
            f"{greeting}"
            f"😔 No active codes found right now.\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🔍 I check every **5 minutes** automatically!\n"
            f"🔔 You'll get pinged the moment a new code drops."
        )
        title = "🎮 Kingshot Active Codes"
        color = BOT_COLOR_RED

    embed = discord.Embed(title=title, description=desc, color=color,
                          timestamp=datetime.now(timezone.utc))
    embed.add_field(
        name="📌 How to redeem:",
        value=(
            "**1.** Open **Kingshot** game\n"
            "**2.** Tap your **Avatar** (top-left)\n"
            "**3.** Tap **Gift Code**\n"
            "**4.** Paste code → tap **Confirm** ✅\n"
            f"**5.** Or [redeem on official website]({REDEEM_URL})"
        ),
        inline=False
    )
    embed.set_footer(text=footer())
    return embed

def build_new_code_embed(new_codes: list) -> discord.Embed:
    desc = (
        f"🆕 **{len(new_codes)} new code{'s' if len(new_codes) > 1 else ''} just dropped!**\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{format_codes_list(new_codes)}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"💡 *Tap any code to select it, then copy!*"
    )
    embed = discord.Embed(
        title="🚨 New Kingshot Gift Code Alert!",
        description=desc,
        color=BOT_COLOR,
        timestamp=datetime.now(timezone.utc)
    )
    embed.add_field(
        name="📌 How to redeem:",
        value=(
            "**1.** Open **Kingshot** game\n"
            "**2.** Tap your **Avatar** (top-left)\n"
            "**3.** Tap **Gift Code**\n"
            "**4.** Paste code → tap **Confirm** ✅\n"
            f"**5.** Or [redeem on official website]({REDEEM_URL})"
        ),
        inline=False
    )
    embed.set_footer(text=footer())
    return embed

def build_welcome_embed(guild_name: str, channel: discord.TextChannel) -> discord.Embed:
    embed = discord.Embed(
        title=f"👋 Kingshot Codes Bot has arrived in {guild_name}!",
        description=(
            f"Hey everyone! I'll automatically post Kingshot gift codes\n"
            f"in {channel.mention} and ping **@everyone** instantly! 🎉\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"**Just type any of these to get codes:**\n"
            f"`code` • `codes` • `!codes` • `any codes?`\n\n"
            f"**Other commands:**\n"
            f"`hi` — Say hello to the bot\n"
            f"`help` — See all commands\n"
            f"`!status` — Check bot status\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━"
        ),
        color=BOT_COLOR_BLUE,
        timestamp=datetime.now(timezone.utc)
    )
    embed.add_field(
        name="⚙️ How it works:",
        value=(
            "✅ Checks for new codes every **5 minutes**\n"
            "✅ **Instant @everyone alert** for new codes\n"
            "✅ **Reminder** every 12 hours\n"
            "✅ Shows **how long ago** each code was found\n"
            "✅ Runs **24/7** automatically"
        ),
        inline=False
    )
    embed.set_footer(text=footer())
    return embed


# ── auto channel ──────────────────────────────

async def get_or_create_codes_channel(guild: discord.Guild) -> discord.TextChannel:
    server_data = get_server(guild.id)
    if "channel_id" in server_data:
        ch = guild.get_channel(int(server_data["channel_id"]))
        if ch:
            return ch
    for ch in guild.text_channels:
        if "kingshot" in ch.name.lower() or "codes" in ch.name.lower():
            server_data["channel_id"] = ch.id
            save_server(guild.id, server_data)
            return ch
    try:
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(send_messages=False, read_messages=True),
            guild.me: discord.PermissionOverwrite(send_messages=True, read_messages=True, mention_everyone=True)
        }
        ch = await guild.create_text_channel(
            "kingshot-codes",
            overwrites=overwrites,
            topic=f"🎮 Auto Kingshot gift code alerts • {footer()}"
        )
        server_data["channel_id"] = ch.id
        save_server(guild.id, server_data)
        return ch
    except Exception as e:
        log.error(f"Could not create channel: {e}")
        for ch in guild.text_channels:
            if ch.permissions_for(guild.me).send_messages:
                server_data["channel_id"] = ch.id
                save_server(guild.id, server_data)
                return ch
    return None


# ── tasks ─────────────────────────────────────

@tasks.loop(minutes=CHECK_INTERVAL)
async def check_codes():
    known = load_known_codes()
    found = await scrape_all_codes()
    new_codes = sorted(found - known)
    now = datetime.now(timezone.utc)
    settings = load_settings()

    if new_codes:
        record_code_time(set(new_codes))

    for guild_id, server_data in settings.items():
        guild = bot.get_guild(int(guild_id))
        if not guild:
            continue
        channel_id = server_data.get("channel_id")
        channel = guild.get_channel(int(channel_id)) if channel_id else None
        if not channel:
            channel = await get_or_create_codes_channel(guild)
        if not channel:
            continue

        if new_codes:
            try:
                embed = build_new_code_embed(new_codes)
                await channel.send(
                    content="@everyone 🚨 **New Kingshot gift codes just dropped!**",
                    embed=embed
                )
            except Exception as e:
                log.error(f"Error sending to {guild.name}: {e}")

        last_reminder = server_data.get("last_reminder")
        should_remind = not last_reminder or (
            now - datetime.fromisoformat(last_reminder).replace(tzinfo=timezone.utc)
            >= timedelta(hours=ALERT_INTERVAL_H)
        )

        if should_remind and (found | known):
            all_codes = sorted(found | known)
            try:
                embed = build_codes_embed(all_codes)
                await channel.send(
                    content="@everyone ⏰ **Kingshot codes reminder!**",
                    embed=embed
                )
                server_data["last_reminder"] = now.isoformat()
                save_server(int(guild_id), server_data)
            except Exception as e:
                log.error(f"Error sending reminder: {e}")

    if new_codes:
        known |= set(new_codes)
        save_known_codes(known)

@check_codes.before_loop
async def before_check():
    await bot.wait_until_ready()


# ── events ─────────────────────────────────────

@bot.event
async def on_ready():
    log.info(f"Logged in as {bot.user}")
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name="for Kingshot codes 🎮"
        )
    )
    check_codes.start()
    print(f"✅ Kingshot Code Bot online! {footer()}")

@bot.event
async def on_guild_join(guild: discord.Guild):
    channel = await get_or_create_codes_channel(guild)
    if channel:
        embed = build_welcome_embed(guild.name, channel)
        await channel.send(embed=embed)

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    content = message.content.strip().lower()
    name = message.author.display_name

    # ── code triggers ──
    code_triggers = [
        "code", "codes", "!code", "!codes",
        "kingshot code", "kingshot codes",
        "gift code", "any codes", "any codes?",
        "show codes", "get codes", "redeem code"
    ]
    if content in code_triggers:
        async with message.channel.typing():
            found = await scrape_all_codes()
            known = load_known_codes()
            all_codes = sorted(found | known)
            if found - known:
                record_code_time(found - known)
                save_known_codes(known | found)

        if not all_codes:
            await message.channel.send(
                f"Hey **{name}**! 😔 No active codes right now.\n"
                f"🔔 I'll ping you the moment a new code drops!"
            )
            return

        # header message
        await message.channel.send(
            f"Hey **{name}**! 👋 Found **{len(all_codes)} active code{'s' if len(all_codes) > 1 else ''}** — tap to copy! 👇"
        )

        # each code as its own separate message for easy copy
        for code in all_codes:
            age = get_code_age(code)
            await message.channel.send(
                f"```\n{code}\n```"
                f"⏱ Found: {age}  •  [Redeem here]({REDEEM_URL})"
            )

        # footer message
        await message.channel.send(
            f"📌 **How to redeem:**\n"
            f"1️⃣ Open Kingshot → tap **Avatar**\n"
            f"2️⃣ Tap **Gift Code** → paste → **Confirm** ✅\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"*Powered by DEADPOOL • faysal4641*"
        )
        return

    # ── greeting triggers ──
    greet_triggers = ["hi", "hello", "hey", "helo", "hii", "hiii", "sup", "yo"]
    if content in greet_triggers:
        known = load_known_codes()
        count = len(known)
        responses = [
            f"Hey **{name}**! 👋 Welcome! I'm watching Kingshot 24/7 🎮\nCurrently **{count} active code{'s' if count != 1 else ''}** — type `code` to see them!",
            f"Hi **{name}**! 😄 Hope you're having a great day!\nType `code` to check the latest Kingshot gift codes 🎁",
            f"Hello **{name}**! 👋 Ready to get some free rewards?\nType `code` to see **{count} active Kingshot code{'s' if count != 1 else ''}**! 🎮",
        ]
        await message.channel.send(random.choice(responses))
        return

    # ── thanks triggers ──
    thanks_triggers = ["thanks", "thank you", "thx", "ty", "tysm", "thank u"]
    if content in thanks_triggers:
        responses = [
            f"You're welcome **{name}**! 🎮 Happy gaming! Don't forget to redeem your codes!",
            f"Anytime **{name}**! 😄 Good luck in Kingshot! 🎮",
            f"No problem **{name}**! 🙌 I'll keep watching for new codes 24/7!",
        ]
        await message.channel.send(random.choice(responses))
        return

    # ── how many codes ──
    count_triggers = ["how many codes", "how many codes?", "how many", "count codes"]
    if content in count_triggers:
        known = load_known_codes()
        count = len(known)
        if count == 0:
            await message.channel.send(f"Hey **{name}**! 😔 No active codes right now. I'll alert you the moment one drops!")
        else:
            await message.channel.send(f"Hey **{name}**! 🎮 There are currently **{count} active code{'s' if count != 1 else ''}**! Type `code` to see them all!")
        return

    # ── help trigger ──
    help_triggers = ["help", "!help", "commands", "?"]
    if content in help_triggers:
        embed = discord.Embed(
            title="🤖 Kingshot Bot — Help",
            description=f"Hey **{name}**! Here's everything I can do:",
            color=BOT_COLOR_BLUE,
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(
            name="💬 Just type these:",
            value=(
                "`code` or `codes` — See all active codes\n"
                "`hi` / `hello` — Say hello!\n"
                "`how many codes` — Quick count\n"
                "`thanks` — You're welcome 😄\n"
                "`help` — This menu"
            ),
            inline=False
        )
        embed.add_field(
            name="🔧 Admin commands:",
            value=(
                "`!setup #channel` — Set alert channel\n"
                "`!checknow` — Force check now\n"
                "`!status` — Bot status\n"
                "`!clearknown` — Reset codes list"
            ),
            inline=False
        )
        embed.add_field(
            name="⚙️ Auto features:",
            value=(
                "✅ Checks every **5 minutes**\n"
                "✅ Instant alert for new codes\n"
                "✅ Reminder every **12 hours**\n"
                "✅ Shows how long ago code was found"
            ),
            inline=False
        )
        embed.set_footer(text=footer())
        await message.channel.send(embed=embed)
        return

    await bot.process_commands(message)


# ── commands ───────────────────────────────────

@bot.command(name="codes")
async def cmd_codes(ctx):
    name = ctx.author.display_name
    async with ctx.typing():
        found = await scrape_all_codes()
        known = load_known_codes()
        all_codes = sorted(found | known)
        if found - known:
            record_code_time(found - known)
            save_known_codes(known | found)

    if not all_codes:
        await ctx.send(f"Hey **{name}**! 😔 No active codes right now. I'll ping when new ones drop!")
        return

    await ctx.send(f"Hey **{name}**! 👋 Found **{len(all_codes)} active code{'s' if len(all_codes) > 1 else ''}** — tap to copy! 👇")
    for code in all_codes:
        age = get_code_age(code)
        await ctx.send(f"```\n{code}\n```⏱ Found: {age}  •  [Redeem here]({REDEEM_URL})")
    await ctx.send(
        f"📌 **How to redeem:**\n"
        f"1️⃣ Open Kingshot → tap **Avatar**\n"
        f"2️⃣ Tap **Gift Code** → paste → **Confirm** ✅\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"*Powered by DEADPOOL • faysal4641*"
    )

@bot.command(name="setup")
@commands.has_permissions(administrator=True)
async def setup(ctx, channel: discord.TextChannel = None):
    if channel is None:
        await ctx.send("❌ Example: `!setup #kingshot-codes`")
        return
    server_data = get_server(ctx.guild.id)
    server_data["channel_id"] = channel.id
    save_server(ctx.guild.id, server_data)
    await ctx.send(f"✅ Done! Alerts will post in {channel.mention}\nChecking every **{CHECK_INTERVAL} min**, reminders every **{ALERT_INTERVAL_H} hours**!")

@bot.command(name="checknow")
@commands.has_permissions(administrator=True)
async def status(ctx):
    server_data = get_server(ctx.guild.id)
    channel_id = server_data.get("channel_id")
    last_reminder = server_data.get("last_reminder", "Never")
    known = load_known_codes()
    embed = discord.Embed(title="🤖 Kingshot Bot Status", color=BOT_COLOR_BLUE,
                          timestamp=datetime.now(timezone.utc))
    if channel_id:
        ch = ctx.guild.get_channel(int(channel_id))
        embed.add_field(name="📢 Alert Channel", value=ch.mention if ch else "Not found", inline=True)
    else:
        embed.add_field(name="📢 Alert Channel", value="Auto (#kingshot-codes)", inline=True)
    embed.add_field(name="🔍 Check Every", value=f"{CHECK_INTERVAL} minutes", inline=True)
    embed.add_field(name="⏰ Reminder Every", value=f"{ALERT_INTERVAL_H} hours", inline=True)
    embed.add_field(name="🎮 Active Codes", value=str(len(known)), inline=True)
    embed.add_field(name="📅 Last Reminder", value=last_reminder[:16] if last_reminder != "Never" else "Never", inline=True)
    embed.set_footer(text=footer())
    await ctx.send(embed=embed)
 
@bot.command(name="clearknown")
@commands.has_permissions(administrator=True)
async def clear_known(ctx):
    save_known_codes(set())
    save_codes_time({})
    await ctx.send("✅ Known codes and timestamps cleared.")
 
bot.run(BOT_TOKEN)
