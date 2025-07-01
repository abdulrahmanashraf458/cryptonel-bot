import discord
from discord.ext import commands, tasks

class StatusCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.status_task.start()

    def cog_unload(self):
        self.status_task.cancel()

    @tasks.loop(minutes=5)
    async def status_task(self):
        """Changes the bot's status every 5 minutes."""
        await self.bot.change_presence(
            activity=discord.Game(name="CRN")
        )

    @status_task.before_loop
    async def before_status_task(self):
        """Wait until the bot is ready before starting the task."""
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(StatusCog(bot)) 