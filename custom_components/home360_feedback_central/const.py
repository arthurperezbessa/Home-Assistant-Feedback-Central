"""Constantes da integração Home360 Feedback Central (HA da empresa)."""

from __future__ import annotations

DOMAIN = "home360_feedback_central"

# Chaves de configuração
CONF_WEBHOOK_ID = "webhook_id"
CONF_NOTIFY_SERVICE = "notify_service"
CONF_CLIENTS = "clients"

# Header HTTP que carrega o token do cliente.
TOKEN_HEADER = "X-Home360-Token"

# Categorias aceitas (devem casar com a integração do cliente).
CATEGORIES: list[str] = [
    "Erros Gerais",
    "Áudio e Vídeo",
    "Iluminação",
    "Ar Condicionado",
    "Cortinas",
    "Automações ou Cenas",
    "Melhorias",
]

# Limite de tamanho do texto do report (defesa contra abuso).
MAX_TEXT_LENGTH = 500

# Evento disparado a cada report válido (para automações do usuário).
EVENT_REPORT = f"{DOMAIN}_report"


def signal_new_report(entry_id: str) -> str:
    """Sinal (dispatcher) por config entry, para atualizar o sensor."""
    return f"{DOMAIN}_report_{entry_id}"
