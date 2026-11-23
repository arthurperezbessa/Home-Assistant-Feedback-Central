"""Resumo diário de monitoramento: 1 push por cliente com problema.

Lê o atributo `estado` de cada `sensor.feedback_<cliente>_monitoring` (enviado
pelo Entity Monitor) e monta uma notificação por cliente listando as
integrações que tiveram **alguma entidade indisponível por pelo menos N
minutos contínuos** nas últimas 24h. Para cada integração mostra a entidade que
mais tempo ficou fora e a que mais deu flicker.

Cliente sem estado recente (HA ou internet fora do ar) gera um alerta próprio.
Cliente sem nada a reportar não gera notificação.
"""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from .const import (
    DIGEST_STALE_HOURS,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


def _fmt_duration(seconds: float) -> str:
    """Duração curta: 45s, 12m, 3h, 2d (mesma ideia do Entity Monitor)."""
    total = int(seconds or 0)
    if total <= 0:
        return "0s"
    if total < 60:
        return f"{total}s"
    minutes = total // 60
    if minutes < 60:
        return f"{minutes}m"
    hours = (minutes + 29) // 60
    if hours < 48:
        return f"{hours}h"
    return f"{hours // 24}d"


def _int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _titulo_cliente(client_id: str) -> str:
    return client_id[:1].upper() + client_id[1:]


def _monitor_entity_ids(hass: HomeAssistant, entry: ConfigEntry) -> list[str]:
    """entity_ids dos sensores de monitoramento desta entry."""
    ent_reg = er.async_get(hass)
    return [
        ent.entity_id
        for ent in er.async_entries_for_config_entry(ent_reg, entry.entry_id)
        if (ent.unique_id or "").endswith("_monitor")
    ]


def _pior_queda(integ: dict, min_seconds: int) -> dict | None:
    """Entidade que mais tempo ficou fora em 24h, se passar o corte.

    Usa `pior_queda_24h` (Entity Monitor >= 0.11, calculado sobre todas as
    entidades). Em clientes mais antigos cai para as entidades detalhadas,
    onde o corte é aplicado sobre o tempo somado — aproximação.
    """
    pior = integ.get("pior_queda_24h")
    if isinstance(pior, dict) and pior.get("nome"):
        maior = _int(pior.get("maior_queda"))
        if maior >= min_seconds:
            return {
                "nome": str(pior["nome"]),
                "tempo_fora": _int(pior.get("tempo_fora")),
                "maior_queda": maior,
                "quedas": _int(pior.get("quedas")),
                "caida_agora": bool(pior.get("caida_agora")),
            }
        return None

    # Fallback (estado versão 1): sem a maior queda contínua, usa o tempo
    # somado nas 24h das entidades detalhadas.
    melhor: dict | None = None
    for ent in integ.get("entidades") or []:
        if not isinstance(ent, dict):
            continue
        dia = ent.get("dia") if isinstance(ent.get("dia"), dict) else {}
        tempo = _int(dia.get("outage_downtime"))
        if tempo < min_seconds:
            continue
        if melhor is None or tempo > melhor["tempo_fora"]:
            melhor = {
                "nome": str(ent.get("nome") or ent.get("entity_id") or "?"),
                "tempo_fora": tempo,
                "maior_queda": _int(dia.get("longest_outage")) or tempo,
                "quedas": _int(dia.get("outages")),
                "caida_agora": bool(ent.get("caida_agora")),
            }
    return melhor


def _pior_flicker(integ: dict) -> dict | None:
    """Entidade com mais flickers em 24h na integração."""
    pior = integ.get("pior_flicker_24h")
    if isinstance(pior, dict) and pior.get("nome"):
        flickers = _int(pior.get("flickers"))
        if flickers > 0:
            return {"nome": str(pior["nome"]), "flickers": flickers}
        return None

    melhor: dict | None = None
    for ent in integ.get("entidades") or []:
        if not isinstance(ent, dict):
            continue
        dia = ent.get("dia") if isinstance(ent.get("dia"), dict) else {}
        flickers = _int(dia.get("flickers"))
        if flickers <= 0:
            continue
        if melhor is None or flickers > melhor["flickers"]:
            melhor = {
                "nome": str(ent.get("nome") or ent.get("entity_id") or "?"),
                "flickers": flickers,
            }
    return melhor


def _linha_queda(integracao: str, pior: dict) -> str:
    """'Tuya · Luz Quarto 25m (1 queda)'."""
    tempo = _fmt_duration(pior["tempo_fora"])
    if pior["caida_agora"]:
        detalhe = "caída agora"
    elif pior["quedas"] > 1:
        detalhe = (
            f"{pior['quedas']} quedas, maior "
            f"{_fmt_duration(pior['maior_queda'])}"
        )
    else:
        detalhe = "1 queda"
    return f"{integracao} · {pior['nome']} {tempo} ({detalhe})"


def build_client_digest(
    estado: dict, sincronizado_em: str | None, min_minutes: int, now
) -> dict | None:
    """Monta o resumo de um cliente, ou None se não há nada a reportar.

    Retorna {"tipo": "sem_contato" | "quedas", "titulo", "mensagem"}.
    """
    idade_horas = None
    sync = dt_util.parse_datetime(sincronizado_em or "")
    if sync is not None:
        idade_horas = (now - sync).total_seconds() / 3600

    if idade_horas is None or idade_horas > DIGEST_STALE_HOURS:
        quando = (
            f"há {_fmt_duration(idade_horas * 3600)}"
            if idade_horas is not None
            else "desde o último reinício do central"
        )
        return {
            "tipo": "sem_contato",
            "titulo": "⚫ Sem contato",
            "mensagem": (
                f"Nenhum estado recebido {quando}. "
                "Verifique o Home Assistant e a internet do cliente."
            ),
        }

    min_seconds = max(0, min_minutes) * 60
    linhas: list[str] = []
    integracoes = estado.get("integracoes")
    for integ in integracoes if isinstance(integracoes, list) else []:
        if not isinstance(integ, dict):
            continue
        pior = _pior_queda(integ, min_seconds)
        if pior is None:
            continue
        nome_integ = str(integ.get("integracao") or integ.get("slug") or "?")
        linhas.append(_linha_queda(nome_integ, pior))
        flicker = _pior_flicker(integ)
        if flicker is not None:
            linhas.append(
                f"  ⚡ {flicker['nome']}: {flicker['flickers']} flickers"
            )

    if not linhas:
        return None

    caidas = _int(estado.get("caidas_agora"))
    titulo = "🔴 Caída agora" if caidas else "🟠 Quedas em 24h"
    return {
        "tipo": "quedas",
        "titulo": titulo,
        "mensagem": "\n".join(linhas),
    }


def build_digest(
    hass: HomeAssistant, entry: ConfigEntry, min_minutes: int
) -> list[dict]:
    """Resumos a enviar agora, um por cliente com algo a reportar."""
    now = dt_util.now()
    saida: list[dict] = []

    for entity_id in _monitor_entity_ids(hass, entry):
        state = hass.states.get(entity_id)
        if state is None:
            continue
        cliente = str(state.attributes.get("cliente") or "")
        if not cliente:
            continue
        estado = state.attributes.get("estado")
        resumo = build_client_digest(
            estado if isinstance(estado, dict) else {},
            state.attributes.get("sincronizado_em"),
            min_minutes,
            now,
        )
        if resumo is None:
            continue
        saida.append({"cliente": cliente, **resumo})

    # Sem contato primeiro, depois caída agora, depois o resto.
    ordem = {"sem_contato": 0, "quedas": 1}
    saida.sort(
        key=lambda r: (
            ordem.get(r["tipo"], 9),
            0 if r["titulo"].startswith("🔴") else 1,
            r["cliente"],
        )
    )
    return saida


async def async_send_digest(
    hass: HomeAssistant,
    entry: ConfigEntry,
    notify_service: str,
    min_minutes: int,
) -> int:
    """Envia o resumo diário. Retorna quantos clientes foram notificados."""
    resumos = build_digest(hass, entry, min_minutes)
    if not resumos:
        _LOGGER.info("Home360 Monitor: resumo diário sem nada a reportar")
        return 0

    if not notify_service:
        _LOGGER.warning(
            "Home360 Monitor: %s cliente(s) no resumo diário, mas nenhum "
            "serviço de notificação configurado",
            len(resumos),
        )
        return 0

    domain, _, service = notify_service.partition(".")
    if not service:
        domain, service = "notify", notify_service
    if not hass.services.has_service(domain, service):
        _LOGGER.warning(
            "Home360 Monitor: serviço de notificação %s indisponível",
            notify_service,
        )
        return 0

    for resumo in resumos:
        cliente = resumo["cliente"]
        await hass.services.async_call(
            domain,
            service,
            {
                "title": f"{resumo['titulo']} · {_titulo_cliente(cliente)}",
                "message": resumo["mensagem"],
                "data": {
                    # tag por cliente: o resumo de hoje substitui o de ontem.
                    "tag": f"{DOMAIN}_digest_{cliente}",
                    "group": f"{DOMAIN}_digest",
                },
            },
            blocking=False,
        )
    _LOGGER.info(
        "Home360 Monitor: resumo diário enviado para %s cliente(s)",
        len(resumos),
    )
    return len(resumos)
