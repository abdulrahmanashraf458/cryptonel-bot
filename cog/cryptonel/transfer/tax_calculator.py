import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View, Modal, TextInput
import traceback
import re
from typing import Dict
import pymongo
import os
from dotenv import load_dotenv

from .utils import get_transfer_settings, calculate_fee

# Load environment variables
load_dotenv('clyne.env')

# MongoDB connection
MONGODB_URI = os.getenv('MONGODB_URI')
client = pymongo.MongoClient(MONGODB_URI)

# Define databases and collections
db_wallet = client['cryptonel_wallet']
users = db_wallet['users']

class FeeCalculatorModal(Modal):
    def __init__(self, transfer_settings):
        super().__init__(title="Fee Calculator")
        self.transfer_settings = transfer_settings
        
        # Get fee rate for display
        fee_rate = float(transfer_settings.get("tax_rate", "0.01"))
        fee_percentage = fee_rate * 100
        
        # Add amount input
        self.amount = TextInput(
            label=f"Amount To Send",
            placeholder=f"Enter amount to calculate {fee_percentage:.1f}% fee",
            required=True
        )
        self.add_item(self.amount)
    
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Get input values
            amount_str = self.amount.value.strip()
            
            # Validate amount
            try:
                # Check for invalid formats
                if re.match(r'^0\d+', amount_str):
                    embed = discord.Embed(
                        title="Invalid Amount Format",
                        description="Please enter a valid number format without leading zeros. Examples: 1, 1.5, 0.75, etc.",
                        color=0x8f92b1
                    )
                    await interaction.followup.send(embed=embed, ephemeral=True)
                    return
                
                # Convert to float
                amount = float(amount_str)
                if amount <= 0:
                    embed = discord.Embed(
                        title="Invalid Amount",
                        description="Please enter an amount greater than zero.",
                        color=0x8f92b1
                    )
                    await interaction.followup.send(embed=embed, ephemeral=True)
                    return
                
            except ValueError:
                embed = discord.Embed(
                    title="Invalid Amount",
                    description="Please enter a valid number for the amount.",
                    color=0x8f92b1
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return
            
            # Get user data to check premium status
            user_id = str(interaction.user.id)
            user_data = users.find_one({"user_id": user_id})
            is_premium = user_data.get("premium", False) if user_data else False
            
            # Calculate fee
            fee, amount_after_fee = await calculate_fee(amount, is_premium, self.transfer_settings)
            
            # Format numbers for display with 8 decimal places maximum
            def format_amount(value):
                # دائمًا أظهر 8 أرقام عشرية بدون حذف الأصفار
                return f"{float(value):.8f}"
            
            amount_display = format_amount(amount)
            fee_display = format_amount(fee)
            total_display = format_amount(amount + fee)
            
            # Create result embed
            fee_rate = float(self.transfer_settings.get("tax_rate", "0.01"))
            fee_percentage = fee_rate * 100
            
            premium_settings = self.transfer_settings.get("premium_settings", {})
            premium_exempt = premium_settings.get("tax_exempt_enabled", True) and premium_settings.get("tax_exempt", True)
            
            embed = discord.Embed(
                title="Fee Calculation Results",
                color=0x8f92b1
            )
            
            if is_premium and premium_exempt:
                embed.description = f"Current fee rate: 0% (Premium Benefit)"
                embed.add_field(name="Amount to Send", value=f"{amount_display} CRN", inline=True)
                embed.add_field(name="Fee", value=f"0 CRN", inline=True)
                embed.add_field(name="Total Deduction", value=f"{amount_display} CRN", inline=False)
            else:
                embed.description = f"Current fee rate: {fee_percentage:.1f}%"
                embed.add_field(name="Amount to Send", value=f"{amount_display} CRN", inline=True)
                embed.add_field(name="Fee", value=f"{fee_display} CRN", inline=True)
                embed.add_field(name="Total Deduction", value=f"{total_display} CRN", inline=False)
            
            # Add a note about how fee is calculated
            embed.set_footer(text="Fee is calculated based on the transfer amount")
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            print(f"Error in fee calculator: {e}")
            print(traceback.format_exc())
            
            embed = discord.Embed(
                title="Error",
                description="An error occurred while calculating the fee. Please try again later.",
                color=0x8f92b1
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

async def calculate_fee_callback(interaction: discord.Interaction):
    # Check if user can use fee calculator
    try:
        # Get transfer settings
        transfer_settings = await get_transfer_settings()
        
        # Check if fee is enabled
        fee_enabled = transfer_settings.get("tax_enabled", True)
        if not fee_enabled:
            # Defer response since we're not showing a modal
            await interaction.response.defer(ephemeral=True)
            embed = discord.Embed(
                title="Fee Calculator",
                description="Transfers are currently fee-free for all users.",
                color=0x8f92b1
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        
        # Create modal - no need to defer when sending a modal
        modal = FeeCalculatorModal(transfer_settings)
        await interaction.response.send_modal(modal)
    except Exception as e:
        print(f"Error in fee calculator: {e}")
        print(traceback.format_exc())
        
        # Defer response if we haven't responded yet
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)
            
        embed = discord.Embed(
            title="Error",
            description="An error occurred while processing your request. Please try again later.",
            color=0x8f92b1
        )
        await interaction.followup.send(embed=embed, ephemeral=True) 