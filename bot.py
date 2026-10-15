import discord
from discord.ext import commands, tasks
import aiohttp
from bs4 import BeautifulSoup
import json
import os
import logging
from datetime import datetime, timedelta

# ─────────────────────────────────────────────
BOT_TOKEN         = os.getenv("DISCORD_TOKEN")
CHECK_INTERVAL    = 5       # check every 5 minutes for NEW codes
ALERT_INTERVAL_H  = 12      # repeat known codes alert every 12 hours
OWNER_NAME        = "DEADPOOL"
OWNER_USERNAME    = "faysal4641"
REDEEM_URL        = "https://kingshot.me/gift-code"
BOT_COLOR         = 0xFFD700   # gold
BOT_COLOR_GREEN   = 0x00FF99
BOT_COLOR_BLUE    = 0x7289DA
# ─────────────────────────────────────────────

CODES_FILE    = "known_codes.json"
SETTINGS_FILE = "server_settings.json"

SOURCES = [
    {
        "name": "Pocket Tactics",
        "url": "https://www.pockettactics.com/kingshot/codes",
        "selector": "code, strong, li strong, p strong",
    },
    {
        "name": "UCN.gg",
        "url": "https://ucn.gg/kingshot-gift-codes",
        "selector": "code, .code, span[class*='code'], td, li",
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
    # must have at least some digits OR be all caps with letters+digits
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

def footer_text():
    return f"Powered by {OWNER_NAME} • {OWNER_USERNAME}"

def build_new_code_embed(new_codes: list) -> discord.Embed:
    embed = discord.Embed(
        title="🚨 NEW Kingshot Gift Code(s) Alert!",
        description="\n".join(f"```{c}```" for c in new_codes),
        color=BOT_COLOR,
        timestamp=datetime.utcnow(),
    )
    embed.add_field(
        name="📌 How to redeem:",
        value=(
            "1️⃣ Open **Kingshot** game\n"
            "2️⃣ Tap **Avatar** → **Gift Code**\n"
            "3️⃣ Enter code → **Confirm**\n"
            f"4️⃣ Or [redeem on website]({REDEEM_URL})"
        ),
        inline=False
    )
    embed.set_footer(text=footer_text())
    return embed

def build_all_codes_embed(codes: list) -> discord.Embed:
    if codes:
        desc = "\n".join(f"```{c}```" for c in codes)
        title = f"🎮 Kingshot Active Codes ({len(codes)} found)"
    else:
        desc = "❌ No active codes found right now.\nCheck back soon — bot checks every 5 minutes!"
        title = "🎮 Kingshot Active Codes"

    embed = discord.Embed(title=title, description=desc, color=BOT_COLOR_GREEN, timestamp=datetime.utcnow())
    embed.add_field(
        name="📌 How to redeem:",
        value=(
            "1️⃣ Open **Kingshot** game\n"
            "2️⃣ Tap **Avatar** → **Gift Code**\n"
            "3️⃣ Enter code → **Confirm**\n"
            f"4️⃣ Or [redeem on website]({REDEEM_URL})"
        ),
        inline=False
    )
    embed.set_footer(text=footer_text())
    return embed

def build_welcome_embed(guild_name: str, channel: discord.TextChannel) -> discord.Embed:
    embed = discord.Embed(
        title=f"👋 Kingshot Codes Bot has joined {guild_name}!",
        description=(
            "I will **automatically** post new Kingshot gift codes in "
            f"{channel.mention} and ping **@everyone**!\n\n"
            "No setup needed — I'm already watching for codes! 🎉"
        ),
        color=BOT_COLOR_BLUE,
        timestamp=datetime.utcnow(),
    )
    embed.add_field(
        name="💬 Commands (type anywhere):",
        value=(
            "`!codes` or just type `codes` → See all active codes\n"
            "`!status` → Check bot status\n"
            "`!setup #channel` → [Admin] Change alert channel\n"
            "`!checknow` → [Admin] Force check now\n"
            "`!help2` → Full command list"
        ),
        inline=False
    )
    embed.add_field(
        name="⚙️ How it works:",
        value=(
            "✅ Checks for new codes every **5 minutes**\n"
            "✅ Alerts **@everyone** instantly for NEW codes\n"
            "✅ Posts reminder of all codes every **12 hours**\n"
            "✅ Runs **24/7** automatically"
        ),
        inline=False
    )
    embed.set_footer(text=footer_text())
    return embed


# ── auto-create channel ───────────────────────

async def get_or_create_codes_channel(guild: discord.Guild) -> discord.TextChannel:
    """Find existing kingshot channel or create one automatically"""
    # check if already set in settings
    server_data = get_server(guild.id)
    if "channel_id" in server_data:
        ch = guild.get_channel(int(server_data["channel_id"]))
        if ch:
            return ch

    # look for existing channel with kingshot in name
    for ch in guild.text_channels:
        if "kingshot" in ch.name.lower() or "codes" in ch.name.lower():
            server_data["channel_id"] = ch.id
            save_server(guild.id, server_data)
            return ch

    # create new channel automatically
    try:
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(send_messages=False, read_messages=True),
            guild.me: discord.PermissionOverwrite(send_messages=True, read_messages=True, mention_everyone=True)
        }
        ch = await guild.create_text_channel(
            "kingshot-codes",
            overwrites=overwrites,
            topic="🎮 Auto Kingshot gift code alerts • Powered by " + footer_text()
        )
        server_data["channel_id"] = ch.id
        save_server(guild.id, server_data)
        log.info(f"Created #kingshot-codes in {guild.name}")
        return ch
    except Exception as e:
        log.error(f"Could not create channel in {guild.name}: {e}")
        # fallback to first available channel
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

    # check which servers need 12-hour reminder
    now = datetime.utcnow()
    settings = load_settings()

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

        # send NEW code alert immediately
        if new_codes:
            try:
                embed = build_new_code_embed(new_codes)
                await channel.send(
                    content="@everyone 🚨 **New Kingshot gift codes just dropped!**",
                    embed=embed
                )
                log.info(f"Sent new codes to {guild.name}")
            except Exception as e:
                log.error(f"Error sending to {guild.name}: {e}")

        # send 12-hour reminder of all codes
        last_reminder = server_data.get("last_reminder")
        should_remind = False
        if not last_reminder:
            should_remind = True
        else:
            last_dt = datetime.fromisoformat(last_reminder)
            if now - last_dt >= timedelta(hours=ALERT_INTERVAL_H):
                should_remind = True

        if should_remind and (found | known):
            all_codes = sorted(found | known)
            try:
                embed = build_all_codes_embed(all_codes)
                await channel.send(
                    content="@everyone ⏰ **Kingshot codes reminder!**",
                    embed=embed
                )
                server_data["last_reminder"] = now.isoformat()
                save_server(int(guild_id), server_data)
                log.info(f"Sent 12h reminder to {guild.name}")
            except Exception as e:
                log.error(f"Error sending reminder to {guild.name}: {e}")

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
    print(f"✅ Kingshot Code Bot online! Powered by {OWNER_NAME} • {OWNER_USERNAME}")

@bot.event
async def on_guild_join(guild: discord.Guild):
    """Auto setup when bot joins a new server"""
    channel = await get_or_create_codes_channel(guild)
    if channel:
        embed = build_welcome_embed(guild.name, channel)
        await channel.send(embed=embed)
        log.info(f"Joined and set up in {guild.name}")

@bot.event
async def on_message(message: discord.Message):
    """Allow users to just type 'codes' or 'code' without ! prefix"""
    if message.author.bot:
        return
    content = message.content.strip().lower()
    # respond to natural typing: "codes", "code", "kingshot codes", "gift code"
    triggers = ["codes", "code", "kingshot code", "kingshot codes", "gift code", "redeem code"]
    if content in triggers:
        ctx = await bot.get_context(message)
        await active_codes(ctx)
        return
    await bot.process_commands(message)


# ── commands ───────────────────────────────────

@bot.command(name="codes")
async def active_codes(ctx):
    """Show all currently active Kingshot codes"""
    msg = await ctx.send("🔍 Fetching active Kingshot codes...")
    found = await scrape_all_codes()
    known = load_known_codes()
    all_codes = sorted(found | known)
    if found - known:
        save_known_codes(known | found)
    embed = build_all_codes_embed(all_codes)
    await msg.edit(content=None, embed=embed)

@bot.command(name="setup")
@commands.has_permissions(administrator=True)
async def setup(ctx, channel: discord.TextChannel = None):
    if channel is None:
        await ctx.send("❌ Example: `!setup #kingshot-codes`")
        return
    server_data = get_server(ctx.guild.id)
    server_data["channel_id"] = channel.id
    save_server(ctx.guild.id, server_data)
    await ctx.send(
        f"✅ Done! Alerts will post in {channel.mention}\n"
        f"Checking every **{CHECK_INTERVAL} min**, reminders every **{ALERT_INTERVAL_H} hours**!"
    )

@bot.command(name="checknow")
@commands.has_permissions(administrator=True)
async def check_now(ctx):
    await ctx.send("🔍 Force checking for new codes...")
    await check_codes()
    await ctx.send("✅ Check complete!")

@bot.command(name="status")
async def status(ctx):
    server_data = get_server(ctx.guild.id)
    channel_id = server_data.get("channel_id")
    last_reminder = server_data.get("last_reminder", "Never")
    known = load_known_codes()
    embed = discord.Embed(title="🤖 Kingshot Bot Status", color=BOT_COLOR_BLUE)
    if channel_id:
        ch = ctx.guild.get_channel(int(channel_id))
        embed.add_field(name="📢 Alert Channel", value=ch.mention if ch else "Not found", inline=True)
    else:
        embed.add_field(name="📢 Alert Channel", value="Auto (kingshot-codes)", inline=True)
    embed.add_field(name="🔍 Check Interval", value=f"Every {CHECK_INTERVAL} minutes", inline=True)
    embed.add_field(name="⏰ Reminder Interval", value=f"Every {ALERT_INTERVAL_H} hours", inline=True)
    embed.add_field(name="🎮 Known Codes", value=str(len(known)), inline=True)
    embed.add_field(name="📅 Last Reminder", value=last_reminder[:16] if last_reminder != "Never" else "Never", inline=True)
    embed.set_footer(text=footer_text())
    await ctx.send(embed=embed)

@bot.command(name="clearknown")
@commands.has_permissions(administrator=True)
async def clear_known(ctx):
    save_known_codes(set())
    await ctx.send("✅ Known codes cleared.")

@bot.command(name="help2")
async def help2(ctx):
    embed = discord.Embed(
        title="🤖 Kingshot Bot — Command Guide",
        color=BOT_COLOR_BLUE,
        timestamp=datetime.utcnow()
    )
    embed.add_field(
        name="👥 For Everyone:",
        value=(
            "`!codes` or type `codes` → Show all active codes\n"
            "`!status` → Bot status & info\n"
            "`!help2` → This help menu"
        ),
        inline=False
    )
    embed.add_field(
        name="🔧 Admin Only:",
        value=(
            "`!setup #channel` → Change alert channel\n"
            "`!checknow` → Force check right now\n"
            "`!clearknown` → Reset known codes list"
        ),
        inline=False
    )
    embed.add_field(
        name="⚙️ How it works:",
        value=(
            f"✅ Checks every **{CHECK_INTERVAL} minutes**\n"
            "✅ **Instant alert** for brand new codes\n"
            f"✅ **Reminder** every {ALERT_INTERVAL_H} hours\n"
            "✅ Auto creates **#kingshot-codes** channel\n"
            "✅ Runs **24/7** automatically"
        ),
        inline=False
    )
    embed.set_footer(text=footer_text())
    await ctx.send(embed=embed)

bot.run(BOT_TOKEN)
