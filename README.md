# UnaTopPet (Pets Una) — CRUD, área administrativa e aplicativo do tutor

Projeto acadêmico desenvolvido para a disciplina de Banco de Dados.

Sistema em **Python + Flask + SQLite**. O protótipo mobile (`pets_una_prot_tipo_mobile.html`) agora lê e grava no banco `Database/clinica_veterinaria.db`, e existe uma área administrativa para os funcionários do pet shop.

<img width="1138" height="751" alt="image" src="https://github.com/user-attachments/assets/04d5f101-ba9d-4c57-9326-8d998fe2be84" />

<img width="1304" height="600" alt="image" src="https://github.com/user-attachments/assets/47135c4a-99a4-45b8-9d54-3da7dcb3cc73" />

<img width="1305" height="611" alt="image" src="https://github.com/user-attachments/assets/61b8f5b1-4907-4338-85d5-862e449f0bb3" />



## Como rodar

```bash
pip install -r requirements.txt
python app.py
```

| Endereço | O que é | Acesso de demonstração |
|----------|---------|------------------------|
| http://127.0.0.1:5000/ | Aplicativo do tutor (protótipo mobile ligado ao banco) | `ana.mendes@email.com` / `123456` (ou “Criar Conta”) |
| http://127.0.0.1:5000/admin | Área administrativa do pet shop | `admin` / `admin123` |

> **Troque as senhas de demonstração** antes de qualquer uso real. As telas usam Tailwind e fontes via CDN, então precisam de internet.

Na **primeira execução** o sistema aplica `Database/script_migracao_v3.sql` (uma única vez) e antes cria o backup `Database/clinica_veterinaria_backup_v2.db`.

## Requisitos da minha parte

| Requisito | Onde está |
|-----------|-----------|
| CRUD de clientes, animais, profissionais, serviços | Admin → menus correspondentes (cadastrar, pesquisar, editar, excluir/reativar) |
| CRUD de agendamentos | Admin → Agendamentos (criar, filtrar por data/profissional/cliente/status, reagendar, cancelar) |
| CRUD de histórico de saúde | Admin → Histórico de saúde (incluindo anexos); consulta por animal (RF10) |
| Área administrativa | `/admin` com login, painel, log de alterações e backup do banco |
| Status do agendamento | **Agendado** → **Realizado** (botão “✔ Realizado” ou ao registrar o atendimento, RF09). Também existe **Cancelado** (RF07) |
| Notificação “pronto para buscar” | Botão 🔔 em Agendamentos + aviso no app do tutor + atalho WhatsApp. Avaliação completa em [`docs/avaliacao-notificacao.md`](docs/avaliacao-notificacao.md) |
| Protótipo conectado ao banco | `static/tutor/` (HTML + `app.js`) usando a API `/api/...` |

Também cobre RF06 (valida profissional livre, horário de funcionamento e serviço habilitado), RF11 (log com data e usuário), RF12 (validação dos campos) e RNF05 (backup).

## Decisões importantes (conversar com o grupo)

1. **“Excluir” = exclusão lógica.** O banco bloqueia `DELETE` por trigger e os requisitos pedem “inativar” (RF01/RF02, RNF02). Então “Excluir” marca `Ativo = 0`: o registro some das listas, mas o histórico é preservado e pode ser reativado. Só é permitido se não houver dependentes ativos (ex.: cliente com animais ativos ou agendamentos em aberto). Agendamentos não são excluídos: são **cancelados**.
2. **Status:** o banco usava “Concluído”; virou **Realizado**. Foi mantido **Cancelado** porque o índice único de horário do profissional já o considera.
3. **Alterações no banco** (todas no `script_migracao_v3.sql`): coluna `Ativo` (Cliente, Animal, Profissional, Servico, Historico_saude), `Senha_hash` e e-mail único em Cliente, e as tabelas novas `Profissional_Servico`, `Usuario_admin`, `Log_alteracao` e `Notificacao`. **O DER (`DER_clinica_veterinaria_v2.*`) ainda não reflete essas mudanças** e precisa ser atualizado pelo grupo.
4. **Serviços por profissional:** a carga inicial vem dos agendamentos já existentes. Na base de exemplo, **Dra. Fernanda não tem serviço habilitado** até alguém marcar em Admin → Profissionais → Editar.
5. **Horário de funcionamento assumido:** segunda a sexta 8h–18h, sábado 8h–12h, domingo fechado (constante `HORARIO_FUNCIONAMENTO` em `regras.py`). Ajustar ao horário real.
6. **Anexo no agendamento:** o campo “Anexo de mídia” do protótipo foi removido da tela de agendamento, porque no banco o anexo pertence ao **histórico de saúde**, não ao agendamento.
7. **CPF:** valida só os 11 dígitos (sem dígito verificador), pois os CPFs de exemplo do banco não passariam.
8. O tutor **não edita histórico de saúde** no app (só consulta); quem registra é o profissional na área administrativa.

## Estrutura

```
app.py            rotas: área administrativa + API do tutor
db.py             conexão, migração automática, log de alterações
regras.py         validações e regras de agendamento
entidades.py      configuração dos cadastros simples (gera as telas genéricas)
templates/admin/  telas da área administrativa
static/tutor/     aplicativo do tutor (index.html + app.js)
Database/         banco, scripts SQL (inclui script_migracao_v3.sql) e DER
docs/             avaliação da notificação
tests/test_crud.py  testes automáticos (python tests/test_crud.py)
```

## Backup e testes

- Admin → **Baixar backup do banco** gera uma cópia consistente do SQLite.
- `python tests/test_crud.py` roda os testes sobre uma cópia temporária do banco (não altera o seu).
