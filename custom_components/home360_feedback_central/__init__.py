"""Home360 Feedback Central.

Integração "mestre", instalada no Home Assistant da empresa. Registra um webhook
que recebe os reports enviados pelos HAs dos clientes, valida (token + cliente +
categoria), e então: cria uma notificação persistente (ticket), manda push,
dispara um evento e atualiza o sensor de "último report".

Toda a configuração (clientes, tokens, serviço de push) é feita pela UI.
"""

from __future__ import annotations

import logging

from aiohttp import web

from homeassistant.components import webhook
from homeassistant.components.persistent_notification import async_create
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.util import dt as dt_util

from .const import (
    CATEGORIES,
    CONF_CLIENTS,
    CONF_NOTIFY_SERVICE,
    CONF_WEBHOOK_ID,
    DOMAIN,
    EVENT_REPORT,
    MAX_TEXT_LENGTH,
    TOKEN_HEADER,
    signal_new_report,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]


def get_config(entry: ConfigEntry) -> dict:
    """Config atual, mesclando data (fixo) com options (editável pela UI)."""
    data = entry.data
    opts = entry.options
    return {
        "webhook_id": data.get(CONF_WEBHOOK_ID),
        "notify_service": opts.get(
            CONF_NOTIFY_SERVICE, data.get(CONF_NOTIFY_SERVICE, "")
        ),
        "clients": opts.get(CONF_CLIENTS, data.get(CONF_CLIENTS, {})),
    }


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Configura a integração central."""
    cfg = get_config(entry)
    webhook_id = cfg["webhook_id"]

    async def _handler(
        hass: HomeAssistant, webhook_id: str, request: web.Request
    ) -> None:
        await _async_handle_report(hass, entry, request)

    # Remove um registro que possa ter ficado de uma tentativa anterior que
    # falhou (evita o erro "Handler is already defined" ao reconfigurar).
    try:
        webhook.async_unregister(hass, webhook_id)
    except (ValueError, KeyError):
        pass
    webhook.async_register(
        hass, DOMAIN, "Home360 Feedback Central", webhook_id, _handler
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Recarrega a integração quando as options mudam (novo cliente, etc.).
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Remove a integração central."""
    webhook.async_unregister(hass, get_config(entry)["webhook_id"])
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Recarrega a entry após alteração das options."""
    await hass.config_entries.async_reload(entry.entry_id)


async def _async_handle_report(
    hass: HomeAssistant, entry: ConfigEntry, request: web.Request
) -> None:
    """Recebe, valida e processa um report vindo de um cliente."""
    cfg = get_config(entry)

    try:
        data = await request.json()
    except ValueError:
        return
    if not isinstance(data, dict):
        return

    cliente = str(data.get("client_id", "")).strip()
    token_recebido = request.headers.get(TOKEN_HEADER) or str(data.get("token", ""))
    token_esperado = cfg["clients"].get(cliente)

    # Validação: cliente conhecido + token confere. Caso contrário, ignora.
    if not token_esperado or token_recebido != token_esperado:
        _LOGGER.warning(
            "Home360 Feedback: report rejeitado (cliente/token inválido): %r",
            cliente,
        )
        return

    categoria = str(data.get("categoria", "")).strip()
    if categoria not in CATEGORIES:
        categoria = "Outro"
    texto = str(data.get("texto", "")).strip()[:MAX_TEXT_LENGTH] or "(sem texto)"
    local = str(data.get("local", "")).strip()[:100]
    agora = dt_util.now()

    report = {
        "cliente": cliente,
        "categoria": categoria,
        "texto": texto,
        "local": local,
        "em": agora.isoformat(timespec="seconds"),
    }

    _LOGGER.info("Home360 Feedback: report de %s (%s)", cliente, categoria)

    # 1) Ticket na interface do central --------------------------------------
    async_create(
        hass,
        (
            f"{texto}\n\n"
            f"**Cliente:** {cliente}\n"
            + (f"**Local:** {local}\n" if local else "")
            + f"**Quando:** {agora.strftime('%d/%m/%Y %H:%M')}"
        ),
        title=f"🔔 {categoria} — {cliente}",
        notification_id=f"{DOMAIN}_{cliente}_{int(agora.timestamp())}",
    )

    # 2) Push no celular ------------------------------------------------------
    await _async_push(hass, cfg["notify_service"], cliente, categoria, texto)

    # 3) Logbook: histórico permanente e pesquisável --------------------------
    if hass.services.has_service("logbook", "log"):
        await hass.services.async_call(
            "logbook",
            "log",
            {
                "name": f"Feedback · {cliente}",
                "message": f"[{categoria}] {texto}"
                + (f" (Local: {local})" if local else ""),
            },
            blocking=False,
        )

    # 4) Evento para automações do usuário ------------------------------------
    hass.bus.async_fire(EVENT_REPORT, report)

    # 5) Atualiza o sensor de "último report" ---------------------------------
    async_dispatcher_send(hass, signal_new_report(entry.entry_id), report)


async def _async_push(
    hass: HomeAssistant,
    notify_service: str,
    cliente: str,
    categoria: str,
    texto: str,
) -> None:
    """Envia o push pelo serviço notify configurado (se houver)."""
    if not notify_service:
        return
    domain, _, service = notify_service.partition(".")
    if not service:  # usuário digitou só o nome do serviço
        domain, service = "notify", notify_service
    if not hass.services.has_service(domain, service):
        _LOGGER.warning(
            "Home360 Feedback: serviço de notificação %s indisponível",
            notify_service,
        )
        return
    await hass.services.async_call(
        domain,
        service,
        {
            "title": f"🔔 {cliente} · {categoria}",
            "message": texto,
            "data": {"tag": "home360_feedback", "group": cliente},
        },
        blocking=False,
    )
