"""
Testes automáticos do sistema. Rodam sobre uma CÓPIA temporária do banco.
Uso (na pasta do projeto):  python tests/test_crud.py
"""
import os, sys, sqlite3, io, re, shutil, tempfile
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = tempfile.mkdtemp()
BANCO_TESTE = os.path.join(TMP, "t.db")
shutil.copyfile(os.path.join(RAIZ, "Database", "clinica_veterinaria.db"), BANCO_TESTE)
os.environ["UNATOPPET_DB"] = BANCO_TESTE
sys.path.insert(0, RAIZ)
from datetime import datetime, timedelta
import app as A

ok = fail = 0
def check(nome, cond, extra=""):
    global ok, fail
    if cond: ok += 1; print("  ✓", nome)
    else: fail += 1; print("  ✗ FALHOU:", nome, extra)

con = sqlite3.connect(BANCO_TESTE, isolation_level=None); con.row_factory = sqlite3.Row
print("== Migração")
check("user_version=3", con.execute("pragma user_version").fetchone()[0] == 3)
check("status só Agendado/Realizado", {r[0] for r in con.execute("select distinct status from Agendamento")} <= {"Agendado","Realizado"})
check("Profissional_Servico preenchida", con.execute("select count(*) from Profissional_Servico").fetchone()[0] == 3)
check("backup v2 criado", os.path.exists(BANCO_TESTE.replace(".db", "_backup_v2.db")))
check("migrar() é idempotente", A.banco.migrar() is False)
try:
    con.execute("insert into Agendamento(Data_Hora,status,ID_Servico,ID_Cliente,ID_Animal,ID_Profissional) values ('2030-01-01 10:00:00','Concluído',1,1,1,1)")
    check("trigger de status bloqueia valor inválido", False)
except sqlite3.IntegrityError: check("trigger de status bloqueia valor inválido", True)
try:
    con.execute("delete from Cliente where ID_Cliente=1"); check("DELETE físico segue bloqueado", False)
except sqlite3.IntegrityError: check("DELETE físico segue bloqueado", True)

c = A.app.test_client()
def csrf(cl):
    with cl.session_transaction() as s: s["_csrf"] = "tok"
    return {"_csrf": "tok"}
def post(cl, url, data=None, **kw):
    d = {**(data or {}), **csrf(cl)}
    return cl.post(url, data=d, **kw)
def flashes(cl):
    with cl.session_transaction() as s: return [m for _, m in s.get("_flashes", [])]

print("== Acesso admin")
r = c.get("/admin"); check("sem login redireciona", r.status_code == 302 and "/admin/login" in r.location)
r = post(c, "/admin/login", {"login": "admin", "senha": "errada"}); check("senha errada não entra", r.status_code == 200)
r = c.post("/admin/login", data={"login":"admin","senha":"admin123"}); check("POST sem CSRF é recusado", r.status_code == 400)
r = post(c, "/admin/login", {"login": "admin", "senha": "admin123"}); check("login admin ok", r.status_code == 302)
for u in ["/admin","/admin/clientes","/admin/animais","/admin/profissionais","/admin/servicos","/admin/agendamentos","/admin/historico","/admin/notificacoes","/admin/log",
          "/admin/clientes/novo","/admin/animais/novo","/admin/profissionais/novo","/admin/servicos/novo","/admin/agendamentos/novo","/admin/historico/novo",
          "/admin/clientes/1/editar","/admin/profissionais/1/editar","/admin/servicos/1/editar","/admin/agendamentos/3/editar","/admin/historico/1/editar",
          "/admin/historico?animal=1","/admin/agendamentos?status=Agendado&data=2026-10-30","/admin/clientes?q=ana&inativos=1"]:
    r = c.get(u); check(f"GET {u} = 200", r.status_code == 200, r.status_code)
check("entidade inexistente = 404", c.get("/admin/xyz").status_code == 404)

print("== Clientes (RF01, RF12)")
r = post(c, "/admin/clientes/novo", {"Nome": "", "CPF": "123", "Telefone": "1", "Email": "x"}); html = r.get_data(as_text=True)
check("campos obrigatórios/validação", r.status_code == 200 and "Nome completo é obrigatório" in html and "CPF deve ter 11" in html and "Telefone inválido" in html and "E-mail inválido" in html)
novo = {"Nome": "Teste Silva", "CPF": "11122233344", "Telefone": "31988887777", "Email": "Teste@Email.com", "Endereco": "Rua A", "senha": "abc123"}
r = post(c, "/admin/clientes/novo", novo); check("cria cliente", r.status_code == 302)
cli = con.execute("select * from Cliente where Nome='Teste Silva'").fetchone()
check("CPF/telefone/e-mail normalizados", cli["CPF"] == "111.222.333-44" and cli["Telefone"] == "(31) 98888-7777" and cli["Email"] == "teste@email.com")
check("senha gravada como hash", cli["Senha_hash"] and cli["Senha_hash"] != "abc123")
r = post(c, "/admin/clientes/novo", {**novo, "Nome": "Outro", "Email": "outro@x.com"}); check("CPF duplicado recusado", "CPF" in r.get_data(as_text=True) and r.status_code == 200)
r = post(c, "/admin/clientes/novo", {**novo, "Nome": "Outro", "CPF": "99988877766"}); check("e-mail duplicado recusado", "e-mail" in r.get_data(as_text=True))
r = post(c, f"/admin/clientes/{cli['ID_Cliente']}/editar", {**novo, "Nome": "Teste Silva Jr", "senha": ""}); check("edita cliente", r.status_code == 302)
check("nome atualizado", con.execute("select Nome from Cliente where ID_Cliente=?", (cli["ID_Cliente"],)).fetchone()[0] == "Teste Silva Jr")
CID = cli["ID_Cliente"]

print("== Animais (RF02)")
an = {"ID_cliente": str(CID), "nome": "Bolt", "especie": "Canina", "raca": "Vira-lata", "data_nascimento": "2023-01-10", "sexo": "M", "porte": "Médio"}
r = post(c, "/admin/animais/novo", {**an, "raca": ""}); check("raça obrigatória", "Raça é obrigatório" in r.get_data(as_text=True))
r = post(c, "/admin/animais/novo", {**an, "data_nascimento": "2999-01-01"}); check("nascimento no futuro recusado", "futuro" in r.get_data(as_text=True))
r = post(c, "/admin/animais/novo", an); check("cria animal", r.status_code == 302)
AID = con.execute("select ID_animal from Animal where nome='Bolt'").fetchone()[0]

print("== Serviços (RF04) e Profissionais (RF03)")
r = post(c, "/admin/servicos/novo", {"Nome_Servico": "Banho e Tosa", "Categoria": "Estética", "duracao_min": "60", "Preco": "85,50"}); check("cria serviço", r.status_code == 302)
SID = con.execute("select Id_servico, Preco from Servico where Nome_Servico='Banho e Tosa'").fetchone()
check("preço com vírgula", SID["Preco"] == 85.5); SERV = SID["Id_servico"]
r = post(c, "/admin/servicos/novo", {"Nome_Servico": "Banho e Tosa", "Preco": "10"}); check("nome de serviço único", "nome de serviço" in r.get_data(as_text=True))
r = post(c, "/admin/servicos/novo", {"Nome_Servico": "X", "Preco": "-5"}); check("valor deve ser > 0", "maior que zero" in r.get_data(as_text=True))
r = post(c, "/admin/profissionais/novo", {"Nome": "Lucas Tosador", "CRMV": "ESTET-001", "Especialidade": "Estética", "Telefone": "31977776666", "servicos": [str(SERV)]}); check("cria profissional + serviços", r.status_code == 302)
PID = con.execute("select ID_Profissional from Profissional where CRMV='ESTET-001'").fetchone()[0]
check("serviço habilitado gravado", con.execute("select count(*) from Profissional_Servico where ID_Profissional=? and ID_Servico=?", (PID, SERV)).fetchone()[0] == 1)
r = post(c, "/admin/profissionais/novo", {"Nome": "Dup", "CRMV": "ESTET-001"}); check("CRMV único", "CRMV" in r.get_data(as_text=True))

print("== Agendamentos (RF05-RF07)")
hoje = datetime.now()
seg = hoje + timedelta(days=(7 - hoje.weekday()) % 7 or 7)       # próxima segunda
seg = seg.replace(hour=10, minute=0, second=0, microsecond=0)
def ag(data, serv=SERV, prof=PID, cli=CID, ani=AID, **kw):
    return post(c, "/admin/agendamentos/novo", {"ID_Cliente": str(cli), "ID_Animal": str(ani), "ID_Servico": str(serv), "ID_Profissional": str(prof), "Data_Hora": data.strftime("%Y-%m-%dT%H:%M")}, **kw)
r = ag(seg); check("cria agendamento válido", r.status_code == 302, r.get_data(as_text=True)[:300])
AG1 = con.execute("select * from Agendamento where ID_Profissional=? ", (PID,)).fetchone()
check("status inicial Agendado", AG1["status"] == "Agendado")
r = ag(seg + timedelta(minutes=30)); check("conflito de horário (sobreposição) recusado", "já tem um agendamento" in r.get_data(as_text=True))
r = ag(seg + timedelta(minutes=60)); check("horário logo após o término é aceito", r.status_code == 302)
r = ag(seg.replace(hour=7)); check("antes do horário de funcionamento recusado", "Fora do horário" in r.get_data(as_text=True))
r = ag(seg.replace(hour=17, minute=30)); check("serviço que ultrapassa o fechamento recusado", "Fora do horário" in r.get_data(as_text=True))
dom = seg + timedelta(days=6); r = ag(dom); check("domingo recusado", "não funciona neste dia" in r.get_data(as_text=True))
r = ag(hoje - timedelta(days=2)); check("data passada recusada", "já passou" in r.get_data(as_text=True))
r = ag(seg + timedelta(days=1), serv=1); check("profissional não habilitado no serviço recusado", "não está habilitado" in r.get_data(as_text=True))
r = ag(seg + timedelta(days=1), cli=1); check("animal de outro tutor recusado", "não pertence ao cliente" in r.get_data(as_text=True))
r = post(c, f"/admin/agendamentos/{AG1['ID_Agendamento']}/editar", {"ID_Cliente": str(CID), "ID_Animal": str(AID), "ID_Servico": str(SERV), "ID_Profissional": str(PID), "Data_Hora": (seg + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M")})
check("reagendar ok (ignora o próprio horário)", r.status_code == 302)
check("data alterada", con.execute("select Data_Hora from Agendamento where ID_Agendamento=?", (AG1["ID_Agendamento"],)).fetchone()[0][:10] == (seg + timedelta(days=2)).strftime("%Y-%m-%d"))
for q in ["?data="+(seg + timedelta(days=2)).strftime("%Y-%m-%d"), f"?profissional={PID}", "?cliente=Teste", "?status=Agendado"]:
    h = c.get("/admin/agendamentos"+q).get_data(as_text=True); check(f"filtro {q[:22]}", "Bolt" in h)

print("== Status e notificação")
AGID = AG1["ID_Agendamento"]
r = post(c, f"/admin/agendamentos/{AGID}/notificar"); check("notificar tutor", r.status_code == 302)
check("notificação gravada", con.execute("select count(*) from Notificacao where ID_Agendamento=?", (AGID,)).fetchone()[0] == 1)
h = c.get("/admin/agendamentos").get_data(as_text=True); check("link WhatsApp na lista", "wa.me/5531988887777" in h)
r = post(c, f"/admin/agendamentos/{AGID}/realizado"); check("marcar Realizado", con.execute("select status from Agendamento where ID_Agendamento=?", (AGID,)).fetchone()[0] == "Realizado")
r = post(c, f"/admin/agendamentos/{AGID}/cancelar"); check("não cancela Realizado", con.execute("select status from Agendamento where ID_Agendamento=?", (AGID,)).fetchone()[0] == "Realizado")
r = post(c, f"/admin/agendamentos/{AGID}/notificar"); check("não notifica Realizado", con.execute("select count(*) from Notificacao").fetchone()[0] == 1)
AG2 = con.execute("select ID_Agendamento from Agendamento where ID_Profissional=? and status='Agendado'", (PID,)).fetchone()[0]
r = post(c, f"/admin/agendamentos/{AG2}/cancelar"); check("cancelar Agendado", con.execute("select status from Agendamento where ID_Agendamento=?", (AG2,)).fetchone()[0] == "Cancelado")
r = ag(seg + timedelta(minutes=60)); check("horário de agendamento cancelado volta a ficar livre", r.status_code == 302)

print("== Histórico de saúde (RF08-RF10)")
AG3 = con.execute("select ID_Agendamento from Agendamento where ID_Profissional=? and status='Agendado'", (PID,)).fetchone()[0]
r = c.get(f"/admin/historico/novo?agendamento={AG3}"); h = r.get_data(as_text=True); check("form pré-preenchido pelo agendamento", f'value="{AG3}" data-animal' in h and "selected" in h)
r = post(c, "/admin/historico/novo", {"ID_Agendamento": str(AG3), "ID_animal": str(AID), "ID_Profissional": str(PID), "data_registro": seg.strftime("%Y-%m-%dT%H:%M"), "tipo_registro": "Observação", "descricao": "Banho feito, pelagem ok.", "anexo_url": "foto.jpg", "anexo_tipo": "imagem"})
check("cria histórico", r.status_code == 302, r.get_data(as_text=True)[:300])
check("RF09: agendamento virou Realizado", con.execute("select status from Agendamento where ID_Agendamento=?", (AG3,)).fetchone()[0] == "Realizado")
check("anexo gravado", con.execute("select count(*) from Anexo_midia where url_midia='foto.jpg'").fetchone()[0] == 1)
r = post(c, "/admin/historico/novo", {"ID_Agendamento": str(AG2), "ID_animal": str(AID), "ID_Profissional": str(PID), "data_registro": seg.strftime("%Y-%m-%dT%H:%M"), "descricao": "x"}); check("agendamento cancelado não gera atendimento", "cancelado" in r.get_data(as_text=True))
r = post(c, "/admin/historico/novo", {"ID_Agendamento": str(AG3), "ID_animal": "1", "ID_Profissional": str(PID), "data_registro": seg.strftime("%Y-%m-%dT%H:%M"), "descricao": "x"}); check("animal diferente do agendamento recusado", "mesmo do agendamento" in r.get_data(as_text=True))
r = post(c, "/admin/historico/novo", {"ID_animal": str(AID), "ID_Profissional": str(PID), "data_registro": "", "descricao": ""}); check("descrição e data obrigatórias", "descrição é obrigatória" in r.get_data(as_text=True).lower() or "obrigatória" in r.get_data(as_text=True))
HID = con.execute("select ID_historico from Historico_saude where descricao like 'Banho feito%'").fetchone()[0]
r = post(c, f"/admin/historico/{HID}/editar", {"ID_animal": str(AID), "ID_Profissional": str(PID), "data_registro": seg.strftime("%Y-%m-%dT%H:%M"), "tipo_registro": "Observação", "descricao": "Editado."}); check("edita histórico", r.status_code == 302)
h = c.get(f"/admin/historico?animal={AID}").get_data(as_text=True); check("RF10: histórico por animal", "Editado." in h and "Bolt" in h)
r = post(c, f"/admin/historico/{HID}/inativar"); check("exclusão lógica do histórico", con.execute("select Ativo from Historico_saude where ID_historico=?", (HID,)).fetchone()[0] == 0)
check("some da lista padrão", "Editado." not in c.get(f"/admin/historico?animal={AID}").get_data(as_text=True))
post(c, f"/admin/historico/{HID}/reativar"); check("reativa histórico", con.execute("select Ativo from Historico_saude where ID_historico=?", (HID,)).fetchone()[0] == 1)

print("== Exclusão lógica com proteção de dependentes (RNF02)")
r = post(c, f"/admin/clientes/{CID}/inativar"); check("cliente com animal ativo não é excluído", con.execute("select Ativo from Cliente where ID_Cliente=?", (CID,)).fetchone()[0] == 1 and any("animais ativos" in m for m in flashes(c)))
ag(seg + timedelta(days=4))  # garante um agendamento em aberto
r = post(c, f"/admin/profissionais/{PID}/inativar"); check("profissional com agendamento aberto não é excluído", con.execute("select Ativo from Profissional where ID_Profissional=?", (PID,)).fetchone()[0] == 1)
post(c, f"/admin/agendamentos/{AG3}/cancelar")  # Realizado: não cancela
open_ids = [r[0] for r in con.execute("select ID_Agendamento from Agendamento where status='Agendado' and ID_Cliente=?", (CID,))]
for i in open_ids: post(c, f"/admin/agendamentos/{i}/cancelar")
r = post(c, f"/admin/animais/{AID}/inativar"); check("animal sem agendamento aberto é excluído (lógico)", con.execute("select Ativo from Animal where ID_animal=?", (AID,)).fetchone()[0] == 0)
r = post(c, f"/admin/clientes/{CID}/inativar"); check("cliente sem dependentes é excluído (lógico)", con.execute("select Ativo from Cliente where ID_Cliente=?", (CID,)).fetchone()[0] == 0)
check("registro continua no banco", con.execute("select count(*) from Cliente where ID_Cliente=?", (CID,)).fetchone()[0] == 1)
check("excluído some da lista", "Teste Silva" not in c.get("/admin/clientes").get_data(as_text=True) and "Teste Silva" in c.get("/admin/clientes?inativos=1").get_data(as_text=True))
post(c, f"/admin/animais/{AID}/reativar"); check("animal não reativa com tutor inativo", con.execute("select Ativo from Animal where ID_animal=?", (AID,)).fetchone()[0] == 0)
post(c, f"/admin/clientes/{CID}/reativar"); post(c, f"/admin/animais/{AID}/reativar")
check("reativa cliente e animal", con.execute("select Ativo from Cliente where ID_Cliente=?", (CID,)).fetchone()[0] == 1 and con.execute("select Ativo from Animal where ID_animal=?", (AID,)).fetchone()[0] == 1)
r = ag(seg + timedelta(days=3), cli=CID); 
post(c, f"/admin/clientes/{CID}/inativar"); 

print("== Backup (RNF05) e log (RF11)")
r = c.get("/admin/backup"); check("backup baixa um SQLite válido", r.status_code == 200 and r.data[:15] == b"SQLite format 3")
log = con.execute("select Usuario, Tabela, Acao from Log_alteracao").fetchall()
check("log registra usuário admin", any(l["Usuario"] == "admin:admin" and l["Tabela"] == "Cliente" and l["Acao"] == "incluir" for l in log))
check("log registra reagendar/cancelar/realizar/notificar", {"reagendar","cancelar","realizar","notificar"} <= {l["Acao"] for l in log})
check("log não vaza senha", not any("abc123" in (d[0] or "") for d in con.execute("select Detalhes from Log_alteracao")))

print("== API do tutor")
t = A.app.test_client()
H = {"X-Requested-With": "fetch"}
r = t.get("/api/dados", headers=H); check("sem sessão = 401", r.status_code == 401)
r = t.post("/api/login", json={"email": "ana.mendes@email.com", "senha": "123456"}); check("POST sem cabeçalho X-Requested-With = 400", r.status_code == 400)
r = t.post("/api/login", json={"email": "ana.mendes@email.com", "senha": "errada"}, headers=H); check("senha errada = 401", r.status_code == 401)
r = t.post("/api/login", json={"email": "ana.mendes@email.com", "senha": "123456"}, headers=H); check("login tutor (e-mail em qualquer caixa)", r.status_code == 200)
d = t.get("/api/dados", headers=H).get_json()
check("dados do tutor", d["cliente"]["nome"].startswith("Ana") and len(d["pets"]) == 1 and d["pets"][0]["nome"] == "Thor")
check("histórico do pet (seed)", len(d["historico"]) == 1 and d["historico"][0]["pet_id"] == 1)
check("profissionais trazem serviços habilitados", all("servicos" in p for p in d["profissionais"]))
r = t.post("/api/pets", json={"nome": "Mimi", "especie": "Felina", "raca": "Persa", "porte": "Pequeno", "sexo": "F", "data_nascimento": "2024-05-01"}, headers=H); check("tutor cadastra pet", r.status_code == 200)
PET = r.get_json()["id"]
r = t.post("/api/pets", json={"nome": "", "especie": "Felina", "raca": ""}, headers=H); check("pet inválido = 400", r.status_code == 400 and "obrigatório" in r.get_json()["erro"])
r = t.put(f"/api/pets/{PET}", json={"nome": "Mimi Real", "especie": "Felina", "raca": "Persa"}, headers=H); check("tutor edita pet", r.status_code == 200)
r = t.put(f"/api/pets/{AID}", json={"nome": "Invasor", "especie": "Canina", "raca": "x"}, headers=H); check("não edita pet de outro tutor", r.status_code == 404)
r = t.post("/api/agendamentos", json={"pet_id": AID, "servico_id": 1, "prof_id": 1, "data_hora": seg.strftime("%Y-%m-%dT%H:%M")}, headers=H); check("não agenda pet de outro tutor", r.status_code == 400)
nxt = (seg + timedelta(days=7)).replace(hour=9)
r = t.post("/api/agendamentos", json={"pet_id": PET, "servico_id": 1, "prof_id": 1, "data_hora": nxt.strftime("%Y-%m-%dT%H:%M")}, headers=H); check("tutor agenda", r.status_code == 200, r.get_json())
BID = r.get_json()["id"]
r = t.post("/api/agendamentos", json={"pet_id": PET, "servico_id": 1, "prof_id": 1, "data_hora": nxt.strftime("%Y-%m-%dT%H:%M")}, headers=H); check("API aplica regra de conflito", r.status_code == 400 and "já tem" in r.get_json()["erro"])
r = t.delete(f"/api/pets/{PET}", headers=H); check("pet com agendamento aberto não é removido", r.status_code == 400 and "Cancele" in r.get_json()["erro"])
r = t.post(f"/api/agendamentos/{BID}/cancelar", headers=H); check("tutor cancela", r.status_code == 200)
r = t.delete(f"/api/pets/{PET}", headers=H); check("tutor remove pet (lógico)", r.status_code == 200)
# notificação chega ao tutor
con.commit()
ag_ana = con.execute("select ID_Agendamento from Agendamento where ID_Cliente=1 and status='Agendado'").fetchall()
if not ag_ana:
    nova = (seg + timedelta(days=14)).replace(hour=11)
    post(c, "/admin/agendamentos/novo", {"ID_Cliente": "1", "ID_Animal": "1", "ID_Servico": "1", "ID_Profissional": "1", "Data_Hora": nova.strftime("%Y-%m-%dT%H:%M")})
    ag_ana = con.execute("select ID_Agendamento from Agendamento where ID_Cliente=1 and status='Agendado'").fetchall()
post(c, f"/admin/agendamentos/{ag_ana[0][0]}/notificar")
d = t.get("/api/dados", headers=H).get_json()
check("tutor recebe notificação 'pronto para buscar'", len(d["notificacoes"]) == 1 and "pronto" in d["notificacoes"][0]["mensagem"] and "Thor" in d["notificacoes"][0]["mensagem"])
t.post(f"/api/notificacoes/{d['notificacoes'][0]['id']}/lida", headers=H)
check("marcar como lida", t.get("/api/dados", headers=H).get_json()["notificacoes"] == [])
r = t.post("/api/logout", headers=H); check("logout", t.get("/api/dados", headers=H).status_code == 401)
r = t.post("/api/cadastro", json={"Nome": "Nova Tutora", "CPF": "55566677788", "Telefone": "31955554444", "Endereco": "Rua B", "Email": "nova@x.com", "senha": "12345"}, headers=H); check("cadastro: senha curta recusada", r.status_code == 400)
r = t.post("/api/cadastro", json={"Nome": "Nova Tutora", "CPF": "55566677788", "Telefone": "31955554444", "Endereco": "Rua B", "Email": "nova@x.com", "senha": "123456"}, headers=H); check("auto-cadastro do tutor", r.status_code == 200)
check("já entra logado", t.get("/api/dados", headers=H).get_json()["cliente"]["nome"] == "Nova Tutora")
r = t.post("/api/cadastro", json={"Nome": "Dup", "CPF": "55566677788", "Telefone": "31955554444", "Email": "dup@x.com", "senha": "123456"}, headers=H); check("cadastro: CPF duplicado recusado", r.status_code == 400)
r = t.get("/"); check("GET / serve o app do tutor", r.status_code == 200 and b"app.js" in r.data)
r = t.get("/static/tutor/app.js"); check("app.js servido", r.status_code == 200)

print(f"\n{ok} ok, {fail} falhas"); sys.exit(1 if fail else 0)
