# Home360 Feedback Central

Integração **mestre**, instalada no Home Assistant da empresa. Recebe os reports
enviados pelos HAs dos clientes (pela integração
[Home360 Feedback](https://github.com/home360/Home-Assistant-Feedback)) e faz
tudo **pela UI** — sem editar YAML.

- Registra o **webhook automaticamente** (nada de packages).
- **Adiciona clientes pela interface**, gerando o token de cada um.
- **Valida** token + cliente + categoria antes de aceitar.
- A cada report válido: **notificação persistente** (ticket) + **push** no celular
  + **evento** `home360_feedback_central_report` + atualiza o **sensor** de último report.

```
HA dos Clientes ──POST /api/webhook/<id> (+token)──▶ Home360 Feedback Central
                                                       • valida token/cliente
                                                       • ticket + push + evento
                                                       • sensor.ultimo_report
```

---

## Instalação

1. Copie `custom_components/home360_feedback_central` para o `<config>/custom_components/`
   do **HA da empresa** (ou instale via HACS como repositório custom).
2. Reinicie o Home Assistant.
3. **Configurações → Dispositivos e serviços → Adicionar integração → Home360 Feedback Central**.
4. (Opcional) informe o **serviço de push**, ex.: `notify.mobile_app_seu_celular`.
   Pode deixar em branco e definir depois.

O webhook já está registrado. Não precisa mexer em `configuration.yaml`.

---

## Adicionar um cliente (pela UI)

1. Em **Home360 Feedback Central → Configurar** (ícone de engrenagem).
2. Menu **Adicionar cliente** → informe a identificação (ex.: `casa_silva`).
3. Uma **notificação** aparece com a **URL do webhook** e o **token** gerado.
4. No HA daquele cliente, configure a integração Home360 Feedback com esses dados.

Outras opções do menu:
- **Remover cliente** — revoga o token na hora.
- **Alterar serviço de push** — troca o `notify.*`.
- **Ver URL e tokens** — mostra tudo de novo numa notificação (para reconfigurar um cliente).

---

## O que a integração cria

Para **cada cliente cadastrado**, um dispositivo "Feedback `<cliente>`" com duas entidades:

| Entidade | Para quê |
|----------|----------|
| `sensor.feedback_<cliente>` | Feedback: estado = total de reports; atributos = últimas 10 mensagens (categoria, texto, local, data) |
| `sensor.feedback_<cliente>_monitoramento` | Monitoramento: estado = total de alertas; atributos = últimos 10 alertas N1/N2/N3 (kind, integração, entidades, mensagem, data) |

E dispara dois eventos para automações:
- **`home360_feedback_central_report`** (`cliente`, `categoria`, `texto`, `local`, `em`) — feedback.
- **`home360_feedback_central_monitor`** (`cliente`, `kind`, `integracao`, `entidades`, `mensagem`, `em`) — monitoramento.

---

## Monitoramento (Entity Monitor)

Além do feedback dos clientes, o central recebe **alertas de indisponibilidade**
da integração [Entity Monitor](https://github.com/arthurperezbessa/Entity-Monitor)
instalada em cada cliente — em vez de notificações no celular, viram um dashboard.

- A Entity Monitor manda cada **N1/N2/N3** para o mesmo webhook, com `tipo: "monitor"`,
  usando o **mesmo `client_id` e token** daquele cliente.
- O central valida o token e atualiza o `sensor.feedback_<cliente>_monitoramento`
  (sem push, sem notificação persistente — o canal é o dashboard).
- Registra no **logbook** para histórico.

---

## Segurança

Mesmo modelo da versão em package, agora gerenciado pela UI:

- **Token por cliente** — o central só aceita se o token bate com o `client_id`.
  Removeu o cliente → token deixa de valer imediatamente.
- **Validação** — ignora clientes desconhecidos, limita o texto (500) e só aceita
  categorias válidas.
- O endpoint `/api/webhook/<id>` é público por design (não passa pelo login do HA);
  a proteção real é o **token**. Recomendado: **rate limiting no Cloudflare** em
  `/api/webhook/*` (~10 req/min por IP).
- A automação/handler **só notifica e registra** — nunca controla dispositivos com
  base no conteúdo recebido.

---

## Testar

Instale a integração Home360 Feedback num cliente de teste, cadastre-o aqui pelo
menu **Adicionar cliente**, e mande uma mensagem pelo card. Deve aparecer o ticket,
o push e o `sensor.feedback_<cliente>` deve incrementar. Para o monitoramento,
configure a Entity Monitor daquele cliente com a URL/token e dispare o botão de
teste — o `sensor.feedback_<cliente>_monitoramento` deve incrementar.
