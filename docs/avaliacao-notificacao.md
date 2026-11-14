# Avaliação: notificar o tutor quando o animal estiver pronto para buscar

**Conclusão: é viável.** Foi implementada uma versão sem custo e sem serviço externo
(aviso dentro do aplicativo + atalho de WhatsApp). Canais automáticos (SMS, e-mail,
WhatsApp oficial) são possíveis, mas dependem de contas e serviços de terceiros.

## Opções analisadas

| Canal | Como funciona | Depende de terceiros? | Esforço | Situação |
|-------|---------------|-----------------------|---------|----------|
| **Aviso no aplicativo** | Funcionário clica em “🔔 Pronto p/ buscar”; o aviso fica gravado na tabela `Notificacao` e aparece na tela inicial do aplicativo do tutor até ele tocar em “Entendi”. | Não | Baixo | **Implementado** |
| **WhatsApp por link (click-to-chat)** | O botão “WhatsApp” abre `wa.me/55DDDNÚMERO?text=…` com a mensagem pronta; o funcionário só aperta enviar. | Não (usa o WhatsApp do próprio pet shop) | Baixo | **Implementado** (envio manual) |
| **E-mail (SMTP)** | O sistema envia o e-mail sozinho ao clicar no botão. | Sim: servidor SMTP / conta de e-mail | Médio | Viável; não implementado |
| **SMS** | Envio automático por API de um provedor de SMS. | Sim: conta e créditos pagos | Médio | Viável; não implementado |
| **WhatsApp Business API** | Mensagem automática pelo número oficial da empresa. | Sim: conta verificada, provedor e modelos de mensagem aprovados | Alto | Viável para produção; fora do escopo acadêmico |
| **Push (PWA)** | Notificação no celular, mesmo com o app fechado. | Parcial: exige HTTPS, service worker e permissão do usuário | Alto | Evolução futura |

## O que foi feito

- Tabela `Notificacao` (agendamento, cliente, canal, mensagem, data de envio, lida/não lida).
- Botão **🔔 Pronto p/ buscar** em *Agendamentos* (disponível enquanto o status é *Agendado*, isto é, o pet ainda está no pet shop). A mensagem usa o nome do tutor e do animal.
- O envio fica no *Log de alterações* e na tela *Notificações* do admin.
- No aplicativo do tutor, o aviso aparece no topo da tela inicial.
- Fluxo sugerido: pet pronto → clicar em “Pronto p/ buscar” (e, se quiser, no “WhatsApp”) → tutor busca → marcar o agendamento como **Realizado**.

## Limitações atuais

- O aviso no app só é visto quando o tutor abre o aplicativo (não há push).
- O WhatsApp é manual: o sistema monta a mensagem, mas quem envia é o funcionário.
- Para automatizar, o ponto de extensão é a rota `admin_agendamento_notificar` em `app.py`: depois de gravar a `Notificacao`, chamar a função de envio do canal escolhido (e registrar o canal na coluna `Canal`).

## Recomendação

Para a entrega acadêmica, manter o que está implementado. Para uso real, o próximo passo de melhor custo-benefício é o **e-mail via SMTP**, e depois o **WhatsApp Business API**, que é o canal que o tutor mais costuma ler.
