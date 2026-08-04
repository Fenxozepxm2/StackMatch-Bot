import logging
import sys

import structlog
from structlog.stdlib import ProcessorFormatter

# Для цветов на Windows (опционально)
try:
    import colorama

    colorama.just_fix_windows_console()
except ImportError:
    pass


def setup_logging(log_level: str = "INFO") -> None:
    # Настройка стандартного logging (уровень и базовый формат)
    logging.basicConfig(
        format="%(message)s",
        level=getattr(logging, log_level.upper(), logging.INFO),
        stream=sys.stdout,
    )

    # 1. Процессоры, общие для всех логов (и structlog, и стандартных)
    shared_processors = [
        structlog.stdlib.add_log_level,  # добавляет level
        structlog.stdlib.add_logger_name,  # добавляет logger name
        structlog.stdlib.PositionalArgumentsFormatter(),  # поддержка %s
        structlog.processors.TimeStamper(fmt="iso"),  # временная метка
        structlog.processors.StackInfoRenderer(),  # стек
        structlog.processors.format_exc_info,  # исключения
    ]

    # 2. Цепочка для преобразования "чужих" логов (от aiogram и др.)
    #    в формат event_dict, понятный structlog
    foreign_pre_chain = (
        shared_processors
        + [
            # Этот процессор добавляет ключ _record, который нужен для remove_processors_meta
            # НО мы его не будем использовать, чтобы избежать ошибки
            # Вместо этого мы сделаем так:
        ]
    )

    # 3. Создаём форматтер для консоли
    #    Используем более простую цепочку без remove_processors_meta
    formatter = ProcessorFormatter(
        processors=[
            # Убираем мета-информацию, которую ProcessorFormatter сам добавляет
            ProcessorFormatter.remove_processors_meta,
            # Красивый цветной вывод в консоль
            structlog.dev.ConsoleRenderer(colors=True),
        ],
        foreign_pre_chain=foreign_pre_chain,
    )

    # 4. Применяем форматтер к корневому логгеру
    root_logger = logging.getLogger()
    # Удаляем все старые хендлеры, чтобы не было дублей
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # 5. Глобальная конфигурация structlog
    structlog.configure(
        processors=shared_processors
        + [
            # Этот процессор — мост между structlog и стандартным logging
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
