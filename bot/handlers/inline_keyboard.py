from aiogram import Router, F
from aiogram.types import InlineQuery, InlineQueryResultArticle, InputTextMessageContent

inline_router = Router(name="inline_stack")

# Наш ИТ-словарь подсказок для автодополнения (Расширенный)
TECH_DICTIONARY = [
    # --- Backend (Python) ---
    "Python", "Django", "Flask", "FastAPI", "SQLAlchemy", "Alembic", "Celery", "Asyncio", "Pytest", "Ruff", "uv", "Poetry",
    
    # --- Backend (JS / TS) ---
    "JavaScript", "TypeScript", "Node.js", "Express", "NestJS", "Fastify", "Prisma", "Sequelize",
    
    # --- Backend (Go) ---
    "Golang", "Gin", "Fiber", "Echo", "gRPC", "Protobuf", "Go-kit",
    
    # --- Backend (Java / Kotlin) ---
    "Java", "Kotlin", "Spring Boot", "Spring MVC", "Hibernate", "Maven", "Gradle",
    
    # --- Backend (C# / .NET) ---
    "C#", ".NET", "ASP.NET Core", "Entity Framework", "LINQ",
    
    # --- Frontend ---
    "React", "Vue.js", "Angular", "Next.js", "Nuxt.js", "Redux", "MobX", "Pinia", "Zustand", 
    "HTML5", "CSS3", "SASS", "LESS", "Tailwind CSS", "Webpack", "Vite", "Babel", "NPM", "Yarn", "PNPM",
    
    # --- Базы данных & Кеширование ---
    "PostgreSQL", "MySQL", "MongoDB", "Redis", "ClickHouse", "SQLite", "Oracle", "Microsoft SQL Server", 
    "Cassandra", "Elasticsearch", "Memcached", "Neo4j", "Firebase",
    
    # --- DevOps, Инфраструктура & CI/CD ---
    "Docker", "Docker Compose", "Kubernetes", "K8s", "Git", "GitLab CI/CD", "GitHub Actions", "Jenkins", 
    "Ansible", "Terraform", "Nginx", "Apache", "Linux", "Bash", "AWS", "Google Cloud", "Azure", "Yandex Cloud",
    
    # --- Очереди сообщений & Стриминг ---
    "RabbitMQ", "Kafka", "NATS", "MQTT",
    
    # --- Тестирование & QA ---
    "Selenium", "Playwright", "Cypress", "Postman", "Swagger", "JMeter",
    
    # --- Аналитика, Data Science & ML ---
    "Pandas", "NumPy", "Scikit-learn", "TensorFlow", "PyTorch", "Hadoop", "Spark", "Tableau", "Power BI",
    
    # --- Мобильная разработка ---
    "Flutter", "React Native", "Swift", "Objective-C", "Dart",
    
    # --- Архитектура & Протоколы (Общее) ---
    "REST API", "GraphQL", "WebSockets", "OOP", "SOLID", "DRY", "KISS", "Microservices", "DDD"
]


@inline_router.inline_query(F.query.startswith("stack:"))
async def handle_inline_stack_suggestions(inline_query: InlineQuery):
    # Вытаскиваем то, что юзер пишет ПОСЛЕ префикса "stack:"
    raw_search = inline_query.query.replace("stack:", "").strip().lower()
    
    results = []
    
    # Фильтруем наш словарь по введенным буквам
    matched_techs = [tech for tech in TECH_DICTIONARY if raw_search in tech.lower()]
    
    # Если юзер еще ничего не написал или совпадений нет, показываем топ дефолтных технологий
    if not raw_search or not matched_techs[:8]:
        matched_techs = TECH_DICTIONARY

    # Собираем интерактивные плитки подсказок над клавиатурой
    for i, tech in enumerate(matched_techs[:10]): # Максимум 10 подсказок на экран
        results.append(
            InlineQueryResultArticle(
                id=f"tech_{i}",
                title=tech,
                description=f"Выбрать и добавить {tech} в свой стек",
                input_message_content=InputTextMessageContent(
                    message_text=f"добавить_стек: {tech}" # Это сообщение улетит в чат при клике
                )
            )
        )

    # Отправляем массив подсказок обратно в клиент Телеграма
    await inline_query.answer(results=results, cache_time=1, is_personal=True)
