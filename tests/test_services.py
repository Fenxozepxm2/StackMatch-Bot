import pytest

from bot.services.to_hhApi import HHAPI


@pytest.mark.asyncio
async def test_clean_html():
    raw = "<highlight>Python</highlight> и <highlight>Django</highlight>"
    cleaned = await HHAPI.clean_html(raw)
    assert cleaned == "Python и Django"


@pytest.mark.asyncio
async def test_check_skill_with_context():
    text = "требуется знание Python и Django"
    assert await HHAPI.check_skill_with_context(text, "python") is True
    text2 = "не работаем с Python"
    assert await HHAPI.check_skill_with_context(text2, "python") is False


@pytest.mark.asyncio
async def test_format_vacancies():
    vac = {
        "id": "1",
        "name": "Dev",
        "alternate_url": "https://hh.ru/1",
        "salary": {"from": 100000, "to": 150000, "currency": "RUR"},
        "area": {"name": "Москва"},
        "employer": {"name": "Company"},
        "experience": {"name": "от 3 до 6 лет"},
        "snippet": {"requirement": "Python", "responsibility": "кодить"},
    }
    result = await HHAPI.format_vacancies(vac, score=5)
    assert result["name"] == "Dev"
    assert "Python" in result["html_content"]
