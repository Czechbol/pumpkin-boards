from __future__ import annotations

from enum import Enum
from typing import Dict, Optional, List, Union

from sqlalchemy import func
from sqlalchemy import BigInteger, Column, Integer, String

from database import database, session


class BoardOrder(Enum):
    ASC = 0
    DESC = 1


class BoardType(Enum):
    taken = -1
    value = 0
    given = 1


class KarmaActionActor(Enum):
    GIVER = 0
    RECEIVER = 1


class KarmaMember(database.base):
    __tablename__ = "boards_karma_members"

    idx = Column(Integer, primary_key=True, autoincrement=True)
    guild_id = Column(BigInteger)
    user_id = Column(BigInteger, default=None)
    value = Column(Integer, default=0)
    given = Column(Integer, default=0)
    taken = Column(Integer, default=0)

    @staticmethod
    def get_or_add(guild_id: int, user_id: int) -> KarmaMember:
        member = KarmaMember.get(guild_id, user_id)
        if not member:
            member = KarmaMember.add(guild_id, user_id)
        return member

    @staticmethod
    def get(guild_id: int, user_id: int) -> Optional[KarmaMember]:
        query = (
            session.query(KarmaMember)
            .filter_by(guild_id=guild_id, user_id=user_id)
            .one_or_none()
        )
        return query

    @staticmethod
    def get_count(guild_id: int) -> int:
        count = (
            session.query(func.count(KarmaMember.user_id))
            .filter_by(guild_id=guild_id)
            .scalar()
        )

        return count

    @staticmethod
    def get_some(
        guild_id: int, board: BoardType, order: BoardOrder, limit: int, offset: int
    ) -> List[KarmaMember]:
        column = getattr(KarmaMember, board.name)

        if order == BoardOrder.ASC:
            order_by = column.asc()
        elif order == BoardOrder.DESC:
            order_by = column.desc()
        else:
            raise ValueError(f"Unsupported BoardOrder {order}.")

        query = (
            session.query(KarmaMember)
            .filter_by(guild_id=guild_id)
            .order_by(order_by)
            .offset(offset)
            .limit(limit)
            .all()
        )

        return query

    @staticmethod
    def add(guild_id: int, user_id: int) -> KarmaMember:
        if KarmaMember.get(guild_id, user_id):
            raise ValueError(f"Member {user_id} already exists in guild {guild_id}.")
        member = KarmaMember(guild_id=guild_id, user_id=user_id)
        session.add(member)
        session.commit()
        return member

    @staticmethod
    def update(
        guild_id: int, user_id: int, actor: KarmaActionActor, value: int
    ) -> KarmaMember:
        """Update member entry."""
        member = KarmaMember.get(guild_id, user_id)
        if not member:
            member = KarmaMember.add(guild_id, user_id)

        if value == 0:
            return member

        if actor == KarmaActionActor.RECEIVER:
            member.value += value
        elif actor == KarmaActionActor.GIVER and value > 0:
            member.given += value
        elif actor == KarmaActionActor.GIVER and value < 0:
            member.taken += -value

        session.commit()
        return member

    @property
    def value_position(self) -> int:
        value = (
            session.query(func.count(KarmaMember.user_id))
            .filter(KarmaMember.value > self.value)
            .one()
        )
        return value[0] + 1

    @property
    def given_position(self) -> int:
        value = (
            session.query(func.count(KarmaMember.user_id))
            .filter(KarmaMember.given > self.given)
            .one()
        )
        return value[0] + 1

    @property
    def taken_position(self) -> int:
        value = (
            session.query(func.count(KarmaMember.user_id))
            .filter(KarmaMember.taken > self.taken)
            .one()
        )
        return value[0] + 1

    def __repr__(self) -> str:
        return (
            f"<KarmaMember idx='{self.idx}' "
            f"guild_id='{self.guild_id}' user_id='{self.user_id}' "
            f"value='{self.value}' given='{self.given}' taken='{self.taken}'>"
        )

    def dump(self) -> Dict[str, int]:
        return {
            "guild_id": self.guild_id,
            "user_id": self.user_id,
            "value": self.value,
            "given": self.given,
            "taken": self.taken,
        }


class KarmaEmoji:
    @staticmethod
    def add(guild_id: int, emoji: Union[str, int], value: int):
        if type(emoji) == int:
            return DiscordEmoji.add(guild_id, emoji, value)
        elif type(emoji) == str and value != 0:
            return UnicodeEmoji.add(guild_id, emoji, value)

    @staticmethod
    def get(
        guild_id: int, emoji: Union[str, int]
    ) -> Optional[Union[DiscordEmoji, UnicodeEmoji]]:
        if type(emoji) == int:
            return DiscordEmoji.get(guild_id, emoji)
        elif type(emoji) == str:
            return UnicodeEmoji.get(guild_id, emoji)

    @staticmethod
    def get_all(guild_id) -> List[Union[DiscordEmoji, UnicodeEmoji]]:
        return DiscordEmoji.get_all(guild_id) + UnicodeEmoji.get_all(guild_id)

    @staticmethod
    def remove(guild_id: int, emoji: Union[str, int]) -> int:
        if type(emoji) == int:
            return DiscordEmoji.remove(guild_id, emoji)
        elif type(emoji) == str:
            return UnicodeEmoji.remove(guild_id, emoji)


class DiscordEmoji(database.base):
    __tablename__ = "boards_karma_discord_emojis"

    idx = Column(Integer, primary_key=True, autoincrement=True)
    guild_id = Column(BigInteger)
    emoji_id = Column(BigInteger)
    value = Column(Integer)

    @staticmethod
    def add(guild_id: int, emoji_id: int, value: int) -> DiscordEmoji:
        query = DiscordEmoji.get(guild_id, emoji_id)
        if not query:
            query = DiscordEmoji(guild_id=guild_id, emoji_id=emoji_id)
        query.value = value
        session.merge(query)
        session.commit()
        return query

    @staticmethod
    def get(guild_id: int, emoji_id: int) -> Optional[DiscordEmoji]:
        query = (
            session.query(DiscordEmoji)
            .filter_by(guild_id=guild_id, emoji_id=emoji_id)
            .one_or_none()
        )
        return query

    @staticmethod
    def get_all(guild_id: int) -> List[DiscordEmoji]:
        query = session.query(DiscordEmoji).filter_by(guild_id=guild_id).all()
        return query

    @staticmethod
    def remove(guild_id: int, emoji_id: int) -> int:
        query = (
            session.query(DiscordEmoji)
            .filter_by(guild_id=guild_id, emoji_id=emoji_id)
            .delete()
        )
        return query

    def __repr__(self) -> str:
        return (
            f"<DiscordEmoji idx='{self.idx}' guild_id='{self.guild_id}' "
            f"emoji_id='{self.emoji_id}' value='{self.value}'>"
        )

    def __str__(self) -> str:
        return f"<:pumpkin:{self.emoji_id}>"

    def dump(self) -> Dict[str, int]:
        return {
            "guild_id": self.guild_id,
            "emoji_id": self.emoji_id,
            "value": self.value,
        }


class UnicodeEmoji(database.base):
    __tablename__ = "boards_karma_unicode_emojis"

    idx = Column(Integer, primary_key=True, autoincrement=True)
    guild_id = Column(BigInteger)
    emoji = Column(String)
    value = Column(Integer)

    @staticmethod
    def add(guild_id: int, emoji: str, value: int) -> UnicodeEmoji:
        query = UnicodeEmoji.get(guild_id, emoji)
        if not query:
            query = UnicodeEmoji(guild_id=guild_id, emoji=emoji)
        query.value = value
        session.merge(query)
        session.commit()
        return query

    @staticmethod
    def get(guild_id: int, emoji: str) -> Optional[UnicodeEmoji]:
        query = (
            session.query(UnicodeEmoji)
            .filter_by(guild_id=guild_id, emoji=emoji)
            .one_or_none()
        )
        return query

    @staticmethod
    def get_all(guild_id: int) -> List[UnicodeEmoji]:
        query = session.query(UnicodeEmoji).filter_by(guild_id=guild_id).all()
        return query

    @staticmethod
    def remove(guild_id: int, emoji: str) -> int:
        query = (
            session.query(UnicodeEmoji)
            .filter_by(guild_id=guild_id, emoji=emoji)
            .delete()
        )
        return query

    def __repr__(self) -> str:
        return (
            f"<UnicodeEmoji idx='{self.idx}' guild_id='{self.guild_id}' "
            f"emoji='{self.emoji}' value='{self.value}'>"
        )

    def __str__(self) -> str:
        return self.emoji

    def dump(self) -> Dict[str, Union[str, int]]:
        return {
            "guild_id": self.guild_id,
            "emoji": self.emoji,
            "value": self.value,
        }


class IgnoredChannel(database.base):
    """Channels where karma is disabled."""

    __tablename__ = "boards_karma_ignored"

    idx = Column(Integer, primary_key=True, autoincrement=True)
    guild_id = Column(BigInteger)
    channel_id = Column(BigInteger)

    @staticmethod
    def get(guild_id: int, channel_id: int) -> Optional[IgnoredChannel]:
        query = (
            session.query(IgnoredChannel)
            .filter_by(guild_id=guild_id, channel_id=channel_id)
            .one_or_none()
        )
        return query

    @staticmethod
    def add(guild_id: int, channel_id: int) -> IgnoredChannel:
        if IgnoredChannel.get(guild_id, channel_id) is not None:
            return
        query = IgnoredChannel(guild_id=guild_id, channel_id=channel_id)
        session.add(query)
        session.commit()
        return query

    @staticmethod
    def remove(guild_id: int, channel_id: int) -> int:
        query = (
            session.query(IgnoredChannel)
            .filter_by(guild_id=guild_id, channel_id=channel_id)
            .delete()
        )
        return query

    def __repr__(self) -> str:
        return (
            f"<{self.__class__.__name__} "
            f"guild_id='{self.guild_id}' channel_id='{self.channel_id}'>"
        )

    def dump(self) -> Dict[str, int]:
        return {
            "guild_id": self.guild_id,
            "channel_id": self.channel_id,
        }
