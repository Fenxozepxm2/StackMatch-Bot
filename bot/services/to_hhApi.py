import asyncio
import re
from typing import Any

import aiohttp
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import *
from bot.db.repos.repo_filters import get_user_filters
from bot.db.repos.repo_vacancies import get_viewed_vacancy_ids
from bot.services.city_mapper import CityMapper

# Маппинг для опыта работы
EXPERIENCE_MAP = {
    "Без опыта": "noExperience",
    "от 1 до 3": "between1And3",
    "от 3 до 6": "between3And6",
    "Более 6": "moreThan6"
}

# Маппинг для графика работы 
SCHEDULE_MAP = {
    "Сменный": "shift",
    "Удалённо": "remote",
    "Гибкий": "flexible",  
    "Полный день": "fullDay"
}

# Маппинг для формата работы 
WORKFORMAT_MAP = {
    "Удалённо": "remote",
    "На месте работодателя": "office",
    "Гибрид": "hybrid",
    "Разъездной": "mobile"
}


async def filters_to_params_hh_api(tg_id: int, session: AsyncSession, page: int = 0):
    params: dict[str, any] = {}
    

    user_filters = await get_user_filters(session,tg_id)

    # для поиска (text)
    search_parts = []
    if user_filters.get("specialization"):
        search_parts.append(user_filters["specialization"])
    if user_filters.get("find_key_words"):
        search_parts.extend(user_filters["find_key_words"])
    if search_parts:
        params["text"] = " ".join(search_parts)

    # для региона (area)
    city = user_filters.get("city")
    if city:
        city_id = CityMapper.get_city_id(city)
        if city_id:
            params["area"] = city_id


    # ЗАРПЛАТА (salary)
    # Если есть обе границы, передаем ТОЛЬКО salary_from и salary_to
    if user_filters.get("salary_from") and user_filters.get("salary_to"):
        params["salary_from"] = int(user_filters["salary_from"])
        params["salary_to"] = int(user_filters["salary_to"])
        params["only_with_salary"] = True
    # Если есть только нижняя граница
    elif user_filters.get("salary_from"):
        params["salary"] = int(user_filters["salary_from"])
        params["only_with_salary"] = True
    # Если есть только верхняя граница
    elif user_filters.get("salary_to"):
        params["salary"] = int(user_filters["salary_to"])
        params["only_with_salary"] = True
    else:
        params["only_with_salary"] = False




    # опыт работы (experience)
    if user_filters.get("exp"):
        exp_val = user_filters.get("exp")
        for i in exp_val:
            if i in EXPERIENCE_MAP:
                params["experience"] = []
                params["experience"].append(EXPERIENCE_MAP[i])
    
    

    # График работы (schedule)
    # Обработка графиков работы пользователя (5/2, 2/2 и т.д.) !!!!доработать!!!!
    params["schedule"] = []
    if user_filters.get("schedule"):
        sched_val = user_filters.get("schedule")
        for i in sched_val:
            # ОБЪЕДИНИЛИ ЧЕРЕЗ and
            if i in SCHEDULE_MAP and SCHEDULE_MAP[i] not in params["schedule"]:
                params["schedule"].append(SCHEDULE_MAP[i])

    # Обработка формата работы (Удалённо)
    if user_filters.get("workformat"):
        work_formats = user_filters.get("workformat")
        # ОБЪЕДИНИЛИ ЧЕРЕЗ and
        if "Удалённо" in work_formats and "remote" not in params["schedule"]:
            params["schedule"].append("remote")


    # Если список schedule остался пустым, удаляем ключ, чтобы не отправлять пустой параметр в API
    if not params["schedule"]:
        del params["schedule"]


    # ТУТ КОРОЧЕ СДЕЛАТЬ ОБРАБОТКУ ИСКЛЮЧАЮЩИЙ СЛОВ, ПОКА ЧТО ВПАДЛУ


    params["order_by"] = "publication_time"

    params["per_page"] = 50  # Берём оптимальный размер пачки (максимум у HH — 100)
    params["page"] = page    # Теперь страница динамическая

    # Очищаем от пустых значений
    params = {k: v for k, v in params.items() if v is not None and v != "" and v != []}

    # ИСПРАВЛЕНИЕ ДЛЯ aiohttp: Конвертируем True/False в строки "true"/"false"
    for k, v in params.items():
        if isinstance(v, bool):
            params[k] = "true" if v else "false"

    print(params)

    return params
        



class HHAPI:
    BASE_URL = "https://api.hh.ru"
    
    @staticmethod
    async def format_vacancies(vac: dict, score: int = 0) -> dict: 
        id_vac = vac.get("id")
        name = vac.get("name")
        vac_url = vac.get("alternate_url")
        published_at = vac.get("published_at")
        created_at = vac.get("created_at")
        
        exp = vac.get("experience", {}).get("name", "не требуется")
        
        salary_data = vac.get("salary")
        salary_str = "не указана"
        if salary_data:
            sal_from = f"от {salary_data.get('from')}" if salary_data.get('from') else ""
            sal_to = f"до {salary_data.get('to')}" if salary_data.get('to') else ""
            currency = salary_data.get('currency', '')
            salary_str = f"{sal_from} {sal_to} {currency}".strip()
        
        city = vac.get("area", {}).get("name")
        id_employer = vac.get("employer", {}).get("id")
        name_employer = vac.get("employer", {}).get("name")

        vaca = {
            "id_vac": id_vac,
            "name": name,
            "vac_url": vac_url,
            "published_at": published_at,
            "created_at": created_at,
            "exp": exp,
            "salary": salary_str,
            "city": city,
            "id_employer": id_employer,
            "name_employer": name_employer,
            "score": score 
        }

        accredited_it_employer = vac.get("employer", {}).get("accredited_it_employer")
        if accredited_it_employer:
            vaca["accredited_it_employer"] = accredited_it_employer

        address = vac.get("address")
        if address and address.get("city"):
            vaca["address"] = address.get("city")

        snippet = vac.get("snippet", {}) or {}
        raw_requirement = snippet.get("requirement", "не указаны") or "не указаны"
        raw_responsibility = snippet.get("responsibility", "не указаны") or "не указаны"

        requirement = re.sub(r'</?highlight>', lambda m: '<u>' if m.group(0) == '<highlight>' else '</u>', raw_requirement)
        responsibility = re.sub(r'</?highlight>', lambda m: '<u>' if m.group(0) == '<highlight>' else '</u>', raw_responsibility)

        it_badge = " <mark>[IT-аккредитованная компания]</mark>" if vaca.get("accredited_it_employer") else ""
        
        score_color = "🟢" if score > 0 else ("🔴" if score < 0 else "⚪️")
        score_text = f"{score_color} Рейтинг соответствия: {score:+d}" # +d выведет знак плюс, например +4 или -5

        html_content = (
            f"<h1>💼 {vaca['name']}</h1>"
            f"<hr>"
            f"<p>🏢 <b>Компания:</b> {vaca['name_employer']}{it_badge}</p>"
            f"<p>💰 <b>Зарплата:</b> {vaca['salary']}</p>"
            f"<p>📍 <b>Город:</b> {vaca['city']}</p>"
            f"<p>⏳ <b>Опыт:</b> {vaca['exp']}</p>"
            f"<br>"
            f"<p>📝 <b>Требования:</b>\n<i>{requirement}</i></p>"
            f"<br>"
            f"<p>🛠 <b>Обязанности:</b>\n<i>{responsibility}</i></p>"
            f"<br>"
            f"<p>🔗 <a href='{vaca['vac_url']}'>Открыть вакансию на HH.ru</a></p>"
            f"<br>"
            f"<footer>{score_text}</footer>" 
        )
        
        vaca["html_content"] = html_content
        return vaca





    @staticmethod
    async def clean_html(text: str) -> str:
        if not text:
            return ""
        # Удаляем все HTML-теги
        text = re.sub(r'<[^>]+>', '', text)
        # Схлопываем множественные пробелы в один
        text = re.sub(r'\s+', ' ', text).strip()
        return text


    @staticmethod
    async def check_skill_with_context(text: str, skill: str) -> bool:
        """
        Проверяет наличие навыка в тексте с защитой от ложных срабатываний.
        Возвращает True, если навык найден и перед ним нет отрицания.
        """
        text = text.lower()
        skill_escaped = re.escape(skill.lower())
        
        pattern = rf'\b{skill_escaped}\b'
        
        # 1. Проверяем, есть ли вообще это слово в тексте
        if not re.search(pattern, text):
            return False
            
        # 2. ЗАЩИТА ОТ ЛОЖНЫХ СРАБАТЫВАНИЙ (Контекстный фильтр)
        # Ищем, нет ли перед нашим навыком стоп-слов в радиусе 3-4 слов
        # Пример: "не работаем с PHP", "без знания PHP"
        negative_pattern = rf'(?:не|без|not|no|кроме|исключая)\s+(?:\w+\s+){{0,3}}{skill_escaped}'
        
        return not re.search(negative_pattern, text)


    
    @staticmethod
    async def personalize_score_safe(vacancy: dict, user_skills: list, user_disliked_skills: list, user_liked_skills: list) -> int:
        """Безопасное гибридное ранжирование по тексту сниппета с разбором истории."""
        score = 0

        name = vacancy.get("name", "") or ""
        snippet = vacancy.get("snippet", {}) or {}
        requirement = await HHAPI.clean_html(snippet.get("requirement", ""))
        responsibility = await HHAPI.clean_html(snippet.get("responsibility", ""))
        
        full_text = f"{name} {requirement} {responsibility}".lower()

        for skill in (user_skills or []):
            if await HHAPI.check_skill_with_context(full_text, skill):
                score += 10

        # Превращаем массив составных тегов в плоский список отдельных важных слов
        flatten_likes = set()
        for item in (user_liked_skills or []):
            item_lower = item.lower()
            # Если это короткое слово или известный термин, берем целиком
            if len(item_lower.split()) == 1 or "api" in item_lower or "git" in item_lower:
                flatten_likes.add(item_lower)
            else:
                # Иначе разбиваем фразу "тестирование баз данных" на ["тестирование", "баз", "данных"]
                # и убираем короткие предлоги (и, в, на, с)
                words = [w for w in item_lower.split() if len(w) > 2]
                flatten_likes.update(words)

        for liked in flatten_likes:
            if await HHAPI.check_skill_with_context(full_text, liked):
                score += 2

        flatten_dislikes = set()
        for item in (user_disliked_skills or []):
            item_lower = item.lower()
            if len(item_lower.split()) == 1 or "api" in item_lower:
                flatten_dislikes.add(item_lower)
            else:
                words = [w for w in item_lower.split() if len(w) > 2]
                flatten_dislikes.update(words)

        for bad in flatten_dislikes:
            if await HHAPI.check_skill_with_context(full_text, bad):
                score -= 5

        return score






    @staticmethod
    async def full_vacanci_id(vac_id: int, access_token, htpp_session: aiohttp.ClientSession):


        headers = {
            "User-Agent": "JobParserBot/1.0 (ваш_контактный_email@gmail.com)",
            "Authorization": f"Bearer {access_token}"
        }

        url = f"{HHAPI.BASE_URL}/vacancies/{vac_id}"

        async with htpp_session.get(url, headers=headers) as response:
                if response.status == 200:

                    data = await response.json()


                    
                    raw_skills = data.get("key_skills", [])
                    
                    key_skills_list = []
                    for item in raw_skills:
                        skill_name = item.get("name")
                        if skill_name:
                            key_skills_list.append(skill_name)

                    print(f"✅ Успешно спарсили навыки для вакансии {vac_id}: {key_skills_list}")
                    return key_skills_list

                else:
                    error_text = await response.text()
                    raise Exception(f"Ошибка API hh.ru: {response.status}. Ответ: {error_text}")  





    @staticmethod
    async def search_vacancies(params: dict[str, Any], access_token: str, session: AsyncSession, http_session: aiohttp.ClientSession, tg_id: int) -> dict[str, Any]:
        url = f"{HHAPI.BASE_URL}/vacancies"
        
        current_params = params.copy()

        
        
        db_ids = await get_viewed_vacancy_ids(session, tg_id)
        viewed_vac_ids = set(str(vid) for vid in db_ids)

        headers = {
            "User-Agent": "JobParserBot/1.0 (ваш_контактный_email@gmail.com)",
            "Authorization": f"Bearer {access_token}"
        }

        
        # Запускаем цикл: если вся страница оказалась просмотренной, автоматически запрашиваем следующую
        for attempt in range(5):
            flat_params = []
                
            for key, value in current_params.items():
                if isinstance(value, list):
                    for item in value:
                        flat_params.append((key, item))
                else:
                    flat_params.append((key, value))

                async with http_session.get(url, params=flat_params, headers=headers) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise Exception(f"Ошибка API hh.ru: {response.status}. Ответ: {error_text}")

                    data = await response.json()
                    raw_vacan = data.get("items", [])

                    if not raw_vacan:
                        return data

                    filtered_vacan = [
                        vac for vac in raw_vacan
                        if str(vac.get("id")) not in viewed_vac_ids   
                    ]

                    if filtered_vacan:
                        data["items"] = filtered_vacan
                        return data
                    
                    print(f" На page={current_params.get('page', 0)} всё просмотрено. Листаем дальше...")
                    current_params["page"] = current_params.get("page", 0) + 1


            if not data["items"]:
                data["items"] = []



            print(data[:1])

            
            return data


    @staticmethod
    async def test_connection():
        url = "https://api.hh.ru/vacancies"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Referer": "https://hh.ru/",
        }
        async with aiohttp.ClientSession(headers=headers, trust_env=False) as session, session.get(url, params={}) as response:
                print(await response.text())


