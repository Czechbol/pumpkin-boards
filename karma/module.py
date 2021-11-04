import asyncio
import contextlib
from typing import Optional, List

from emoji import UNICODE_EMOJI as _UNICODE_EMOJI


import discord
from discord.ext import commands

from core import check, i18n, logger, utils
from core import TranslationContext

from .database import (
    KarmaActionActor,
    KarmaMember,
    KarmaEmoji,
    UnicodeEmoji,
    DiscordEmoji,
    IgnoredChannel,
    BoardOrder,
    BoardType,
)

UNICODE_EMOJI = _UNICODE_EMOJI["en"]
del _UNICODE_EMOJI

_ = i18n.Translator("modules/boards").translate
bot_log = logger.Bot.logger()
guild_log = logger.Guild.logger()


class Karma(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.check(check.acl)
    @commands.group(name="karma")
    async def karma_(self, ctx):
        await utils.Discord.send_help(ctx)

    @commands.check(check.acl)
    @karma_.command(name="get")
    async def karma_get(self, ctx, member: Optional[discord.Member] = None):
        """Display karma information on some user."""
        if member is None:
            member = ctx.author
        kmember = KarmaMember.get_or_add(ctx.guild.id, member.id)

        embed = utils.Discord.create_embed(
            author=ctx.author,
            title=_(ctx, "User karma"),
            description=utils.Text.sanitise(member.display_name),
        )

        embed.add_field(
            name=_(ctx, "Karma value"),
            value=f"**{kmember.value}** (#{kmember.value_position})",
            inline=False,
        )
        embed.add_field(
            name=_(ctx, "Karma given"),
            value=f"**{kmember.given}** (#{kmember.given_position})",
        )
        embed.add_field(
            name=_(ctx, "Karma taken"),
            value=f"**{kmember.taken}** (#{kmember.taken_position})",
        )

        avatar_url: str = member.display_avatar.replace(size=256).url
        embed.set_thumbnail(url=avatar_url)

        await ctx.reply(embed=embed)

    @commands.check(check.acl)
    @karma_.command(name="emoji")
    async def karma_emoji(self, ctx, emoji: str):
        """Display karma information on emoji."""
        with contextlib.suppress(commands.EmojiNotFound):
            emoji = await commands.EmojiConverter().convert(ctx, emoji)

        if type(emoji) != discord.Emoji and emoji not in UNICODE_EMOJI:
            await ctx.reply(
                _(ctx, "I can only use Unicode emojis or emojis from this server.")
            )
            return

        if type(emoji) == discord.Emoji:
            emoji_id = emoji.id
            emoji_url = emoji.url
        else:
            emoji_id = emoji
            emoji_url = discord.Embed.Empty

        kemoji = KarmaEmoji.get(ctx.guild.id, emoji_id)
        if not kemoji:
            await ctx.reply(_(ctx, "This emoji does not have karma value."))
            return

        embed = utils.Discord.create_embed(
            author=ctx.author,
            title=_(ctx, "Emoji karma"),
        )

        embed.add_field(name=_(ctx, "Karma value"), value=kemoji.value)

        embed.set_thumbnail(url=emoji_url)

        await ctx.reply(embed=embed)

    @commands.check(check.acl)
    @karma_.command(name="emojis")
    async def karma_emojis(self, ctx):
        """Display karma emojis on this server."""
        kemojis = KarmaEmoji.get_all(ctx.guild.id)
        if not kemojis:
            await ctx.reply(_(ctx, "No emoji has karma value on this server."))
            return

        emojis_positive = [e for e in kemojis if e.value > 0]
        emojis_neutral = [e for e in kemojis if e.value == 0]
        emojis_negative = [e for e in kemojis if e.value < 0]

        def format_emojis(emojis) -> List[str]:
            emoji_lists = {}
            for i, emoji in enumerate(emojis):
                if type(emoji) == UnicodeEmoji:
                    emoji_str = emoji.emoji
                elif type(emoji) == DiscordEmoji:
                    emoji_str = f"<:pumpkin:{emoji.emoji_id}>"

                idx = i // 8
                if i % 8 == 0:
                    emoji_lists[idx] = []
                emoji_lists[idx].append(emoji_str)

            lines = [" ".join(line) for line in emoji_lists.values()]
            return lines

        if len(emojis_positive):
            await ctx.send(_(ctx, "Emojis with positive karma"))
            for line in format_emojis(emojis_positive):
                if line:
                    await ctx.send(line)
        if len(emojis_neutral):
            await ctx.send(_(ctx, "Emojis with neutral karma"))
            for line in format_emojis(emojis_neutral):
                if line:
                    await ctx.send(line)
        if len(emojis_negative):
            await ctx.send(_(ctx, "Emojis with negative karma"))
            for line in format_emojis(emojis_negative):
                if line:
                    await ctx.send(line)

    @commands.check(check.acl)
    @karma_.command(name="vote")
    async def karma_vote(self, ctx, emoji: str = None):
        """Vote over emoji's karma value."""
        await utils.Discord.delete_message(ctx.message)

        with contextlib.suppress(commands.EmojiNotFound):
            emoji = await commands.EmojiConverter().convert(ctx, emoji)

        if emoji is None:
            voted_ids = [e.emoji_id for e in DiscordEmoji.get_all(ctx.guild.id)]
            for guild_emoji in ctx.guild.emojis:
                if guild_emoji.id not in voted_ids:
                    emoji = guild_emoji
                    break

        if emoji is None:
            await ctx.author.send(
                _(ctx, "All server emojis have been assigned a karma value.")
            )
            return
        emoji_name: str = getattr(emoji, "name", str(emoji))

        message = (
            _(ctx, "Karma vote over the value of {emoji} started.")
            + "\n"
            + _(ctx, "The vote will run for **{minutes}** minutes.")
            + " "
            + _(ctx, "Required minimum vote count is **{count}**.")
        )
        # TODO Make configurable
        vote_message = await ctx.send(
            message.format(emoji=str(emoji), minutes=120, count=10)
        )

        # Set the value to zero, so we can run this command multiple times
        # without starting a vote over the same emoji over and over.
        if type(emoji) is discord.Emoji:
            DiscordEmoji.add(ctx.guild.id, emoji.id, 0)

        await guild_log.info(
            ctx.author, ctx.channel, f"Karma vote over emoji '{emoji_name}' started."
        )

        votes = {"🔼": 0, "0⃣": 0, "🔽": 0}
        emoji_labels = {"🔼": "+1", "0⃣": "0", "🔽": "-1"}
        for vote_option in votes.keys():
            await vote_message.add_reaction(vote_option)

        # TODO Make configurable
        await asyncio.sleep(10)

        # Fetch updated message with the votes
        vote_message = await vote_message.channel.fetch_message(vote_message.id)
        for reaction in vote_message.reactions:
            votes[reaction.emoji] = reaction.count - 1

        log_message: str = (
            f"Karma vote over emoji '{emoji_name}' ended: "
            + ", ".join(f"{v}x {emoji_labels[k]}" for k, v in votes.items())
            + "."
        )

        result: Optional[int] = None
        if votes["🔼"] > votes["0⃣"] and votes["🔼"] > votes["🔽"]:
            result = 1
        elif votes["0⃣"] > votes["🔽"] and votes["0⃣"] > votes["🔼"]:
            result = 0
        elif votes["🔽"] > votes["0⃣"] and votes["🔽"] > votes["🔼"]:
            result = -1
        else:
            await guild_log.info(
                ctx.author,
                ctx.channel,
                _(ctx, log_message + " Inconconclusive, aborted."),
            )
            await ctx.send(_(ctx, "Vote over {emoji} failed.").format(emoji=str(emoji)))
            return

        if type(emoji) is discord.Emoji:
            DiscordEmoji.add(ctx.guild.id, emoji.id, result)
        elif type(emoji) is str:
            UnicodeEmoji.add(ctx.guild.id, emoji, result)

        await guild_log.info(
            ctx.author, ctx.channel, log_message + f" Setting to {result}."
        )
        await ctx.send(
            _(ctx, "Karma value of {emoji} is **{value}**.").format(
                emoji=str(emoji), value=result
            )
        )

    @commands.check(check.acl)
    @karma_.command(name="set")
    async def karma_set(self, ctx, emoji: str, value: int):
        """Set emoji's karma value."""
        with contextlib.suppress(commands.EmojiNotFound):
            emoji = await commands.EmojiConverter().convert(ctx, emoji)

        if type(emoji) != discord.Emoji and emoji not in UNICODE_EMOJI:
            await ctx.reply(
                _(ctx, "I can only use Unicode emojis or emojis from this server.")
            )
            return

        if value not in (-1, 0, 1):
            await ctx.reply(
                _(ctx, "I'll use the value, but usually they are only 1, 0 or -1.")
            )

        if type(emoji) == discord.Emoji:
            DiscordEmoji.add(ctx.guild.id, emoji.id, value)
        elif type(emoji) == str:
            UnicodeEmoji.add(ctx.guild.id, emoji, value)

        await ctx.reply(_(ctx, "The value has been set."))

    @commands.check(check.acl)
    @karma_.command(name="message")
    async def karma_message(self, ctx, message: discord.Message):
        """Display total message karma."""
        if IgnoredChannel.get(message.guild.id, message.channel.id) is not None:
            await ctx.reply(_(ctx, "Karma is disabled for this message."))
            return

        message_karma: int = 0
        output = {"negative": [], "neutral": [], "positive": []}
        for reaction in message.reactions:
            if type(reaction.emoji) is discord.Emoji:
                emoji = DiscordEmoji.get(ctx.guild.id, reaction.emoji.id)
            elif type(reaction.emoji) is str:
                emoji = UnicodeEmoji.get(ctx.guild.id, reaction.emoji)
            else:
                # PartialEmoji which is not usable by the bot
                emoji = None

            if not emoji:
                continue

            if emoji.value < 0:
                output["negative"].append(emoji)
                message_karma -= reaction.count
            elif emoji.value > 0:
                output["positive"].append(emoji)
                message_karma += reaction.count
            else:
                output["neutral"].append(emoji)

        embed = utils.Discord.create_embed(
            author=ctx.author,
            title=_(ctx, "Message karma"),
            description=_(
                ctx,
                "Total karma value of [the message]({link}) is {value} karma points.",
            ).format(link=message.jump_url, value=message_karma),
        )

        timestamp: str = utils.Time.datetime(utils.Time.id_to_datetime(message.id))
        embed.add_field(
            name=timestamp,
            value=_(ctx, "**{user}** in #{channel}").format(
                user=utils.Text.sanitise(message.author.display_name),
                channel=message.channel.name,
            ),
            inline=True,
        )

        if message.content:
            embed.add_field(
                name=_(ctx, "Message content"),
                value=message.content[:512],
                inline=False,
            )

        if output["positive"]:
            embed.add_field(
                name=_(ctx, "Positive reactions"),
                value=" ".join(str(e) for e in output["positive"]),
                inline=False,
            )
        if output["negative"]:
            embed.add_field(
                name=_(ctx, "Negative reactions"),
                value=" ".join(str(e) for e in output["negative"]),
                inline=False,
            )
        if output["neutral"]:
            embed.add_field(
                name=_(ctx, "Neutral reactions"),
                value=" ".join(str(e) for e in output["neutral"]),
                inline=False,
            )

        await ctx.reply(embed=embed)

    @commands.check(check.acl)
    @karma_.command(name="give")
    async def karma_give(
        self, ctx, members: commands.Greedy[discord.Member], value: int
    ):
        """Give some karma to multiple users."""
        for member in members:
            KarmaMember.update(
                ctx.guild.id, member.id, KarmaActionActor.RECEIVER, value
            )
        reply: str
        if len(members) == 1:
            reply = _(ctx, "{member} got {value} karma points.").format(
                member=utils.Text.sanitise(member.name),
                value=value,
            )
        else:
            reply = _(ctx, "Every member got {value} karma points").format(
                value=value,
            )
        await ctx.reply(reply)

        await guild_log.info(
            ctx.author,
            ctx.channel,
            f"{value} karma points added to " + ", ".join([m.name for m in members]),
        )

    @commands.check(check.acl)
    @karma_.command(name="leaderboard")
    async def karma_leaderboard(self, ctx):
        """Display karma leaders."""
        embeds = Karma._create_embeds(
            ctx=ctx,
            title=_(ctx, "Karma leaderboard"),
            description=_(ctx, "Score, descending"),
            board=BoardType.value,
            order=BoardOrder.DESC,
        )

        if not embeds:
            await ctx.reply(_(ctx, "Karma data not yet available."))
            return

        scrollable = utils.ScrollableEmbed()
        scrollable.from_iter(ctx, embeds)
        await scrollable.scroll(ctx)

    @commands.check(check.acl)
    @karma_.command(name="loserboard")
    async def karma_loserboard(self, ctx):
        """Display karma losers."""
        embeds = Karma._create_embeds(
            ctx=ctx,
            title=_(ctx, "Karma loserboard"),
            description=_(ctx, "Score, ascending"),
            board=BoardType.value,
            order=BoardOrder.ASC,
        )

        if not embeds:
            await ctx.reply(_(ctx, "Karma data not yet available."))
            return

        scrollable = utils.ScrollableEmbed()
        scrollable.from_iter(ctx, embeds)
        await scrollable.scroll(ctx)

    @commands.check(check.acl)
    @karma_.command(name="givingboard")
    async def karma_givingboard(self, ctx):
        """Display karma givers."""
        embeds = Karma._create_embeds(
            ctx=ctx,
            title=_(ctx, "Karma givingboard"),
            description=_(ctx, "Score, descending"),
            board=BoardType.given,
            order=BoardOrder.DESC,
        )

        if not embeds:
            await ctx.reply(_(ctx, "Karma data not yet available."))
            return

        scrollable = utils.ScrollableEmbed()
        scrollable.from_iter(ctx, embeds)
        await scrollable.scroll(ctx)

    @commands.check(check.acl)
    @karma_.command(name="takingboard")
    async def karma_takingboard(self, ctx):
        """Display karma takers."""
        embeds = Karma._create_embeds(
            ctx=ctx,
            title=_(ctx, "Karma takingboard"),
            description=_(ctx, "Score, descending"),
            board=BoardType.taken,
            order=BoardOrder.DESC,
        )

        if not embeds:
            await ctx.reply(_(ctx, "Karma data not yet available."))
            return

        scrollable = utils.ScrollableEmbed()
        scrollable.from_iter(ctx, embeds)
        await scrollable.scroll(ctx)

    #

    @staticmethod
    def _create_embeds(
        *,
        ctx: commands.Context,
        title: str,
        description: str,
        board: BoardType,
        order: BoardOrder,
        item_count: int = 10,
        page_count: int = 10,
    ) -> List[discord.Embed]:
        pages: List[discord.Embed] = []

        author = KarmaMember.get(ctx.guild.id, ctx.author.id)
        guild_limit: int = KarmaMember.get_count(ctx.guild.id)
        limit: int = min(guild_limit, page_count * item_count)

        embed = utils.Discord.create_embed(
            author=ctx.author,
            title=title,
            description=description,
        )

        for page_number in range(page_count):
            users = KarmaMember.get_some(
                ctx.guild.id,
                board,
                order,
                item_count,
                item_count * page_number,
            )
            if not users:
                break

            page = embed.copy()

            page_title: str
            if order == BoardOrder.DESC:
                page_title = _(ctx, "Top {limit}").format(limit=limit)
            elif order == BoardOrder.ASC:
                page_title = _(ctx, "Worst {limit}").format(limit=limit)

            page.add_field(
                name=page_title,
                value=Karma._create_embed_page(users, ctx.author, ctx.guild, board),
                inline=False,
            )

            if ctx.author.id not in [u.user_id for u in users]:
                page.add_field(
                    name=_(ctx, "Your score"),
                    value=Karma._create_embed_page(
                        [author], ctx.author, ctx.guild, board
                    ),
                    inline=False,
                )

            pages.append(page)

        return pages

    @staticmethod
    def _create_embed_page(
        users: List[KarmaMember],
        author: discord.Member,
        guild: discord.Guild,
        board: BoardType,
    ) -> str:
        result = []
        line_template = "`{value:>6}` … {name}"
        tc = TranslationContext(guild.id, author.id)

        for user in users:
            member = guild.get_member(user.user_id)
            if member and member.display_name:
                name = utils.Text.sanitise(member.display_name, limit=32)
            else:
                name = _(tc, "Unknown member")

            if user.user_id == author.id:
                name = f"**{name}**"

            result.append(
                line_template.format(
                    value=getattr(user, board.name),
                    name=name,
                )
            )

        return "\n".join(result)


def setup(bot) -> None:
    bot.add_cog(Karma(bot))
