import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    String,
    UniqueConstraint,
    false,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    tg_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(nullable=True)
    name: Mapped[str | None] = mapped_column(nullable=True)
    last_seen_in_bot: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    balance: Mapped[int] = mapped_column(default=0)

    last_vacancy_check: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, server_default=func.now()
    )

    skills: Mapped[list[str] | None] = mapped_column(
        JSONB, server_default=text("'[]'::jsonb"), nullable=True
    )
    liked: Mapped[list[str] | None] = mapped_column(
        JSONB, server_default=text("'[]'::jsonb"), nullable=True
    )
    disliked: Mapped[list[str] | None] = mapped_column(
        JSONB, server_default=text("'[]'::jsonb"), nullable=True
    )

    filter: Mapped[Optional["Filter_HH"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class User_notification(Base):
    __tablename__ = "users_notification"

    id: Mapped[int] = mapped_column(primary_key=True)

    # ForeignKey идёт ВТОРЫМ аргументом mapped_column, тип колонки — первым
    tg_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.tg_id", ondelete="CASCADE", name="fk_user_notification_tg_id"),
        index=True,
    )

    vacancy_id: Mapped[str] = mapped_column(String(124), nullable=False)

    vacancy_data: Mapped[dict] = mapped_column(
        JSONB, server_default=text("'{}'::jsonb"), nullable=True
    )

    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    viewed: Mapped[bool] = mapped_column(default=False, server_default=false())

    # Уникальность на пару (юзер, вакансия), а не глобально по vacancy_id
    __table_args__ = (
        UniqueConstraint("tg_id", "vacancy_id", name="uq_notification_user_vacancy"),
    )


class Filter_HH(Base):
    __tablename__ = "filters_hh"

    id: Mapped[int] = mapped_column(primary_key=True)

    # В репозитории сюда пишется Telegram ID, поэтому FK на users.tg_id (BigInteger),
    # а не на users.id
    tg_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.tg_id", ondelete="CASCADE", name="fk_filters_hh_tg_id"),
        unique=True,
        index=True,
    )

    filters: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    user: Mapped["User"] = relationship(back_populates="filter", uselist=False)


class ActionType(enum.Enum):
    LIKE = "like"
    SKIP = "skip"
    VIEWED = "view"


class VacancyAction(Base):
    __tablename__ = "vacancy_actions"

    id: Mapped[int] = mapped_column(primary_key=True)

    vacancy_id: Mapped[str] = mapped_column(String(124), index=True)

    action: Mapped[ActionType] = mapped_column(Enum(ActionType), nullable=False)

    vacancy_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    vacancy_url: Mapped[str | None] = mapped_column(String(512), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Репозиторий пишет сюда внутренний User.id (db_user.id), поэтому FK на users.id (Integer)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE", name="fk_vacancy_action_user_id"),
        index=True,
    )

    # Один пользователь не может лайкнуть/скипнуть одну и ту же вакансию дважды
    __table_args__ = (
        UniqueConstraint("user_id", "vacancy_id", name="uq_user_vacancy_action"),
    )