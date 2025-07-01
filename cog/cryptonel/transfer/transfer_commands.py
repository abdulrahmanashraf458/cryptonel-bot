import discord
from discord.ext import commands
from discord import app_commands
from discord.ui import Select, View, Button, Modal, TextInput
import datetime
import pymongo
import os
from dotenv import load_dotenv
import asyncio
import traceback
import uuid
import re
from typing import Dict, List, Optional, Union, Tuple
from .utils import (
    check_transfer_status,
    get_transfer_settings,
    check_recipient,
    calculate_fee,
    verify_auth,
    record_transaction,
    TransferRateLimiter
)
# Email sending is handled by record_transaction

# Load environment variables
load_dotenv('clyne.env')

# MongoDB connection
MONGODB_URI = os.getenv('MONGODB_URI')
client = pymongo.MongoClient(MONGODB_URI)

# Define databases and collections
db_wallet = client['cryptonel_wallet']
users = db_wallet['users']
db_settings = client['cryptonel_settings']
settings = db_settings['settings']

# Initialize rate limiter
transfer_rate_limiter = TransferRateLimiter()

# Set up the dropdown view
class TransferView(View):
    def __init__(self, bot, cog):
        super().__init__(timeout=60)
        self.bot = bot
        self.cog = cog
        self.add_item(TransferDropdown(bot, cog))

# Create dropdown menu for transfer options
class TransferDropdown(Select):
    def __init__(self, bot, cog):
        self.bot = bot
        self.cog = cog
        options = [
            discord.SelectOption(label="Send CRN", value="send_coins", 
                                description="Transfer CRN to another user"),
            discord.SelectOption(label="Transfer History", value="transfer_history", 
                                description="View your transfer history"),
            discord.SelectOption(label="Fee Calculator", value="fee_calculator", 
                                description="Calculate fee on your transfers"),
            discord.SelectOption(label="⚡ Quick Transfer (Premium)", value="quick_transfer",
                                description="Quickly transfer to contacts (Premium users only)")
        ]
        super().__init__(placeholder="Select a transfer option...", options=options)
    
    async def callback(self, interaction: discord.Interaction):
        try:
            if self.values[0] == "send_coins":
                await self.send_coins_callback(interaction)
            elif self.values[0] == "transfer_history":
                await self.transfer_history_callback(interaction)
            elif self.values[0] == "fee_calculator":
                await self.fee_calculator_callback(interaction)
            elif self.values[0] == "quick_transfer":
                await self.quick_transfer_callback(interaction)
        except Exception as e:
            print(f"Error in transfer dropdown callback: {e}")
            print(traceback.format_exc())
            
            # Send error message to user
            try:
                embed = discord.Embed(
                    title="Error",
                    description="An error occurred while processing your request. Please try again later.",
                    color=0x8f92b1
                )
                if interaction.response.is_done():
                    await interaction.followup.send(embed=embed, ephemeral=True)
                else:
                    await interaction.response.send_message(embed=embed, ephemeral=True)
            except:
                pass

    async def send_coins_callback(self, interaction: discord.Interaction):
        # Check if user can transfer funds
        if not await check_transfer_status(interaction):
            return
        
        # Get user data
        user_id = str(interaction.user.id)
        user_data = users.find_one({"user_id": user_id})
        
        # Get transfer settings
        transfer_settings = await get_transfer_settings()
        
        # Check if user is rate limited
        is_limited, remaining, reset_time = await transfer_rate_limiter.check_rate_limit(
            user_id, transfer_settings
        )
        if is_limited:
            embed = discord.Embed(
                title="⏱️ Rate Limited",
                description=f"You've reached the maximum number of transfers. Please wait {reset_time} minute(s) to make another transfer.",
                color=0x8f92b1
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # Determine authentication method
        auth_methods = user_data.get("transfer_auth", {"secret_word": True})
        auth_type = None
        auth_label = None
        
        if auth_methods.get("secret_word", True):
            auth_type = "secret_word"
            auth_label = "Secret Word"
        elif auth_methods.get("2fa", False):
            auth_type = "2fa"
            auth_label = "2FA Code"
        elif auth_methods.get("password", False):
            auth_type = "password"
            auth_label = "Transfer Password"
        else:
            # Default to secret_word if nothing is specified
            auth_type = "secret_word"
            auth_label = "Secret Word"
            
        # Create modal for transfer information with authentication
        transfer_modal = TransferModal(user_data, transfer_settings, auth_type, auth_label)
        await interaction.response.send_modal(transfer_modal)

    async def transfer_history_callback(self, interaction: discord.Interaction):
        # Check if user can use transfer features
        if not await check_transfer_status(interaction):
            return
        
        # Defer the response to give us time to fetch data
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Get user data
            user_id = str(interaction.user.id)
            
            # Get transactions
            db_wallet = client['cryptonel_wallet']
            transactions = db_wallet['user_transactions']
            user_transactions = transactions.find_one({"user_id": user_id})
            
            if not user_transactions or "transactions" not in user_transactions or not user_transactions["transactions"]:
                embed = discord.Embed(
                    title="📜 Transfer History",
                    description="You don't have any transfer history yet.",
                    color=0x8f92b1
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return
            
            # Get last 5 transactions
            tx_list = user_transactions["transactions"]
            tx_list.sort(key=lambda x: x.get("timestamp", datetime.datetime.min), reverse=True)
            recent_tx = tx_list[:5]
            
            # Create embed
            embed = discord.Embed(
                title="📜 Recent Transfers",
                description="Here are your most recent transfers:",
                color=0x8f92b1
            )
            
            for tx in recent_tx:
                tx_type = tx.get("type", "unknown")
                # Format amount to show proper decimal places
                amount_str = tx.get("amount", "0")
                try:
                    amount_float = float(amount_str)
                    # Display integer part if it's a whole number, otherwise show with appropriate decimals
                    if amount_float.is_integer():
                        amount_display = f"{int(amount_float)}"
                    else:
                        # Show up to 2 decimal places if there are meaningful decimals
                        amount_display = f"{amount_float:.2f}".rstrip('0').rstrip('.') if '.' in f"{amount_float:.2f}" else f"{int(amount_float)}"
                except:
                    amount_display = amount_str
                    
                timestamp = tx.get("timestamp", datetime.datetime.now()).strftime("%Y-%m-%d %H:%M:%S")
                counterparty = tx.get("counterparty_username", "Unknown")
                
                if tx_type == "sent":
                    embed.add_field(
                        name=f"Sent {amount_display} CRN",
                        value=f"To: {counterparty}\nDate: {timestamp}\nReason: {tx.get('reason', 'Not specified')}",
                        inline=False
                    )
                else:
                    embed.add_field(
                        name=f"Received {amount_display} CRN",
                        value=f"From: {counterparty}\nDate: {timestamp}\nReason: {tx.get('reason', 'Not specified')}",
                        inline=False
                    )
            
            embed.set_footer(text="For full history, visit the Cryptonel website")
            
            # Add button to view full history
            view = View()
            history_button = Button(
                label="View Full History", 
                url="https://cryptonel.online/history",
                style=discord.ButtonStyle.url
            )
            view.add_item(history_button)
            
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        except Exception as e:
            print(f"Error in transfer history: {e}")
            print(traceback.format_exc())
            
            embed = discord.Embed(
                title="❌ Error",
                description="An error occurred while retrieving your transfer history. Please try again later.",
                color=0x8f92b1
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

    async def fee_calculator_callback(self, interaction: discord.Interaction):
        # Check if user can use fee calculator
        if not await check_transfer_status(interaction):
            return
        
        # Import the fee calculator functionality
        from .fee_calculator import calculate_fee_callback
        await calculate_fee_callback(interaction)
        
    async def quick_transfer_callback(self, interaction: discord.Interaction):
        # Check if user is premium
        user_data = users.find_one({"user_id": str(interaction.user.id)})
        if not user_data or not user_data.get("premium", False):
            embed = discord.Embed(
                title="⭐ Premium Only",
                description="Quick Transfer is a premium feature. Upgrade to premium to use this feature!",
                color=0x8f92b1
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
            
        # Check if user can transfer
        if not await check_transfer_status(interaction):
            return
        
        # Show contacts selection
        from .quick_transfer import show_contacts_selection
        await show_contacts_selection(interaction)

# Transfer modal for collecting transfer details
class TransferModal(Modal):
    def __init__(self, user_data, transfer_settings, auth_type, auth_label):
        super().__init__(title="Transfer Funds")
        self.user_data = user_data
        self.transfer_settings = transfer_settings
        self.auth_type = auth_type
        self.auth_label = auth_label
        
        # Calculate fee rate and set placeholder text
        fee_rate = float(transfer_settings.get("tax_rate", "0.01"))
        fee_percentage = fee_rate * 100
        is_premium = user_data.get("premium", False)
        premium_settings = transfer_settings.get("premium_settings", {})
        
        # Determine if fee applies to this user
        fee_applies = transfer_settings.get("tax_enabled", True)
        if is_premium and premium_settings.get("tax_exempt_enabled", True) and premium_settings.get("tax_exempt", True):
            fee_applies = False
        
        # Create fee info text
        if fee_applies:
            fee_info = f"({fee_percentage:.1f}% fee will be deducted)"
        else:
            fee_info = "(No fee - Premium Benefit)"
        
        # Add inputs
        self.private_address = TextInput(
            label="Recipient's Private Address",
            placeholder="Enter the recipient's private address",
            required=True
        )
        self.add_item(self.private_address)
        
        # Set min and max amounts
        min_amount = float(transfer_settings.get("min_amount", "0.25"))
        max_amount = float(transfer_settings.get("max_amount", "1000.0"))
        
        self.amount = TextInput(
            label=f"Amount (Min: {min_amount}, Max: {max_amount})",
            placeholder=f"Enter amount to send {fee_info}",
            required=True
        )
        self.add_item(self.amount)
        
        self.reason = TextInput(
            label="Reason for Transfer",
            placeholder="Enter the reason for this transfer",
            required=True,
            max_length=100
        )
        self.add_item(self.reason)
        
        # Add authentication field
        self.auth_input = TextInput(
            label=f"Enter your {auth_label}",
            placeholder=f"Provide your {auth_label} for security verification",
            required=True
        )
        self.add_item(self.auth_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        # Defer the response to give us time to process
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Get input values
            private_address = self.private_address.value.strip()
            amount_str = self.amount.value.strip()
            reason = self.reason.value.strip()
            auth_value = self.auth_input.value.strip()
            
            # Verify authentication first
            auth_valid = await verify_auth(self.user_data, auth_value, self.auth_type)
            
            if not auth_valid:
                embed = discord.Embed(
                    title="❌ Authentication Failed",
                    description=f"The {self.auth_label} you provided is incorrect. Transfer cancelled.",
                    color=0xff0000
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return
            
            # Validate recipient
            recipient_exists, recipient_data = await check_recipient(private_address)
            if not recipient_exists:
                embed = discord.Embed(
                    title="❌ Invalid Recipient",
                    description="The private address you entered does not exist. Please check and try again.",
                    color=0x8f92b1
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return
            
            # Prevent self-transfers
            if recipient_data.get("user_id") == self.user_data.get("user_id"):
                embed = discord.Embed(
                    title="❌ Self Transfer",
                    description="You cannot transfer funds to yourself.",
                    color=0x8f92b1
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return
            
            # Validate amount format and value
            try:
                # Check for invalid formats like leading zeros (except for decimal < 1)
                if re.match(r'^0\d+', amount_str):
                    embed = discord.Embed(
                        title="❌ Invalid Amount Format",
                        description="Please enter a valid number format without leading zeros. Examples: 1, 1.5, 0.75, etc.",
                        color=0x8f92b1
                    )
                    await interaction.followup.send(embed=embed, ephemeral=True)
                    return
                
                # Convert to float and normalize to 8 decimal places
                amount_str = amount_str.replace(',', '.')
                amount_float = float(amount_str)
                amount = float(f"{amount_float:.8f}")
                
                min_amount = float(self.transfer_settings.get("min_amount", "0.25"))
                max_amount = float(self.transfer_settings.get("max_amount", "1000.0"))
                
                if amount < min_amount:
                    embed = discord.Embed(
                        title="❌ Amount Too Small",
                        description=f"The minimum transfer amount is {min_amount} CRN.",
                        color=0x8f92b1
                    )
                    await interaction.followup.send(embed=embed, ephemeral=True)
                    return
                
                if amount > max_amount:
                    embed = discord.Embed(
                        title="❌ Amount Too Large",
                        description=f"The maximum transfer amount is {max_amount} CRN.",
                        color=0x8f92b1
                    )
                    await interaction.followup.send(embed=embed, ephemeral=True)
                    return
                
                # Calculate fee and total amount sender will pay
                is_premium = self.user_data.get("premium", False)
                fee, amount_after_fee = await calculate_fee(amount, is_premium, self.transfer_settings)
                
                # Check if user has enough balance for amount
                user_balance = float(self.user_data.get("balance", "0"))
                if amount > user_balance:
                    # Calculate how much they need to add
                    shortfall = amount - user_balance
                    
                    embed = discord.Embed(
                        title="❌ Insufficient Funds",
                        description=f"You don't have enough funds to send {amount} CRN.\n\n"
                                    f"Required: {amount:.2f} CRN\n"
                                    f"Your balance: {user_balance:.2f} CRN\n"
                                    f"Shortfall: {shortfall:.2f} CRN",
                        color=0x8f92b1
                    )
                    await interaction.followup.send(embed=embed, ephemeral=True)
                    return
                
            except ValueError:
                embed = discord.Embed(
                    title="❌ Invalid Amount",
                    description="Please enter a valid number for the amount.",
                    color=0x8f92b1
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return
            
            # Calculate fee for display
            is_premium = self.user_data.get("premium", False)
            fee, amount_after_fee = await calculate_fee(amount, is_premium, self.transfer_settings)
            total_amount = amount + fee  # This is what will be deducted from sender
            
            # Format amounts for display with appropriate decimals
            def format_amount(value):
                if float(value).is_integer():
                    return str(int(float(value)))
                else:
                    # Format with 8 decimal places max, remove trailing zeros
                    return f"{float(value):.8f}".rstrip('0').rstrip('.') 
            
            amount_display = format_amount(amount)
            fee_display = format_amount(fee)
            total_display = format_amount(total_amount)
            
            # Process the transfer
            try:
                # Double check user's balance before proceeding
                updated_user = users.find_one({"user_id": self.user_data.get("user_id")})
                current_balance = float(updated_user.get("balance", "0"))
                
                if amount > current_balance:
                    embed = discord.Embed(
                        title="❌ Insufficient Funds",
                        description=f"Your balance has changed. You need {amount} CRN to complete this transfer.\n"
                                    f"Current balance: {current_balance:.2f} CRN",
                        color=0xff0000
                    )
                    await interaction.followup.send(embed=embed, ephemeral=True)
                    return
                
                # Process the transfer - ensure all values are properly formatted to 8 decimal places
                tx_id = await record_transaction(
                    self.user_data,
                    recipient_data,
                    float(f"{amount:.8f}"),  # Format to 8 decimal places
                    float(f"{amount_after_fee:.8f}"),  # Recipient gets amount after fee
                    float(f"{fee:.8f}"),
                    reason
                )
                
                # Send confirmation to sender
                embed = discord.Embed(
                    title="✅ Transfer Complete",
                    description=f"You have successfully transferred funds to {recipient_data.get('username')}.",
                    color=0x00ff00
                )
                
                embed.add_field(
                    name="Amount Sent",
                    value=f"{amount_display} CRN",
                    inline=True
                )
                
                if fee > 0:
                    embed.add_field(
                        name="Transaction Fee",
                        value=f"{fee_display} CRN",
                        inline=True
                    )
                    
                    embed.add_field(
                        name="Recipient Received",
                        value=f"{format_amount(amount_after_fee)} CRN",
                        inline=True
                    )
                else:
                    embed.add_field(
                        name="Transaction Fee",
                        value="0 CRN (Premium Benefit)",
                        inline=True
                    )
                    
                    embed.add_field(
                        name="Recipient Received",
                        value=f"{amount_display} CRN",
                        inline=True
                    )
                
                embed.add_field(
                    name="Transaction ID",
                    value=tx_id,
                    inline=False
                )
                
                await interaction.followup.send(embed=embed, ephemeral=True)
                
                # Try to send DM to recipient
                try:
                    recipient_user_id = int(recipient_data.get("user_id"))
                    recipient_user = interaction.client.get_user(recipient_user_id)
                    
                    if recipient_user:
                        recipient_embed = discord.Embed(
                            title="💰 Funds Received",
                            description=f"You have received funds from {self.user_data.get('username')}.",
                            color=0x00ff00
                        )
                        
                        recipient_embed.add_field(
                            name="Amount Received",
                            value=f"{format_amount(amount_after_fee)} CRN",
                            inline=True
                        )
                        
                        if fee > 0:
                            recipient_embed.add_field(
                                name="Fee Deducted",
                                value=f"{fee_display} CRN",
                                inline=True
                            )
                        
                        recipient_embed.add_field(
                            name="Reason",
                            value=reason,
                            inline=False
                        )
                        
                        recipient_embed.add_field(
                            name="Transaction ID",
                            value=tx_id,
                            inline=False
                        )
                        
                        await recipient_user.send(embed=recipient_embed)
                except Exception as e:
                    print(f"Failed to send DM to recipient: {e}")
                    # Don't notify the sender about this failure
            
            except Exception as e:
                print(f"Error processing transfer: {e}")
                print(traceback.format_exc())
                
                embed = discord.Embed(
                    title="❌ Transfer Failed",
                    description="An error occurred while processing your transfer. Please try again later.",
                    color=0xff0000
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            print(f"Error in transfer modal submission: {e}")
            print(traceback.format_exc())
            
            embed = discord.Embed(
                title="❌ Error",
                description="An error occurred while processing your transfer. Please try again later.",
                color=0x8f92b1
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

class TransferCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    @app_commands.command(name="transfer", description="Transfer CRN to another user")
    async def transfer(self, interaction: discord.Interaction):
        try:
            # Defer response immediately to prevent timeout
            await interaction.response.defer(ephemeral=True)
            
            # Check if user can use transfer features
            status_check = await check_transfer_status(interaction)
            if not status_check:
                return
            
            # Get user data and transfer settings
            user_id = str(interaction.user.id)
            user_data = users.find_one({"user_id": user_id})
            
            # Double check user has a wallet (should already be checked by check_transfer_status)
            if not user_data:
                return
                
            transfer_settings = await get_transfer_settings()
            
            # Create embed with fee information
            embed = discord.Embed(
                title="Transfer Options",
                color=0x8f92b1
            )
            
            # Get fee rate and check premium status
            fee_rate = float(transfer_settings.get("tax_rate", "0.01"))
            fee_percentage = fee_rate * 100
            is_premium = user_data.get("premium", False)
            premium_settings = transfer_settings.get("premium_settings", {})
            
            # Build description with fee info
            description = "Select an option to proceed:\n\n"
            
            if transfer_settings.get("tax_enabled", True):
                if is_premium and premium_settings.get("tax_exempt_enabled", True) and premium_settings.get("tax_exempt", True):
                    description += f"**Current Fee Rate:** 0% (Premium Benefit)\n"
                    description += "As a premium user, you are exempt from transfer fees."
                else:
                    description += f"**Current Fee Rate:** {fee_percentage:.1f}%\n"
                    description += f"This fee will be deducted from your transfer amount."
            else:
                description += "**Current Fee Rate:** 0%\n"
                description += "Transfers are currently fee-free for all users."
            
            # Add premium quick transfer info if user is premium
            if is_premium:
                description += "\n\n⚡ **Premium Quick Transfer** is available in the dropdown menu!"
            
            embed.description = description
            
            # Create view with dropdown menu
            view = TransferView(self.bot, self)
            
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
            
        except Exception as e:
            print(f"Error in transfer command: {e}")
            print(traceback.format_exc())
            
            embed = discord.Embed(
                title="❌ Error",
                description="An error occurred while processing your request. Please try again later.",
                color=0x8f92b1
            )
            
            # Use followup instead of response since we've already deferred
            try:
                await interaction.followup.send(embed=embed, ephemeral=True)
            except:
                pass

# Setup function for loading the cog
async def setup(bot):
    await bot.add_cog(TransferCog(bot))
    print("Transfer commands cog loaded successfully") 