import discord
import pymongo
import os

# Function to check user ban status AND wallet lock
async def check_ban_status(interaction):
    """
    Check if a user is banned or has a locked wallet
    
    Parameters:
        interaction (discord.Interaction): Discord interaction object
        
    Returns:
        bool: True if user can use command, False if banned or wallet locked
    """
    user_id = str(interaction.user.id)
    
    # Get database connection
    from dotenv import load_dotenv
    load_dotenv('clyne.env')
    client = pymongo.MongoClient(os.getenv('MONGODB_URI'))
    db_wallet = client['cryptonel_wallet']
    users = db_wallet['users']
    
    # Find user data
    user_data = users.find_one({"user_id": user_id})
    
    # If user not in database
    if not user_data:
        # Create wallet button
        embed = discord.Embed(
            title="❌ No Wallet Found",
            description="You need to create a wallet to use mining features. Please visit our dashboard to register.",
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
    
    # Check if user is banned
    if user_data.get('ban', False):
        embed = discord.Embed(
            title="⛔ Permanently Banned",
            description="Your wallet has received a permanent ban. You cannot use mining commands.",
            color=0xff0000
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return False
    
    # Check if wallet is locked
    if user_data.get('wallet_lock', False):
        embed = discord.Embed(
            title="🔒 Wallet Under Review",
            description="Your wallet is temporarily locked and under review by our team. Mining is disabled.",
            color=0xFFD700  # Yellow/gold color
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return False
    
    # User is allowed
    return True 