import asyncio
import unittest

from bot.domain.search_filters import (
    PRESETS,
    FilterInputError,
    SearchFilters,
    format_int,
    parse_items,
    parse_salary,
    plural,
    relax_hints,
)


class FromDictTests(unittest.TestCase):
    def test_none_and_garbage(self):
        self.assertEqual(SearchFilters.from_dict(None), SearchFilters())
        self.assertEqual(SearchFilters.from_dict("oops"), SearchFilters())
        self.assertEqual(SearchFilters.from_dict({}), SearchFilters())

    def test_legacy_city_empty_list_becomes_empty_string(self):
        # старый виджет «очистить город» писал filters["city"] = []
        self.assertEqual(SearchFilters.from_dict({"city": []}).city, "")

    def test_unknown_options_are_dropped(self):
        flt = SearchFilters.from_dict({"exp": ["Без опыта", "Космонавт"]})
        self.assertEqual(flt.exp, ("Без опыта",))

    def test_exclude_aliases(self):
        self.assertEqual(
            SearchFilters.from_dict({"exclude_keywords": ["php"]}).exclude_key_words, ("php",)
        )
        self.assertEqual(
            SearchFilters.from_dict({"exclude_key_words": ["1c"]}).exclude_key_words, ("1c",)
        )

    def test_bad_numbers_and_currency(self):
        flt = SearchFilters.from_dict({"salary_from": "abc", "salary_to": -5, "currency": "XXX"})
        self.assertIsNone(flt.salary_from)
        self.assertIsNone(flt.salary_to)
        self.assertEqual(flt.currency, "RUR")

    def test_roundtrip(self):
        flt = SearchFilters(
            specialization="Python разработчик",
            city="Москва",
            salary_from=150_000,
            user_tech_stack=("Python", "Docker"),
            exp=("Без опыта",),
            exclude_key_words=("PHP",),
        )
        self.assertEqual(SearchFilters.from_dict(flt.to_dict()), flt)

    def test_dedup_is_case_insensitive(self):
        flt = SearchFilters.from_dict({"user_tech_stack": ["Python", "python", " PYTHON "]})
        self.assertEqual(flt.user_tech_stack, ("Python",))


class MutationTests(unittest.TestCase):
    def test_toggle_keeps_catalog_order_and_is_immutable(self):
        base = SearchFilters()
        a = base.toggle("exp", "Более 6").toggle("exp", "Без опыта")
        self.assertEqual(a.exp, ("Без опыта", "Более 6"))
        self.assertEqual(base.exp, ())  # исходный объект не тронут
        self.assertEqual(a.toggle("exp", "Без опыта").exp, ("Более 6",))

    def test_toggle_unknown_option(self):
        with self.assertRaises(ValueError):
            SearchFilters().toggle("exp", "нет такого")

    def test_add_and_remove_items(self):
        flt = SearchFilters().add_items("user_tech_stack", ["Python", "Go"])
        flt = flt.add_items("user_tech_stack", ["python", "Rust"])
        self.assertEqual(flt.user_tech_stack, ("Python", "Go", "Rust"))
        self.assertEqual(flt.remove_at("user_tech_stack", 1).user_tech_stack, ("Python", "Rust"))
        self.assertEqual(flt.remove_at("user_tech_stack", 99), flt)

    def test_without(self):
        flt = SearchFilters(city="Москва", salary_from=1, salary_to=2, exp=("Без опыта",))
        self.assertFalse(flt.without("salary").is_set("salary"))
        self.assertEqual(flt.without("city").city, "")
        self.assertEqual(flt.without("exp").exp, ())

    def test_currency_cycle(self):
        c = SearchFilters()
        self.assertEqual(
            [c.currency, (c := c.next_currency()).currency, (c := c.next_currency()).currency,
             c.next_currency().currency],
            ["RUR", "USD", "EUR", "RUR"],
        )

    def test_active_count(self):
        self.assertEqual(SearchFilters().active_count, 0)
        self.assertEqual(SearchFilters(city="X", salary_from=1, exp=("Без опыта",)).active_count, 3)


class QueryTests(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(SearchFilters().build_text_query(), "")

    def test_stack_is_or_not_and(self):
        q = SearchFilters(user_tech_stack=("Python", "FastAPI")).build_text_query()
        self.assertEqual(q, '("Python" OR "FastAPI")')

    def test_full_query(self):
        q = SearchFilters(
            specialization="Python разработчик",
            user_tech_stack=("Python", "C++"),
            find_key_words=("REST API",),
            exclude_key_words=("PHP", "1С"),
        ).build_text_query()
        self.assertEqual(
            q,
            'NAME:(Python разработчик) AND ("Python" OR "C++") AND "REST API" NOT "PHP" NOT "1С"',
        )

    def test_exclude_alone_is_not_sent(self):
        self.assertEqual(SearchFilters(exclude_key_words=("PHP",)).build_text_query(), "")

    def test_query_syntax_chars_are_sanitized(self):
        q = SearchFilters(specialization='Py"thon (dev)').build_text_query()
        self.assertNotIn('"', q)
        self.assertEqual(q, "NAME:(Py thon dev)")


class HhParamsTests(unittest.TestCase):
    area_of = staticmethod(lambda name: {"Москва": 1, "Санкт-Петербург": 2}.get(name))

    def test_minimal(self):
        self.assertEqual(SearchFilters().to_hh_params(), {"per_page": 100, "page": 0})

    def test_page_is_passed(self):
        self.assertEqual(SearchFilters().to_hh_params(page=3)["page"], 3)

    def test_city_and_choices(self):
        p = SearchFilters(
            city="Москва", exp=("Без опыта", "от 1 до 3"), schedule=("Сменный",)
        ).to_hh_params(area_of=self.area_of)
        self.assertEqual(p["area"], 1)
        self.assertEqual(p["experience"], ["noExperience", "between1And3"])
        self.assertEqual(p["schedule"], ["shift"])

    def test_remote_from_schedule_and_workformat_merge_without_duplicates(self):
        p = SearchFilters(schedule=("Удалённо",), workformat=("Удалённо",)).to_hh_params()
        self.assertEqual(p["schedule"], ["remote"])

    def test_remote_drops_area(self):
        p = SearchFilters(city="Москва", workformat=("Удалённо",)).to_hh_params(area_of=self.area_of)
        self.assertNotIn("area", p)

    def test_options_without_hh_value_are_not_sent(self):
        p = SearchFilters(workformat=("Гибрид", "Разъездной")).to_hh_params()
        self.assertNotIn("schedule", p)

    def test_unknown_city_is_skipped(self):
        self.assertNotIn("area", SearchFilters(city="Нигдеград").to_hh_params(area_of=self.area_of))

    def test_salary(self):
        p = SearchFilters(salary_from=150_000, salary_to=300_000, currency="USD").to_hh_params()
        self.assertEqual((p["salary"], p["only_with_salary"], p["currency"]), (150_000, "true", "USD"))
        self.assertEqual(SearchFilters(salary_to=90_000).to_hh_params()["salary"], 90_000)
        self.assertNotIn("currency", SearchFilters().to_hh_params())


class ParseSalaryTests(unittest.TestCase):
    def test_cases(self):
        cases = {
            "150000": (150_000, None),
            "от 150к": (150_000, None),
            "до 300 000": (None, 300_000),
            "100к - 200к": (100_000, 200_000),
            "70 000 – 120 000": (70_000, 120_000),
            "70000-120000": (70_000, 120_000),
            "от 70000 до 120000": (70_000, 120_000),
            "1.5к": (1_500, None),
            "200 K": (200_000, None),
            "от 80 тыс": (80_000, None),
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(parse_salary(text), expected)

    def test_errors(self):
        for bad in ("", "много", "200000 - 100000", "99999999999"):
            with self.subTest(bad=bad), self.assertRaises(FilterInputError):
                parse_salary(bad)

    def test_word_starting_with_k_is_not_a_multiplier(self):
        self.assertEqual(parse_salary("100 компания"), (100, None))


class ParseItemsTests(unittest.TestCase):
    def test_split_and_clean(self):
        self.assertEqual(
            parse_items("Python, FastAPI;  Docker\nGit,, python"),
            ["Python", "FastAPI", "Docker", "Git"],
        )

    def test_dot_net_survives(self):
        self.assertEqual(parse_items(".NET, Node.js"), [".NET", "Node.js"])

    def test_too_long_item_dropped(self):
        self.assertEqual(parse_items("a" * 41 + ", ok"), ["ok"])


class FormatTests(unittest.TestCase):
    def test_plural(self):
        forms = ("вакансия", "вакансии", "вакансий")
        got = {n: plural(n, forms) for n in (0, 1, 2, 5, 11, 12, 21, 22, 25, 111, 1243)}
        self.assertEqual(
            got,
            {0: "вакансий", 1: "вакансия", 2: "вакансии", 5: "вакансий", 11: "вакансий",
             12: "вакансий", 21: "вакансия", 22: "вакансии", 25: "вакансий", 111: "вакансий",
             1243: "вакансии"},
        )

    def test_format_int(self):
        self.assertEqual(format_int(1243), "1\u00a0243")
        self.assertEqual(format_int(12), "12")

    def test_salary_text(self):
        self.assertEqual(SearchFilters(salary_from=150_000).salary_text(), "от 150\u00a0000 ₽")
        self.assertEqual(SearchFilters(salary_to=9, currency="USD").salary_text(), "до 9 $")
        self.assertEqual(
            SearchFilters(salary_from=1, salary_to=2, currency="EUR").salary_text(), "1 – 2 €"
        )


class PresetTests(unittest.TestCase):
    def test_preset_keeps_city_and_salary(self):
        base = SearchFilters(city="Москва", salary_from=100_000, exp=("Более 6",))
        out = PRESETS[0].apply(base)
        self.assertEqual((out.city, out.salary_from), ("Москва", 100_000))
        self.assertEqual(out.exp, ("Без опыта", "от 1 до 3"))
        self.assertIn("FastAPI", out.user_tech_stack)

    def test_all_presets_use_valid_options(self):
        # если кто-то опечатается в пресете, from_dict молча выкинет опцию — ловим это тут
        for p in PRESETS:
            with self.subTest(preset=p.key):
                flt = p.apply(SearchFilters())
                self.assertEqual(SearchFilters.from_dict(flt.to_dict()), flt)


class RelaxTests(unittest.TestCase):
    def test_hints_follow_priority_and_skip_zero(self):
        flt = SearchFilters(
            specialization="X", city="Москва", exp=("Без опыта",), exclude_key_words=("php",)
        )

        async def counter(f: SearchFilters):
            return {  # сколько вакансий будет без соответствующего фильтра
                "exclude_key_words": 0,
                "exp": 340,
                "city": 1200,
                "specialization": 99999,
            }[next(k for k in ("exclude_key_words", "exp", "city", "specialization")
                   if not f.is_set(k))]

        hints = asyncio.run(relax_hints(flt, counter, limit=2))
        self.assertEqual(hints, [("exp", 340), ("city", 1200)])

    def test_counter_errors_are_ignored(self):
        flt = SearchFilters(city="Москва", exp=("Без опыта",))

        async def counter(f):
            if not f.is_set("city"):
                raise RuntimeError("hh упал")
            return None

        self.assertEqual(asyncio.run(relax_hints(flt, counter)), [])

    def test_no_active_filters(self):
        async def counter(f):
            return 5

        self.assertEqual(asyncio.run(relax_hints(SearchFilters(), counter)), [])


if __name__ == "__main__":
    unittest.main()