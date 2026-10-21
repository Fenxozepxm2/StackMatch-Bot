"""
Доменный слой: поисковые фильтры вакансий.

Ничего не знает про aiogram, SQLAlchemy и aiohttp — только чистый Python.
Поэтому всё здесь тестируется без бота и без базы (см. tests/test_search_filters.py).

Главные идеи:
  * SearchFilters — неизменяемый value object. Вместо `filters["exp"].append(...)`
    в словаре из FSM (откуда берутся баги с рассинхроном) — `flt.toggle("exp", "Без опыта")`,
    который возвращает НОВЫЙ объект.
  * Хранение в БД не меняется: to_dict()/from_dict() дают тот же JSON, что и раньше
    (ключи user_tech_stack, strict_stack_filter, exp, ...), старые записи читаются без миграции.
  * Все справочники (опыт, график, формат) описаны один раз декларативно —
    из них же строится и UI, и запрос к hh. Новый фильтр = несколько строк.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, replace
from typing import Any, Awaitable, Callable

# ───────────────────────────── Справочники ─────────────────────────────


@dataclass(frozen=True)
class Option:
    label: str                    # то, что видит и хранит пользователь
    hh_value: str | None = None   # значение для API hh; None -> в запрос не уходит
    hh_param: str | None = None   # если параметр отличается от ChoiceSpec.hh_param


@dataclass(frozen=True)
class ChoiceSpec:
    key: str
    hh_param: str
    options: tuple[Option, ...]

    def labels(self) -> tuple[str, ...]:
        return tuple(o.label for o in self.options)


EXPERIENCE = ChoiceSpec(
    key="exp",
    hh_param="experience",
    options=(
        Option("Без опыта", "noExperience"),
        Option("от 1 до 3", "between1And3"),
        Option("от 3 до 6", "between3And6"),
        Option("Более 6", "moreThan6"),
    ),
)

SCHEDULE = ChoiceSpec(
    key="schedule",
    hh_param="schedule",
    options=(
        Option("Сменный", "shift"),
        Option("Удалённо", "remote"),
        Option("Гибкий", "flexible"),
        Option("Полный день", "fullDay"),
        Option("Вахта", "flyInFlyOut"),
    ),
)

# ВАЖНО: раньше в API уходил только "Удалённо" (как schedule=remote), остальные форматы
# молча игнорировались. Это поведение сохранено. Чтобы включить остальные — найди
# параметр в https://api.hh.ru/openapi/redoc и впиши, например:
#     Option("Гибрид", "HYBRID", hh_param="work_format")
# Больше ничего менять не нужно: UI и запрос подхватят сами.
WORKFORMAT = ChoiceSpec(
    key="workformat",
    hh_param="schedule",
    options=(
        Option("На месте работодателя"),
        Option("Удалённо", "remote"),
        Option("Гибрид"),
        Option("Разъездной"),
    ),
)

CHOICES: dict[str, ChoiceSpec] = {s.key: s for s in (EXPERIENCE, SCHEDULE, WORKFORMAT)}
LIST_FIELDS = ("user_tech_stack", "find_key_words", "exclude_key_words")

# Все «фильтры» с точки зрения пользователя (salary объединяет from/to)
FILTER_KEYS = (
    "specialization",
    "city",
    "salary",
    "user_tech_stack",
    "exp",
    "schedule",
    "workformat",
    "find_key_words",
    "exclude_key_words",
)

# В каком порядке предлагать «убери вот это, и вакансии появятся»:
# сначала то, чем пользователю меньше всего жалко пожертвовать.
RELAX_ORDER = (
    "exclude_key_words",
    "find_key_words",
    "workformat",
    "schedule",
    "exp",
    "salary",
    "city",
    "user_tech_stack",
    "specialization",
)

CURRENCIES = ("RUR", "USD", "EUR")
CURRENCY_SIGN = {"RUR": "₽", "USD": "$", "EUR": "€"}

# Старые версии виджета «исключить» могли писать в другой ключ — читаем все варианты.
_EXCLUDE_KEYS = ("exclude_key_words", "exclude_keywords", "exclude")

MAX_ITEMS = 30
MAX_ITEM_LEN = 40


class FilterInputError(ValueError):
    """Ошибка пользовательского ввода. Текст можно показывать пользователю как есть."""


# ───────────────────────────── Вспомогательное ─────────────────────────────


def format_int(n: int) -> str:
    """1243 -> '1 243' (неразрывные пробелы, чтобы число не рвалось на переносе)."""
    return f"{n:,}".replace(",", "\u00a0")


def plural(n: int, forms: tuple[str, str, str]) -> str:
    """plural(1, ('вакансия','вакансии','вакансий')) -> 'вакансия'."""
    n10, n100 = n % 10, n % 100
    if n10 == 1 and n100 != 11:
        return forms[0]
    if 2 <= n10 <= 4 and not 12 <= n100 <= 14:
        return forms[1]
    return forms[2]


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool) or value in (None, ""):
        return None
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _clean_list(value: Any, allowed: tuple[str, ...] | None = None) -> tuple[str, ...]:
    if isinstance(value, str):
        value = re.split(r"[,;\n]", value)
    if not isinstance(value, (list, tuple)):
        return ()
    seen: set[str] = set()
    out: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        item = re.sub(r"\s+", " ", item).strip()
        if not item or (allowed is not None and item not in allowed):
            continue
        folded = item.casefold()
        if folded in seen:
            continue
        seen.add(folded)
        out.append(item)
    return tuple(out[:MAX_ITEMS])


def _q(term: str) -> str:
    """Терм для языка запросов hh"""
    cleaned = re.sub(r'["()]', " ", term)
    return '"' + re.sub(r"\s+", " ", cleaned).strip() + '"'


def _any_of(terms: tuple[str, ...]) -> str:
    return "(" + " OR ".join(_q(t) for t in terms) + ")"


# ───────────────────────────── Модель ─────────────────────────────


@dataclass(frozen=True)
class SearchFilters:
    specialization: str = ""
    city: str = ""
    salary_from: int | None = None
    salary_to: int | None = None
    currency: str = "RUR"
    user_tech_stack: tuple[str, ...] = ()
    strict_stack_filter: bool = False
    exp: tuple[str, ...] = ()
    schedule: tuple[str, ...] = ()
    workformat: tuple[str, ...] = ()
    find_key_words: tuple[str, ...] = ()
    exclude_key_words: tuple[str, ...] = ()

    # ── (де)сериализация ──

    @classmethod
    def from_dict(cls, raw: Any) -> SearchFilters:
        """Терпимо читает что угодно: None, пустой dict, старые записи, мусор в полях."""
        raw = raw if isinstance(raw, dict) else {}

        exclude: Any = ()
        for key in _EXCLUDE_KEYS:
            if raw.get(key):
                exclude = raw[key]
                break

        currency = raw.get("currency")
        spec = raw.get("specialization")
        city = raw.get("city")
        return cls(
            specialization=spec.strip() if isinstance(spec, str) else "",
            city=city.strip() if isinstance(city, str) else "",
            salary_from=_as_int(raw.get("salary_from")),
            salary_to=_as_int(raw.get("salary_to")),
            currency=currency if currency in CURRENCIES else "RUR",
            user_tech_stack=_clean_list(raw.get("user_tech_stack")),
            strict_stack_filter=bool(raw.get("strict_stack_filter", False)),
            exp=_clean_list(raw.get("exp"), EXPERIENCE.labels()),
            schedule=_clean_list(raw.get("schedule"), SCHEDULE.labels()),
            workformat=_clean_list(raw.get("workformat"), WORKFORMAT.labels()),
            find_key_words=_clean_list(raw.get("find_key_words")),
            exclude_key_words=_clean_list(exclude),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "specialization": self.specialization,
            "city": self.city,
            "salary_from": self.salary_from,
            "salary_to": self.salary_to,
            "currency": self.currency,
            "user_tech_stack": list(self.user_tech_stack),
            "strict_stack_filter": self.strict_stack_filter,
            "exp": list(self.exp),
            "schedule": list(self.schedule),
            "workformat": list(self.workformat),
            "find_key_words": list(self.find_key_words),
            "exclude_key_words": list(self.exclude_key_words),
        }

    # ── состояние ──

    def is_set(self, key: str) -> bool:
        if key == "salary":
            return bool(self.salary_from or self.salary_to)
        if key not in FILTER_KEYS:
            raise KeyError(key)
        return bool(getattr(self, key))

    @property
    def active_count(self) -> int:
        return sum(1 for k in FILTER_KEYS if self.is_set(k))

    def without(self, key: str) -> SearchFilters:
        if key == "salary":
            return replace(self, salary_from=None, salary_to=None)
        if key not in FILTER_KEYS:
            raise KeyError(key)
        empty: Any = "" if isinstance(getattr(self, key), str) else ()
        return replace(self, **{key: empty})

    # ── изменения (всегда возвращают новый объект) ──

    def toggle(self, key: str, label: str) -> SearchFilters:
        spec = CHOICES[key]
        if label not in spec.labels():
            raise ValueError(f"unknown option {label!r} for {key}")
        chosen = set(getattr(self, key))
        chosen.symmetric_difference_update({label})
        return replace(self, **{key: tuple(l for l in spec.labels() if l in chosen)})

    def add_items(self, key: str, items: list[str]) -> SearchFilters:
        if key not in LIST_FIELDS:
            raise KeyError(key)
        return replace(self, **{key: _clean_list([*getattr(self, key), *items])})

    def remove_at(self, key: str, index: int) -> SearchFilters:
        if key not in LIST_FIELDS:
            raise KeyError(key)
        current = list(getattr(self, key))
        if not 0 <= index < len(current):
            return self
        del current[index]
        return replace(self, **{key: tuple(current)})

    def next_currency(self) -> SearchFilters:
        nxt = CURRENCIES[(CURRENCIES.index(self.currency) + 1) % len(CURRENCIES)]
        return replace(self, currency=nxt)

    # ── представление ──

    def salary_text(self) -> str:
        sign = CURRENCY_SIGN.get(self.currency, self.currency)
        if self.salary_from and self.salary_to:
            return f"{format_int(self.salary_from)} – {format_int(self.salary_to)} {sign}"
        if self.salary_from:
            return f"от {format_int(self.salary_from)} {sign}"
        if self.salary_to:
            return f"до {format_int(self.salary_to)} {sign}"
        return ""

    def describe(self) -> list[tuple[str, str]]:
        """Только заданные фильтры: [(key, значение)]."""
        out: list[tuple[str, str]] = []
        if self.specialization:
            out.append(("specialization", self.specialization))
        if self.city:
            out.append(("city", self.city))
        if self.is_set("salary"):
            out.append(("salary", self.salary_text()))
        for key in (
            "user_tech_stack",
            "exp",
            "schedule",
            "workformat",
            "find_key_words",
            "exclude_key_words",
        ):
            values = getattr(self, key)
            if values:
                out.append((key, ", ".join(values)))
        return out

    # ── запрос к hh.ru ──

    def build_text_query(self) -> str:
        """
        Язык запросов hh (поле `text`):
          направление      -> NAME:(...)                 в названии вакансии
          мой стек         -> ("A" OR "B" OR ...)        ЛЮБАЯ технология (дальше ранжирует скоринг)
          ключевые слова   -> "A" AND "B"                КАЖДОЕ слово должно встретиться
          исключить        -> NOT "X"                    такого слова быть не должно

        """
        positive: list[str] = []
        if self.specialization:
            spec = re.sub(r'["()]', " ", self.specialization)
            spec = re.sub(r"\s+", " ", spec).strip()
            if spec:
                positive.append(f"NAME:({spec})")
        if self.user_tech_stack:
            positive.append(_any_of(self.user_tech_stack))
        positive.extend(_q(w) for w in self.find_key_words)
        if not positive:
            return ""
        query = " AND ".join(positive)
        for word in self.exclude_key_words:
            query += f" NOT {_q(word)}"
        return query

    def to_hh_params(
        self,
        page: int = 0,
        per_page: int = 100,
        area_of: Callable[[str], int | str | None] | None = None,
    ) -> dict[str, Any]:
        """
        area_of — функция «название города -> id региона hh» (CityMapper.get_city_id).
        Передаётся снаружи, чтобы домен не зависел от инфраструктуры.
        """
        params: dict[str, Any] = {}

        query = self.build_text_query()
        if query:
            params["text"] = query

        collected: dict[str, list[str]] = {}
        for spec in CHOICES.values():
            selected = getattr(self, spec.key)
            for opt in spec.options:
                if opt.label in selected and opt.hh_value:
                    bucket = collected.setdefault(opt.hh_param or spec.hh_param, [])
                    if opt.hh_value not in bucket:
                        bucket.append(opt.hh_value)
        params.update(collected)

        if self.city and area_of is not None:
            area = area_of(self.city)
            if area:
                params["area"] = int(area)

        if "remote" in params.get("schedule", []):
            params.pop("area", None)

        amount = self.salary_from or self.salary_to
        if amount:
            params["salary"] = amount
            params["only_with_salary"] = "true"
            params["currency"] = self.currency

        params["per_page"] = per_page
        params["page"] = page
        return params


# ───────────────────────────── Парсеры пользовательского ввода ─────────────────────────────

_SALARY_NUMBER = re.compile(
    r"(\d+(?:[ \u00a0]\d{3})*)(?:[.,](\d+))?\s*(?:(к|k|тыс)(?![a-zа-яё]))?",
    re.IGNORECASE,
)


def parse_salary(text: str) -> tuple[int | None, int | None]:
    """
    '150000' | 'от 150к' | 'до 300 000' | '100к - 200к' | '70 000 – 120 000'
    -> (salary_from, salary_to)
    """
    t = (text or "").lower().replace("\u00a0", " ")
    t = re.sub(r"[–—−]", "-", t)

    numbers: list[int] = []
    for m in _SALARY_NUMBER.finditer(t):
        whole = re.sub(r"[ ]", "", m.group(1))
        value = float(f"{whole}.{m.group(2)}" if m.group(2) else whole)
        if m.group(3):
            value *= 1000
        numbers.append(int(round(value)))

    if not numbers:
        raise FilterInputError("Не нашёл цифр. Пример: 150000, от 150к или 100к - 200к")
    if any(n < 1 or n > 10_000_000 for n in numbers):
        raise FilterInputError("Сумма выглядит нереалистично, проверь число")

    if len(numbers) == 1:
        if re.search(r"\bдо\b", t) and not re.search(r"\bот\b", t):
            return None, numbers[0]
        return numbers[0], None

    low, high = numbers[0], numbers[1]
    if low > high:
        raise FilterInputError("Минимум не может быть больше максимума")
    return low, high


def parse_items(text: str) -> list[str]:
    """'Python, FastAPI; Docker\\nGit' -> ['Python', 'FastAPI', 'Docker', 'Git']"""
    items: list[str] = []
    seen: set[str] = set()
    for chunk in re.split(r"[,;\n]", text or ""):
        item = re.sub(r"\s+", " ", chunk).strip(" \t,;")
        if not item or len(item) > MAX_ITEM_LEN or item.casefold() in seen:
            continue
        seen.add(item.casefold())
        items.append(item)
    return items


# ───────────────────────────── Пресеты ─────────────────────────────


@dataclass(frozen=True)
class Preset:
    key: str
    title: str
    specialization: str
    stack: tuple[str, ...]
    exp: tuple[str, ...]
    schedule: tuple[str, ...] = ()
    workformat: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()

    def apply(self, flt: SearchFilters) -> SearchFilters:
        """Меняет «профессиональную» часть, а город, зарплату и валюту оставляет."""
        return replace(
            flt,
            specialization=self.specialization,
            user_tech_stack=self.stack,
            exp=self.exp,
            schedule=self.schedule,
            workformat=self.workformat,
            exclude_key_words=self.exclude,
        )


PRESETS: tuple[Preset, ...] = (
    Preset(
        "py_junior", "🐍 Python Junior · удалённо", "Python разработчик",
        ("Python", "FastAPI", "PostgreSQL", "Docker", "Git"),
        ("Без опыта", "от 1 до 3"), schedule=("Удалённо",), workformat=("Удалённо",),
    ),
    Preset(
        "backend_mid", "⚙️ Backend Middle", "Backend разработчик",
        ("Python", "Django", "PostgreSQL", "Redis", "Docker"),
        ("от 3 до 6",),
    ),
    Preset(
        "frontend", "⚛️ Frontend · React", "Frontend разработчик",
        ("React", "TypeScript", "JavaScript", "HTML", "CSS"),
        ("от 1 до 3",),
    ),
    Preset(
        "qa_auto", "🧪 QA Automation", "QA инженер",
        ("Python", "Pytest", "Selenium", "SQL", "Postman"),
        ("от 1 до 3",),
    ),
)


# ───────────────────────────── Подсчёт вакансий и подсказки ─────────────────────────────

Counter = Callable[[SearchFilters], Awaitable["int | None"]]


async def relax_hints(
    flt: SearchFilters, counter: Counter, limit: int = 3
) -> list[tuple[str, int]]:
    """
    Для каждого заданного фильтра считает, сколько вакансий было бы БЕЗ него,
    и возвращает [(ключ_фильтра, сколько_станет)] только там, где результат > 0.

    counter инжектится снаружи
    """
    keys = [k for k in RELAX_ORDER if flt.is_set(k)]
    if not keys:
        return []
    counts = await asyncio.gather(
        *(counter(flt.without(k)) for k in keys), return_exceptions=True
    )
    hints = [
        (k, n)
        for k, n in zip(keys, counts)
        if isinstance(n, int) and not isinstance(n, bool) and n > 0
    ]
    return hints[:limit]