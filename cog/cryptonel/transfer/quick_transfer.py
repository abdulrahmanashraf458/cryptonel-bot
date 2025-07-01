import discord
from discord.ext import commands
from discord import app_commands
from discord.ui import View, Button, Select, Modal, TextInput
import pymongo
import os
from dotenv import load_dotenv
import datetime
import asyncio
from typing import List, Dict, Optional, Union
import traceback
import re

# Import utility functions
from .utils import (
    check_transfer_status,
    get_transfer_settings,
    check_recipient,
    calculate_fee,
    record_transaction,
    TransferRateLimiter
)

# Load environment variables
load_dotenv('clyne.env')

# MongoDB connection
MONGODB_URI = os.getenv('MONGODB_URI')
client = pymongo.MongoClient(MONGODB_URI)

# Define databases and collections
db_wallet = client['cryptonel_wallet']
users = db_wallet['users']
contacts = db_wallet['quick_transfer_contacts']
transactions = db_wallet['user_transactions']

# Function to normalize amount to 8 decimal places max
def normalize_amount(amount_str: str) -> float:
    """Convert user input amount to standard float with max 8 decimal places"""
    # Replace comma with period
    amount_str = amount_str.strip().replace(',', '.')
    
    # Parse as float
    amount_float = float(amount_str)
    
    # Format to exactly 8 decimal places for database consistency
    amount_formatted = "{:.8f}".format(amount_float)
    
    # Convert back to float
    return float(amount_formatted)

# Get user's contacts from quick_transfer_contacts collection
async def get_user_contacts(user_id: str) -> List[Dict]:
    """Get a user's contacts from the quick_transfer_contacts collection"""
    user_contacts = contacts.find_one({"user_id": user_id})
    if not user_contacts or "contacts" not in user_contacts:
        return []
    return user_contacts.get("contacts", [])

# Function to show contacts selection
async def show_contacts_selection(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    
    # Get user's contacts from quick_transfer_contacts collection
    contacts_list = await get_user_contacts(user_id)
    
    if not contacts_list:
        embed = discord.Embed(
            title="📒 No Contacts",
            description="You don't have any contacts saved. To add contacts, go to your wallet settings on the website.",
            color=0x8f92b1
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    # Create contacts dropdown
    contacts_view = ContactsSelectionView(contacts_list)
    
    embed = discord.Embed(
        title="⚡ Quick Transfer",
        description="Select a contact to transfer CRN to:",
        color=0x8f92b1
    )
    
    await interaction.response.send_message(embed=embed, view=contacts_view, ephemeral=True)

# Contacts Selection View
class ContactsSelectionView(View):
    def __init__(self, contacts_list: List[Dict]):
        super().__init__(timeout=60)
        self.add_item(ContactsDropdown(contacts_list))

# Contacts Dropdown
class ContactsDropdown(Select):
    def __init__(self, contacts_list: List[Dict]):
        # Create options from contacts
        options = []
        for contact in contacts_list[:25]:  # Discord limits to 25 options
            contact_name = contact.get("username", "Unknown")
            contact_address = contact.get("private_address", "")
            
            # Create option with user avatar if available
            option = discord.SelectOption(
                label=contact_name,
                value=contact_address,
                description=f"Address: {contact_address[:10]}..."
            )
            options.append(option)
        
        super().__init__(
            placeholder="Select a contact...",
            min_values=1,
            max_values=1,
            options=options
        )
    
    async def callback(self, interaction: discord.Interaction):
        # Get selected contact address
        recipient_address = self.values[0]
        
        # Check if recipient exists
        exists, recipient_data = await check_recipient(recipient_address)
        if not exists:
            embed = discord.Embed(
                title="❌ Invalid Recipient",
                description="The selected contact's address is invalid or no longer exists.",
                color=0x8f92b1
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # Create transfer modal
        user_id = str(interaction.user.id)
        user_data = users.find_one({"user_id": user_id})
        transfer_settings = await get_transfer_settings()
        
        # Create and show ultra-simplified modal
        transfer_modal = QuickTransferModal(
            user_data=user_data,
            recipient_data=recipient_data,
            transfer_settings=transfer_settings
        )
        
        await interaction.response.send_modal(transfer_modal)

# Ultra-Simplified Quick Transfer Modal
class QuickTransferModal(Modal):
    def __init__(self, user_data, recipient_data, transfer_settings):
        super().__init__(title="Quick Transfer")
        self.user_data = user_data
        self.recipient_data = recipient_data
        self.transfer_settings = transfer_settings
        
        # Current balance
        self.balance = float(user_data.get("balance", "0"))
        
        # Initialize fee rate
        self.fee_rate = float(transfer_settings.get("tax_rate", "0.01"))
        self.is_premium = user_data.get("premium", False)
        
        # Create form field - only amount
        self.amount_input = TextInput(
            label="Amount (CRN)",
            placeholder=f"Available: {self.balance} CRN",
            required=True,
            min_length=1,
            max_length=20
        )
        self.add_item(self.amount_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        # Defer response
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Get amount value and normalize
            amount_str = self.amount_input.value
            # Set default reason with recipient username
            reason = f"Quick Transfer to {self.recipient_data.get('username', 'recipient')}"
            
            # Validate and parse amount
            try:
                # Normalize amount to 8 decimal places
                amount = normalize_amount(amount_str)
                
                if amount <= 0:
                    embed = discord.Embed(
                        title="❌ Invalid Amount",
                        description="Amount must be greater than zero.",
                        color=0x8f92b1
                    )
                    await interaction.followup.send(embed=embed, ephemeral=True)
                    return
            except ValueError:
                embed = discord.Embed(
                    title="❌ Invalid Amount",
                    description="Please enter a valid number.",
                    color=0x8f92b1
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return
            
            # Check if user has enough balance
            if amount > self.balance:
                embed = discord.Embed(
                    title="❌ Insufficient Balance",
                    description=f"You don't have enough CRN. Your balance: {self.balance} CRN",
                    color=0x8f92b1
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return
            
            # Calculate fee
            fee_amount, recipient_amount = await calculate_fee(amount, self.is_premium, self.transfer_settings)
            
            # Format amount displays
            def format_amount(value):
                """Format amount for display with proper decimal places"""
                try:
                    # If it's a whole number, display as integer
                    if float(value).is_integer():
                        return f"{int(float(value))}"
                    else:
                        # Format with 8 decimal places max, remove trailing zeros
                        return f"{float(value):.8f}".rstrip('0').rstrip('.')
                except:
                    return str(value)
            
            # Process transfer and record in database
            # Emails are automatically sent by the record_transaction function
            transaction_id = await record_transaction(
                sender_data=self.user_data,
                recipient_data=self.recipient_data,
                amount=amount,
                recipient_amount=recipient_amount,
                fee=fee_amount,
                reason=reason
            )
            
            # Send success message
            embed = discord.Embed(
                title="✅ Transfer Successful",
                description=f"You've successfully sent {format_amount(amount)} CRN to {self.recipient_data.get('username', 'the recipient')}!",
                color=0x8f92b1
            )
            
            embed.add_field(
                name="Details",
                value=f"""
                **Amount:** {format_amount(amount)} CRN
                **Fee:** {format_amount(fee_amount)} CRN
                **Recipient Gets:** {format_amount(recipient_amount)} CRN
                """,
                inline=False
            )
            
            # Add note about confirmation email
            embed.set_footer(text="A confirmation email has been sent to you and the recipient.")
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            print(f"Error in quick transfer: {e}")
            print(traceback.format_exc())
            
            embed = discord.Embed(
                title="❌ Transfer Error",
                description="An error occurred while processing your transfer. Please try again later.",
                color=0x8f92b1
            )
            await interaction.followup.send(embed=embed, ephemeral=True) 