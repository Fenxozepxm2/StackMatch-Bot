<div align="center">

# 🎯 StackMatch Bot

### Поиск IT-вакансий в Telegram, где вместо ленты свайпы, а вместо фильтров алгоритм, который учится на твоих решениях

[![Открыть бота](https://img.shields.io/badge/Открыть%20бота-@StackMatch__bot-26A5E4?style=for-the-badge&logo=telegram&logoColor=white)](https://t.me/StackMatch_bot)

![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![aiogram](https://img.shields.io/badge/aiogram-3-2CA5E0?logo=telegram&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-4169E1?logo=postgresql&logoColor=white)
![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.0%20async-D71F00?logo=sqlalchemy&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)

</div>

<div align="center">
  <img width="30%" alt="Главное меню" src="https://github.com/user-attachments/assets/c338ab84-5cb4-477b-bd67-e8c0d36f6d20" />

  <img width="30%" height="350" alt="Фильтры" src="https://github.com/user-attachments/assets/d3ca7288-9fbc-4f04-a66b-4a67014bd5eb" />

  <img width="30%" alt="Карточка вакансии" src="https://github.com/user-attachments/assets/16e73189-6fd6-4a47-bac5-49f53972a4b9" />



</div>

---

## Что это

Сайты вакансий заточены под бесконечную ленту и простыни текста. **StackMatch** превращает поиск работы в быстрый цикл: *увидел карточку → лайк или скип*. Бот запоминает, что тебе нравится, и поднимает похожие вакансии выше.

Это мой самостоятельный проект: от идеи и модели данных до работающего бота, запакованного в Docker. Бот живой, его можно открыть и потыкать: **[@StackMatch_bot](https://t.me/StackMatch_bot)**.

## Что умеет

- 🔥 **Свайпы как в Tinder.** Карточки вакансий с кнопками ❤️ / ❌ / ⏪ / ➡️. Лайкнутое собирается в Избранное
- 🧠 **Персональная лента.** Каждая вакансия получает оценку под конкретного пользователя, лучшие идут первыми
- ⚙️ **Тонкие фильтры.** Город, опыт, график, формат работы, зарплата, ключевые слова и исключения
- ⏰ **Ежедневный Top-5.** Бот сам присылает подборку лучших вакансий на сегодня
- 🏙 **Города по сокращениям.** «спб», «мск», «екб» понимаются без единого запроса в сеть

## Что внутри интересного

**🧠 Скоринг, который учится.** Оценка вакансии складывается из совпадения со стеком пользователя и из навыков, которые встречались в ранее лайкнутых и скипнутых вакансиях. Чем больше свайпов, тем точнее лента.

**🏗 Слоистая архитектура.** Хендлеры → сервисы → репозитории. Telegram-часть не знает, как устроена база, а работа с данными спрятана за репозиториями.

**🗄 Данные по-взрослому.** SQLAlchemy 2.0 в async-режиме, версионирование схемы через Alembic, JSONB для гибких структур вроде фильтров и навыков, типизированные модели.

**⚡ Быстрый ввод-вывод.** Бот целиком асинхронный. Одна общая HTTP-сессия на всё приложение вместо новой на каждый запрос, а справочник городов HeadHunter загружается один раз и живёт в памяти.

**⏰ Фоновые задачи.** Планировщик рассылает ежедневные подборки пачками, не блокируя обработку сообщений остальных пользователей.

**🐳 Запуск одной командой.** Docker Compose поднимает бота вместе с PostgreSQL, секреты живут вне образа, миграции применяются при старте.

**🧹 Инженерная гигиена.** Структурированные логи, линтер Ruff, тесты, зависимости под управлением uv.

## Архитектура

<div align="center">

<table>
  <tr>
    <td align="center" colspan="2">
      <b>👤 Пользователь · Telegram</b>
    </td>
  </tr>
  <tr>
    <td align="center" colspan="2">↕</td>
  </tr>
  <tr>
    <td align="center" colspan="2">
      <b>🤖 Handlers</b><br/>
      <sub>aiogram · Routers · FSM</sub>
    </td>
  </tr>
  <tr>
    <td align="center">↙</td>
    <td align="center">↘</td>
  </tr>
  <tr>
    <td align="center">
      <b>⚙️ Services</b><br/>
      <sub>Скоринг · HeadHunter API</sub><br/>
      <sub>Кэш городов · Бизнес-логика</sub>
    </td>
    <td align="center">
      <b>⏰ APScheduler</b><br/>
      <sub>Ежедневный Top-5</sub>
    </td>
  </tr>
  <tr>
    <td align="center">↕</td>
    <td align="center">↙</td>
  </tr>
  <tr>
    <td align="center">
      <b>🗄 Repositories</b><br/>
      <sub>SQLAlchemy 2.0 Async</sub>
    </td>
    <td align="center">
      <b>⚙️ Services</b><br/>
      <sub>Фоновая обработка</sub>
    </td>
  </tr>
  <tr>
    <td align="center">↕</td>
    <td align="center">↘</td>
  </tr>
  <tr>
    <td align="center" colspan="2">
      <b>🐘 PostgreSQL</b><br/>
      <sub>Пользователи · Фильтры · Вакансии · Свайпы</sub>
    </td>
  </tr>
</table>

</div>



**Внешняя интеграция:** HeadHunter API — получение вакансий и справочника городов.



## Стек

| Область | Технологии |
|---|---|
| Язык и бот | Python 3.12, aiogram 3 (роутеры, FSM), asyncio, aiohttp |
| Данные | PostgreSQL, SQLAlchemy 2.0 (async), Alembic |
| Фон | APScheduler |
| Инфраструктура | Docker, Docker Compose, GitHub Actions |
| Качество | Ruff, structlog, pytest, uv |



---

<div align="center">

**Fenxozepxm2** · Python-разработчик · [GitHub](https://github.com/Fenxozepxm2) · [Telegram](https://t.me/sanyaplan)

</div>
