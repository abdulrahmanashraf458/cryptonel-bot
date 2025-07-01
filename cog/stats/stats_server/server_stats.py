import discord
from discord.ext import commands, tasks
import datetime

class ServerStatsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.stats_task.start()

    def cog_unload(self):
        self.stats_task.cancel()

    @tasks.loop(hours=1)
    async def stats_task(self):
        """Prints server statistics to the terminal every hour"""
        # Get current time for logging
        current_time = datetime.datetime.now().strftime("%m-%d %H:%M:%S")
        
        # Get statistics
        server_count = len(self.bot.guilds)
        user_count = sum(guild.member_count for guild in self.bot.guilds)
        
        # Print statistics
        print(f"{current_time} ==================================================")
        print(f"{current_time} Logged in as: {self.bot.user.name} (ID: {self.bot.user.id})")
        print(f"{current_time} Connected to {server_count} servers with {user_count} users")
        print(f"{current_time} All commands and features are disabled")
        print(f"{current_time} ==================================================")

    @tasks.loop(hours=1)
    async def first_run(self):
        """Run once then cancel itself"""
        await self.print_stats()
        self.first_run.cancel()

    async def print_stats(self):
        """Prints server statistics to the terminal"""
        # Get current time for logging
        current_time = datetime.datetime.now().strftime("%m-%d %H:%M:%S")
        
        # Get statistics
        server_count = len(self.bot.guilds)
        user_count = sum(guild.member_count for guild in self.bot.guilds)
        
        # Print statistics
        print(f"{current_time} ==================================================")
        print(f"{current_time} Logged in as: {self.bot.user.name} (ID: {self.bot.user.id})")
        print(f"{current_time} Connected to {server_count} servers with {user_count} users")
        print(f"{current_time} All commands and features are disabled")
        print(f"{current_time} ==================================================")

    @stats_task.before_loop
    async def before_stats_task(self):
        """Wait until the bot is ready before starting the task."""
        await self.bot.wait_until_ready()

    @first_run.before_loop
    async def before_first_run(self):
        """Wait until the bot is ready before running."""
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_ready(self):
        """Event triggered when the bot is ready."""
        await self.print_stats()

async def setup(bot):
    await bot.add_cog(ServerStatsCog(bot)) 