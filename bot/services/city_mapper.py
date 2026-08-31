# bot/services/city_mapper.py

from typing import ClassVar
import aiohttp

class CityMapper:
    _city_map: ClassVar[dict[str, str]] = {}
    _city_id_map: ClassVar[dict[str, str]] = {}
    _aliases: ClassVar[dict[str, str]] = {
        "питер": "Санкт-Петербург", "спб": "Санкт-Петербург", "мск": "Москва",
        "нск": "Новосибирск", "екб": "Екатеринбург", "нн": "Нижний Новгород",
        "кз": "Казань", "чел": "Челябинск", "омск": "Омск", "самара": "Самара",
        "рнд": "Ростов-на-Дону", "уфа": "Уфа", "крд": "Краснодар", "крс": "Красноярск",
        "врн": "Воронеж", "пнз": "Пенза", "пермь": "Пермь", "влг": "Волгоград",
        "срт": "Саратов", "тлт": "Тольятти", "тмн": "Тюмень", "иж": "Ижевск",
        "брн": "Барнаул", "у-у": "Улан-Удэ", "ирк": "Иркутск", "влд": "Владивосток",
        "хбр": "Хабаровск", "якутск": "Якутск", "махачкала": "Махачкала",
        "сев": "Севастополь", "сим": "Симферополь", "клд": "Калининград",
    }

    @classmethod
    async def load_cities(cls, http_session: aiohttp.ClientSession):
        """Загружает справочник городов с hh.ru через общую сессию."""
        url = "https://api.hh.ru/areas"
        async with http_session.get(url, ssl=False) as resp:
            data = await resp.json()
            cls._city_map.clear()
            cls._city_id_map.clear()
            cls._recursive_parse(data)

    @classmethod
    def _recursive_parse(cls, areas):
        for area in areas:
            sub_areas = area.get("areas", [])
            
            # Названия городов/регионов для сохранения
            name = area["name"]
            city_id = area["id"]

            if sub_areas:
                # Если есть подкатегории, сначала рекурсивно парсим их
                cls._recursive_parse(sub_areas)
                
                # ИСКЛЮЧЕНИЕ ДЛЯ КРУПНЫХ ГОРОДОВ:
                # В HH API Москва (id: 1) и Санкт-Петербург (id: 2) находятся на уровне областей
                # и содержат внутри себя районы/метро. Их нужно сохранить как города.
                if city_id in ["1", "2"]:
                    cls._city_map[name.lower()] = name
                    cls._city_id_map[name.lower()] = int(city_id)  # Сохраняем как int для надежности
            else:
                # Это конечный населенный пункт (город/поселок)
                cls._city_map[name.lower()] = name
                cls._city_id_map[name.lower()] = int(city_id)  # Сохраняем как int



    @classmethod
    def search_cities(cls, query: str, limit: int = 10) -> list[str]:
        """Умный поиск городов с приоритетом точного совпадения."""
        query = query.lower().strip()
        if not query or query == ".":
            return []

        if query in cls._aliases:
            canonical = cls._aliases[query]
            return [canonical] if canonical.lower() in cls._city_map else []

        exact_match = []
        starts_with_match = []
        contains_match = []

        for city_lower, city_name in cls._city_map.items():
            if city_lower == query:
                exact_match.append(city_name)
            elif city_lower.startswith(query):
                starts_with_match.append(city_name)
            elif query in city_lower:
                contains_match.append(city_name)

        starts_with_match.sort(key=len)
        contains_match.sort(key=len)


        combined_results = exact_match + starts_with_match + contains_match

        return list(dict.fromkeys(combined_results))[:limit]

    @classmethod
    def get_city_id(cls, city_name: str) -> str | None:
        """Возвращает ID города по его названию."""
        return cls._city_id_map.get(city_name.lower())
