"""Constantes da integração Home360 Feedback Central (HA da empresa)."""

from __future__ import annotations

DOMAIN = "home360_feedback_central"

# Chaves de configuração
CONF_WEBHOOK_ID = "webhook_id"
CONF_NOTIFY_SERVICE = "notify_service"
CONF_CLIENTS = "clients"

# Resumo diário de monitoramento (1 push por cliente com problema).
CONF_DIGEST_ENABLED = "digest_enabled"
CONF_DIGEST_HOUR = "digest_hour"
CONF_DIGEST_MINUTE = "digest_minute"
CONF_DIGEST_MIN_MINUTES = "digest_min_minutes"
CONF_DIGEST_NOTIFY_SERVICE = "digest_notify_service"

DEFAULT_DIGEST_ENABLED = True
DEFAULT_DIGEST_HOUR = 9
DEFAULT_DIGEST_MINUTE = 30
# Só entra no resumo a entidade que ficou indisponível por pelo menos este
# tempo CONTÍNUO (uma única queda) nas últimas 24h.
DEFAULT_DIGEST_MIN_MINUTES = 10
# Acima disto o cliente é tratado como "sem contato" no resumo (horas).
DIGEST_STALE_HOURS = 1

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

# Limites do estado de monitoramento aceito por cliente (defesa contra abuso;
# o Entity Monitor manda no máximo 30 entidades no total).
MAX_ESTADO_INTEGRACOES = 30
MAX_ESTADO_ENTIDADES = 50

# Evento disparado a cada report válido (para automações do usuário).
EVENT_REPORT = f"{DOMAIN}_report"


def signal_new_report(entry_id: str) -> str:
    """Sinal (dispatcher) por config entry, para o sensor de feedback."""
    return f"{DOMAIN}_report_{entry_id}"


def signal_new_monitor(entry_id: str) -> str:
    """Sinal (dispatcher) por config entry, para o sensor de monitoramento."""
    return f"{DOMAIN}_monitor_{entry_id}"


# Evento disparado a cada alerta de monitoramento válido.
EVENT_MONITOR = f"{DOMAIN}_monitor"

# Serviço que monta e envia o resumo diário na hora (para testar).
SERVICE_SEND_DIGEST = "send_daily_digest"
