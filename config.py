from typing import Tuple
from pydantic import BaseModel, BaseSettings
from pydantic.env_settings import SettingsSourceCallable


class VoIPSettings(BaseModel):
    server: str
    port: int = 5060
    username: str
    password: str


class DiscordConfig(BaseModel):
    home_guild_id: int
    token: str


class Settings(BaseSettings):
    voip: VoIPSettings
    discord: DiscordConfig

    class Config:
        env_nested_delimiter = '__'
        env_prefix = 'voipcord_'

        # Make environment variables take precedence over the config file.
        @classmethod
        def customise_sources(
            cls,
            init_settings: SettingsSourceCallable,
            env_settings: SettingsSourceCallable,
            file_secret_settings: SettingsSourceCallable,
        ) -> Tuple[SettingsSourceCallable, ...]:
            return env_settings, init_settings, file_secret_settings
