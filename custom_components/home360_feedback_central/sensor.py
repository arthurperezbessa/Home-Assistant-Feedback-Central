"""Um sensor de reports por cliente (contador + últimas 10 mensagens)."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from . import get_config
from .const import DOMAIN, signal_new_monitor, signal_new_report

# Quantas mensagens/alertas recentes manter por cliente.
MAX_RECENT = 10

# Chaves guardadas de cada mensagem de feedback (o cliente já é o do sensor).
_MSG_KEYS = ("categoria", "texto", "local", "em")

# Chaves guardadas de cada alerta de monitoramento.
_ALERT_KEYS = ("kind", "integracao", "entidades", "mensagem", "em")


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Cria um sensor por cliente cadastrado e limpa órfãos."""
    clients = get_config(entry)["clients"]

    _async_cleanup_orphans(hass, entry, clients)

    entities: list[SensorEntity] = []
    for client_id in clients:
        entities.append(ClientReportSensor(entry, client_id))
        entities.append(ClientMonitorSensor(entry, client_id))
    async_add_entities(entities)


@callback
def _async_cleanup_orphans(
    hass: HomeAssistant, entry: ConfigEntry, clients: dict
) -> None:
    """Remove entidades/dispositivos de clientes que não existem mais.

    Também remove o sensor único da versão anterior desta integração.
    """
    valid_uids = {f"{entry.entry_id}_{cid}" for cid in clients} | {
        f"{entry.entry_id}_{cid}_monitor" for cid in clients
    }
    ent_reg = er.async_get(hass)
    for ent in er.async_entries_for_config_entry(ent_reg, entry.entry_id):
        if ent.unique_id not in valid_uids:
            ent_reg.async_remove(ent.entity_id)

    valid_dev_ids = {(DOMAIN, f"{entry.entry_id}_{cid}") for cid in clients}
    dev_reg = dr.async_get(hass)
    for device in dr.async_entries_for_config_entry(dev_reg, entry.entry_id):
        if not (device.identifiers & valid_dev_ids):
            dev_reg.async_update_device(
                device.id, remove_config_entry_id=entry.entry_id
            )


class ClientReportSensor(RestoreEntity, SensorEntity):
    """Reports de um cliente: estado = total; atributos = últimas 10."""

    _attr_has_entity_name = True
    _attr_name = None  # usa o nome do dispositivo (o cliente)
    _attr_icon = "mdi:message-alert"
    _attr_should_poll = False

    def __init__(self, entry: ConfigEntry, client_id: str) -> None:
        """Inicializa o sensor do cliente."""
        self._entry = entry
        self._client_id = client_id
        self._attr_unique_id = f"{entry.entry_id}_{client_id}"
        self._count = 0
        self._recent: list[dict] = []
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry.entry_id}_{client_id}")},
            name=f"Feedback {client_id}",
            manufacturer="Home360",
            model="Cliente",
        )

    @property
    def native_value(self) -> int:
        """Total de reports deste cliente."""
        return self._count

    @property
    def extra_state_attributes(self) -> dict:
        """Cliente + últimas 10 mensagens + atalhos da última."""
        attrs: dict = {
            "cliente": self._client_id,
            "ultimas_mensagens": self._recent,
        }
        if self._recent:
            ultimo = self._recent[0]
            attrs.update(
                {
                    "ultima_categoria": ultimo["categoria"],
                    "ultimo_texto": ultimo["texto"],
                    "ultimo_local": ultimo["local"],
                    "ultimo_em": ultimo["em"],
                }
            )
        return attrs

    async def async_added_to_hass(self) -> None:
        """Restaura o estado anterior e assina o sinal de novos reports."""
        await super().async_added_to_hass()

        last = await self.async_get_last_state()
        if last and last.state not in (None, "unknown", "unavailable"):
            try:
                self._count = int(float(last.state))
            except ValueError:
                self._count = 0
            recentes = last.attributes.get("ultimas_mensagens")
            if isinstance(recentes, list) and recentes:
                self._recent = [
                    {key: msg.get(key, "") for key in _MSG_KEYS}
                    for msg in recentes
                    if isinstance(msg, dict)
                ][:MAX_RECENT]

        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                signal_new_report(self._entry.entry_id),
                self._handle_report,
            )
        )

    @callback
    def _handle_report(self, report: dict) -> None:
        """Se o report é deste cliente, incrementa e guarda no topo."""
        if report.get("cliente") != self._client_id:
            return
        self._count += 1
        self._recent.insert(0, {key: report.get(key, "") for key in _MSG_KEYS})
        del self._recent[MAX_RECENT:]
        self.async_write_ha_state()


class ClientMonitorSensor(RestoreEntity, SensorEntity):
    """Alertas de monitoramento (Entity Monitor) de um cliente.

    Estado = total de alertas; atributos = últimos 10 alertas N1/N2/N3.
    Fica no mesmo dispositivo do cliente, como entidade separada.
    """

    _attr_has_entity_name = True
    _attr_translation_key = "monitoramento"
    _attr_icon = "mdi:lan-disconnect"
    _attr_should_poll = False

    def __init__(self, entry: ConfigEntry, client_id: str) -> None:
        """Inicializa o sensor de monitoramento do cliente."""
        self._entry = entry
        self._client_id = client_id
        self._attr_unique_id = f"{entry.entry_id}_{client_id}_monitor"
        self._count = 0
        self._recent: list[dict] = []
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry.entry_id}_{client_id}")},
            name=f"Feedback {client_id}",
            manufacturer="Home360",
            model="Cliente",
        )

    @property
    def native_value(self) -> int:
        """Total de alertas de monitoramento deste cliente."""
        return self._count

    @property
    def extra_state_attributes(self) -> dict:
        """Cliente + últimos 10 alertas + atalhos do último."""
        attrs: dict = {
            "cliente": self._client_id,
            "ultimos_alertas": self._recent,
        }
        if self._recent:
            ultimo = self._recent[0]
            attrs.update(
                {
                    "ultimo_kind": ultimo["kind"],
                    "ultima_integracao": ultimo["integracao"],
                    "ultima_mensagem": ultimo["mensagem"],
                    "ultimo_em": ultimo["em"],
                }
            )
        return attrs

    async def async_added_to_hass(self) -> None:
        """Restaura o estado anterior e assina o sinal de novos alertas."""
        await super().async_added_to_hass()

        last = await self.async_get_last_state()
        if last and last.state not in (None, "unknown", "unavailable"):
            try:
                self._count = int(float(last.state))
            except ValueError:
                self._count = 0
            recentes = last.attributes.get("ultimos_alertas")
            if isinstance(recentes, list) and recentes:
                self._recent = [
                    {key: a.get(key, "") for key in _ALERT_KEYS}
                    for a in recentes
                    if isinstance(a, dict)
                ][:MAX_RECENT]

        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                signal_new_monitor(self._entry.entry_id),
                self._handle_alert,
            )
        )

    @callback
    def _handle_alert(self, alerta: dict) -> None:
        """Se o alerta é deste cliente, incrementa e guarda no topo."""
        if alerta.get("cliente") != self._client_id:
            return
        self._count += 1
        self._recent.insert(0, {key: alerta.get(key, "") for key in _ALERT_KEYS})
        del self._recent[MAX_RECENT:]
        self.async_write_ha_state()
