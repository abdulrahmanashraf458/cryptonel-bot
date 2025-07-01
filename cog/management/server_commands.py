import discord
from discord.ext import commands
from discord import app_commands
import pymongo
import os
import asyncio
from dotenv import load_dotenv
import traceback
from enum import Enum

class ServerAction(Enum):
    ADD = "add"
    RELOAD = "reload"
    REMOVE = "remove"

class ServerType(Enum):
    PARTNER = "partner"
    SERVICE = "service"
    SERVER_SHOP = "server_shop"

class ServerManagement(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # List of owners who can use the command
        self.owner_ids = [
            964005304943661106,  # Original owner
            1137470473819656293,  # Added owner
            217013625066356738    # Added owner
        ]
        
        # Load environment variables
        load_dotenv('clyne.env')
        
        # Connect to MongoDB
        self.mongodb_uri = os.getenv('MONGODB_URI')
        if self.mongodb_uri:
            try:
                self.mongo_client = pymongo.MongoClient(self.mongodb_uri)
                self.db = self.mongo_client.get_database("staff")
                self.server_collection = self.db["server_trade_crn"]  # English collection name
                print("MongoDB connection established for server management")
            except Exception as e:
                print(f"Error connecting to MongoDB: {e}")
                self.mongo_client = None
                self.db = None
                self.server_collection = None
        else:
            print("WARNING: MongoDB URI not found in environment variables")
            self.mongo_client = None
            self.db = None
            self.server_collection = None

    # Owner-only check
    def is_owner(self, user_id):
        return user_id in self.owner_ids

    @app_commands.command(name="serveradd", description="Add, reload or remove server information")
    @app_commands.describe(
        action="Choose action: add a new server, reload all servers, or remove a server",
        server_id="The ID of the server to add or remove (only needed for 'add' and 'remove' actions)",
        server_type="The type of server (only needed for 'add' action)"
    )
    @app_commands.choices(
        action=[
            app_commands.Choice(name="Add Server", value="add"),
            app_commands.Choice(name="Reload All Servers", value="reload"),
            app_commands.Choice(name="Remove Server", value="remove")
        ],
        server_type=[
            app_commands.Choice(name="Partner", value="partner"),
            app_commands.Choice(name="Service", value="service"),
            app_commands.Choice(name="Server Shop", value="server_shop")
        ]
    )
    async def serveradd(
        self, 
        interaction: discord.Interaction, 
        action: str,
        server_id: str = None,
        server_type: str = None
    ):
        # Check if the user is an owner
        if not self.is_owner(interaction.user.id):
            # Silent rejection for non-owners
            await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
            return
        
        # Defer response and show processing message
        await interaction.response.defer()
        
        if action == "add":
            if not server_id:
                await interaction.followup.send("Server ID is required for the 'add' action.")
                return
            if not server_type:
                await interaction.followup.send("Server type is required for the 'add' action.")
                return
            await self.add_server(interaction, server_id, server_type)
        elif action == "reload":
            await self.reload_servers(interaction)
        elif action == "remove":
            if not server_id:
                await interaction.followup.send("Server ID is required for the 'remove' action.")
                return
            await self.remove_server(interaction, server_id)
        else:
            await interaction.followup.send("Invalid action. Please choose 'add', 'reload', or 'remove'.")

    async def add_server(self, interaction, server_id, server_type):
        status_message = await interaction.followup.send(content="Adding server...")
        
        try:
            # Convert server_id to integer
            guild_id = int(server_id)
            
            # Try to fetch the guild
            guild = self.bot.get_guild(guild_id)
            
            if guild is None:
                await status_message.edit(content="I couldn't find a server with this ID or I'm not a member of it.")
                return
                
            # Get server data and save to database
            server_data = await self.get_server_data(guild)
            
            # Add server type information
            server_data.update({
                "partner": server_type == "partner",
                "service": server_type == "service",
                "server_shop": server_type == "server_shop",
                "server_type": server_type
            })
            
            # Create embed with server information
            embed = self.create_server_embed(server_data)
            
            # Save server information to MongoDB if available
            if self.server_collection is not None:
                try:
                    # Update if exists, insert if not
                    self.server_collection.update_one(
                        {"server_id": guild.id}, 
                        {"$set": server_data},
                        upsert=True
                    )
                    print(f"Server data saved to MongoDB: {server_data}")
                except Exception as mongo_error:
                    print(f"MongoDB error: {mongo_error}")
                    traceback.print_exc()
            else:
                print("WARNING: Server collection not available - data not saved")
            
            # Send the response
            await status_message.delete()
            await interaction.followup.send(embed=embed)
            
        except ValueError:
            await status_message.edit(content="Invalid server ID. Please provide a valid numeric ID.")
        except Exception as e:
            print(f"Error processing server add command: {e}")
            traceback.print_exc()
            await status_message.edit(content=f"An error occurred: {str(e)}")

    async def remove_server(self, interaction, server_id):
        status_message = await interaction.followup.send(content="Removing server...")
        
        try:
            # Convert server_id to integer
            guild_id = int(server_id)
            
            # Check if server exists in database
            if self.server_collection is None:
                await status_message.edit(content="Database connection is not available.")
                return
                
            server_data = self.server_collection.find_one({"server_id": guild_id})
            
            if server_data is None:
                await status_message.edit(content="Server not found in the database.")
                return
                
            # Remove server from database
            self.server_collection.delete_one({"server_id": guild_id})
            
            # Create embed for confirmation
            embed = discord.Embed(
                title="Server Removed",
                description=f"Server **{server_data.get('server_name', 'Unknown')}** (ID: {guild_id}) was removed from the database.",
                color=0xff5555  # Red color for deletion
            )
            
            await status_message.delete()
            await interaction.followup.send(embed=embed)
            
        except ValueError:
            await status_message.edit(content="Invalid server ID. Please provide a valid numeric ID.")
        except Exception as e:
            print(f"Error processing server remove command: {e}")
            traceback.print_exc()
            await status_message.edit(content=f"An error occurred: {str(e)}")

    async def reload_servers(self, interaction):
        status_message = await interaction.followup.send(content="Reloading all servers from database...")
        
        try:
            if self.server_collection is None:
                await status_message.edit(content="Database connection is not available.")
                return
                
            # Get all servers from database
            server_records = list(self.server_collection.find({}))
            
            if not server_records:
                await status_message.edit(content="No servers found in the database.")
                return
                
            updated_count = 0
            failed_count = 0
            
            for server_record in server_records:
                try:
                    guild_id = server_record.get("server_id")
                    guild = self.bot.get_guild(guild_id)
                    
                    if guild:
                        # Get updated server data
                        server_data = await self.get_server_data(guild)
                        
                        # Preserve the server type information
                        server_data.update({
                            "partner": server_record.get("partner", False),
                            "service": server_record.get("service", False),
                            "server_shop": server_record.get("server_shop", False),
                            "server_type": server_record.get("server_type", "unknown")
                        })
                        
                        # Update database
                        self.server_collection.update_one(
                            {"server_id": guild_id},
                            {"$set": server_data}
                        )
                        updated_count += 1
                    else:
                        failed_count += 1
                        print(f"Could not find guild with ID: {guild_id}")
                except Exception as e:
                    failed_count += 1
                    print(f"Error updating server {server_record.get('server_name', 'Unknown')}: {e}")
            
            # Create summary embed
            summary_embed = discord.Embed(
                title="Server Reload Summary",
                description=f"Updated {updated_count} servers\nFailed to update {failed_count} servers",
                color=0x8f92b1
            )
            
            await status_message.delete()
            await interaction.followup.send(embed=summary_embed)
            
        except Exception as e:
            print(f"Error reloading servers: {e}")
            traceback.print_exc()
            await status_message.edit(content=f"An error occurred: {str(e)}")

    async def get_server_data(self, guild):
        """Get all relevant data for a server"""
        # Create an invite link
        try:
            # Find a text channel to create an invite from
            invite_channel = None
            for channel in guild.text_channels:
                # Check if the bot has permission to create invites in this channel
                if channel.permissions_for(guild.me).create_instant_invite:
                    invite_channel = channel
                    break
            
            if invite_channel is None:
                invite_link = "Could not generate an invite link (missing permissions)"
            else:
                invite = await invite_channel.create_invite(max_age=0, max_uses=0, reason="Server reload")
                invite_link = str(invite)
        except Exception as e:
            print(f"Error creating invite: {e}")
            invite_link = f"Could not generate an invite link: {str(e)}"
        
        # Count members
        total_members = guild.member_count or "Unknown"
        
        # Get server icon URL
        icon_url = guild.icon.url if guild.icon else None
        
        # Get server banner URL if available
        banner_url = guild.banner.url if guild.banner else None
        
        # Return server data
        return {
            "server_id": guild.id,
            "server_name": guild.name,
            "member_count": total_members,
            "invite_link": invite_link,
            "icon_url": icon_url,
            "banner_url": banner_url
        }
        
    def create_server_embed(self, server_data):
        """Create an embed for server information"""
        embed = discord.Embed(
            title=f"Server Information: {server_data['server_name']}",
            description=f"Server ID: {server_data['server_id']}",
            color=0x8f92b1
        )
        
        # Add server icon if available
        if server_data['icon_url']:
            embed.set_thumbnail(url=server_data['icon_url'])
            
        # Add banner as image if available
        if server_data['banner_url']:
            embed.set_image(url=server_data['banner_url'])
        
        # Add member information
        embed.add_field(name="Total Members", value=str(server_data['member_count']), inline=True)
        
        # Add server type information
        server_type_display = {
            "partner": "Partner",
            "service": "Service", 
            "server_shop": "Server Shop"
        }.get(server_data.get('server_type'), "Unknown")
        
        embed.add_field(name="Server Type", value=server_type_display, inline=True)
        embed.add_field(name="Invite Link", value=server_data['invite_link'], inline=False)
        
        return embed

async def setup(bot):
    try:
        await bot.add_cog(ServerManagement(bot))
        print("ServerManagement cog loaded successfully")
    except Exception as e:
        print(f"Error loading ServerManagement cog: {e}")
        traceback.print_exc() 