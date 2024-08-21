from typing import Tuple, Type
from pydantic import BaseModel
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource


class VoIPSettings(BaseModel):
    server: str
    port: int = 5060
    username: str
    password: str


class DiscordConfig(BaseModel):
    home_guild_id: int
    default_text_channel_id: int
    default_voice_channel_id: int
    token: str


class Settings(BaseSettings):
    voip: VoIPSettings
    discord: DiscordConfig

    class Config:
        env_nested_delimiter = '__'
        env_prefix = 'voipcord_'

        # Make environment variables take precedence over the config file.
        @classmethod
        def settings_customise_sources(
                cls,
                _: Type[BaseSettings],
                init_settings: PydanticBaseSettingsSource,
                env_settings: PydanticBaseSettingsSource,
                __: PydanticBaseSettingsSource,
                file_secret_settings: PydanticBaseSettingsSource,
        ) -> Tuple[PydanticBaseSettingsSource, ...]:
            return env_settings, init_settings, file_secret_settings
