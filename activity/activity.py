import discord
from discord.ext import commands
from .utils.chat_formatting import *
from .utils.dataIO import dataIO
from cogs.utils import checks
import asyncio
import os
import urllib.request
import aiohttp
import json
import time

class ActivityChecker():

    def __init__(self, bot):
        self.bot = bot
        self.settings_file = "data/activity/settings.json"
        self.log_file = "data/activity/log.json"
        self.settings = dataIO.load_json(self.settings_file)
        self.log = dataIO.load_json(self.log_file)
        self.units = {"minute" : 60, "hour" : 3600, "day" : 86400, "week": 604800, "month": 2592000}

    @commands.group(pass_context=True)
    @checks.mod_or_permissions(kick_members=True)
    async def activity(self, ctx):
        """Setup an activity checker channel"""
        if ctx.invoked_subcommand is None:
            await self.bot.send_cmd_help(ctx)

    @activity.command(pass_context=True, name="list")
    async def list_roles(self, ctx):
        """lists the roles checked"""
        server = ctx.message.server
        if server.id not in self.log:
            await self.bot.send_message(ctx.message.channel, "I am not setup to check activity on this server!")
        else:
            msg = ""
            for role in self.settings[server.id]["check_roles"]:
                msg += role + ", "
        await self.bot.send_message(ctx.message.channel, "```" + msg[:-2] + "```")

    @activity.command(pass_context=True, name="remove")
    async def rem_server(self, ctx, server:discord.server=None):
        """Removes a server from the activity checker"""
        if server is None:
            server = ctx.message.server
        if server.id in self.settings:
            del self.log[server.id]
            del self.settings[server.id]
        dataIO.save_json(self.log_file, self.log)
        dataIO.save_json(self.settings_file, self.settings)
        await self.bot.send_message(ctx.message.channel, "Done! No more activity checking in {}!".format(server.name))

    @activity.command(pass_context=True, name="role")
    async def role_ignore(self, ctx, role:discord.Role):
        """Add or remove a role to be checked. Remove all roles to check everyone."""
        server = ctx.message.server
        server_roles = self.settings[server.id]["check_roles"]
        channel = ctx.message.channel
        added_role = False
        if role.name in server_roles:
            self.settings[server.id]["check_roles"].remove(role.name)
            await self.bot.send_message(channel, "Now ignoring {}!".format(role.name))
            added_role = True
        if role.name not in server_roles and not added_role:
            self.settings[server.id]["check_roles"].append(role.name)
            await self.bot.send_message(channel, "Now checking {}!".format(role.name))
        if len(server_roles) < 1:
            self.settings[server.id]["check_roles"].append("@everyone")
            await self.bot.send_message(channel, "Now checking everyone!")
        if len(server_roles) > 1 and "@everyone" in server_roles:
            self.settings[server.id]["check_roles"].remove("@everyone")
        dataIO.save_json(self.settings_file, self.settings)

    @activity.command(pass_context=True, name="invite")
    async def send_invite(self, ctx):
        """Toggles sending user invite links to re-join the server"""
        server = ctx.message.server
        if server.id not in self.settings:
            await self.bot.send_message(ctx.message.channel, "I am not setup to check activity on this server!")
            return
        if self.settings[server.id]["invite"]:
            self.settings[server.id]["invite"] = False
            await self.bot.send_message(ctx.message.channel, "No longer sending invite links!")
            return
        if not self.settings[server.id]["invite"]:
            self.settings[server.id]["invite"] = True
            await self.bot.send_message(ctx.message.channel, "Sending invite links to kicked users!")
            return
        

    @activity.command(pass_context=True)
    async def refresh(self, ctx, channel:discord.channel=None, server:discord.server=None):
        """Refreshes the activity checker to start right now"""
        if server is None:
            server = ctx.message.server
        await self.build_list(ctx, server)
        await self.bot.send_message(ctx.message.channel, "The list has been refreshed!")

    async def build_list(self, ctx, server):
        """Builds a new list of all server members"""
        cur_time = time.time()
        self.log[server.id] = {}
        for member in server.members:
            self.log[server.id][member.id] = cur_time
        dataIO.save_json(self.log_file, self.log)
        return

    @activity.command(pass_context=True, name="time")
    async def set_time(self, ctx, quantity : int, time_unit : str):
        """Set the time to check for removal"""
        time_unit = time_unit.lower()
        server = ctx.message.server
        s = ""
        if time_unit.endswith("s"):
            time_unit = time_unit[:-1]
            s = "s"
        if not time_unit in self.units:
            await self.bot.send_message(ctx.message.channel, "Invalid time unit. Choose minutes/hours/days/weeks/month")
            return
        if quantity < 1:
            await self.bot.send_message(ctx.message.channel, "Quantity must not be 0 or negative.")
            return
        seconds = self.units[time_unit] * quantity
        self.settings[server.id]["time"] = seconds
        dataIO.save_json(self.settings_file, self.settings)
        await self.bot.send_message(ctx.message.channel, "Okay, setting the server time check to {}".format(seconds))

    @activity.command(pass_context=True, name="channel")
    async def set_channel(self, ctx, channel:discord.Channel=None):
        """Set the channel to post activity messages"""
        server = ctx.message.server
        if channel is None:
            channel = ctx.message.channel
        if server.id not in self.settings:
            await self.bot.send_message(ctx.message.channel, "I am not setup to check activity on this server!")
            return
        self.settings[server.id]["channel"] = channel.id
        dataIO.save_json(self.settings_file, self.settings)


    @activity.command(pass_context=True, name="set")
    async def add_server(self, ctx, channel:discord.Channel=None, role:discord.Role=None):
        """Set the server for activity checking"""
        server = ctx.message.server
        if channel is None:
            channel = ctx.message.channel
        if role is not None:
            role = role.name
        if role is None:
            role = "@everyone"
        if server.id in self.log:
            await self.bot.say("This server is already checking for activity!")
            return
        await self.build_list(ctx, server)
        self.settings[server.id] = {"channel": channel.id,
                                    "check_roles": [role],
                                    "time": 604800,
                                    "invite": True}
        dataIO.save_json(self.settings_file, self.settings)
        await self.bot.send_message(ctx.message.channel, "Sending activity check messages to {}".format(channel.mention))

    def check_roles(self, member, roles):
        """Checks if a role name is in a members roles."""
        has_role = False
        for role in member.roles:
            if role.name in roles:
                has_role = True
        return has_role

    async def activity_checker(self):
        while self is self.bot.get_cog("ActivityChecker"):
            for server_id in self.log:
                server = self.bot.get_server(id=server_id)
                channel = self.bot.get_channel(id=self.settings[server.id]["channel"])
                roles = self.settings[server.id]["check_roles"]
                cur_time = time.time()
                for member_id in self.log[server.id]:
                    member = server.get_member(member_id)
                    user = await self.bot.get_user_info(member.id)
                    if not self.check_roles(member, roles):
                        continue
                    if user.bot or member is server.owner or member.id == self.bot.settings.owner:
                        print("I Should ignore this user " + user.name)
                        continue
                    last_msg_time = cur_time - self.log[server.id][member.id]
                    if last_msg_time > self.settings[server.id]["time"]:
                        msg = await self.bot.send_message(channel, "{} you haven't talked in a while! you have 15 seconds to react to this message to stay!"
                                                          .format(member.mention, last_msg_time))
                        await self.bot.add_reaction(msg, "☑")
                        answer = await self.bot.wait_for_reaction(emoji="☑", user=member, message=msg, timeout=15.0)
                        if answer is not None:
                            await self.bot.send_message(channel, "Good, you decided to stay!")
                        if answer is None:
                            await self.bot.send_message(channel, "Goodbye {}!".format(member.mention))
                            if self.settings[server.id]["invite"]:
                                invite = await self.bot.create_invite(server, unique=False)
                                try:
                                    await self.bot.send_message(discord.User(id=member.id), invite.url)
                                except(discord.errors.Forbidden, discord.errors.NotFound):
                                    await self.bot.send_message(channel, "RIP")
                                except discord.errors.HTTPException:
                                    pass
                            await self.bot.kick(member)
                            del self.log[server.id][member.id]
                            dataIO.save_json(self.log_file, self.log)
            await asyncio.sleep(5)



    async def on_message(self, message):
        server = message.server
        author = message.author
        if server.id not in self.log:
            return
        if author.id not in self.log[server.id]:
            self.log[server.id][author.id] = time.time()
        self.log[server.id][author.id] = time.time()
        dataIO.save_json(self.log_file, self.log)

def check_folder():
    if not os.path.exists("data/activity"):
        print("Creating data/activity folder")
        os.makedirs("data/activity")


def check_file():
    data = {}
    log = "data/activity/log.json"
    if not dataIO.is_valid_json(log):
        print("Creating default log.json...")
        dataIO.save_json("data/activity/log.json", data)
    settings = "data/activity/settings.json"
    if not dataIO.is_valid_json(settings):
        print("Creating default settings.json...")
        dataIO.save_json("data/activity/settings.json", data)


def setup(bot):
    check_folder()
    check_file()
    n = ActivityChecker(bot)
    loop = asyncio.get_event_loop()
    loop.create_task(n.activity_checker())
    bot.add_cog(n)