from unittest.mock import MagicMock

from aiogram.types import Message, User

from bot.config import load_config
from bot.db.database import Async_Fabric_Session
from bot.services.to_hhApi import HHAPI, filters_to_params_hh_api

config = load_config()


async def test_get_vacancies():
    mock_message = MagicMock(spec=Message)
    mock_message.from_user = MagicMock(spec=User)

    tg_id = 7183877497

    async with Async_Fabric_Session() as session:
        print("1. Формируем параметры запроса из фильтров БД...")
        try:
            params = await filters_to_params_hh_api(tg_id=tg_id, session=session)
            print(f" Сформированные параметры для HH: {params}\n")

            print("2. Отправляем тестовый запрос в API hh.ru (в обход Happ)...")
            response = await HHAPI.search_vacancies(
                params, config.access_token.access_token, session=session, tg_id=tg_id
            )

            assert response, "Ответ от API пустой"
            assert isinstance(response, dict), "Ответ не является словарем"

            if response:
                print(" Ответ от HeadHunter успешно получен:")
                print(
                    f"Всего найдено вакансий по вашим фильтрам: {response.get('found', 0)}"
                )

            # Показываем первые 3 вакансии для проверки вывода
            items = response.get("items", [])
            if items:
                print("\nПримеры найденных вакансий:")
                for i, vacancy in enumerate(items[:3], 1):
                    salary = vacancy.get("salary")
                    salary_str = "Не указана"
                    if salary:
                        fr = f"от {salary.get('from')}" if salary.get("from") else ""
                        to = f"до {salary.get('to')}" if salary.get("to") else ""
                        salary_str = f"{fr} {to} {salary.get('currency')}".strip()

                    print(
                        f"{i}. {vacancy.get('name')} | Зарплата: {salary_str} | Компания: {vacancy.get('employer', {}).get('name')}"
                    )
            else:
                print("⚠ Вакансий по выбранным фильтрам не обнаружено.")

        except Exception as e:
            assert False, f"❌ Произошла ошибка во время теста: {e}"
