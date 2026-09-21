import asyncio
import re
from typing import Any

import aiohttp
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import *
from bot.db.repos.repo_filters import get_user_filters
from bot.db.repos.repo_vacancies import get_viewed_vacancy_ids
from bot.services.city_mapper import CityMapper
from bot.config import load_config 


config = load_config()


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
    "Полный день": "fullDay",
    "Вахта": "flyInFlyOut"
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
        spec = user_filters["specialization"].strip()
        search_parts.append(f"NAME:({spec})")



    if user_filters.get("user_tech_stack"):
        # Вытаскиваем массив строк, например: ["FastAPI", "Docker", "PostgreSQL"]
        tech_stack = user_filters["user_tech_stack"]
        if isinstance(tech_stack, list) and tech_stack:
            # Собираем технологии через пробел для ключевых слов API HH
            search_parts.append(" ".join(tech_stack))


    if user_filters.get("only_startups"):
        search_parts.append("(startup OR стартап OR опцион OR equity OR доля)")

    if search_parts:
        params["text"] = " ".join(search_parts)

    # для региона (area)
    city = user_filters.get("city")
    if city:
        city_id = CityMapper.get_city_id(city)
        if city_id:
            params["area"] = int(city_id)




    # ЗАРПЛАТА (salary)
    # Если есть обе границы, передаем ТОЛЬКО salary_from и salary_to
    if user_filters.get("salary_from"):
        params["salary"] = int(user_filters["salary_from"])
        params["only_with_salary"] = "true"
    elif user_filters.get("salary_to"):
        params["salary"] = int(user_filters["salary_to"])
        params["only_with_salary"] = "true"

    if user_filters.get("currency"):
        params["currency"] = user_filters["currency"]



    # опыт работы (experience)
    if user_filters.get("exp"):
        params["experience"] = []
        for i in user_filters["exp"]:
            if i in EXPERIENCE_MAP:
                params["experience"].append(EXPERIENCE_MAP[i])
        
    

    # График работы (schedule)
    # Обработка графиков работы пользователя (5/2, 2/2 и т.д.) !!!!доработать!!!!
    params["schedule"] = []
    if user_filters.get("schedule"):
        for i in user_filters["schedule"]:
            if i in SCHEDULE_MAP and SCHEDULE_MAP[i] not in params["schedule"]:
                params["schedule"].append(SCHEDULE_MAP[i])

    # Обработка формата работы (Удалённо)
    work_formats = user_filters.get("workformat") or []
    if "Удалённо" in work_formats and "remote" not in params["schedule"]:
        params["schedule"].append("remote")


    if not params["schedule"]:
        del params["schedule"]

    # если у типа удалёнка
    if params.get("schedule") and "remote" in params["schedule"] and "area" in params:
        del params["area"]
        


    # ТУТ КОРОЧЕ СДЕЛАТЬ ОБРАБОТКУ ИСКЛЮЧАЮЩИЙ СЛОВ, ПОКА ЧТО ВПАДЛУ


    # params["order_by"] = "publication_time"

    params["per_page"] = 100  # Берём оптимальный размер пачки (максимум у HH — 100)
    params["page"] = page    # Теперь страница динамическая

    # Очищаем от пустых значений
    params = {k: v for k, v in params.items() if v is not None and v != "" and v != []}

    # ИСПРАВЛЕНИЕ ДЛЯ aiohttp: Конвертируем True/False в строки "true"/"false"
    params = {k: v for k, v in params.items() if v is not None and v != "" and v != []}
    for k, v in params.items():
        if isinstance(v, bool):
            params[k] = "true" if v else "false"

    print('-'*80 + f'{params}' + '\n' + '-'*80)

    return params

        



class HHAPI:
    BASE_URL = "https://api.hh.ru"
    
    @staticmethod
    def clean_html(text: str) -> str:
        if not text:
            return ""
        text = re.sub(r'<[^>]+>', '', text)
        return re.sub(r'\s+', ' ', text).strip()

    # @staticmethod
    # async def full_vacanci_id(vac_id: int, access_token, htpp_session: aiohttp.ClientSession):
    #     headers = {
    #         "User-Agent": "StackMatchBot/1.0 (tarik2046@mail.ru)",
    #         "Authorization": f"Bearer {access_token}"
    #     }

    #     url = f"{HHAPI.BASE_URL}/vacancies/{vac_id}"

    #     async with htpp_session.get(url, headers=headers) as response:
    #         if response.status == 200:
    #             data = await response.json()
    #             print(data)
    #             raw_skills = data.get("key_skills", [])
    #             key_skills_list = [item.get("name") for item in raw_skills if item.get("name")]
    #             print(f"✅ Успешно спарсили навыки для вакансии {vac_id}: {key_skills_list}")
                
    #             return data
    #         else:
    #             error_text = await response.text()
    #             raise Exception(f"Ошибка API hh.ru: {response.status}. Ответ: {error_text}")

    @staticmethod
    async def format_vacancies(vac: dict, score: int = 0, http_session: aiohttp.ClientSession = None) -> dict: 
        id_vac = vac.get("id")
        
        clean_description = "Описание загружается..."
        if id_vac and http_session:
            try:
                full_data = await HHAPI.full_vacanci_id(id_vac, config.access_token.access_token, http_session)
                clean_description = HHAPI.clean_html(full_data.get("description", ""))
            except Exception:
                clean_description = "Не удалось подгрузить полное описание вакансии."



        salary_data = vac.get("salary")
        salary_str = "не указана"
        if salary_data:
            sal_from = f"от {salary_data.get('from')}" if salary_data.get('from') else ""
            sal_to = f"до {salary_data.get('to')}" if salary_data.get('to') else ""
            salary_str = f"{sal_from} {sal_to} {salary_data.get('currency', '')}".strip()

        it_badge = " <mark>[IT-аккредитованная компания]</mark>" if vac.get("employer", {}).get("accredited_it_employer") else ""
        score_color = "🟢" if score > 0 else ("🔴" if score < 0 else "⚪️")

        raw_skills = full_data.get("key_skills", [])
        key_skills_list = [item.get("name") for item in raw_skills if item.get("name")]
        
        if key_skills_list:
            skills_text = ", ".join([f"<code>{skill}</code>" for skill in key_skills_list])
        else:
            skills_text = "<i>не указаны</i>"


        
        
        # Собираем современный ИТ-шаблон с поддержкой тегов раскрытия <details>
        html_content = (
            f"<h1>💼 {vac.get('name')}</h1>"
            f"<hr>"
            f"<p>🏢 <b>Компания:</b> {vac.get('employer', {}).get('name')}{it_badge}</p>"
            f"<p>💰 <b>Зарплата:</b> {salary_str}</p>"
            f"<p>📍 <b>Город:</b> {vac.get('area', {}).get('name')}</p>"
            f"<p>⏳ <b>Опыт:</b> {vac.get('experience', {}).get('name', 'не указан')}</p>"
            f"<br>"
            f"<details>"
            f"  <summary><b>📝 Показать полное описание вакансии</b></summary>"
            f"  <p><i>{clean_description}</i></p>"
            f"</details>"
            f"<br>"
            f"<p>🛠 <b>Ключевые навыки:</b> {skills_text}</p>"
            f"<br>"
            f"<p>🔗 <a href='{vac.get('alternate_url')}'>Открыть вакансию на HH.ru</a></p>"
            f"<br>"
            f"<footer>{score_color} Рейтинг соответствия: {score:+d}</footer>"
        )
        
        return {
            "id_vac": id_vac,
            "html_content": html_content
        }

    @staticmethod
    async def personalize_score_safe(vacancy: dict, user_skills: list, user_disliked: list, user_liked: list, user_filters: dict = None) -> int:
        """
        ИТ-скоринг вакансии на основе key_skills и текста.
        Если включен тумблер stack_strict и совпало < 50% стека, возвращает -999 для отсечения.
        """
        score = 0
        user_filters = user_filters or {}
        
        # 1. Получаем реальные навыки вакансии (из key_skills)
        raw_skills = vacancy.get("key_skills", []) or []
        vac_skills = [str(item.get("name", "")).strip().lower() for item in raw_skills if item.get("name")]
        
        # Собираем текст названия и описания для поиска технологий
        vac_name_lower = str(vacancy.get("name", "")).lower()
        vac_desc_lower = str(vacancy.get("description", "")).lower()
        full_vac_text = f"{vac_name_lower} {vac_desc_lower}"

        # 2. ПРОВЕРКА НА 50%+ СОВПАДЕНИЕ СТЕКА (Используем правильные ключи из фильтров: "stack" и "stack_strict")
        user_tech_stack = user_filters.get("stack", [])
        strict_stack_filter = user_filters.get("stack_strict", False)

        if user_tech_stack:
            matched_count = 0
            for tech in user_tech_stack:
                tech_lower = tech.lower()
                
                # Ищем технологию сначала в официальных тегах, а если там нет — в самом тексте вакансии
                if tech_lower in vac_skills or tech_lower in full_vac_text:
                    matched_count += 1

            # Вычисляем процент совпадения
            match_percentage = (matched_count / len(user_tech_stack)) * 100
            
            # Если включен тумблер ЖЕСТКОГО ОТБОРА и совпало меньше половины — бракуем вакансию
            if strict_stack_filter and match_percentage < 50:
                return -999  # Секретный маркер для удаления из списка

        # 3. НАЧИСЛЕНИЕ БАЛЛОВ ЗА СТЕК
        if user_tech_stack:
            for tech in user_tech_stack:
                tech_lower = tech.lower()
                if tech_lower in vac_skills:
                    score += 10
                elif tech_lower in full_vac_text:
                    score += 5  # чуть меньше, если совпало просто в тексте

        # 4. СКОРИНГ НА ОСНОВЕ ИСТОРИИ ЛАЙКОВ/ДИЗЛАЙКОВ
        for skill in (user_skills or []):
            if skill.lower() in vac_skills or skill.lower() in full_vac_text:
                score += 5

        for liked in (user_liked or []):
            if liked.lower() in vac_skills or liked.lower() in full_vac_text:
                score += 2

        for disliked in (user_disliked or []):
            if disliked.lower() in vac_skills or disliked.lower() in full_vac_text:
                score -= 10  # Жестко опускаем вниз за дизлайкнутый стек

        return score



    @staticmethod
    async def search_vacancies(params: dict[str, Any], access_token: str, session: AsyncSession, http_session: aiohttp.ClientSession, tg_id: int) -> dict[str, Any]:
        url = f"{HHAPI.BASE_URL}/vacancies"
        current_params = params.copy()

        db_ids = await get_viewed_vacancy_ids(session, tg_id)
        viewed_vac_ids = set(str(vid) for vid in db_ids)

        headers = {
            "User-Agent": "StackMatchBot/1.0 (tarik2046@mail.ru)",
            "Authorization": f"Bearer {access_token}"
        }

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
                    return {"items": []}

                data = await response.json()
                raw_vacan = data.get("items", [])

                if not raw_vacan:
                    return data

                # Фильтруем от просмотренного + СРАЗУ убираем дубликаты одинаковой удаленки!
                filtered_vacan = []
                seen_keys = set()
                
                for vac in raw_vacan:
                    vac_id = str(vac.get("id"))
                    if vac_id in viewed_vac_ids:
                        continue
                        
                    # Ключ дедупликации: Имя вакансии + Имя компании
                    vac_key = f"{vac.get('name', '').lower()} | {vac.get('employer', {}).get('name', '').lower()}"
                    if vac_key not in seen_keys:
                        seen_keys.add(vac_key)
                        filtered_vacan.append(vac)

                if filtered_vacan:
                    data["items"] = filtered_vacan
                    return data
                
                current_params["page"] = current_params.get("page", 0) + 1

        data["items"] = []
        return data



    @staticmethod
    async def full_vacanci_id(vac_id: int, access_token, htpp_session: aiohttp.ClientSession) -> dict:


        headers = {
            "User-Agent": "JobParserBot/1.0 (ваш_контактный_email@gmail.com)",
            "Authorization": f"Bearer {access_token}"
        }

        url = f"{HHAPI.BASE_URL}/vacancies/{vac_id}"

        async with htpp_session.get(url, headers=headers) as response:
                if response.status == 200:

                    data = await response.json()
                    print(data)
                    # raw_skills = data.get("key_skills", [])
                    
                    # key_skills_list = []
                    # for item in raw_skills:
                    #     skill_name = item.get("name")
                    #     if skill_name:
                    #         key_skills_list.append(skill_name)

                    # print(f"✅ Успешно спарсили навыки для вакансии {vac_id}: {key_skills_list}")
                    return data


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

        for attempt in range(5):
            flat_params = []
                
            # 1. СНАЧАЛА ПОЛНОСТЬЮ СОБИРАЕМ ВСЕ ПАРАМЕТРЫ ИЗ СЛОВАРЯ
            for key, value in current_params.items():
                if isinstance(value, list):
                    for item in value:
                        flat_params.append((key, item))
                else:
                    flat_params.append((key, value))

            # 2. И ТОЛЬКО КОГДА flat_params ПОЛНОСТЬЮ ГОТОВ — ДЕЛАЕМ ЗАПРОС (ВНЕ ЦИКЛА FOR!)
            async with http_session.get(url, params=flat_params, headers=headers) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"Ошибка API hh.ru: {response.status}. Ответ: {error_text}")

                data = await response.json()
                raw_vacan = data.get("items", [])

                if not raw_vacan:
                    return data

                # Фильтруем от того, что юзер уже лайкнул/скипнул ранее
                filtered_vacan = [
                    vac for vac in raw_vacan
                    if str(vac.get("id")) not in viewed_vac_ids   
                ]

                # Если на этой странице есть хотя бы одна новая вакансия — отдаем её
                if filtered_vacan:
                    data["items"] = filtered_vacan
                    return data
                
                current_params["page"] = current_params.get("page", 0) + 1

        # Если за 5 страниц вообще ничего нового не нашли
        data["items"] = []
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


