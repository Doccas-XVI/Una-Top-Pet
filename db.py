"""
db.py - Acesso ao banco SQLite (RNF01), migração automática e auditoria (RF11).
"""
import os
import shutil
import sqlite3

from flask import g, session
from werkzeug.security import generate_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get(
    "UNATOPPET_DB", os.path.join(BASE_DIR, "Database", "clinica_veterinaria.db")
)
MIGRACAO_V3 = os.path.join(BASE_DIR, "Database", "script_migracao_v3.sql")
VERSAO_ESQUEMA = 3

# Credenciais de demonstração criadas na primeira execução.
# TROQUE antes de qualquer uso real.
ADMIN_PADRAO = ("Administrador", "admin", "admin123")
SENHA_DEMO_TUTOR = "123456"


def conectar(caminho=None):
    """Abre uma conexão nova com chaves estrangeiras ativadas."""
    con = sqlite3.connect(caminho or DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def get_db():
    """Uma conexão por requisição (guardada em flask.g)."""
    if "db" not in g:
        g.db = conectar()
    return g.db


def fechar_db(_erro=None):
    con = g.pop("db", None)
    if con is not None:
        con.close()


def migrar():
    """
    Leva o banco para a versão 3 (uma única vez, controlado por user_version).
    Antes de alterar, cria uma cópia de segurança (RNF05).
    """
    con = conectar()
    try:
        versao = con.execute("PRAGMA user_version").fetchone()[0]
        if versao >= VERSAO_ESQUEMA:
            return False

        con.close()
        backup = DB_PATH.replace(".db", "_backup_v2.db")
        if not os.path.exists(backup):
            shutil.copyfile(DB_PATH, backup)

        con = conectar()
        with open(MIGRACAO_V3, encoding="utf-8") as f:
            con.executescript(f.read())

        # Dados iniciais que dependem de hash de senha (não dá para fazer em SQL puro)
        nome, login, senha = ADMIN_PADRAO
        con.execute(
            "INSERT OR IGNORE INTO Usuario_admin (Nome, Login, Senha_hash) VALUES (?,?,?)",
            (nome, login, generate_password_hash(senha)),
        )
        con.execute(
            "UPDATE Cliente SET Senha_hash = ? WHERE Senha_hash IS NULL",
            (generate_password_hash(SENHA_DEMO_TUTOR),),
        )
        con.execute(f"PRAGMA user_version = {VERSAO_ESQUEMA}")
        con.commit()
        return True
    finally:
        con.close()


def usuario_atual():
    """Quem está fazendo a alteração (admin logado ou tutor do aplicativo)."""
    if session.get("admin_id"):
        return f"admin:{session.get('admin_login')}"
    if session.get("cliente_id"):
        return f"tutor:{session.get('cliente_id')}"
    return "sistema"


def registrar_log(db, tabela, id_registro, acao, detalhes=""):
    """RF11 - grava data (automática) e usuário responsável pela alteração."""
    db.execute(
        "INSERT INTO Log_alteracao (Usuario, Tabela, ID_Registro, Acao, Detalhes) "
        "VALUES (?,?,?,?,?)",
        (usuario_atual(), tabela, id_registro, acao, detalhes),
    )
