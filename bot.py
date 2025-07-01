import discord
import os
import asyncio
from dotenv import load_dotenv
from discord.ext import commands

# Load environment variables from clyne.env
load_dotenv('clyne.env')

# Set up intents - disable privileged intents
intents = discord.Intents.default()
intents.message_content = False  # Disable message content intent (privileged)

# Create bot instance
bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    print(f'Bot is ready! Logged in as {bot.user}')
    print(f'Bot ID: {bot.user.id}')
    
    # Sync slash commands using the correct method
    print("Syncing slash commands...")
    try:
        # For discord.py and newer pycord versions
        if hasattr(bot, 'sync_commands'):
            await bot.sync_commands()
            print("Synced commands using bot.sync_commands()")
        # For older pycord versions
        elif hasattr(bot, 'tree') and hasattr(bot.tree, 'sync'):
            synced = await bot.tree.sync()
            print(f"Synced {len(synced)} command(s) using bot.tree.sync()")
        # Fallback for discord.py
        else:
            guild_ids = [guild.id for guild in bot.guilds]
            for guild_id in guild_ids:
                await bot.sync_commands(guild_id=guild_id)
            print(f"Synced commands for {len(guild_ids)} guilds")
    except Exception as e:
        print(f"Failed to sync commands: {e}")

async def load_extensions():
    try:
        # Load status cog
        await bot.load_extension("cog.stats.bot_stats.status")
        print("Status cog loaded successfully")
        
        # Load server stats cog
        await bot.load_extension("cog.stats.stats_server.server_stats")
        print("Server stats cog loaded successfully")
        
        # Load mining commands cog
        await bot.load_extension("cog.cryptonel.mining.mining_commands")
        print("Mining commands cog loaded successfully")
        
        # Load wallet commands cog
        await bot.load_extension("cog.cryptonel.wallet.wallet_commands")
        print("Wallet commands cog loaded successfully")
        
        # Transfer commands disabled as requested
        # await bot.load_extension("cog.cryptonel.transfer.transfer_commands")
        # print("Transfer commands cog loaded successfully")
        
        # Load server management commands cog
        await bot.load_extension("cog.management.server_commands")
        print("Server management cog loaded successfully")
    except Exception as e:
        print(f"Failed to load extension: {e}")
        import traceback
        traceback.print_exc()

async def main():
    # Get the token and strip any whitespace
    token = os.getenv('TOKEN')
    if token:
        token = token.strip()
    else:
        print("ERROR: No token found in environment variables")
        return
    
    try:
        # Load extensions first
        await load_extensions()
        # Then run the bot
        print("Connecting to Discord...")
        await bot.start(token)
    except Exception as e:
        print(f"Error starting the bot: {e}")
        import traceback
        traceback.print_exc()

# Run the bot
if __name__ == "__main__":
    asyncio.run(main()) 