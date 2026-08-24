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

| Entidade | Para quê |
|----------|----------|
| `sensor.home360_feedback_central_ultimo_report` | Estado = total de reports; atributos = cliente, categoria, texto, local e data do último |

E dispara o evento **`home360_feedback_central_report`** (com `cliente`, `categoria`,
`texto`, `local`, `em`) para você montar automações (ex.: mandar pra um grupo de Telegram).

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
o push e o `sensor.home360_feedback_central_ultimo_report` deve incrementar.
