import datetime
import random
from typing import Union, Dict, List

import nextcord
from nextcord.ext import commands, tasks

import pie.database.config
from pie import utils, i18n

from .database import UserStats, BoardOrder

_ = i18n.Translator("modules/boards").translate
config = pie.database.config.Config.get()

LIMITS_MESSAGE = [15, 25]
LIMITS_REACTION = [0, 5]

TIMER_MESSAGE = 60
TIMER_REACTION = 30


class Points(commands.Cog):
    """Get points by having conversations"""

    def __init__(self, bot):
        self.bot = bot

        self.stats_message = {}
        self.stats_reaction = {}

        self.cleanup.start()

    # Commands

    @commands.guild_only()
    @commands.group(name="points")
    async def points(self, ctx):
        """Get information about user points"""
        await utils.discord.send_help(ctx)

    @points.command(name="get")
    async def points_get(self, ctx, member: nextcord.Member = None):
        """Get user points"""
        if member is None:
            member = ctx.author

        result = UserStats.get_stats(ctx.guild.id, member.id)

        embed = utils.discord.create_embed(
            author=ctx.author,
            title=_(ctx, "Points"),
            description=_(ctx, "**{user}'s** points").format(
                user=utils.text.sanitise(member.display_name)
            ),
        )
        points = getattr(result, "points", 0)
        message = "**{points}** ({position}.)".format(
            points=points, position=UserStats.get_position(ctx.guild.id, points)
        )

        embed.set_thumbnail(url=member.display_avatar.replace(size=256).url)
        embed.add_field(
            name=_(ctx, "Points and ranking"),
            value=_(ctx, message),
        )
        await ctx.send(embed=embed)
        await utils.discord.delete_message(ctx.message)

    @points.command(name="leaderboard", aliases=["best"])
    async def points_leaderboard(self, ctx):
        """Points leaderboard"""
        title = _(ctx, "Points leaderboard")
        description = _(ctx, "Score, descending")

        embeds = Points._create_embeds(
            ctx=ctx,
            title=title,
            description=description,
            order=BoardOrder.DESC,
            element_count=10,
            page_count=10,
        )

        await utils.discord.delete_message(ctx.message)

        scrollable_embed = utils.ScrollableEmbed(ctx, embeds)
        await scrollable_embed.scroll()

    # Listeners

    @commands.Cog.listener()
    async def on_message(self, message):
        """Add points on message"""
        if message.author.bot:
            return

        # Ignore DMs
        if not isinstance(message.channel, nextcord.TextChannel):
            return

        value = random.randint(LIMITS_MESSAGE[0], LIMITS_MESSAGE[1])

        Points._handle_points(
            message.guild.id,
            message.author.id,
            self.stats_message,
            TIMER_MESSAGE,
            value,
        )

    # Helper functions

    @staticmethod
    def _get_page(
        guild: nextcord.Guild,
        author: Union[nextcord.User, nextcord.Member],
        users: list,
        offset: int = 0,
    ) -> str:
        result = []
        template = "`{points:>8}` … {name}"
        utx = i18n.TranslationContext(guild.id, author.id)
        for db_user in users:
            user = guild.get_member(db_user.user_id)
            if user and user.display_name:
                name = utils.text.sanitise(user.display_name, limit=1900)
            else:
                name = _(utx, "Unknown")

            if db_user.user_id == author.id:
                name = "**" + name + "**"

            result.append(template.format(points=db_user.points, name=name))
        return "\n".join(result)

    @staticmethod
    def _create_embeds(
        ctx,
        title: str,
        description: str,
        order: BoardOrder,
        element_count: int,
        page_count: int,
    ) -> List[nextcord.Embed]:
        elements = []

        author = UserStats.get_stats(ctx.guild.id, ctx.author.id)

        limit = min(UserStats.get_count(ctx.guild.id), page_count * element_count)

        for page_number in range(page_count):
            users = UserStats.get_best(
                ctx.guild.id, order, element_count, page_number * element_count
            )

            if not users:
                break

            page = utils.discord.create_embed(
                author=ctx.author,
                title=title,
                description=description,
            )

            value = Points._get_page(ctx.guild, ctx.author, users)

            page.add_field(
                name=_(ctx, "Top {limit}").format(limit=limit),
                value=value,
                inline=False,
            )

            if ctx.author.id not in [u.user_id for u in users]:
                page.add_field(
                    name=_(ctx, "Your score"),
                    value="`{points:>8}` … {name}".format(
                        points=author.points,
                        name="**" + utils.text.sanitise(ctx.author.display_name) + "**",
                    ),
                    inline=False,
                )

            elements.append(page)

        return elements

    @staticmethod
    def _handle_points(
        guild_id: int, user_id: int, stats: Dict, timer: int, value: int
    ):
        now = datetime.datetime.now()
        if guild_id not in stats:
            stats[guild_id] = {}

        if (
            user_id not in stats[guild_id]
            or (now - stats[guild_id][user_id]).total_seconds() >= timer
        ):
            stats[guild_id][user_id] = now
            UserStats.increment(guild_id, user_id, value)

    # Tasks

    @tasks.loop(seconds=120.0)
    async def cleanup(self):
        for guild in self.stats_message.keys():
            delete = []
            for uid, time in self.stats_message[guild].items():
                if (datetime.datetime.now() - time).total_seconds() >= TIMER_MESSAGE:
                    delete.append(uid)
            for uid in delete:
                self.stats_message[guild].pop(uid)

        for guild in self.stats_reaction.keys():
            delete = []
            for uid, time in self.stats_reaction[guild].items():
                if (datetime.datetime.now() - time).total_seconds() >= TIMER_REACTION:
                    delete.append(uid)

            for uid in delete:
                self.stats_reaction[guild].pop(uid)


def setup(bot) -> None:
    bot.add_cog(Points(bot))
