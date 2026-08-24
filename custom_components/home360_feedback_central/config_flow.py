"""Config flow e options flow da Home360 Feedback Central."""

from __future__ import annotations

import secrets
from typing import Any

import voluptuous as vol

from homeassistant.components import webhook
from homeassistant.components.persistent_notification import async_create
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv

from .const import (
    CONF_CLIENTS,
    CONF_NOTIFY_SERVICE,
    CONF_WEBHOOK_ID,
    DOMAIN,
)


def _webhook_url(hass, webhook_id: str) -> str:
    """URL pública do webhook (usa a URL externa configurada)."""
    try:
        return webhook.async_generate_url(hass, webhook_id)
    except Exception:  # noqa: BLE001 - sem URL externa configurada
        return f"/api/webhook/{webhook_id}"


class Home360CentralConfigFlow(ConfigFlow, domain=DOMAIN):
    """Configuração inicial (uma única instância)."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Passo único: define o serviço de push e gera o webhook."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        if user_input is not None:
            webhook_id = f"h360_{secrets.token_hex(20)}"
            return self.async_create_entry(
                title="Home360 Feedback Central",
                data={
                    CONF_WEBHOOK_ID: webhook_id,
                    CONF_NOTIFY_SERVICE: user_input.get(CONF_NOTIFY_SERVICE, "").strip(),
                    CONF_CLIENTS: {},
                },
            )

        schema = vol.Schema(
            {vol.Optional(CONF_NOTIFY_SERVICE, default=""): str}
        )
        return self.async_show_form(step_id="user", data_schema=schema)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Retorna o fluxo de options (gerenciar clientes)."""
        return Home360CentralOptionsFlow(config_entry)


class Home360CentralOptionsFlow(OptionsFlow):
    """Gerencia clientes, tokens e o serviço de push pela UI."""

    def __init__(self, entry: ConfigEntry) -> None:
        """Guarda a entry sendo editada."""
        self._entry = entry

    def _current(self) -> dict:
        """Estado atual mesclado (options sobre data)."""
        data = self._entry.data
        opts = self._entry.options
        return {
            "notify_service": opts.get(
                CONF_NOTIFY_SERVICE, data.get(CONF_NOTIFY_SERVICE, "")
            ),
            "clients": dict(
                opts.get(CONF_CLIENTS, data.get(CONF_CLIENTS, {}))
            ),
        }

    def _save(self, notify_service: str, clients: dict) -> ConfigFlowResult:
        """Grava o conjunto completo de options (substitui as anteriores)."""
        return self.async_create_entry(
            title="",
            data={
                CONF_NOTIFY_SERVICE: notify_service,
                CONF_CLIENTS: clients,
            },
        )

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Menu principal."""
        return self.async_show_menu(
            step_id="init",
            menu_options=["add_client", "remove_client", "notify", "info"],
        )

    async def async_step_add_client(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Adiciona um cliente e gera o token automaticamente."""
        errors: dict[str, str] = {}
        cur = self._current()

        if user_input is not None:
            client_id = user_input["client_id"].strip()
            if not client_id:
                errors["client_id"] = "invalid_client_id"
            elif client_id in cur["clients"]:
                errors["client_id"] = "client_exists"
            else:
                token = secrets.token_hex(16)
                cur["clients"][client_id] = token
                # Mostra o token e a URL numa notificação para você copiar.
                url = _webhook_url(self.hass, self._entry.data[CONF_WEBHOOK_ID])
                async_create(
                    self.hass,
                    (
                        f"Cliente **{client_id}** adicionado. Configure a integração "
                        f"no HA do cliente com estes dados:\n\n"
                        f"**URL do webhook:**\n`{url}`\n\n"
                        f"**Token:**\n`{token}`"
                    ),
                    title=f"Home360 Feedback: cliente {client_id}",
                    notification_id=f"{DOMAIN}_novo_{client_id}",
                )
                return self._save(cur["notify_service"], cur["clients"])

        return self.async_show_form(
            step_id="add_client",
            data_schema=vol.Schema({vol.Required("client_id"): str}),
            errors=errors,
        )

    async def async_step_remove_client(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Remove um ou mais clientes."""
        cur = self._current()
        existentes = sorted(cur["clients"])

        if not existentes:
            return self.async_abort(reason="no_clients")

        if user_input is not None:
            for client_id in user_input.get("clients", []):
                cur["clients"].pop(client_id, None)
            return self._save(cur["notify_service"], cur["clients"])

        return self.async_show_form(
            step_id="remove_client",
            data_schema=vol.Schema(
                {vol.Required("clients", default=[]): cv.multi_select(existentes)}
            ),
        )

    async def async_step_notify(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Altera o serviço de push."""
        cur = self._current()

        if user_input is not None:
            return self._save(
                user_input.get(CONF_NOTIFY_SERVICE, "").strip(), cur["clients"]
            )

        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_NOTIFY_SERVICE, default=cur["notify_service"]
                ): str
            }
        )
        return self.async_show_form(step_id="notify", data_schema=schema)

    async def async_step_info(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Mostra a URL do webhook e os clientes/tokens no próprio diálogo."""
        cur = self._current()

        if user_input is not None:
            # Botão OK: fecha preservando as options atuais.
            return self._save(cur["notify_service"], cur["clients"])

        url = _webhook_url(self.hass, self._entry.data[CONF_WEBHOOK_ID])
        if cur["clients"]:
            linhas = "\n".join(
                f"- **{cid}**: `{tok}`" for cid, tok in sorted(cur["clients"].items())
            )
        else:
            linhas = "_(nenhum cliente ainda)_"

        info = f"**URL do webhook:**\n`{url}`\n\n**Clientes:**\n{linhas}"
        return self.async_show_form(
            step_id="info",
            data_schema=vol.Schema({}),
            description_placeholders={"info": info},
        )
