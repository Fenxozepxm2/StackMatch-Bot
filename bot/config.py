import tomllib
from dataclasses import dataclass


@dataclass
class BotConfig:
    token: str


@dataclass
class BotDatabaseConf:
    url: str


@dataclass
class BotParsingConf:
    hh_api_url: str
    update_interval_min: int


@dataclass
class Boti18nConfig:
    default_lang: str


@dataclass
class BotAccessToken:
    access_token: str


@dataclass
class Config:
    bot: BotConfig
    database: BotDatabaseConf
    parsers: BotParsingConf
    i18n: Boti18nConfig
    access_token: BotAccessToken


def load_config() -> Config:
    with open("settings.toml", "rb") as f:
        data = tomllib.load(f)
    return Config(
        bot=BotConfig(token=data["bot"]["token"]),
        database=BotDatabaseConf(url=data["database"]["url"]),
        parsers=BotParsingConf(
            hh_api_url=data["parsers"]["hh_api_url"],
            update_interval_min=data["parsers"]["update_interval_min"],
        ),
        i18n=Boti18nConfig(default_lang=data["i18n"]["default_lang"]),
        access_token=BotAccessToken(
            access_token=data["access_bot_token"]["access_token"]
        ),
    )
