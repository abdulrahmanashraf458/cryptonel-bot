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
from .utils import check_wallet_status

# Load environment variables
load_dotenv('clyne.env')

# MongoDB connection
MONGODB_URI = os.getenv('MONGODB_URI')
client = pymongo.MongoClient(MONGODB_URI)

# Define database and collection
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
class WalletView(View):
    def __init__(self, bot, cog):
        super().__init__(timeout=60)
        self.bot = bot
        self.cog = cog
        self.add_item(WalletDropdown(bot, cog))

# Create dropdown menu for wallet options
class WalletDropdown(Select):
    def __init__(self, bot, cog):
        self.bot = bot
        self.cog = cog
        options = [
            discord.SelectOption(label="Check Balance", value="check_balance", 
                                description="View your CRN balance"),
            discord.SelectOption(label="Private Address", value="private_address", 
                                description="View your private address")
        ]
        super().__init__(placeholder="Select a wallet option...", options=options)
    
    async def callback(self, interaction: discord.Interaction):
        try:
            if self.values[0] == "check_balance":
                await self.check_balance_callback(interaction)
            elif self.values[0] == "private_address":
                await self.private_address_callback(interaction)
        except Exception as e:
            print(f"Error in wallet dropdown callback: {e}")
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

    async def check_balance_callback(self, interaction: discord.Interaction):
        try:
            user_id = str(interaction.user.id)
            
            # Check if user has a wallet
            try:
                wallet = users.find_one({"user_id": user_id})
                if not wallet:
                    embed = discord.Embed(
                        title="❌ Wallet Required",
                        description="You need to create a wallet to view your balance. Please visit https://cryptonel.online to register.",
                        color=0x8f92b1
                    )
                    
                    # Create a view with a button
                    wallet_view = View()
                    wallet_button = Button(label="Create Wallet", url="https://cryptonel.online", style=discord.ButtonStyle.url)
                    wallet_view.add_item(wallet_button)
                    
                    await interaction.response.send_message(embed=embed, view=wallet_view, ephemeral=True)
                    return
            except Exception as e:
                print(f"Error checking wallet: {e}")
                embed = discord.Embed(
                    title="❌ Database Error",
                    description="Unable to check your wallet. Please try again later.",
                    color=0x8f92b1
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            # Get balance
            try:
                balance = wallet.get("balance", "0")
                
                # Show both decimal and integer representations
                try:
                    decimal_balance = balance
                    integer_balance = int(float(balance))
                except:
                    decimal_balance = balance
                    integer_balance = 0
                
                embed = discord.Embed(
                    title="Wallet Balance",
                    description=f"Here is your current wallet balance:",
                    color=0x8f92b1
                )
                embed.add_field(name="Balance", value=f"**{integer_balance}** CRN\n\n{decimal_balance} CRN", inline=False)
                embed.add_field(name="Dashboard", value="[Open Wallet Dashboard](https://cryptonel.online/wallet)", inline=False)
                embed.set_footer(text="Cryptonel Wallet")
                
                await interaction.response.send_message(embed=embed)
            except Exception as e:
                print(f"Error retrieving balance: {e}")
                print(traceback.format_exc())
                embed = discord.Embed(
                    title="❌ Error",
                    description="An error occurred while retrieving your balance. Please try again later.",
                    color=0x8f92b1
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            print(f"Unhandled error in check_balance_callback: {e}")
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

    async def private_address_callback(self, interaction: discord.Interaction):
        try:
            user_id = str(interaction.user.id)
            
            # Check if user has a wallet
            try:
                wallet = users.find_one({"user_id": user_id})
                if not wallet:
                    embed = discord.Embed(
                        title="❌ Wallet Required",
                        description="You need to create a wallet to view your private address. Please visit https://cryptonel.online to register.",
                        color=0x8f92b1
                    )
                    
                    # Create a view with a button
                    wallet_view = View()
                    wallet_button = Button(label="Create Wallet", url="https://cryptonel.online", style=discord.ButtonStyle.url)
                    wallet_view.add_item(wallet_button)
                    
                    await interaction.response.send_message(embed=embed, view=wallet_view, ephemeral=True)
                    return
            except Exception as e:
                print(f"Error checking wallet: {e}")
                embed = discord.Embed(
                    title="❌ Database Error",
                    description="Unable to check your wallet. Please try again later.",
                    color=0x8f92b1
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            # Get private address
            try:
                private_address = wallet.get("private_address", "Not available")
                
                embed = discord.Embed(
                    title="Private Address",
                    description=f"Here is your private address for your wallet:",
                    color=0x8f92b1
                )
                embed.add_field(name="Private Address", value=f"`{private_address}`", inline=False)
                embed.add_field(name="Dashboard", value="[Open Wallet Dashboard](https://cryptonel.online/wallet)", inline=False)
                embed.set_footer(text="Cryptonel Wallet")
                
                # Create a copy button class for this specific interaction
                class CopyButton(Button):
                    def __init__(self, address):
                        super().__init__(label="Copy Address", style=discord.ButtonStyle.primary)
                        self.address = address
                        
                    async def callback(self, interaction):
                        try:
                            # Send a plain text message with the address
                            await interaction.response.send_message(self.address, ephemeral=True)
                        except Exception as e:
                            print(f"Error in copy button callback: {e}")
                
                # Create the view with the copy button
                address_view = View()
                address_view.add_item(CopyButton(private_address))
                address_view.add_item(Button(label="Open Wallet", url="https://cryptonel.online/wallet", style=discord.ButtonStyle.url))
                
                # Send as an ephemeral message for security
                await interaction.response.send_message(embed=embed, view=address_view, ephemeral=True)
            except Exception as e:
                print(f"Error retrieving private address: {e}")
                print(traceback.format_exc())
                embed = discord.Embed(
                    title="❌ Error",
                    description="An error occurred while retrieving your private address. Please try again later.",
                    color=0x8f92b1
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            print(f"Unhandled error in private_address_callback: {e}")
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

class WalletCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.rate_limiter = RateLimiter(max_calls=10, cooldown=60)
    
    @app_commands.command(name="wallet", description="Access Cryptonel wallet features")
    async def wallet(self, interaction: discord.Interaction):
        """Wallet command with dropdown menu for various wallet options"""
        try:
            # Check if user is banned or wallet is locked
            if not await check_wallet_status(interaction):
                return  # User is banned or wallet is locked, message already sent by check_wallet_status
                
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
                return # check_wallet_status already showed the message and button
            
            embed = discord.Embed(
                title="Cryptonel Wallet",
                description="Select an option from the dropdown menu below:",
                color=0x8f92b1
            )
            view = WalletView(self.bot, self)
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        except Exception as e:
            print(f"Error in wallet command: {e}")
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

async def setup(bot):
    await bot.add_cog(WalletCog(bot)) 