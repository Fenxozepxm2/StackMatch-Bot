"""
Панель фильтров (заменяет filters.py + весь filters_widget/* + filter_keyboard + filter_states).

Что изменилось по сравнению со старой версией:
  * Один экран = ОДНО сообщение, которое редактируется на месте (раньше сообщения
    удалялись и отправлялись заново, чат мерцал и засорялся).
  * Живой счётчик «найдено на hh.ru: N» обновляется при каждом клике.
  * Если вакансий 0 — бот сам предлагает, какой фильтр убрать и сколько станет вакансий.
  * Пресеты «в один тап» для типовых IT-ролей.
  * Автосохранение в БД на каждое действие. Кнопки «Готово/Сохранить» больше не нужны,
    а источник истины один — БД (никакого рассинхрона FSM-словаря и базы).
  * Три одинаковых виджета (опыт/график/формат) заменены одним дженериком на основе
    справочников из домена. Callback'и — через CallbackData с индексами, а не split("_")
    по русским строкам (у Telegram лимит callback_data 64 БАЙТА, кириллица — 2 байта/символ).
  * Ввод текста — через явное FSM-состояние, а не магическую строку `expecting`.
"""

from __future__ import annotations

import html
from dataclasses import dataclass, replace

import aiohttp
import structlog
from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from bot.domain.search_filters import (
    CHOICES,
    LIST_FIELDS,
    PRESETS,
    FilterInputError,
    SearchFilters,
    format_int,
    parse_items,
    parse_salary,
    plural,
    relax_hints,
)
from bot.services.hh_count import make_counter
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import load_config
from bot.db.repos.repo_filters import get_user_filters, save_filters
from bot.db.repos.repo_user import save_user
from bot.services.city_mapper import CityMapper

config = load_config()
logger = structlog.get_logger(__name__)
router = Router(name="Filters")


# ═════════════════════════ Описание экранов (презентация) ═════════════════════════


@dataclass(frozen=True)
class FieldView:
    key: str
    emoji: str
    title: str
    kind: str  # choice | list | text | salary | city


FIELDS = (
    FieldView("city", "🏙", "Город", "city"),
    FieldView("salary", "💰", "Зарплата", "salary"),
    FieldView("specialization", "🧭", "Направление", "text"),
    FieldView("user_tech_stack", "🛠", "Мой стек", "list"),
    FieldView("exp", "🕒", "Опыт", "choice"),
    FieldView("schedule", "📅", "График", "choice"),
    FieldView("workformat", "🏢", "Формат", "choice"),
    FieldView("find_key_words", "🔑", "Слова", "list"),
    FieldView("exclude_key_words", "🚫", "Исключить", "list"),
)
FIELD_BY_KEY = {f.key: f for f in FIELDS}

PROMPTS = {
    "specialization": (
        "🧭 <b>Направление</b>\nНапиши роль, которую ищешь. Например: <i>Python разработчик</i>."
    ),
    "salary": (
        "💰 <b>Зарплата</b>\nНапиши сумму как удобно:\n"
        "• <code>150000</code> или <code>от 150к</code>\n"
        "• <code>до 300 000</code>\n"
        "• <code>100к - 200к</code>"
    ),
    "city": "🏙 <b>Город</b>\nНапиши название, можно сокращённо: <i>спб</i>, <i>москва</i>.",
    "user_tech_stack": (
        "🛠 <b>Мой стек</b>\nПеречисли технологии через запятую:\n"
        "<i>Python, FastAPI, PostgreSQL, Docker</i>"
    ),
    "find_key_words": (
        "🔑 <b>Обязательные слова</b>\nЧерез запятую. Каждое должно встретиться в вакансии:\n"
        "<i>REST API, Django</i>"
    ),
    "exclude_key_words": (
        "🚫 <b>Исключить</b>\nЧерез запятую. Вакансии с этими словами не покажу:\n"
        "<i>PHP, 1С, стажировка</i>"
    ),
}

VACANCY_FORMS = ("вакансия", "вакансии", "вакансий")


class FilterCB(CallbackData, prefix="flt"):
    a: str  # действие
    f: str = ""  # ключ фильтра
    i: int = -1  # индекс (опция / элемент списка / пресет / город)


class FilterEdit(StatesGroup):
    waiting_text = State()


def _btn(text: str, a: str, f: str = "", i: int = -1) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=FilterCB(a=a, f=f, i=i).pack())


def _kb(rows: list[list[InlineKeyboardButton]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _count_line(found: int | None) -> str:
    if found is None:
        return "🔎 <i>Число вакансий сейчас недоступно</i>"
    return f"🔎 Найдено на hh.ru: <b>{format_int(found)}</b> {plural(found, VACANCY_FORMS)}"


# ─────────── чистые функции построения экранов: данные -> (текст, клавиатура) ───────────


def build_dashboard(
    flt: SearchFilters,
    found: int | None,
    hints: list[tuple[str, int]],
    notice: str | None = None,
) -> tuple[str, InlineKeyboardMarkup]:
    lines = ["🎛 <b>Фильтры поиска</b>", "", _count_line(found), ""]

    described = flt.describe()
    if described:
        for key, value in described:
            fv = FIELD_BY_KEY[key]
            lines.append(f"{fv.emoji} <b>{fv.title}:</b> {html.escape(value)}")
        if flt.user_tech_stack:
            mode = "вкл" if flt.strict_stack_filter else "откл"
            lines.append(f"🎯 <b>Строгий стек:</b> {mode}")
    else:
        lines.append(
            "<i>Пока ничего не задано — покажу всё подряд. "
            "Возьми пресет ⚡ или настрой вручную.</i>"
        )

    if flt.exclude_key_words and not (
        flt.specialization or flt.user_tech_stack or flt.find_key_words
    ):
        lines += [
            "",
            "ℹ️ <i>Исключения работают вместе с направлением, стеком или словами.</i>",
        ]

    if found == 0:
        lines += [
            "",
            "😕 <b>Ничего не нашлось.</b>" + (" Что, если ослабить:" if hints else ""),
        ]
    elif found is not None and found > 5000 and flt.active_count < 3:
        lines += ["", "💡 <i>Слишком широко — добавь стек или опыт.</i>"]

    if notice:
        lines += ["", notice]

    def field_btn(key: str) -> InlineKeyboardButton:
        fv = FIELD_BY_KEY[key]
        mark = "🟢" if flt.is_set(key) else "⚪"
        return _btn(f"{mark} {fv.title}", "open", key)

    rows: list[list[InlineKeyboardButton]] = []
    for key, n in hints:
        rows.append(
            [
                _btn(
                    f"↩️ Убрать «{FIELD_BY_KEY[key].title}» → {format_int(n)}",
                    "rlx",
                    key,
                )
            ]
        )
    rows += [
        [field_btn("city"), field_btn("salary")],
        [field_btn("specialization"), field_btn("user_tech_stack")],
        [field_btn("exp"), field_btn("schedule")],
        [field_btn("workformat"), field_btn("find_key_words")],
        [field_btn("exclude_key_words"), _btn(f"💱 {flt.currency}", "cur")],
        [
            _btn(
                f"🎯 Строгий стек: {'🟢 вкл' if flt.strict_stack_filter else '⚪ откл'}",
                "strict",
            )
        ],
        [_btn("⚡ Пресеты", "presets"), _btn("🧹 Сбросить всё", "rst")],
        [
            _btn(
                "🚀 Искать вакансии" + (f" ({format_int(found)})" if found else ""),
                "go",
            )
        ],
        [_btn("🏠 В меню", "menu")],
    ]
    return "\n".join(lines), _kb(rows)


def build_choice_view(
    key: str, flt: SearchFilters, found: int | None
) -> tuple[str, InlineKeyboardMarkup]:
    fv, spec = FIELD_BY_KEY[key], CHOICES[key]
    selected = set(getattr(flt, key))
    text = f"{fv.emoji} <b>{fv.title}</b>\nМожно выбрать несколько.\n\n{_count_line(found)}"
    rows = [
        [_btn(("✅ " if opt.label in selected else "▫️ ") + opt.label, "tog", key, idx)]
        for idx, opt in enumerate(spec.options)
    ]
    rows.append([_btn("🧹 Сбросить", "clr", key), _btn("⬅️ Готово", "home")])
    return text, _kb(rows)


def build_list_view(key: str, flt: SearchFilters) -> tuple[str, InlineKeyboardMarkup]:
    fv = FIELD_BY_KEY[key]
    items = getattr(flt, key)
    body = (
        ", ".join(f"<code>{html.escape(i)}</code>" for i in items)
        if items
        else "<i>пусто</i>"
    )
    hint = "\n\n<i>Нажми на элемент, чтобы удалить его.</i>" if items else ""
    text = f"{fv.emoji} <b>{fv.title}</b>\n{body}{hint}"

    rows: list[list[InlineKeyboardButton]] = []
    chips = [_btn(f"❌ {item}", "del", key, idx) for idx, item in enumerate(items)]
    rows += [chips[i : i + 2] for i in range(0, len(chips), 2)]

    controls = [_btn("➕ Добавить", "add", key)]
    if key == "user_tech_stack":
        # подсказки через inline-режим бота работают как раньше
        controls.append(
            InlineKeyboardButton(
                text="⌨️ Подсказки", switch_inline_query_current_chat="stack: "
            )
        )
    rows.append(controls)
    rows.append([_btn("🧹 Очистить", "clr", key), _btn("⬅️ Назад", "home")])
    return text, _kb(rows)


def build_prompt_view(
    key: str, notice: str | None = None
) -> tuple[str, InlineKeyboardMarkup]:
    kind = FIELD_BY_KEY[key].kind
    text = PROMPTS[key] + (f"\n\n{notice}" if notice else "")
    cancel = (
        _btn("❌ Отмена", "open", key) if kind == "list" else _btn("❌ Отмена", "home")
    )
    rows = [[cancel]] if kind == "list" else [[_btn("🧹 Очистить", "clr", key), cancel]]
    return text, _kb(rows)


def build_presets_view() -> tuple[str, InlineKeyboardMarkup]:
    text = (
        "⚡ <b>Пресеты</b>\nОдин тап — и направление, стек и опыт настроены.\n"
        "<i>Город и зарплата сохранятся.</i>"
    )
    rows = [[_btn(p.title, "pre", i=idx)] for idx, p in enumerate(PRESETS)]
    rows.append([_btn("⬅️ Назад", "home")])
    return text, _kb(rows)


def build_city_picker(options: list[str]) -> tuple[str, InlineKeyboardMarkup]:
    text = "🏙 <b>Выбери город</b>\n<i>Не тот? Просто напиши название ещё раз.</i>"
    rows = [[_btn(name, "cpick", i=idx)] for idx, name in enumerate(options)]
    rows.append([_btn("❌ Отмена", "home")])
    return text, _kb(rows)


# ═════════════════════════ Ввод/вывод ═════════════════════════


@dataclass
class Ctx:
    """Всё, что нужно, чтобы перерисовать панель: где она лежит и чем ходить в БД/hh."""

    bot: Bot
    chat_id: int
    message_id: int
    state: FSMContext
    session: AsyncSession
    tg_id: int
    http_session: aiohttp.ClientSession | None


def _ctx_from_callback(
    cb: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    http_session: aiohttp.ClientSession | None,
) -> Ctx | None:
    if cb.message is None:
        return None
    return Ctx(
        bot=cb.bot,
        chat_id=cb.message.chat.id,
        message_id=cb.message.message_id,
        state=state,
        session=session,
        tg_id=cb.from_user.id,
        http_session=http_session,
    )


async def _load(ctx: Ctx) -> SearchFilters:
    return SearchFilters.from_dict(await get_user_filters(ctx.session, ctx.tg_id))


async def _save(ctx: Ctx, flt: SearchFilters) -> None:
    await save_filters(ctx.session, flt.to_dict(), ctx.tg_id)


def _make_counter(ctx: Ctx):
    if ctx.http_session is None:
        return None
    return make_counter(
        ctx.http_session, config.access_token.access_token, CityMapper.get_city_id
    )


async def _render(ctx: Ctx, text: str, kb: InlineKeyboardMarkup) -> None:
    """Редактирует панель на месте. Если сообщение пропало — отправляет новое."""
    try:
        await ctx.bot.edit_message_text(
            chat_id=ctx.chat_id,
            message_id=ctx.message_id,
            text=text,
            reply_markup=kb,
            parse_mode="HTML",
        )
    except TelegramBadRequest as exc:
        reason = str(exc).lower()
        if "message is not modified" in reason:
            return
        if "message to edit not found" in reason or "can't be edited" in reason:
            sent = await ctx.bot.send_message(
                ctx.chat_id, text, reply_markup=kb, parse_mode="HTML"
            )
            ctx.message_id = sent.message_id
            await ctx.state.update_data(panel_id=sent.message_id)
            return
        raise


async def _try_delete(message: Message) -> None:
    try:
        await message.delete()
    except TelegramBadRequest:
        pass


# ─────────── экраны ───────────


async def dashboard(
    ctx: Ctx, flt: SearchFilters | None = None, notice: str | None = None
) -> None:
    flt = flt or await _load(ctx)
    counter = _make_counter(ctx)
    found = await counter(flt) if counter else None
    hints: list[tuple[str, int]] = []
    if counter and found == 0 and flt.active_count:
        hints = await relax_hints(flt, counter)
    text, kb = build_dashboard(flt, found, hints, notice)
    await _render(ctx, text, kb)


async def choice_view(ctx: Ctx, key: str, flt: SearchFilters | None = None) -> None:
    flt = flt or await _load(ctx)
    counter = _make_counter(ctx)
    found = await counter(flt) if counter else None
    text, kb = build_choice_view(key, flt, found)
    await _render(ctx, text, kb)


async def list_view(ctx: Ctx, key: str, flt: SearchFilters | None = None) -> None:
    flt = flt or await _load(ctx)
    text, kb = build_list_view(key, flt)
    await _render(ctx, text, kb)


async def prompt_view(ctx: Ctx, key: str, notice: str | None = None) -> None:
    await ctx.state.set_state(FilterEdit.waiting_text)
    await ctx.state.update_data(field=key, panel_id=ctx.message_id)
    text, kb = build_prompt_view(key, notice)
    await _render(ctx, text, kb)


async def _show_for(ctx: Ctx, key: str, flt: SearchFilters) -> None:
    """После изменения поля показываем тот экран, с которого пришли."""
    kind = FIELD_BY_KEY[key].kind
    if kind == "choice":
        await choice_view(ctx, key, flt)
    elif kind == "list":
        await list_view(ctx, key, flt)
    else:
        await dashboard(ctx, flt)


def _find_cities(query: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for name in CityMapper.search_cities(query, limit=8):
        name = (name or "").strip()
        if name and name != "." and name not in seen:
            seen.add(name)
            out.append(name)
    return out


# ═════════════════════════ Обработчики ═════════════════════════


@router.message(Command("show_filters"))
async def show_filters(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    tg_id: int | None = None,
    http_session: aiohttp.ClientSession | None = None,
):
    """Точка входа. Сигнатура совместима со старой (главное меню вызывает её с tg_id)."""
    if tg_id is None:
        tg_id = message.from_user.id
        await save_user(session, tg_id, message.from_user.username)
    else:
        await save_user(session, tg_id)

    await (
        state.clear()
    )  # иначе чужие state-хендлеры (например browsing) перехватят наши кнопки
    sent = await message.answer("🎛 Загружаю фильтры…")
    await state.update_data(panel_id=sent.message_id)
    ctx = Ctx(
        message.bot,
        message.chat.id,
        sent.message_id,
        state,
        session,
        tg_id,
        http_session,
    )
    await dashboard(ctx)


@router.callback_query(FilterCB.filter(F.a == "home"))
async def on_home(
    cb: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    http_session: aiohttp.ClientSession | None = None,
):
    ctx = _ctx_from_callback(cb, state, session, http_session)
    await cb.answer()
    if ctx is None:
        return
    await state.set_state(None)
    await state.update_data(panel_id=ctx.message_id)
    await dashboard(ctx)


@router.callback_query(FilterCB.filter(F.a == "open"))
async def on_open(
    cb: CallbackQuery,
    callback_data: FilterCB,
    state: FSMContext,
    session: AsyncSession,
    http_session: aiohttp.ClientSession | None = None,
):
    ctx = _ctx_from_callback(cb, state, session, http_session)
    fv = FIELD_BY_KEY.get(callback_data.f)
    if ctx is None or fv is None:
        await cb.answer("Кнопка устарела")
        return
    await cb.answer()
    await state.update_data(panel_id=ctx.message_id)
    if fv.kind == "choice":
        await state.set_state(None)
        await choice_view(ctx, fv.key)
    elif fv.kind == "list":
        await state.set_state(None)
        await list_view(ctx, fv.key)
    else:
        await prompt_view(ctx, fv.key)


@router.callback_query(FilterCB.filter(F.a == "add"))
async def on_add(
    cb: CallbackQuery,
    callback_data: FilterCB,
    state: FSMContext,
    session: AsyncSession,
    http_session: aiohttp.ClientSession | None = None,
):
    ctx = _ctx_from_callback(cb, state, session, http_session)
    if ctx is None or callback_data.f not in LIST_FIELDS:
        await cb.answer("Кнопка устарела")
        return
    await cb.answer()
    await prompt_view(ctx, callback_data.f)


@router.callback_query(FilterCB.filter(F.a == "tog"))
async def on_toggle(
    cb: CallbackQuery,
    callback_data: FilterCB,
    state: FSMContext,
    session: AsyncSession,
    http_session: aiohttp.ClientSession | None = None,
):
    ctx = _ctx_from_callback(cb, state, session, http_session)
    spec = CHOICES.get(callback_data.f)
    if ctx is None or spec is None or not 0 <= callback_data.i < len(spec.options):
        await cb.answer("Кнопка устарела")
        return
    await cb.answer()
    flt = (await _load(ctx)).toggle(spec.key, spec.options[callback_data.i].label)
    await _save(ctx, flt)
    await choice_view(ctx, spec.key, flt)


@router.callback_query(FilterCB.filter(F.a == "del"))
async def on_delete_item(
    cb: CallbackQuery,
    callback_data: FilterCB,
    state: FSMContext,
    session: AsyncSession,
    http_session: aiohttp.ClientSession | None = None,
):
    ctx = _ctx_from_callback(cb, state, session, http_session)
    if ctx is None or callback_data.f not in LIST_FIELDS:
        await cb.answer("Кнопка устарела")
        return
    await cb.answer()
    flt = (await _load(ctx)).remove_at(callback_data.f, callback_data.i)
    await _save(ctx, flt)
    await list_view(ctx, callback_data.f, flt)


@router.callback_query(FilterCB.filter(F.a == "clr"))
async def on_clear(
    cb: CallbackQuery,
    callback_data: FilterCB,
    state: FSMContext,
    session: AsyncSession,
    http_session: aiohttp.ClientSession | None = None,
):
    ctx = _ctx_from_callback(cb, state, session, http_session)
    if ctx is None or callback_data.f not in FIELD_BY_KEY:
        await cb.answer("Кнопка устарела")
        return
    await cb.answer(f"{FIELD_BY_KEY[callback_data.f].title}: очищено 🧹")
    await state.set_state(None)
    flt = (await _load(ctx)).without(callback_data.f)
    await _save(ctx, flt)
    await _show_for(ctx, callback_data.f, flt)


@router.callback_query(FilterCB.filter(F.a == "rlx"))
async def on_relax(
    cb: CallbackQuery,
    callback_data: FilterCB,
    state: FSMContext,
    session: AsyncSession,
    http_session: aiohttp.ClientSession | None = None,
):
    ctx = _ctx_from_callback(cb, state, session, http_session)
    if ctx is None or callback_data.f not in FIELD_BY_KEY:
        await cb.answer("Кнопка устарела")
        return
    await cb.answer("Готово ✨")
    flt = (await _load(ctx)).without(callback_data.f)
    await _save(ctx, flt)
    await dashboard(ctx, flt)


@router.callback_query(FilterCB.filter(F.a == "cur"))
async def on_currency(
    cb: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    http_session: aiohttp.ClientSession | None = None,
):
    ctx = _ctx_from_callback(cb, state, session, http_session)
    await cb.answer()
    if ctx is None:
        return
    flt = (await _load(ctx)).next_currency()
    await _save(ctx, flt)
    await dashboard(ctx, flt)


@router.callback_query(FilterCB.filter(F.a == "strict"))
async def on_strict(
    cb: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    http_session: aiohttp.ClientSession | None = None,
):
    ctx = _ctx_from_callback(cb, state, session, http_session)
    await cb.answer()
    if ctx is None:
        return
    flt = await _load(ctx)
    flt = replace(flt, strict_stack_filter=not flt.strict_stack_filter)
    await _save(ctx, flt)
    await dashboard(ctx, flt)


@router.callback_query(FilterCB.filter(F.a == "presets"))
async def on_presets(
    cb: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    http_session: aiohttp.ClientSession | None = None,
):
    ctx = _ctx_from_callback(cb, state, session, http_session)
    await cb.answer()
    if ctx is None:
        return
    text, kb = build_presets_view()
    await _render(ctx, text, kb)


@router.callback_query(FilterCB.filter(F.a == "pre"))
async def on_preset(
    cb: CallbackQuery,
    callback_data: FilterCB,
    state: FSMContext,
    session: AsyncSession,
    http_session: aiohttp.ClientSession | None = None,
):
    ctx = _ctx_from_callback(cb, state, session, http_session)
    if ctx is None or not 0 <= callback_data.i < len(PRESETS):
        await cb.answer("Кнопка устарела")
        return
    preset = PRESETS[callback_data.i]
    await cb.answer("Пресет применён ⚡")
    flt = preset.apply(await _load(ctx))
    await _save(ctx, flt)
    await dashboard(ctx, flt)


@router.callback_query(FilterCB.filter(F.a == "rst"))
async def on_reset(
    cb: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    http_session: aiohttp.ClientSession | None = None,
):
    ctx = _ctx_from_callback(cb, state, session, http_session)
    await cb.answer("Фильтры сброшены 🧹")
    if ctx is None:
        return
    flt = SearchFilters()
    await _save(ctx, flt)
    await dashboard(ctx, flt)


@router.callback_query(FilterCB.filter(F.a == "cpick"))
async def on_city_pick(
    cb: CallbackQuery,
    callback_data: FilterCB,
    state: FSMContext,
    session: AsyncSession,
    http_session: aiohttp.ClientSession | None = None,
):
    ctx = _ctx_from_callback(cb, state, session, http_session)
    if ctx is None:
        await cb.answer()
        return
    options = (await state.get_data()).get("city_options") or []
    if not 0 <= callback_data.i < len(options):
        await cb.answer("Список устарел, напиши город ещё раз", show_alert=True)
        return
    await cb.answer()
    await state.set_state(None)
    flt = replace(await _load(ctx), city=options[callback_data.i])
    await _save(ctx, flt)
    await dashboard(ctx, flt)


@router.callback_query(FilterCB.filter(F.a == "go"))
async def on_go(
    cb: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    http_session: aiohttp.ClientSession | None = None,
):
    await cb.answer("Ищу… 🔎")
    await state.clear()
    from bot.handlers.find_vacancies import finder  # ленивый импорт: без циклов

    await finder(
        cb.message,
        session=session,
        http_session=http_session,
        state=state,
        tg_id=cb.from_user.id,
    )


@router.callback_query(FilterCB.filter(F.a == "menu"))
async def on_menu(cb: CallbackQuery, state: FSMContext, session: AsyncSession):
    await cb.answer()
    await state.clear()
    from bot.services.main_menu import send_main_menu

    if cb.message is not None:
        await _try_delete(cb.message)
    await send_main_menu(event=cb, session=session, edit=False)


# ─────────── ввод текста ───────────


@router.message(F.text.startswith("добавить_стек:"))
async def on_inline_stack_pick(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    http_session: aiohttp.ClientSession | None = None,
):
    """Пользователь выбрал технологию в inline-подсказках («stack: ...») — прилетает такое сообщение."""
    tech = message.text.split(":", 1)[1].strip()
    await _try_delete(message)
    if not tech:
        return

    panel_id = (await state.get_data()).get("panel_id")
    if panel_id is None:
        sent = await message.answer("🎛 Загружаю…")
        panel_id = sent.message_id
        await state.update_data(panel_id=panel_id)
    ctx = Ctx(
        message.bot,
        message.chat.id,
        panel_id,
        state,
        session,
        message.from_user.id,
        http_session,
    )

    flt = (await _load(ctx)).add_items("user_tech_stack", [tech])
    await _save(ctx, flt)
    await list_view(ctx, "user_tech_stack", flt)


@router.message(FilterEdit.waiting_text, F.text, ~F.text.startswith("/"))
async def on_text(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    http_session: aiohttp.ClientSession | None = None,
):
    data = await state.get_data()
    key = data.get("field")
    panel_id = data.get("panel_id")
    if key not in FIELD_BY_KEY:
        await state.set_state(None)
        return

    if panel_id is None:
        sent = await message.answer("🎛 Загружаю…")
        panel_id = sent.message_id
        await state.update_data(panel_id=panel_id)
    ctx = Ctx(
        message.bot,
        message.chat.id,
        panel_id,
        state,
        session,
        message.from_user.id,
        http_session,
    )

    text = (message.text or "").strip()
    flt = await _load(ctx)
    try:
        if key == "city":
            options = _find_cities(text)
            if not options:
                raise FilterInputError(
                    "Не нашёл такой город. Попробуй полное название."
                )
            await state.update_data(city_options=options)
            await _try_delete(message)
            picker_text, picker_kb = build_city_picker(options)
            await _render(ctx, picker_text, picker_kb)
            return
        if key == "salary":
            low, high = parse_salary(text)
            flt = replace(flt, salary_from=low, salary_to=high)
        elif key == "specialization":
            flt = replace(flt, specialization=text[:100])
        elif key in LIST_FIELDS:
            items = parse_items(text)
            if not items:
                raise FilterInputError(
                    "Не разобрал ни одного слова. Пиши через запятую."
                )
            flt = flt.add_items(key, items)
    except FilterInputError as exc:
        await _try_delete(message)
        await prompt_view(ctx, key, notice=f"⚠️ {html.escape(str(exc))}")
        return

    await _save(ctx, flt)
    await state.set_state(None)
    await _try_delete(message)
    await _show_for(ctx, key, flt)
