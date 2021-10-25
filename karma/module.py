import contextlib
from typing import Optional, List, Tuple, Union

from emoji import UNICODE_EMOJI as _UNICODE_EMOJI


import discord
from discord.ext import commands

from core import check, i18n, logger, utils

from .database import (
    KarmaActionActor,
    KarmaMember,
    KarmaEmoji,
    UnicodeEmoji,
    DiscordEmoji,
    IgnoredChannel,
)

UNICODE_EMOJI = _UNICODE_EMOJI["en"]
del _UNICODE_EMOJI

_ = i18n.Translator("modules/boards").translate
bot_log = logger.Bot.logger()
guild_log = logger.Guild.logger()


class Karma(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.group(name="karma")
    async def karma_(self, ctx):
        await utils.Discord.send_help(ctx)

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

    @karma_.command(name="vote")
    async def karma_vote(self, ctx, emoji: str = None):
        """Vote over emoji's karma value."""
        pass

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

        if type(emoji) == discord.Emoji:
            DiscordEmoji.add(ctx.guild.id, emoji.id, value)
        elif type(emoji) == str:
            UnicodeEmoji.add(ctx.guild.id, emoji, value)

        await ctx.reply(_(ctx, "The value has been set."))

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

    @karma_.command(name="leaderboard")
    async def karma_leaderboard(self, ctx):
        """Display karma leaders."""
        pass

    @karma_.command(name="loserboard")
    async def karma_loserboard(self, ctx):
        """Display karma losers."""
        pass

    @karma_.command(name="givingboard")
    async def karma_givingboard(self, ctx):
        """Display karma givers."""
        pass

    @karma_.command(name="takingboard")
    async def karma_takingboard(self, ctx):
        """Display karma givers."""
        pass


def setup(bot) -> None:
    bot.add_cog(Karma(bot))
