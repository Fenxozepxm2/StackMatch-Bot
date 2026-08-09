# bot/services/city_mapper.py

from typing import ClassVar

import aiohttp


class CityMapper:
    _city_map: ClassVar[dict[str, str]] = {}
    _city_id_map: ClassVar[dict[str, str]] = {}
    _aliases: ClassVar[dict[str, str]] = {
        "питер": "Санкт-Петербург",
        "спб": "Санкт-Петербург",
        "мск": "Москва",
        "нск": "Новосибирск",
        "екб": "Екатеринбург",
        "нн": "Нижний Новгород",
        "кз": "Казань",
        "чел": "Челябинск",
        "омск": "Омск",
        "самара": "Самара",
        "рнд": "Ростов-на-Дону",
        "уфа": "Уфа",
        "крд": "Краснодар",
        "крс": "Красноярск",
        "врн": "Воронеж",
        "пнз": "Пенза",
        "пермь": "Пермь",
        "влг": "Волгоград",
        "срт": "Саратов",
        "тлт": "Тольятти",
        "тмн": "Тюмень",
        "иж": "Ижевск",
        "брн": "Барнаул",
        "у-у": "Улан-Удэ",
        "ирк": "Иркутск",
        "влд": "Владивосток",
        "хбр": "Хабаровск",
        "якутск": "Якутск",
        "махачкала": "Махачкала",
        "сев": "Севастополь",
        "сим": "Симферополь",
        "клд": "Калининград",
    }

    @classmethod
    async def load_cities(cls):
        """Загружает справочник городов с hh.ru и заполняет оба словаря."""
        url = "https://api.hh.ru/areas"
        async with aiohttp.ClientSession(trust_env=False) as session, session.get(url, ssl=False) as resp :
            # убрал проверку SSL aiohttp жалуется (мб из за отозванных SSl сертификатов)
            data = await resp.json()
            cls._city_map.clear()
            cls._city_id_map.clear()
            cls._recursive_parse(data)

    @classmethod
    def _recursive_parse(cls, areas):
        for area in areas:
            if area.get("areas"):
                cls._recursive_parse(area["areas"])
            else:
                name = area["name"]
                city_id = area["id"]
                cls._city_map[name.lower()] = name  # для поиска и отображения
                cls._city_id_map[name.lower()] = city_id  # для ID

    @classmethod
    def search_cities(cls, query: str, limit: int = 10) -> list[str]:
        """
        Ищет города, соответствующие запросу.
        Возвращает список названий (оригинальных) максимум limit штук.
        """
        query = query.lower().strip()
        if not query:
            return []

        # Проверяем синонимы
        if query in cls._aliases:
            canonical = cls._aliases[query]
            return [canonical] if canonical.lower() in cls._city_map else []

        # Ищем частичные совпадения по названиям
        results = []
        for city_lower, city_name in cls._city_map.items():
            if query in city_lower:
                results.append(city_name)
            if len(results) >= limit:
                break
        return results

    @classmethod
    def get_city_id(cls, city_name: str) -> str | None:
        """Возвращает ID города по его названию (для API hh.ru)."""
        return cls._city_id_map.get(city_name.lower())
