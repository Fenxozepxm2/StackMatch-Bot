import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    JSON,
    DateTime,
    Enum,
    ForeignKey,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    tg_id: Mapped[int] = mapped_column(unique=True, index=True)
    username: Mapped[str] = mapped_column(nullable=True)
    name: Mapped[str] = mapped_column(nullable=True)
    last_seen_in_bot: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    balance: Mapped[int] = mapped_column(default=0)

    last_vacancy_check: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=True, server_default=func.now()
    )

    skills: Mapped[list[str] | None] = mapped_column(
        JSON, server_default="[]", nullable=True
    )
    liked: Mapped[list[str] | None] = mapped_column(
        JSON, server_default="[]", nullable=True
    )
    disliked: Mapped[list[str] | None] = mapped_column(
        JSON, server_default="[]", nullable=True
    )

    filter: Mapped[Optional["Filter_HH"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class User_notification(Base):
    __tablename__ = "users_notification"

    id: Mapped[int] = mapped_column(primary_key=True)

    tg_id: Mapped[int] = mapped_column(
        ForeignKey("users.tg_id", ondelete="CASCADE", name="fk_user_notification_tg_id")
    )

    vacancy_id: Mapped[str] = mapped_column(String(124), unique=True, nullable=False)

    vacancy_data: Mapped[str] = mapped_column(JSON, server_default="[]", nullable=True)

    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    viewed: Mapped[bool] = mapped_column(server_default="False")


class Filter_HH(Base):
    __tablename__ = "filters_hh"

    id: Mapped[int] = mapped_column(primary_key=True)
    tg_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True
    )

    filters: Mapped[dict] = mapped_column(JSON, nullable=False, server_default="{}")

    # salary_from: Mapped[int] = mapped_column(default=0)
    # salary_to: Mapped[int] = mapped_column(default=0)

    # city: Mapped[str] = mapped_column(String(100), server_default="any")
    # specialization: Mapped[Optional[str]] = mapped_column(String(100), server_default=None)
    # payday: Mapped[Optional[str]] = mapped_column(String(100), server_default=None)
    # experience: Mapped[Optional[int]] = mapped_column(CheckConstraint("experience <= 9"), server_default=None)
    # employmentZan: Mapped[Optional[str]] = mapped_column(String(100), server_default=None)
    # schedule: Mapped[Optional[str]] = mapped_column(String(100), server_default=None)
    # work_hours: Mapped[Optional[int]] = mapped_column(CheckConstraint("work_hours <= 24"), server_default=None)
    # work_format: Mapped[Optional[str]] = mapped_column(String(100), server_default=None)
    # newest_first: Mapped[Optional[bool]] = mapped_column(default=True)
    # employment_type: Mapped[Optional[str]] = mapped_column(String(100), server_default=None)
    # find_key_words: Mapped[Optional[List[str]]] = mapped_column(JSON, server_default='[]')
    # exclude_key_words: Mapped[Optional[List[str]]] = mapped_column(JSON, server_default='[]')

    user: Mapped["User"] = relationship(back_populates="filter", uselist=False)


class ActionType(enum.Enum):
    LIKE = "like"
    SKIP = "skip"
    VIEWED = "view"


class VacancyAction(Base):
    __tablename__ = "vacancy_actions"

    id: Mapped[int] = mapped_column(primary_key=True)

    vacancy_id: Mapped[str] = mapped_column(String(50), index=True)

    action: Mapped[ActionType] = mapped_column(Enum(ActionType), nullable=False)

    # Дополнительно: сохраним название вакансии и ссылку, чтобы легко выводить список лайкнутых
    vacancy_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    vacancy_url: Mapped[str | None] = mapped_column(String(512), nullable=True)

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    # При следующем обновлении БД обновить на tg_id
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.tg_id", ondelete="CASCADE", name="fk_vacancy_action_user_id"),
        index=True,
    )

    # Уникальный индекс: один пользователь не может лайкнуть/скипнуть одну и ту же вакансию дважды
    __table_args__ = (
        UniqueConstraint("user_id", "vacancy_id", name="uq_user_vacancy_action"),
    )
