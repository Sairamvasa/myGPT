import os
from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Literal

class Settings(BaseSettings):
    app_name: str = Field(default='MyGPT Voice Agent', description='Application name')
    environment: Literal['development', 'production'] = Field(default='development')

    ai_provider: str = Field(default='gemini', env='AI_PROVIDER')
    model_name: str = Field(default='gemini-3.5-flash', env='MODEL_NAME')
    temperature: float = Field(default=0.7, env='TEMPERATURE')

    stt_provider: str = Field(default='whisper', env='STT_PROVIDER')
    tts_provider: str = Field(default='pyttsx3', env='TTS_PROVIDER')
    whisper_model: str = Field(default='base', env='WHISPER_MODEL')
    language: str = Field(default='auto', env='VOICE_LANGUAGE')

    openai_api_key: str = Field(default='', env='OPENAI_API_KEY')
    gemini_api_key: str = Field(default='', env='GEMINI_API_KEY')
    google_api_key: str = Field(default='', env='GOOGLE_API_KEY')

    api_host: str = Field(default='0.0.0.0', env='VOICE_API_HOST')
    api_port: int = Field(default=8001, env='VOICE_API_PORT')
    cors_origins: str = Field(default='*', env='VOICE_CORS_ORIGINS')
    api_token: str = Field(default='', env='VOICE_API_TOKEN')

    class Config:
        env_file = '.env'
        env_file_encoding = 'utf-8'
        extra = 'ignore'

settings = Settings()
