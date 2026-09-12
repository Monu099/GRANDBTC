import discord
from discord.ext import commands, tasks
import json
import os
import random
from datetime import datetime

# ----------------- CONFIGURATION & BOT SETUP -----------------

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

DATA_FILE = "user_data.json"
MARKET_FILE = "market_data.json"

# Settings (Apne Server Ke Hisaab Se Badlein)
LOG_CHANNEL_ID = 123456789012345678      # Apne Log Channel ka ID yahan daalein
MANAGER_ROLE_NAME = "Crypto Manager"    # Manager Role Name

# ----------------- DATABASE HELPERS -----------------

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {}

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

def load_market_data():
    if os.path.exists(MARKET_FILE):
        with open(MARKET_FILE, "r") as f:
            return json.load(f)
    # Default Base Price: 1,000,000 Grand Money = 1 BTC
    return {"base_price": 1000000.0, "current_price": 1000000.0, "trend": "STABLE"}

def save_market_data(data):
    with open(MARKET_FILE, "w") as f:
        json.dump(data, f, indent=4)

# ----------------- UI BUTTON MODALS & VIEWS -----------------

class BuyBTCModal(discord.ui.Modal, title="Buy Bitcoin (BTC)"):
    amount = discord.ui.TextInput(
        label="BTC Amount to Buy",
        placeholder="Enter BTC amount (e.g., 0.5 or 1)",
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            btc_to_buy = float(self.amount.value)
            if btc_to_buy <= 0:
                await interaction.response.send_message("❌ Valid amount daalein!", ephemeral=True)
                return

            market = load_market_data()
            cost_in_grand = btc_to_buy * market["current_price"]
            
            user_id = str(interaction.user.id)
            data = load_data()
            if user_id not in data:
                data[user_id] = {"btc": 0.0, "grand_money": 10000000.0} # Default balance

            if data[user_id]["grand_money"] < cost_in_grand:
                await interaction.response.send_message(
                    f"❌ Insufficient Grand Money! Required: **${cost_in_grand:,.2f}**", 
                    ephemeral=True
                )
                return

            # Update Balance
            data[user_id]["grand_money"] -= cost_in_grand
            data[user_id]["btc"] += btc_to_buy
            save_data(data)

            await interaction.response.send_message(
                f"✅ **Purchase Successful!**\nAapne **{btc_to_buy:.8f} BTC** buy kiya **${cost_in_grand:,.2f} Grand Money** me.",
                ephemeral=True
            )

            await send_transaction_log(
                interaction.guild,
                user=interaction.user,
                action="BUY",
                btc_amount=btc_to_buy,
                grand_amount=cost_in_grand
            )

        except ValueError:
            await interaction.response.send_message("❌ Numbers hi enter karein!", ephemeral=True)

class SellBTCModal(discord.ui.Modal, title="Sell Bitcoin (BTC)"):
    amount = discord.ui.TextInput(
        label="BTC Amount to Sell",
        placeholder="Enter BTC amount (e.g., 0.5 or 1)",
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            btc_to_sell = float(self.amount.value)
            if btc_to_sell <= 0:
                await interaction.response.send_message("❌ Valid amount daalein!", ephemeral=True)
                return

            user_id = str(interaction.user.id)
            data = load_data()

            if user_id not in data or data[user_id]["btc"] < btc_to_sell:
                await interaction.response.send_message("❌ Apke paas itna BTC nahi hai!", ephemeral=True)
                return

            market = load_market_data()
            grand_received = btc_to_sell * market["current_price"]

            # Update Balance
            data[user_id]["btc"] -= btc_to_sell
            data[user_id]["grand_money"] += grand_received
            save_data(data)

            await interaction.response.send_message(
                f"✅ **Sale Successful!**\nAapne **{btc_to_sell:.8f} BTC** sell kiya **${grand_received:,.2f} Grand Money** ke badle.",
                ephemeral=True
            )

            await send_transaction_log(
                interaction.guild,
                user=interaction.user,
                action="SELL",
                btc_amount=btc_to_sell,
                grand_amount=grand_received
            )

        except ValueError:
            await interaction.response.send_message("❌ Numbers hi enter karein!", ephemeral=True)

class CryptoMarketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Buy BTC", style=discord.ButtonStyle.green, custom_id="buy_btc_btn", emoji="🛒")
    async def buy_btc(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(BuyBTCModal())

    @discord.ui.button(label="Sell BTC", style=discord.ButtonStyle.red, custom_id="sell_btc_btn", emoji="💰")
    async def sell_btc(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(SellBTCModal())

    @discord.ui.button(label="Check Price / Balance", style=discord.ButtonStyle.blurple, custom_id="check_price_btn", emoji="📊")
    async def check_price(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = str(interaction.user.id)
        data = load_data()
        user_info = data.get(user_id, {"btc": 0.0, "grand_money": 0.0})
        market = load_market_data()

        trend_emoji = "📈" if market.get("trend") == "UP" else ("📉" if market.get("trend") == "DOWN" else "➡️")

        embed = discord.Embed(title="📊 Live Crypto Market & Wallet", color=0xF2A900)
        embed.add_field(
            name="💎 Current BTC Price", 
            value=f"**1 BTC = ${market['current_price']:,.2f} Grand Money** {trend_emoji}", 
            inline=False
        )
        embed.add_field(name="💳 Your Grand Money", value=f"${user_info['grand_money']:,.2f}", inline=True)
        embed.add_field(name="₿ Your BTC Balance", value=f"{user_info['btc']:.8f} BTC", inline=True)
        embed.set_footer(text="Grand Mobile Market Exchange")

        await interaction.response.send_message(embed=embed, ephemeral=True)

# ----------------- LOGGING SYSTEM -----------------

async def send_transaction_log(guild, user, action, btc_amount, grand_amount):
    channel = guild.get_channel(1548380688699629649)
    if channel:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")
        
        embed = discord.Embed(
            title=f"🚨 Transaction Log: {action}",
            color=0x2ECC71 if action == "BUY" else 0xE74C3C,
            timestamp=datetime.now()
        )
        embed.add_field(name="👤 User", value=f"{user.mention} (`{user.name}`)", inline=False)
        embed.add_field(name="🔄 Action", value=f"**{action}**", inline=True)
        embed.add_field(name="₿ BTC Amount", value=f"`{btc_amount:.8f} BTC`", inline=True)
        embed.add_field(name="💸 Grand Money", value=f"`${grand_amount:,.2f}`", inline=True)
        embed.add_field(name="🕒 Date & Time", value=f"`{now}`", inline=False)
        embed.set_thumbnail(url=user.display_avatar.url)

        await channel.send(embed=embed)

# ----------------- DYNAMIC AUTOMATIC PRICE FLUCTUATION -----------------

@tasks.loop(minutes=5) # Har 5 minute me price up/down fluctuate hoga
async def auto_fluctuate_btc():
    market = load_market_data()
    base = market["base_price"]
    
    # -3% se +3% tak random fluctuation
    percent = random.uniform(-0.03, 0.03)
    new_price = base + (base * percent)
    
    market["trend"] = "UP" if new_price > market["current_price"] else "DOWN"
    market["current_price"] = round(new_price, 2)
    save_market_data(market)
    print(f"[MARKET UPDATE] New Price: 1 BTC = ${market['current_price']:,.2f} Grand Money ({market['trend']})")

# ----------------- COMMANDS -----------------

@bot.event
async def on_ready():
    auto_fluctuate_btc.start()
    bot.add_view(CryptoMarketView())
    print(f"✅ Bot is online as {bot.user.name}")

@bot.command()
@commands.is_owner()
async def setbtcprice(ctx, new_base_price: float):
    """ONLY SERVER OWNER: Change Base BTC Price anytime"""
    if new_base_price <= 0:
        await ctx.send("❌ Price zero se zyada hona chahiye!")
        return

    market = load_market_data()
    market["base_price"] = new_base_price
    market["current_price"] = new_base_price
    market["trend"] = "STABLE"
    save_market_data(market)

    await ctx.send(f"👑 **Owner Action:** 1 BTC ka Base Rate ab **${new_base_price:,.2f} Grand Money** set ho chuka hai!")

@bot.command()
@commands.has_permissions(administrator=True)
async def setup_market(ctx):
    """Admin command to deploy the market panel UI"""
    embed = discord.Embed(
        title="⚡ Grand Mobile Dynamic Crypto Exchange",
        description="Niche diye gaye buttons se BTC Buy/Sell karein, ya live rate check karein.",
        color=0xF2A900
    )
    embed.add_field(name="📈 Market Fluctuation", value="BTC Price har 5 minute me up/down update hoti rehti hai.", inline=False)
    await ctx.send(embed=embed, view=CryptoMarketView())

@bot.command()
@commands.has_role(MANAGER_ROLE_NAME)
async def setbalance(ctx, member: discord.Member, currency: str, amount: float):
    """Manager command to manually set balance for any member"""
    data = load_data()
    user_id = str(member.id)
    if user_id not in data:
        data[user_id] = {"btc": 0.0, "grand_money": 0.0}

    currency = currency.lower()
    if currency in ["btc", "bitcoin"]:
        data[user_id]["btc"] = amount
    elif currency in ["grand", "money"]:
        data[user_id]["grand_money"] = amount
    else:
        await ctx.send("❌ Invalid currency! Use `btc` or `grand`.")
        return

    save_data(data)
    await ctx.send(f"✅ Updated {member.mention}'s {currency.upper()} balance to `{amount}`.")

# Command Error Handlers
@setbtcprice.error
async def setbtcprice_error(ctx, error):
    if isinstance(error, commands.NotOwner):
        await ctx.send("❌ Ye command sirf **Server Owner** hi run kar sakta hai!")

@setbalance.error
async def setbalance_error(ctx, error):
    if isinstance(error, commands.MissingRole):
        await ctx.send("❌ Aapke paas Manager Role ki permission nahi hai!")

# Run Bot
bot.run("MTU0ODM5MjEyMzMzNjc2MTQzNA.G5T3w4.jK6r7M_8UGhEUZ2z3zWz1zZycSkf5_e9rIeja0")
