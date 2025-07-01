import discord
from discord.ext import commands
from discord import app_commands
from discord.ui import Select, View, Button
import datetime
import pymongo
import os
from dotenv import load_dotenv
import asyncio
import traceback
from typing import Dict, List, Optional
from .utils import check_ban_status

# Load environment variables
load_dotenv('clyne.env')

# MongoDB connection
MONGODB_URI = os.getenv('MONGODB_URI')
client = pymongo.MongoClient(MONGODB_URI)

# Define databases and collections
db_mining = client['cryptonel_mining']
mining_data = db_mining['mining_data']

db_wallet = client['cryptonel_wallet']
users = db_wallet['users']

# Rate limit implementation
class RateLimiter:
    def __init__(self, max_calls: int = 10, cooldown: int = 60):
        self.max_calls = max_calls
        self.cooldown = cooldown  # in seconds
        self.users: Dict[str, List[datetime.datetime]] = {}
    
    def is_rate_limited(self, user_id: str) -> bool:
        """Check if a user is rate limited"""
        current_time = datetime.datetime.now()
        
        if user_id not in self.users:
            self.users[user_id] = [current_time]
            return False
            
        # Remove timestamps older than cooldown period
        self.users[user_id] = [ts for ts in self.users[user_id] 
                             if (current_time - ts).total_seconds() < self.cooldown]
                             
        # Add current timestamp
        self.users[user_id].append(current_time)
        
        # Check if rate limited
        return len(self.users[user_id]) > self.max_calls

# Set up the dropdown view
class MiningView(View):
    def __init__(self, bot, cog):
        super().__init__(timeout=60)
        self.bot = bot
        self.cog = cog
        self.add_item(MiningDropdown(bot, cog))

# Create dropdown menu for mining options
class MiningDropdown(Select):
    def __init__(self, bot, cog):
        self.bot = bot
        self.cog = cog
        options = [
            discord.SelectOption(label="Check Mining", value="check_mining", 
                                description="Check when you can mine next"),
            discord.SelectOption(label="Mining Stats", value="mining_stats", 
                                description="View your mining statistics")
        ]
        super().__init__(placeholder="Select a mining option...", options=options)
    
    async def callback(self, interaction: discord.Interaction):
        try:
            if self.values[0] == "check_mining":
                await self.check_mining_callback(interaction)
            elif self.values[0] == "mining_stats":
                await self.mining_stats_callback(interaction)
        except Exception as e:
            print(f"Error in dropdown callback: {e}")
            print(traceback.format_exc())
            
            # Send error message to user
            try:
                embed = discord.Embed(
                    title="❌ Error",
                    description="An error occurred while processing your request. Please try again later.",
                    color=0x8f92b1
                )
                if interaction.response.is_done():
                    await interaction.followup.send(embed=embed, ephemeral=True)
                else:
                    await interaction.response.send_message(embed=embed, ephemeral=True)
            except:
                pass

    async def check_mining_callback(self, interaction: discord.Interaction):
        try:
            user_id = str(interaction.user.id)
            
            # Get mining data
            try:
                mining_info = mining_data.find_one({"user_id": user_id})
            except Exception as e:
                print(f"Error retrieving mining data: {e}")
                embed = discord.Embed(
                    title="❌ Database Error",
                    description="Unable to retrieve your mining data. Please try again later.",
                    color=0x8f92b1
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            if not mining_info or "last_mined" not in mining_info:
                embed = discord.Embed(
                    title="✅ Ready to Mine!",
                    description="You can start mining now! Visit our dashboard to begin:\nhttps://cryptonel.online/mining",
                    color=0x8f92b1
                )
                
                # Create a view with a button
                mining_view = View()
                mining_button = Button(label="Start Mining Now", url="https://cryptonel.online/mining", style=discord.ButtonStyle.url)
                mining_view.add_item(mining_button)
                
                await interaction.response.send_message(embed=embed, view=mining_view)
                return
            
            # Calculate time until next mining
            try:
                last_mined = mining_info["last_mined"]
                now = datetime.datetime.now(datetime.timezone.utc)
                
                # Make sure both datetimes are in the same format (timezone-aware)
                # If last_mined is naive (no timezone), make it aware
                if last_mined.tzinfo is None:
                    last_mined = last_mined.replace(tzinfo=datetime.timezone.utc)
                
                # Default mining cooldown is 24 hours
                mining_cooldown = datetime.timedelta(hours=24)
                next_mining_time = last_mined + mining_cooldown
                
                if now >= next_mining_time:
                    embed = discord.Embed(
                        title="✅ Ready to Mine!",
                        description="You can mine again now! Visit our dashboard to begin:\nhttps://cryptonel.online/mining",
                        color=0x8f92b1
                    )
                    
                    # Create a view with a button
                    mining_view = View()
                    mining_button = Button(label="Start Mining Now", url="https://cryptonel.online/mining", style=discord.ButtonStyle.url)
                    mining_view.add_item(mining_button)
                    
                    await interaction.response.send_message(embed=embed, view=mining_view)
                else:
                    time_left = next_mining_time - now
                    hours, remainder = divmod(time_left.total_seconds(), 3600)
                    minutes, seconds = divmod(remainder, 60)
                    
                    embed = discord.Embed(
                        title="⏳ Mining Cooldown",
                        description=f"You need to wait **{int(hours)}h {int(minutes)}m {int(seconds)}s** before you can mine again.",
                        color=0x8f92b1
                    )
                    embed.add_field(name="Dashboard", value="[Open Mining Dashboard](https://cryptonel.online/mining)")
                    
                    await interaction.response.send_message(embed=embed)
            except Exception as e:
                print(f"Error calculating mining time: {e}")
                print(traceback.format_exc())
                embed = discord.Embed(
                    title="❌ Error",
                    description="An error occurred while calculating your mining time. Please try again later.",
                    color=0x8f92b1
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            print(f"Unhandled error in check_mining_callback: {e}")
            print(traceback.format_exc())
            try:
                embed = discord.Embed(
                    title="❌ Error",
                    description="An unexpected error occurred. Please try again later.",
                    color=0x8f92b1
                )
                if interaction.response.is_done():
                    await interaction.followup.send(embed=embed, ephemeral=True)
                else:
                    await interaction.response.send_message(embed=embed, ephemeral=True)
            except:
                pass

    async def mining_stats_callback(self, interaction: discord.Interaction):
        try:
            user_id = str(interaction.user.id)
            
            # Get mining data
            try:
                mining_info = mining_data.find_one({"user_id": user_id})
            except Exception as e:
                print(f"Error retrieving mining data: {e}")
                embed = discord.Embed(
                    title="❌ Database Error",
                    description="Unable to retrieve your mining data. Please try again later.",
                    color=0x8f92b1
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            if not mining_info:
                embed = discord.Embed(
                    title="📊 Mining Statistics",
                    description="You haven't mined any CRN yet. Start mining today!",
                    color=0x8f92b1
                )
                await interaction.response.send_message(embed=embed)
                return
            
            total_mined = mining_info.get("total_mined", "0")
            
            embed = discord.Embed(
                title="📊 Mining Statistics",
                description=f"Here are your mining statistics:",
                color=0x8f92b1
            )
            embed.add_field(name="Total CRN Mined", value=f"**{total_mined}** CRN", inline=False)
            embed.add_field(name="Dashboard", value="[Open Mining Dashboard](https://cryptonel.online/mining)", inline=False)
            embed.set_footer(text="Cryptonel Mining")
            
            await interaction.response.send_message(embed=embed)
        except Exception as e:
            print(f"Unhandled error in mining_stats_callback: {e}")
            print(traceback.format_exc())
            try:
                embed = discord.Embed(
                    title="❌ Error",
                    description="An unexpected error occurred. Please try again later.",
                    color=0x8f92b1
                )
                if interaction.response.is_done():
                    await interaction.followup.send(embed=embed, ephemeral=True)
                else:
                    await interaction.response.send_message(embed=embed, ephemeral=True)
            except:
                pass

class MiningCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.rate_limiter = RateLimiter(max_calls=10, cooldown=60)
    
    @app_commands.command(name="mining", description="Access Cryptonel mining features")
    async def mining(self, interaction: discord.Interaction):
        """Mining command with dropdown menu for various mining options"""
        try:
            # Check if user is banned
            if not await check_ban_status(interaction):
                return  # User is banned, message already sent by check_ban_status
            
            # Check rate limiting
            if self.rate_limiter.is_rate_limited(str(interaction.user.id)):
                embed = discord.Embed(
                    title="⚠️ Rate Limited",
                    description="You're using this command too frequently. Please wait a minute before trying again.",
                    color=0x8f92b1
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            # Get user data to check if wallet exists
            user_id = str(interaction.user.id)
            user_data = users.find_one({"user_id": user_id})
            
            # If wallet doesn't exist, don't show options - this ensures we don't show options to users without wallets
            if not user_data:
                return # check_ban_status already showed the message and button
            
            embed = discord.Embed(
                title="⛏️ Cryptonel Mining",
                description="Select an option from the dropdown menu below:",
                color=0x8f92b1
            )
            view = MiningView(self.bot, self)
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        except Exception as e:
            print(f"Error in mining command: {e}")
            print(traceback.format_exc())
            try:
                embed = discord.Embed(
                    title="❌ Error",
                    description="An error occurred while processing your request. Please try again later.",
                    color=0x8f92b1
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
            except:
                pass

# Change to non-async version
async def setup(bot):
    await bot.add_cog(MiningCog(bot)) 