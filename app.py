"""
app.py - Sistema UnaTopPet (Pets Una): área administrativa + API do aplicativo do tutor.

  /            -> aplicativo mobile do tutor (protótipo HTML ligado ao banco)
  /api/...     -> API JSON usada pelo aplicativo do tutor
  /admin/...   -> área administrativa do pet shop (CRUD completo)

Executar:  python app.py   (veja o README.md)
"""
import io
import os
import secrets
import sqlite3
import tempfile
from datetime import date, datetime
from functools import wraps
from urllib.parse import quote

from flask import (Flask, abort, flash, jsonify, redirect, render_template,
                   request, send_file, send_from_directory, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

import db as banco
import regras
from db import get_db, registrar_log
from entidades import ENTIDADES, FK_OPCOES

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "troque-esta-chave-em-producao")
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.teardown_appcontext(banco.fechar_db)

banco.migrar()  # aplica a migração v3 uma única vez (faz backup antes)


# ============================================================================
# Utilitários, filtros de template e segurança
# ============================================================================
@app.template_filter("brl")
def brl(valor):
    if valor is None:
        return "—"
    return "R$ " + f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


@app.template_filter("data_br")
def data_br(valor):
    if not valor:
        return "—"
    return f"{valor[8:10]}/{valor[5:7]}/{valor[0:4]}"


@app.template_filter("datahora_br")
def datahora_br(valor):
    if not valor:
        return "—"
    return f"{valor[8:10]}/{valor[5:7]}/{valor[0:4]} {valor[11:16]}"


@app.template_filter("datahora_input")
def datahora_input(valor):
    """Valor do banco -> value de <input type=datetime-local>."""
    return (valor or "")[:16].replace(" ", "T")


def csrf_token():
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_hex(16)
    return session["_csrf"]


def mensagem_pronto(animal, nome_cliente):
    primeiro = (nome_cliente or "tutor(a)").split()[0]
    return f"Olá, {primeiro}! {animal} já está pronto(a) para ser buscado(a) na UnaTopPet. 🐾"


def link_whatsapp(telefone, mensagem):
    digitos = regras.so_digitos(telefone)
    if not digitos:
        return None
    if not digitos.startswith("55"):
        digitos = "55" + digitos
    return f"https://wa.me/{digitos}?text={quote(mensagem)}"


app.jinja_env.globals.update(
    csrf_token=csrf_token, mensagem_pronto=mensagem_pronto, link_whatsapp=link_whatsapp,
    entidades=ENTIDADES,
)

# Nomes amigáveis para erros de restrição do banco (RNF02)
DUPLICADOS = {
    "Cliente.CPF": "CPF",
    "uq_cliente_email": "e-mail",
    "Profissional.CRMV": "CRMV",
    "Servico.Nome_Servico": "nome de serviço",
}


def mensagem_integridade(erro):
    texto = str(erro)
    for chave, nome in DUPLICADOS.items():
        if chave in texto:
            return f"Já existe um registro com este {nome}."
    if "Agendamento.Data_Hora" in texto:
        return "Este profissional já tem um agendamento neste horário."
    if "FOREIGN KEY" in texto:
        return "Vínculo inválido: confira cliente, animal, profissional e serviço."
    return f"Não foi possível salvar: {texto}"


@app.before_request
def protecoes():
    # CSRF: formulários do admin levam _csrf; a API exige o cabeçalho X-Requested-With
    if request.method in ("POST", "PUT", "DELETE", "PATCH"):
        if request.path.startswith("/api/"):
            if request.headers.get("X-Requested-With") != "fetch":
                abort(400)
        elif not secrets.compare_digest(request.form.get("_csrf", ""), session.get("_csrf", "-")):
            abort(400, "Token CSRF inválido. Recarregue a página e tente novamente.")
    # Toda a área /admin (exceto login) exige administrador logado
    if request.path.startswith("/admin") and request.endpoint != "admin_login":
        if not session.get("admin_id"):
            return redirect(url_for("admin_login", next=request.path))


def diferencas(antigo, novos):
    mudancas = [f"{k}: {antigo[k]!r} → {v!r}" for k, v in novos.items() if antigo[k] != v]
    return "; ".join(mudancas) or "sem mudanças"


def salvar_registro(db, ent, valores, rid=None):
    """
    INSERT/UPDATE genérico dos cadastros simples. Nomes de tabela/colunas vêm
    de entidades.py (nunca do usuário); os valores sempre vão como parâmetros.
    """
    cfg = ENTIDADES[ent]
    tabela, pk = cfg["tabela"], cfg["pk"]
    if rid:
        antigo = db.execute(f"SELECT * FROM {tabela} WHERE {pk}=?", (rid,)).fetchone()
        sets = ", ".join(f"{c}=?" for c in valores)
        db.execute(f"UPDATE {tabela} SET {sets} WHERE {pk}=?", [*valores.values(), rid])
        registrar_log(db, tabela, rid, "alterar", diferencas(antigo, valores))
    else:
        colunas = ", ".join(valores)
        marcas = ", ".join("?" for _ in valores)
        cur = db.execute(f"INSERT INTO {tabela} ({colunas}) VALUES ({marcas})", list(valores.values()))
        rid = cur.lastrowid
        registrar_log(db, tabela, rid, "incluir", ", ".join(f"{k}={v!r}" for k, v in valores.items()))
    return rid


def inativar_registro(db, ent, rid):
    """Exclusão lógica. Devolve a mensagem de erro, ou None se deu certo."""
    cfg = ENTIDADES[ent]
    for sql, motivo in cfg["bloqueios"]:
        if db.execute(sql, (rid,)).fetchone()[0] > 0:
            return f"Não é possível excluir: este {cfg['singular']} {motivo}."
    db.execute(f"UPDATE {cfg['tabela']} SET Ativo=0 WHERE {cfg['pk']}=?", (rid,))
    registrar_log(db, cfg["tabela"], rid, "inativar", "exclusão lógica")
    return None


def cfg_ou_404(ent):
    if ent not in ENTIDADES:
        abort(404)
    return ENTIDADES[ent]


def registro_ou_404(db, ent, rid):
    cfg = ENTIDADES[ent]
    row = db.execute(f"SELECT * FROM {cfg['tabela']} WHERE {cfg['pk']}=?", (rid,)).fetchone()
    if row is None:
        abort(404)
    return row


# ============================================================================
# Tutor: aplicativo mobile (protótipo ligado ao banco)
# ============================================================================
@app.route("/")
def tutor_app():
    return send_from_directory(os.path.join(app.static_folder, "tutor"), "index.html")


# ============================================================================
# Admin: login, painel e backup
# ============================================================================
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        login = request.form.get("login", "").strip()
        senha = request.form.get("senha", "")
        usuario = get_db().execute(
            "SELECT * FROM Usuario_admin WHERE Login=? AND Ativo=1", (login,)
        ).fetchone()
        if usuario and check_password_hash(usuario["Senha_hash"], senha):
            session.clear()
            session["admin_id"] = usuario["ID_Usuario"]
            session["admin_login"] = usuario["Login"]
            session["admin_nome"] = usuario["Nome"]
            destino = request.args.get("next", "")
            return redirect(destino if destino.startswith("/admin") else url_for("admin_painel"))
        flash("Login ou senha incorretos.", "erro")
    return render_template("admin/login.html")


@app.route("/admin/logout", methods=["POST"])
def admin_logout():
    session.clear()
    return redirect(url_for("admin_login"))


@app.route("/admin")
def admin_painel():
    db = get_db()
    um = lambda sql, *p: db.execute(sql, p).fetchone()[0]
    hoje = date.today().isoformat()
    stats = {
        "clientes": um("SELECT COUNT(*) FROM Cliente WHERE Ativo=1"),
        "animais": um("SELECT COUNT(*) FROM Animal WHERE Ativo=1"),
        "profissionais": um("SELECT COUNT(*) FROM Profissional WHERE Ativo=1"),
        "servicos": um("SELECT COUNT(*) FROM Servico WHERE Ativo=1"),
        "abertos": um("SELECT COUNT(*) FROM Agendamento WHERE status='Agendado'"),
        "hoje": um("SELECT COUNT(*) FROM Agendamento WHERE date(Data_Hora)=? AND status<>'Cancelado'", hoje),
    }
    agora = datetime.now().strftime(regras.FORMATO_DATAHORA)
    proximos = db.execute(
        SQL_AGENDAMENTO + " WHERE ag.status='Agendado' AND ag.Data_Hora >= ? ORDER BY ag.Data_Hora LIMIT 6",
        (agora,),
    ).fetchall()
    atrasados = db.execute(
        SQL_AGENDAMENTO + " WHERE ag.status='Agendado' AND ag.Data_Hora < ? ORDER BY ag.Data_Hora",
        (agora,),
    ).fetchall()
    return render_template("admin/painel.html", stats=stats, proximos=proximos, atrasados=atrasados, hoje=hoje)


@app.route("/admin/backup")
def admin_backup():
    """RNF05 - baixa uma cópia consistente do banco de dados."""
    db = get_db()
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    destino = sqlite3.connect(tmp.name)
    db.backup(destino)
    destino.close()
    with open(tmp.name, "rb") as f:
        dados = f.read()
    os.remove(tmp.name)
    registrar_log(db, "Banco", None, "backup", "download da cópia de segurança")
    db.commit()
    nome = f"clinica_veterinaria_backup_{datetime.now():%Y%m%d_%H%M%S}.db"
    return send_file(io.BytesIO(dados), as_attachment=True, download_name=nome)


@app.route("/admin/log")
def admin_log():
    q = request.args.get("q", "").strip()
    sql = "SELECT * FROM Log_alteracao"
    params = []
    if q:
        sql += " WHERE Usuario LIKE ? OR Tabela LIKE ? OR Acao LIKE ? OR Detalhes LIKE ?"
        params = [f"%{q}%"] * 4
    linhas = get_db().execute(sql + " ORDER BY ID_Log DESC LIMIT 300", params).fetchall()
    return render_template("admin/log.html", linhas=linhas, q=q)


# ============================================================================
# Admin: CRUD de clientes, animais, profissionais e serviços (genérico)
# ============================================================================
@app.route("/admin/<ent>")
def admin_lista(ent):
    cfg = cfg_ou_404(ent)
    q = request.args.get("q", "").strip()
    inativos = request.args.get("inativos") == "1"
    alias = cfg["alias"]
    where, params = [], []
    if not inativos:
        where.append(f"{alias}.Ativo=1")
    if q:
        where.append("(" + " OR ".join(f"{c} LIKE ?" for c in cfg["busca"]) + ")")
        params += [f"%{q}%"] * len(cfg["busca"])
    sql = cfg["lista_sql"] + (" WHERE " + " AND ".join(where) if where else "")
    sql += f" ORDER BY {alias}.Ativo DESC, {cfg['ordem']}"
    linhas = get_db().execute(sql, params).fetchall()
    return render_template("admin/lista.html", ent=ent, cfg=cfg, linhas=linhas, q=q, inativos=inativos)


@app.route("/admin/<ent>/novo", methods=["GET", "POST"])
@app.route("/admin/<ent>/<int:rid>/editar", methods=["GET", "POST"])
def admin_form(ent, rid=None):
    cfg = cfg_ou_404(ent)
    db = get_db()
    atual = registro_ou_404(db, ent, rid) if rid else None
    erros = []
    valores = dict(atual) if atual else {}

    todos_servicos = db.execute("SELECT * FROM Servico WHERE Ativo=1 ORDER BY Nome_Servico").fetchall()
    habilitados = set()
    if rid and cfg.get("servicos_habilitados"):
        habilitados = {r[0] for r in db.execute(
            "SELECT ID_Servico FROM Profissional_Servico WHERE ID_Profissional=?", (rid,))}

    if request.method == "POST":
        novos, erros = regras.validar_campos(cfg, request.form)
        valores = dict(request.form)

        # chaves estrangeiras precisam existir e estar ativas
        for c in cfg["campos"]:
            if c["tipo"] == "fk" and novos.get(c["col"]):
                alvo = ENTIDADES[c["fk"]]
                ref = db.execute(f"SELECT Ativo FROM {alvo['tabela']} WHERE {alvo['pk']}=?",
                                 (novos[c["col"]],)).fetchone()
                mudou = not atual or atual[c["col"]] != novos[c["col"]]
                if ref is None or (not ref["Ativo"] and mudou):
                    erros.append(f"{c['label']}: selecione um registro ativo.")

        senha = request.form.get("senha", "")
        if cfg.get("campo_senha") and senha and len(senha) < 6:
            erros.append("A senha de acesso deve ter pelo menos 6 caracteres.")

        ids_serv = []
        if cfg.get("servicos_habilitados"):
            validos = {s["Id_servico"] for s in todos_servicos}
            ids_serv = [int(i) for i in request.form.getlist("servicos") if i.isdigit() and int(i) in validos]
            habilitados = set(ids_serv)

        if not erros:
            try:
                rid = salvar_registro(db, ent, novos, rid)
                if cfg.get("campo_senha") and senha:
                    db.execute("UPDATE Cliente SET Senha_hash=? WHERE ID_Cliente=?",
                               (generate_password_hash(senha), rid))
                    registrar_log(db, "Cliente", rid, "alterar", "senha de acesso ao app redefinida")
                if cfg.get("servicos_habilitados"):
                    db.execute("DELETE FROM Profissional_Servico WHERE ID_Profissional=?", (rid,))
                    db.executemany("INSERT INTO Profissional_Servico VALUES (?,?)",
                                   [(rid, s) for s in ids_serv])
                    registrar_log(db, "Profissional_Servico", rid, "alterar", f"serviços habilitados: {ids_serv}")
                db.commit()
                flash(f"{cfg['singular'].capitalize()} salvo com sucesso.", "ok")
                return redirect(url_for("admin_lista", ent=ent))
            except sqlite3.IntegrityError as e:
                db.rollback()
                erros.append(mensagem_integridade(e))

    opcoes_fk = {c["col"]: db.execute(FK_OPCOES[c["fk"]]).fetchall()
                 for c in cfg["campos"] if c["tipo"] == "fk"}
    return render_template("admin/form.html", ent=ent, cfg=cfg, rid=rid, valores=valores, erros=erros,
                           opcoes_fk=opcoes_fk, todos_servicos=todos_servicos, habilitados=habilitados)


@app.post("/admin/<ent>/<int:rid>/inativar")
def admin_inativar(ent, rid):
    cfg_ou_404(ent)
    db = get_db()
    registro_ou_404(db, ent, rid)
    erro = inativar_registro(db, ent, rid)
    if erro:
        flash(erro, "erro")
    else:
        db.commit()
        flash("Registro excluído. Os dados ficam preservados e podem ser reativados.", "ok")
    return redirect(request.referrer or url_for("admin_lista", ent=ent))


@app.post("/admin/<ent>/<int:rid>/reativar")
def admin_reativar(ent, rid):
    cfg = cfg_ou_404(ent)
    db = get_db()
    row = registro_ou_404(db, ent, rid)
    if ent == "animais":
        tutor = db.execute("SELECT Ativo FROM Cliente WHERE ID_Cliente=?", (row["ID_cliente"],)).fetchone()
        if not tutor["Ativo"]:
            flash("Reative primeiro o tutor deste animal.", "erro")
            return redirect(request.referrer or url_for("admin_lista", ent=ent))
    db.execute(f"UPDATE {cfg['tabela']} SET Ativo=1 WHERE {cfg['pk']}=?", (rid,))
    registrar_log(db, cfg["tabela"], rid, "reativar", "")
    db.commit()
    flash("Registro reativado.", "ok")
    return redirect(request.referrer or url_for("admin_lista", ent=ent))


# ============================================================================
# Admin: agendamentos (RF05 a RF07, status Agendado/Realizado/Cancelado)
# ============================================================================
SQL_AGENDAMENTO = """
SELECT ag.*, c.Nome AS cliente, c.Telefone AS cliente_tel, an.nome AS animal,
       p.Nome AS profissional, s.Nome_Servico AS servico, s.Preco AS preco, s.duracao_min,
       (SELECT MAX(Data_Envio) FROM Notificacao n WHERE n.ID_Agendamento = ag.ID_Agendamento) AS ultima_notif
  FROM Agendamento ag
  JOIN Cliente c      ON c.ID_Cliente = ag.ID_Cliente
  JOIN Animal an      ON an.ID_animal = ag.ID_Animal
  JOIN Profissional p ON p.ID_Profissional = ag.ID_Profissional
  JOIN Servico s      ON s.Id_servico = ag.ID_Servico
"""


@app.route("/admin/agendamentos")
def admin_agendamentos():
    db = get_db()
    f = {k: request.args.get(k, "").strip() for k in ("data", "profissional", "cliente", "status")}
    where, params = [], []
    if f["data"]:
        where.append("date(ag.Data_Hora)=?")
        params.append(f["data"])
    if f["profissional"].isdigit():
        where.append("ag.ID_Profissional=?")
        params.append(int(f["profissional"]))
    if f["cliente"]:
        where.append("c.Nome LIKE ?")
        params.append(f"%{f['cliente']}%")
    if f["status"] in ("Agendado", "Realizado", "Cancelado"):
        where.append("ag.status=?")
        params.append(f["status"])
    sql = SQL_AGENDAMENTO + (" WHERE " + " AND ".join(where) if where else "")
    linhas = db.execute(sql + " ORDER BY ag.Data_Hora DESC", params).fetchall()
    profissionais = db.execute("SELECT ID_Profissional, Nome FROM Profissional ORDER BY Nome").fetchall()
    return render_template("admin/agendamentos.html", linhas=linhas, f=f, profissionais=profissionais)


@app.route("/admin/agendamentos/novo", methods=["GET", "POST"])
@app.route("/admin/agendamentos/<int:rid>/editar", methods=["GET", "POST"])
def admin_agendamento_form(rid=None):
    db = get_db()
    atual = None
    if rid:
        atual = db.execute("SELECT * FROM Agendamento WHERE ID_Agendamento=?", (rid,)).fetchone()
        if atual is None:
            abort(404)
        if atual["status"] != "Agendado":
            flash(f"Só é possível reagendar agendamentos com status Agendado (este está {atual['status']}).", "erro")
            return redirect(url_for("admin_agendamentos"))
    erros = []
    valores = dict(atual) if atual else {}

    if request.method == "POST":
        valores = dict(request.form)
        campos = {k: request.form.get(k, "") for k in ("ID_Cliente", "ID_Animal", "ID_Servico", "ID_Profissional")}
        dt = regras.parse_datahora(request.form.get("Data_Hora"))
        if not all(v.isdigit() for v in campos.values()):
            erros.append("Selecione cliente, animal, serviço e profissional.")
        else:
            ids = {k: int(v) for k, v in campos.items()}
            erros = regras.validar_agendamento(
                db, ids["ID_Cliente"], ids["ID_Animal"], ids["ID_Profissional"], ids["ID_Servico"], dt, rid)
        if not erros:
            try:
                dados = {**ids, "Data_Hora": regras.para_banco(dt)}
                if rid:
                    sets = ", ".join(f"{c}=?" for c in dados)
                    db.execute(f"UPDATE Agendamento SET {sets} WHERE ID_Agendamento=?", [*dados.values(), rid])
                    registrar_log(db, "Agendamento", rid, "reagendar", diferencas(atual, dados))
                else:
                    cur = db.execute(
                        "INSERT INTO Agendamento (Data_Hora, status, ID_Servico, ID_Cliente, ID_Animal, ID_Profissional) "
                        "VALUES (?, 'Agendado', ?, ?, ?, ?)",
                        (dados["Data_Hora"], ids["ID_Servico"], ids["ID_Cliente"], ids["ID_Animal"], ids["ID_Profissional"]))
                    registrar_log(db, "Agendamento", cur.lastrowid, "incluir", str(dados))
                db.commit()
                flash("Agendamento salvo com sucesso.", "ok")
                return redirect(url_for("admin_agendamentos"))
            except sqlite3.IntegrityError as e:
                db.rollback()
                erros.append(mensagem_integridade(e))

    contexto = {
        "clientes": db.execute("SELECT ID_Cliente, Nome FROM Cliente WHERE Ativo=1 ORDER BY Nome").fetchall(),
        "animais": db.execute("SELECT ID_animal, ID_cliente, nome, especie FROM Animal WHERE Ativo=1 ORDER BY nome").fetchall(),
        "servicos": db.execute("SELECT Id_servico, Nome_Servico, duracao_min, Preco FROM Servico WHERE Ativo=1 ORDER BY Nome_Servico").fetchall(),
        "profissionais": db.execute(
            "SELECT p.ID_Profissional, p.Nome, p.Especialidade, "
            "(SELECT group_concat(ID_Servico) FROM Profissional_Servico ps WHERE ps.ID_Profissional=p.ID_Profissional) AS servicos "
            "FROM Profissional p WHERE p.Ativo=1 ORDER BY p.Nome").fetchall(),
    }
    dados_js = {  # versão "simples" (listas de dicionários) para o JavaScript do formulário
        "animais": [dict(r) for r in contexto["animais"]],
        "profissionais": [{**dict(r), "servicos": [int(i) for i in (r["servicos"] or "").split(",") if i]}
                          for r in contexto["profissionais"]],
    }
    return render_template("admin/agendamento_form.html", rid=rid, valores=valores, erros=erros,
                           dados_js=dados_js, **contexto)


def agendamento_em_aberto_ou_redirect(db, rid):
    ag = db.execute(SQL_AGENDAMENTO + " WHERE ag.ID_Agendamento=?", (rid,)).fetchone()
    if ag is None:
        abort(404)
    if ag["status"] != "Agendado":
        flash(f"Ação disponível apenas para agendamentos com status Agendado (este está {ag['status']}).", "erro")
        return None
    return ag


@app.post("/admin/agendamentos/<int:rid>/cancelar")
def admin_agendamento_cancelar(rid):
    db = get_db()
    if agendamento_em_aberto_ou_redirect(db, rid):
        db.execute("UPDATE Agendamento SET status='Cancelado' WHERE ID_Agendamento=?", (rid,))
        registrar_log(db, "Agendamento", rid, "cancelar", "status → Cancelado")
        db.commit()
        flash("Agendamento cancelado.", "ok")
    return redirect(request.referrer or url_for("admin_agendamentos"))


@app.post("/admin/agendamentos/<int:rid>/realizado")
def admin_agendamento_realizado(rid):
    db = get_db()
    if agendamento_em_aberto_ou_redirect(db, rid):
        db.execute("UPDATE Agendamento SET status='Realizado' WHERE ID_Agendamento=?", (rid,))
        registrar_log(db, "Agendamento", rid, "realizar", "status → Realizado")
        db.commit()
        flash("Agendamento marcado como Realizado.", "ok")
    return redirect(request.referrer or url_for("admin_agendamentos"))


@app.post("/admin/agendamentos/<int:rid>/notificar")
def admin_agendamento_notificar(rid):
    """Avisa o tutor (no aplicativo) que o animal está pronto para buscar."""
    db = get_db()
    ag = agendamento_em_aberto_ou_redirect(db, rid)
    if ag:
        db.execute(
            "INSERT INTO Notificacao (ID_Agendamento, ID_Cliente, Canal, Mensagem) VALUES (?,?, 'app', ?)",
            (rid, ag["ID_Cliente"], mensagem_pronto(ag["animal"], ag["cliente"])))
        registrar_log(db, "Notificacao", rid, "notificar", f"{ag['animal']} pronto para buscar")
        db.commit()
        flash(f"Tutor avisado no aplicativo: {ag['animal']} está pronto para buscar. "
              "Use o botão WhatsApp para avisar também por mensagem.", "ok")
    return redirect(request.referrer or url_for("admin_agendamentos"))


@app.route("/admin/notificacoes")
def admin_notificacoes():
    linhas = get_db().execute(
        """SELECT n.*, c.Nome AS cliente, an.nome AS animal
             FROM Notificacao n
             JOIN Cliente c ON c.ID_Cliente = n.ID_Cliente
             JOIN Agendamento ag ON ag.ID_Agendamento = n.ID_Agendamento
             JOIN Animal an ON an.ID_animal = ag.ID_Animal
            ORDER BY n.ID_Notificacao DESC LIMIT 200""").fetchall()
    return render_template("admin/notificacoes.html", linhas=linhas)


# ============================================================================
# Admin: histórico de saúde (RF08 a RF10)
# ============================================================================
SQL_HISTORICO = """
SELECT h.*, an.nome AS animal, c.Nome AS tutor, p.Nome AS profissional
  FROM Historico_saude h
  JOIN Animal an      ON an.ID_animal = h.ID_animal
  JOIN Cliente c      ON c.ID_Cliente = an.ID_cliente
  JOIN Profissional p ON p.ID_Profissional = h.ID_Profissional
"""
TIPOS_REGISTRO = ["Atendimento Clínico", "Consulta Especializada", "Vacina", "Exame", "Cirurgia", "Observação"]
TIPOS_MIDIA = ["imagem", "pdf", "outro"]


@app.route("/admin/historico")
def admin_historico():
    db = get_db()
    q = request.args.get("q", "").strip()
    animal_id = request.args.get("animal", "")
    inativos = request.args.get("inativos") == "1"
    where, params = [], []
    if not inativos:
        where.append("h.Ativo=1")
    if animal_id.isdigit():
        where.append("h.ID_animal=?")
        params.append(int(animal_id))
    if q:
        where.append("(h.descricao LIKE ? OR h.tipo_registro LIKE ? OR an.nome LIKE ? OR c.Nome LIKE ?)")
        params += [f"%{q}%"] * 4
    sql = SQL_HISTORICO + (" WHERE " + " AND ".join(where) if where else "")
    linhas = db.execute(sql + " ORDER BY h.data_registro DESC", params).fetchall()
    anexos = {}
    for a in db.execute("SELECT * FROM Anexo_midia ORDER BY Id_anexo"):
        anexos.setdefault(a["id_historico"], []).append(a)
    animal = db.execute("SELECT a.*, c.Nome AS tutor FROM Animal a JOIN Cliente c ON c.ID_Cliente=a.ID_cliente "
                        "WHERE a.ID_animal=?", (int(animal_id),)).fetchone() if animal_id.isdigit() else None
    animais = db.execute("SELECT ID_animal, nome FROM Animal ORDER BY nome").fetchall()
    return render_template("admin/historico.html", linhas=linhas, anexos=anexos, q=q, inativos=inativos,
                           animal=animal, animais=animais, animal_id=animal_id)


@app.route("/admin/historico/novo", methods=["GET", "POST"])
@app.route("/admin/historico/<int:rid>/editar", methods=["GET", "POST"])
def admin_historico_form(rid=None):
    db = get_db()
    atual = None
    if rid:
        atual = db.execute("SELECT * FROM Historico_saude WHERE ID_historico=?", (rid,)).fetchone()
        if atual is None:
            abort(404)
    erros = []
    agora = datetime.now().strftime("%Y-%m-%dT%H:%M")

    if request.method == "GET":
        valores = dict(atual) if atual else {"data_registro": agora}
        # atalho vindo da lista de agendamentos: /admin/historico/novo?agendamento=ID
        ag_param = request.args.get("agendamento", "")
        if not atual and ag_param.isdigit():
            ag = db.execute("SELECT * FROM Agendamento WHERE ID_Agendamento=?", (int(ag_param),)).fetchone()
            if ag:
                valores.update(ID_Agendamento=ag["ID_Agendamento"], ID_animal=ag["ID_Animal"],
                               ID_Profissional=ag["ID_Profissional"])
        if not atual and request.args.get("animal", "").isdigit():
            valores.setdefault("ID_animal", int(request.args["animal"]))
    else:
        valores = dict(request.form)
        f = request.form
        descricao = f.get("descricao", "").strip()
        tipo = f.get("tipo_registro", "").strip() or None
        dt = regras.parse_datahora(f.get("data_registro"))
        animal_id = int(f["ID_animal"]) if f.get("ID_animal", "").isdigit() else None
        prof_id = int(f["ID_Profissional"]) if f.get("ID_Profissional", "").isdigit() else None
        ag = None
        if not rid and f.get("ID_Agendamento", "").isdigit():  # o vínculo só é definido na criação
            ag = db.execute("SELECT * FROM Agendamento WHERE ID_Agendamento=?", (int(f["ID_Agendamento"]),)).fetchone()
            if ag is None:
                erros.append("Agendamento inexistente.")
            elif ag["status"] == "Cancelado":
                erros.append("Não é possível registrar atendimento de um agendamento cancelado.")
            else:
                if animal_id and animal_id != ag["ID_Animal"]:
                    erros.append("O animal do registro deve ser o mesmo do agendamento.")
                prof_id = prof_id or ag["ID_Profissional"]
                animal_id = ag["ID_Animal"]

        if not descricao:
            erros.append("A descrição é obrigatória.")
        if dt is None:
            erros.append("Informe data e hora do registro.")
        if not animal_id or not db.execute("SELECT 1 FROM Animal WHERE ID_animal=? AND Ativo=1", (animal_id,)).fetchone():
            erros.append("Selecione um animal ativo.")
        if not prof_id or not db.execute("SELECT 1 FROM Profissional WHERE ID_Profissional=? AND Ativo=1", (prof_id,)).fetchone():
            erros.append("Selecione um profissional ativo.")
        anexo_url = f.get("anexo_url", "").strip()
        anexo_tipo = f.get("anexo_tipo", "outro")
        if anexo_url and len(anexo_url) > 255:
            erros.append("O link/caminho do anexo deve ter no máximo 255 caracteres.")
        if anexo_tipo not in TIPOS_MIDIA:
            anexo_tipo = "outro"

        if not erros:
            try:
                if rid:
                    db.execute("UPDATE Historico_saude SET ID_animal=?, ID_Profissional=?, data_registro=?, "
                               "tipo_registro=?, descricao=? WHERE ID_historico=?",
                               (animal_id, prof_id, regras.para_banco(dt), tipo, descricao, rid))
                    registrar_log(db, "Historico_saude", rid, "alterar", f"descricao={descricao[:60]!r}")
                else:
                    cur = db.execute(
                        "INSERT INTO Historico_saude (ID_animal, ID_Profissional, ID_Agendamento, data_registro, "
                        "tipo_registro, descricao) VALUES (?,?,?,?,?,?)",
                        (animal_id, prof_id, ag["ID_Agendamento"] if ag else None, regras.para_banco(dt), tipo, descricao))
                    rid = cur.lastrowid
                    registrar_log(db, "Historico_saude", rid, "incluir", f"animal={animal_id}, tipo={tipo!r}")
                    # RF09: registrar o atendimento conclui o agendamento
                    if ag and ag["status"] == "Agendado":
                        db.execute("UPDATE Agendamento SET status='Realizado' WHERE ID_Agendamento=?", (ag["ID_Agendamento"],))
                        registrar_log(db, "Agendamento", ag["ID_Agendamento"], "realizar",
                                      f"status → Realizado (atendimento #{rid})")
                if anexo_url:
                    db.execute("INSERT INTO Anexo_midia (id_historico, url_midia, tipo_midia) VALUES (?,?,?)",
                               (rid, anexo_url, anexo_tipo))
                    registrar_log(db, "Anexo_midia", rid, "incluir", anexo_url)
                db.commit()
                flash("Registro de saúde salvo com sucesso.", "ok")
                return redirect(url_for("admin_historico", animal=animal_id))
            except sqlite3.IntegrityError as e:
                db.rollback()
                erros.append(mensagem_integridade(e))

    agendamentos = db.execute(
        """SELECT ag.ID_Agendamento, ag.ID_Animal, ag.ID_Profissional, ag.Data_Hora, ag.status,
                  an.nome AS animal, s.Nome_Servico AS servico
             FROM Agendamento ag
             JOIN Animal an ON an.ID_animal = ag.ID_Animal
             JOIN Servico s ON s.Id_servico = ag.ID_Servico
            WHERE ag.status <> 'Cancelado' ORDER BY ag.Data_Hora DESC LIMIT 150""").fetchall()
    return render_template(
        "admin/historico_form.html", rid=rid, valores=valores, erros=erros, agendamentos=agendamentos,
        animais=db.execute("SELECT a.ID_animal, a.nome, c.Nome AS tutor FROM Animal a JOIN Cliente c "
                           "ON c.ID_Cliente=a.ID_cliente WHERE a.Ativo=1 ORDER BY a.nome").fetchall(),
        profissionais=db.execute("SELECT ID_Profissional, Nome FROM Profissional WHERE Ativo=1 ORDER BY Nome").fetchall(),
        anexos=db.execute("SELECT * FROM Anexo_midia WHERE id_historico=?", (rid,)).fetchall() if rid else [],
        tipos_registro=TIPOS_REGISTRO, tipos_midia=TIPOS_MIDIA, edicao=bool(atual),
    )


@app.post("/admin/historico/<int:rid>/inativar")
def admin_historico_inativar(rid):
    db = get_db()
    row = db.execute("SELECT * FROM Historico_saude WHERE ID_historico=?", (rid,)).fetchone()
    if row is None:
        abort(404)
    db.execute("UPDATE Historico_saude SET Ativo=0 WHERE ID_historico=?", (rid,))
    registrar_log(db, "Historico_saude", rid, "inativar", "exclusão lógica")
    db.commit()
    flash("Registro excluído. Os dados ficam preservados e podem ser reativados.", "ok")
    return redirect(request.referrer or url_for("admin_historico"))


@app.post("/admin/historico/<int:rid>/reativar")
def admin_historico_reativar(rid):
    db = get_db()
    if db.execute("SELECT 1 FROM Historico_saude WHERE ID_historico=?", (rid,)).fetchone() is None:
        abort(404)
    db.execute("UPDATE Historico_saude SET Ativo=1 WHERE ID_historico=?", (rid,))
    registrar_log(db, "Historico_saude", rid, "reativar", "")
    db.commit()
    flash("Registro reativado.", "ok")
    return redirect(request.referrer or url_for("admin_historico"))


# ============================================================================
# API do aplicativo do tutor (JSON)
# ============================================================================
def erro_json(msg, status=400):
    return jsonify({"erro": msg}), status


def tutor_logado(f):
    @wraps(f)
    def interno(*args, **kwargs):
        if not session.get("cliente_id"):
            return erro_json("Sessão expirada. Entre novamente.", 401)
        return f(*args, **kwargs)
    return interno


def json_do_corpo():
    return request.get_json(silent=True) or {}


@app.post("/api/login")
def api_login():
    d = json_do_corpo()
    email = (d.get("email") or "").strip().lower()
    cliente = get_db().execute(
        "SELECT * FROM Cliente WHERE lower(Email)=? AND Ativo=1", (email,)).fetchone()
    if not cliente or not cliente["Senha_hash"] or not check_password_hash(cliente["Senha_hash"], d.get("senha") or ""):
        return erro_json("E-mail ou senha incorretos.", 401)
    session.clear()
    session["cliente_id"] = cliente["ID_Cliente"]
    return jsonify({"ok": True})


@app.post("/api/cadastro")
def api_cadastro():
    """Auto-cadastro do tutor (RF01)."""
    d = json_do_corpo()
    db = get_db()
    valores, erros = regras.validar_campos(ENTIDADES["clientes"], d)
    if not valores.get("Email"):
        erros.append("E-mail é obrigatório.")
    senha = d.get("senha") or ""
    if len(senha) < 6:
        erros.append("A senha deve ter pelo menos 6 caracteres.")
    if erros:
        return erro_json(" ".join(erros))
    try:
        session.clear()
        rid = salvar_registro(db, "clientes", valores)
        db.execute("UPDATE Cliente SET Senha_hash=? WHERE ID_Cliente=?", (generate_password_hash(senha), rid))
        session["cliente_id"] = rid
        db.commit()
    except sqlite3.IntegrityError as e:
        db.rollback()
        session.clear()
        return erro_json(mensagem_integridade(e))
    return jsonify({"ok": True})


@app.post("/api/logout")
def api_logout():
    session.clear()
    return jsonify({"ok": True})


@app.get("/api/dados")
@tutor_logado
def api_dados():
    """Devolve tudo o que o aplicativo precisa de uma vez (o front re-renderiza a partir disto)."""
    db = get_db()
    cid = session["cliente_id"]
    cliente = db.execute("SELECT * FROM Cliente WHERE ID_Cliente=?", (cid,)).fetchone()
    if cliente is None or not cliente["Ativo"]:
        session.clear()
        return erro_json("Sessão expirada. Entre novamente.", 401)

    hab = {}
    for r in db.execute("SELECT * FROM Profissional_Servico"):
        hab.setdefault(r["ID_Profissional"], []).append(r["ID_Servico"])
    anexos = {}
    for a in db.execute("SELECT * FROM Anexo_midia ORDER BY Id_anexo"):
        anexos.setdefault(a["id_historico"], []).append(a["url_midia"])

    return jsonify({
        "cliente": {"id": cid, "nome": cliente["Nome"], "email": cliente["Email"]},
        "pets": [
            {"id": a["ID_animal"], "nome": a["nome"], "especie": a["especie"], "raca": a["raca"],
             "porte": a["porte"], "sexo": a["sexo"], "data_nascimento": a["data_nascimento"]}
            for a in db.execute("SELECT * FROM Animal WHERE ID_cliente=? AND Ativo=1 ORDER BY ID_animal", (cid,))],
        "servicos": [
            {"id": s["Id_servico"], "nome": s["Nome_Servico"], "categoria": s["Categoria"],
             "duracao": s["duracao_min"], "preco": s["Preco"]}
            for s in db.execute("SELECT * FROM Servico WHERE Ativo=1 ORDER BY Nome_Servico")],
        "profissionais": [
            {"id": p["ID_Profissional"], "nome": p["Nome"], "especialidade": p["Especialidade"],
             "crmv": p["CRMV"], "servicos": hab.get(p["ID_Profissional"], [])}
            for p in db.execute("SELECT * FROM Profissional WHERE Ativo=1 ORDER BY Nome")],
        "agendamentos": [
            {"id": a["ID_Agendamento"], "pet_id": a["ID_Animal"], "pet_nome": a["animal"],
             "pet_especie": a["especie"], "servico_nome": a["servico"], "preco": a["preco"],
             "prof_nome": a["profissional"], "prof_especialidade": a["Especialidade"],
             "data_hora": a["Data_Hora"], "status": a["status"]}
            for a in db.execute(
                """SELECT ag.*, an.nome AS animal, an.especie, s.Nome_Servico AS servico, s.Preco AS preco,
                          p.Nome AS profissional, p.Especialidade
                     FROM Agendamento ag
                     JOIN Animal an ON an.ID_animal = ag.ID_Animal
                     JOIN Servico s ON s.Id_servico = ag.ID_Servico
                     JOIN Profissional p ON p.ID_Profissional = ag.ID_Profissional
                    WHERE ag.ID_Cliente=? ORDER BY ag.Data_Hora""", (cid,))],
        "historico": [
            {"id": h["ID_historico"], "pet_id": h["ID_animal"], "data": h["data_registro"],
             "tipo": h["tipo_registro"], "profissional": h["profissional"], "descricao": h["descricao"],
             "anexos": anexos.get(h["ID_historico"], [])}
            for h in db.execute(
                """SELECT h.*, p.Nome AS profissional
                     FROM Historico_saude h
                     JOIN Animal an ON an.ID_animal = h.ID_animal
                     JOIN Profissional p ON p.ID_Profissional = h.ID_Profissional
                    WHERE an.ID_cliente=? AND h.Ativo=1 ORDER BY h.data_registro DESC""", (cid,))],
        "notificacoes": [
            {"id": n["ID_Notificacao"], "mensagem": n["Mensagem"], "data": n["Data_Envio"]}
            for n in db.execute(
                "SELECT * FROM Notificacao WHERE ID_Cliente=? AND Lida=0 ORDER BY ID_Notificacao DESC", (cid,))],
    })


def pet_do_tutor(db, pet_id):
    return db.execute("SELECT * FROM Animal WHERE ID_animal=? AND ID_cliente=? AND Ativo=1",
                      (pet_id, session["cliente_id"])).fetchone()


@app.post("/api/pets")
@tutor_logado
def api_pet_criar():
    db = get_db()
    valores, erros = regras.validar_campos(ENTIDADES["animais"], {**json_do_corpo(), "ID_cliente": str(session["cliente_id"])})
    if erros:
        return erro_json(" ".join(erros))
    try:
        rid = salvar_registro(db, "animais", valores)
        db.commit()
    except sqlite3.IntegrityError as e:
        db.rollback()
        return erro_json(mensagem_integridade(e))
    return jsonify({"ok": True, "id": rid})


@app.put("/api/pets/<int:pet_id>")
@tutor_logado
def api_pet_alterar(pet_id):
    db = get_db()
    if not pet_do_tutor(db, pet_id):
        return erro_json("Pet não encontrado.", 404)
    valores, erros = regras.validar_campos(ENTIDADES["animais"], {**json_do_corpo(), "ID_cliente": str(session["cliente_id"])})
    if erros:
        return erro_json(" ".join(erros))
    salvar_registro(db, "animais", valores, pet_id)
    db.commit()
    return jsonify({"ok": True})


@app.delete("/api/pets/<int:pet_id>")
@tutor_logado
def api_pet_excluir(pet_id):
    db = get_db()
    if not pet_do_tutor(db, pet_id):
        return erro_json("Pet não encontrado.", 404)
    erro = inativar_registro(db, "animais", pet_id)
    if erro:
        return erro_json(erro + " Cancele os agendamentos antes.")
    db.commit()
    return jsonify({"ok": True})


@app.post("/api/agendamentos")
@tutor_logado
def api_agendamento_criar():
    db = get_db()
    d = json_do_corpo()
    cid = session["cliente_id"]
    try:
        pet_id, serv_id, prof_id = int(d.get("pet_id")), int(d.get("servico_id")), int(d.get("prof_id"))
    except (TypeError, ValueError):
        return erro_json("Escolha o pet, o serviço e o profissional.")
    dt = regras.parse_datahora(d.get("data_hora"))
    erros = regras.validar_agendamento(db, cid, pet_id, prof_id, serv_id, dt)
    if erros:
        return erro_json(" ".join(erros))
    try:
        cur = db.execute(
            "INSERT INTO Agendamento (Data_Hora, status, ID_Servico, ID_Cliente, ID_Animal, ID_Profissional) "
            "VALUES (?, 'Agendado', ?, ?, ?, ?)", (regras.para_banco(dt), serv_id, cid, pet_id, prof_id))
        registrar_log(db, "Agendamento", cur.lastrowid, "incluir", f"via aplicativo, {regras.para_banco(dt)}")
        db.commit()
    except sqlite3.IntegrityError as e:
        db.rollback()
        return erro_json(mensagem_integridade(e))
    return jsonify({"ok": True, "id": cur.lastrowid})


@app.post("/api/agendamentos/<int:ag_id>/cancelar")
@tutor_logado
def api_agendamento_cancelar(ag_id):
    db = get_db()
    ag = db.execute("SELECT * FROM Agendamento WHERE ID_Agendamento=? AND ID_Cliente=?",
                    (ag_id, session["cliente_id"])).fetchone()
    if ag is None:
        return erro_json("Agendamento não encontrado.", 404)
    if ag["status"] != "Agendado":
        return erro_json("Só é possível cancelar agendamentos com status Agendado.")
    db.execute("UPDATE Agendamento SET status='Cancelado' WHERE ID_Agendamento=?", (ag_id,))
    registrar_log(db, "Agendamento", ag_id, "cancelar", "via aplicativo")
    db.commit()
    return jsonify({"ok": True})


@app.post("/api/notificacoes/<int:nid>/lida")
@tutor_logado
def api_notificacao_lida(nid):
    db = get_db()
    db.execute("UPDATE Notificacao SET Lida=1 WHERE ID_Notificacao=? AND ID_Cliente=?",
               (nid, session["cliente_id"]))
    db.commit()
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(debug=True)
