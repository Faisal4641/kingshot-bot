import discord
from discord.ext import commands, tasks
import aiohttp
from bs4 import BeautifulSoup
import json
import os
import logging
from datetime import datetime

# ─────────────────────────────────────────────
#  ONLY THIS ONE LINE TO EDIT BEFORE RUNNING
# ─────────────────────────────────────────────
BOT_TOKEN      = os.getenv("DISCORD_TOKEN")
CHECK_INTERVAL = 30  # minutes between checks

# ─────────────────────────────────────────────
CODES_FILE    = "known_codes.json"
SETTINGS_FILE = "server_settings.json"

SOURCES = [
    {
        "name": "Kingshot Official",
        "url": "https://kingshot.me/gift-code",
        "selector": "code, .gift-code, .redeem-code, span[class*='code']",
    },
    {
        "name": "Pocket Tactics (backup)",
        "url": "https://www.pockettactics.com/kingshot/codes",
        "selector": "code, strong, b",
    },
]

REDEEM_URL = "https://kingshot.me/gift-code"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)


# ── settings helpers ──────────────────────────

def load_settings() -> dict:
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE) as f:
            return json.load(f)
    return {}

def save_settings(settings: dict):
    with open(SETTINGS_FILE, "w") as f:
        json.dump(settings, f, indent=2)

def get_channel_id(guild_id: int):
    return load_settings().get(str(guild_id))

def set_channel_id(guild_id: int, channel_id: int):
    settings = load_settings()
    settings[str(guild_id)] = channel_id
    save_settings(settings)


# ── codes helpers ─────────────────────────────

def load_known_codes() -> set:
    if os.path.exists(CODES_FILE):
        with open(CODES_FILE) as f:
            return set(json.load(f))
    return set()

def save_known_codes(codes: set):
    with open(CODES_FILE, "w") as f:
        json.dump(list(codes), f, indent=2)

def looks_like_code(text: str) -> bool:
    t = text.strip()
    return (
        6 <= len(t) <= 24
        and t.replace("-", "").replace("_", "").isalnum()
        and " " not in t
        and t not in ("Kingshot", "KingShot", "Download", "Redeem", "Click")
    )

async def fetch_codes_from_source(session, source) -> set:
    codes = set()
    try:
        headers = {"User-Agent": "Mozilla/5.0 (KingshotCodeBot/1.0)"}
        async with session.get(source["url"], headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
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
            all_codes |= await fetch_codes_from_source(session, src)
    return all_codes

def build_alert_embed(new_codes: list) -> discord.Embed:
    embed = discord.Embed(
        title="🎁 New Kingshot Gift Code(s) Found!",
        description="\n".join(f"```{c}```" for c in new_codes),
        color=0xFFD700,
        timestamp=datetime.utcnow(),
    )
    embed.add_field(name="Redeem here 👇", value=f"[Click to redeem]({REDEEM_URL})", inline=False)
    embed.set_footer(text="Kingshot Code Bot • Auto Alert")
    return embed

def build_active_embed(codes: list) -> discord.Embed:
    """Embed showing ALL currently known active codes"""
    if codes:
        desc = "\n".join(f"```{c}```" for c in codes)
    else:
        desc = "❌ No active codes found right now.\nCheck back soon!"
    embed = discord.Embed(
        title="🎮 Kingshot — Currently Active Codes",
        description=desc,
        color=0x00FF99,
        timestamp=datetime.utcnow(),
    )
    embed.add_field(
        name="How to redeem 👇",
        value=f"[Tap here to redeem on official site]({REDEEM_URL})",
        inline=False
    )
    embed.add_field(
        name="📌 Steps to redeem:",
        value=(
            "1️⃣ Open Kingshot game\n"
            "2️⃣ Tap your **Avatar** (top left)\n"
            "3️⃣ Tap **Gift Code**\n"
            "4️⃣ Enter the code above\n"
            "5️⃣ Tap **Confirm** to claim rewards!"
        ),
        inline=False
    )
    embed.set_footer(text=f"Total codes: {len(codes)} • Kingshot Code Bot")
    return embed


# ── auto check task ────────────────────────────

@tasks.loop(minutes=CHECK_INTERVAL)
async def check_codes():
    settings = load_settings()
    if not settings:
        return

    known = load_known_codes()
    found = await scrape_all_codes()
    new_codes = sorted(found - known)

    if not new_codes:
        log.info("No new codes found.")
        return

    log.info(f"New codes: {new_codes}")
    embed = build_alert_embed(new_codes)

    for guild_id, channel_id in settings.items():
        channel = bot.get_channel(int(channel_id))
        if channel:
            try:
                await channel.send(
                    content="@everyone 🚨 **New Kingshot gift codes!**",
                    embed=embed
                )
            except Exception as e:
                log.error(f"Failed to send to guild {guild_id}: {e}")

    known |= set(new_codes)
    save_known_codes(known)

@check_codes.before_loop
async def before_check():
    await bot.wait_until_ready()


# ── events ─────────────────────────────────────

@bot.event
async def on_ready():
    log.info(f"Logged in as {bot.user}")
    check_codes.start()
    print(f"✅ Kingshot Code Bot online!")

@bot.event
async def on_guild_join(guild):
    for channel in guild.text_channels:
        if channel.permissions_for(guild.me).send_messages:
            await channel.send(
                "👋 **Kingshot Codes Bot is here!**\n\n"
                "Admin setup: `!setup #channel-name`\n"
                "See active codes: `!codes`"
            )
            break


# ── commands ───────────────────────────────────

@bot.command(name="setup")
@commands.has_permissions(administrator=True)
async def setup(ctx, channel: discord.TextChannel = None):
    if channel is None:
        await ctx.send("❌ Example: `!setup #kingshot-codes`")
        return
    set_channel_id(ctx.guild.id, channel.id)
    await ctx.send(
        f"✅ Done! Kingshot code alerts will be posted in {channel.mention}\n"
        f"I'll check for new codes every **{CHECK_INTERVAL} minutes** automatically!"
    )

@bot.command(name="codes")
async def active_codes(ctx):
    """Show all currently active Kingshot codes right now"""
    msg = await ctx.send("🔍 Fetching current active codes, please wait...")
    found = await scrape_all_codes()
    known = load_known_codes()

    # merge scraped + previously known codes
    all_codes = sorted(found | known)

    # save any newly found ones
    if found - known:
        save_known_codes(known | found)

    embed = build_active_embed(all_codes)
    await msg.edit(content=None, embed=embed)

@bot.command(name="checknow")
@commands.has_permissions(administrator=True)
async def check_now(ctx):
    channel_id = get_channel_id(ctx.guild.id)
    if not channel_id:
        await ctx.send("❌ Use `!setup #channel` first.")
        return
    await ctx.send("🔍 Checking for new codes right now…")
    await check_codes()

@bot.command(name="listcodes")
async def list_codes(ctx):
    known = load_known_codes()
    if not known:
        await ctx.send("No codes recorded yet. Try `!codes` to fetch live!")
        return
    codes_str = "\n".join(f"• `{c}`" for c in sorted(known))
    await ctx.send(f"**Known Kingshot codes:**\n{codes_str}")

@bot.command(name="clearknown")
@commands.has_permissions(administrator=True)
async def clear_known(ctx):
    save_known_codes(set())
    await ctx.send("✅ Known codes cleared.")

@bot.command(name="status")
async def status(ctx):
    channel_id = get_channel_id(ctx.guild.id)
    if channel_id:
        channel = bot.get_channel(int(channel_id))
        await ctx.send(f"✅ Active! Posting alerts in {channel.mention if channel else 'unknown'}")
    else:
        await ctx.send("⚠️ Not set up yet. Admin: `!setup #channel`")

@bot.command(name="help2")
async def help2(ctx):
    embed = discord.Embed(title="🤖 Kingshot Bot Commands", color=0x7289DA)
    embed.add_field(name="!codes", value="Show all currently active codes", inline=False)
    embed.add_field(name="!setup #channel", value="[Admin] Set alert channel", inline=False)
    embed.add_field(name="!checknow", value="[Admin] Force check right now", inline=False)
    embed.add_field(name="!listcodes", value="Show previously found codes", inline=False)
    embed.add_field(name="!status", value="Check bot setup status", inline=False)
    await ctx.send(embed=embed)

bot.run(BOT_TOKEN)
