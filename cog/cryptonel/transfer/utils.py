import discord
import pymongo
import os
from dotenv import load_dotenv
import datetime
import uuid
import time
from typing import Dict, List, Tuple, Optional, Any

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

# Class for rate limiting transfers
class TransferRateLimiter:
    def __init__(self):
        self.rate_limits = {}
        
    async def check_rate_limit(self, user_id: str, transfer_settings: Dict) -> Tuple[bool, int, int]:
        # Get rate limit settings
        max_transfers = int(transfer_settings.get("max_transfers_per_window", "3"))
        window_minutes = int(transfer_settings.get("rate_limit_window_minutes", "5"))
        
        # Check premium status and adjust if needed
        user_data = users.find_one({"user_id": user_id})
        is_premium = user_data.get("premium", False) if user_data else False
        
        premium_settings = transfer_settings.get("premium_settings", {})
        if is_premium and premium_settings.get("rate_limit_exempt_enabled", True):
            max_transfers = max_transfers * 2  # Double the rate limit for premium users
        
        # Get current time
        current_time = time.time()
        window_seconds = window_minutes * 60
        
        # Initialize user if not exists
        if user_id not in self.rate_limits:
            self.rate_limits[user_id] = {"transfers": [], "last_reset": current_time}
        
        # Clean up expired transfers
        self.rate_limits[user_id]["transfers"] = [
            t for t in self.rate_limits[user_id]["transfers"]
            if current_time - t < window_seconds
        ]
        
        # Check if limit reached
        transfers_made = len(self.rate_limits[user_id]["transfers"])
        is_limited = transfers_made >= max_transfers
        
        # Calculate time until reset
        if transfers_made > 0:
            oldest_transfer = min(self.rate_limits[user_id]["transfers"])
            seconds_until_reset = max(0, window_seconds - (current_time - oldest_transfer))
            minutes_until_reset = int(seconds_until_reset / 60) + 1  # Round up
        else:
            minutes_until_reset = 0
            
        # If not limited, add a new transfer
        if not is_limited:
            self.rate_limits[user_id]["transfers"].append(current_time)
        
        # Return result
        transfers_remaining = max(0, max_transfers - transfers_made)
        return is_limited, transfers_remaining, minutes_until_reset

# Function to check if user can use transfer features
async def check_transfer_status(interaction: discord.Interaction) -> bool:
    user_id = str(interaction.user.id)
    
    # Check if user exists in database
    user_data = users.find_one({"user_id": user_id})
    if not user_data:
        embed = discord.Embed(
            title="❌ No Wallet Found",
            description="You don't have a wallet. Please create one first by visiting our dashboard.",
            color=0x8f92b1
        )
        
        # Create a view with a dashboard button
        wallet_view = discord.ui.View()
        wallet_button = discord.ui.Button(
            label="Create Wallet", 
            url="https://cryptonel.online", 
            style=discord.ButtonStyle.url
        )
        wallet_view.add_item(wallet_button)
        
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, view=wallet_view, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, view=wallet_view, ephemeral=True)
        return False
    
    # Check if user is banned - use 'ban' property instead of 'banned'
    if user_data.get("ban", False):
        embed = discord.Embed(
            title="⛔ Permanently Banned",
            description="Your wallet has received a permanent ban. You cannot use transfer features.",
            color=0xff0000
        )
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)
        return False
    
    # Check if wallet is locked - use 'wallet_lock' property instead of 'wallet_locked'
    if user_data.get("wallet_lock", False):
        embed = discord.Embed(
            title="🔒 Wallet Under Review",
            description="Your wallet is temporarily locked and under review by our team.",
            color=0xFFD700  # Yellow/gold color
        )
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)
        return False
    
    # All checks passed
    return True

# Function to get transfer settings
async def get_transfer_settings() -> Dict:
    # Look for settings in cryptonel_wallet database
    wallet_settings = db_wallet['settings']
    transfer_settings = wallet_settings.find_one({"_id": "transfer_settings"})
    
    # Just return what is in the database
    return transfer_settings

# Function to check if recipient exists
async def check_recipient(private_address: str) -> Tuple[bool, Optional[Dict]]:
    recipient = users.find_one({"private_address": private_address})
    if not recipient:
        return False, None
    return True, recipient

# Function to calculate fee on transfer
async def calculate_fee(amount: float, is_premium: bool, transfer_settings: Dict) -> Tuple[float, float]:
    # Check if fee is enabled
    fee_enabled = transfer_settings.get("tax_enabled", True)
    if not fee_enabled:
        return 0.0, amount
    
    # Check premium fee exemption
    premium_settings = transfer_settings.get("premium_settings", {})
    if is_premium and premium_settings.get("tax_exempt_enabled", True) and premium_settings.get("tax_exempt", True):
        return 0.0, amount
    
    # Calculate fee
    fee_rate = float(transfer_settings.get("tax_rate", "0.01"))
    fee_amount = amount * fee_rate
    
    # Fee is deducted from the amount (not added)
    # Recipient gets amount - fee, sender pays the full amount
    amount_after_fee = amount - fee_amount
    return fee_amount, amount_after_fee

# Function to verify authentication
async def verify_auth(user_data: Dict, auth_value: str, auth_type: str) -> bool:
    if auth_type == "secret_word":
        return auth_value == user_data.get("secret_word", "")
    elif auth_type == "2fa":
        # Implement 2FA validation logic
        return True  # Placeholder, actual 2FA validation needs to be implemented
    elif auth_type == "password":
        # Implement password validation logic
        return auth_value == user_data.get("transfer_password", "")
    return False

# Function to record transaction
async def record_transaction(
    sender_data: Dict, 
    recipient_data: Dict, 
    amount: float, 
    recipient_amount: float, 
    fee: float, 
    reason: str
) -> str:
    # Generate transaction ID
    tx_id = str(uuid.uuid4())
    timestamp = datetime.datetime.now()
    
    # Get IDs
    sender_id = sender_data.get("user_id")
    recipient_id = recipient_data.get("user_id")
    
    # Update sender balance
    new_sender_balance = float(sender_data.get("balance", "0")) - (amount + fee)
    users.update_one(
        {"user_id": sender_id},
        {"$set": {"balance": str(new_sender_balance)}}
    )
    
    # Update recipient balance
    new_recipient_balance = float(recipient_data.get("balance", "0")) + recipient_amount
    users.update_one(
        {"user_id": recipient_id},
        {"$set": {"balance": str(new_recipient_balance)}}
    )
    
    # Format all amounts to 8 decimal places for consistency
    formatted_amount = f"{float(amount):.8f}"
    formatted_recipient_amount = f"{float(recipient_amount):.8f}"
    formatted_fee = f"{float(fee):.8f}"
    
    # Record transaction for sender
    sender_tx = {
        "tx_id": tx_id,
        "type": "sent",
        "amount": formatted_amount,
        "timestamp": timestamp,
        "counterparty_address": recipient_data.get("private_address", "Unknown"),
        "counterparty_public_address": recipient_data.get("public_address", "Unknown"),
        "counterparty_id": recipient_id,
        "counterparty_username": recipient_data.get("username", "Unknown"),
        "sender_username": sender_data.get("username", "Unknown"),
        "sender_id": sender_id,
        "status": "completed",
        "fee": formatted_fee,
        "reason": reason
    }
    
    users_transactions = db_wallet["user_transactions"]
    sender_tx_record = users_transactions.find_one({"user_id": sender_id})
    
    if sender_tx_record:
        users_transactions.update_one(
            {"user_id": sender_id},
            {"$push": {"transactions": sender_tx}}
        )
    else:
        users_transactions.insert_one({
            "user_id": sender_id,
            "transactions": [sender_tx]
        })
    
    # Record transaction for recipient
    recipient_tx = {
        "tx_id": tx_id,
        "type": "received",
        "amount": formatted_recipient_amount,
        "timestamp": timestamp,
        "counterparty_address": sender_data.get("private_address", "Unknown"),
        "counterparty_public_address": sender_data.get("public_address", "Unknown"),
        "counterparty_id": sender_id,
        "counterparty_username": sender_data.get("username", "Unknown"),
        "recipient_username": recipient_data.get("username", "Unknown"),
        "recipient_id": recipient_id,
        "status": "completed",
        "fee": formatted_fee,
        "reason": reason
    }
    
    recipient_tx_record = users_transactions.find_one({"user_id": recipient_id})
    
    if recipient_tx_record:
        users_transactions.update_one(
            {"user_id": recipient_id},
            {"$push": {"transactions": recipient_tx}}
        )
    else:
        users_transactions.insert_one({
            "user_id": recipient_id,
            "transactions": [recipient_tx]
        })
    
    # Create transaction object for email
    transaction_for_email = {
        "tx_id": tx_id,
        "amount": formatted_amount,
        "tax": formatted_fee,
        "fee": formatted_fee,
        "reason": reason,
        "timestamp": timestamp,
        "sender_public_address": sender_data.get("public_address", "Unknown"),
        "recipient_public_address": recipient_data.get("public_address", "Unknown")
    }
    
    # Import email sender here to avoid circular imports
    try:
        from .email_sender import send_transaction_emails
        # Send email notifications
        send_transaction_emails(sender_data, recipient_data, transaction_for_email, users)
    except Exception as e:
        print(f"Error sending transaction emails: {str(e)}")
        # Continue with the transaction even if email sending fails
    
    # Return transaction ID
    return tx_id 