"""
regras.py - Validações (RF12) e regras de negócio dos agendamentos (RF05, RF06).
Nenhuma função aqui conhece Flask: recebem a conexão e devolvem dados/erros.
"""
import re
from datetime import date, datetime, timedelta

# --- Funcionamento da clínica (RF06) ----------------------------------------
# 0 = segunda ... 6 = domingo. Valor = (abre, fecha) em horas. Ausente = fechado.
# Valores assumidos: ajuste conforme o horário real do pet shop.
HORARIO_FUNCIONAMENTO = {
    0: (8, 18), 1: (8, 18), 2: (8, 18), 3: (8, 18), 4: (8, 18),
    5: (8, 12),
}
DURACAO_PADRAO_MIN = 30  # usada se o serviço não tiver duração cadastrada

FORMATO_DATAHORA = "%Y-%m-%d %H:%M:%S"


# --- Normalização / validação de campos --------------------------------------
def so_digitos(texto):
    return re.sub(r"\D", "", texto or "")


def formatar_cpf(texto):
    d = so_digitos(texto)
    if len(d) != 11:
        return None
    return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"


def formatar_telefone(texto):
    d = so_digitos(texto)
    if len(d) == 11:
        return f"({d[:2]}) {d[2:7]}-{d[7:]}"
    if len(d) == 10:
        return f"({d[:2]}) {d[2:6]}-{d[6:]}"
    return None


def email_valido(texto):
    return re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", texto or "") is not None


def parse_datahora(texto):
    """Aceita o valor de <input type=datetime-local> ('2026-11-20T15:00') ou do banco."""
    if not texto:
        return None
    texto = texto.strip().replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(texto, fmt)
        except ValueError:
            pass
    return None


def para_banco(dt):
    return dt.strftime(FORMATO_DATAHORA)


# --- Agendamento (RF05, RF06) -------------------------------------------------
def validar_agendamento(db, cliente_id, animal_id, prof_id, servico_id, dt, ignorar_id=None):
    """
    Devolve a lista de erros (vazia = pode salvar).
    Confere: vínculos válidos, animal do cliente, profissional habilitado no
    serviço, horário de funcionamento e disponibilidade do profissional.
    """
    erros = []
    if dt is None:
        return ["Informe uma data e horário válidos."]

    cliente = db.execute("SELECT * FROM Cliente WHERE ID_Cliente=?", (cliente_id,)).fetchone()
    animal = db.execute("SELECT * FROM Animal WHERE ID_animal=?", (animal_id,)).fetchone()
    prof = db.execute("SELECT * FROM Profissional WHERE ID_Profissional=?", (prof_id,)).fetchone()
    serv = db.execute("SELECT * FROM Servico WHERE Id_servico=?", (servico_id,)).fetchone()

    if not cliente or not cliente["Ativo"]:
        erros.append("Cliente inválido ou inativo.")
    if not animal or not animal["Ativo"]:
        erros.append("Animal inválido ou inativo.")
    if not prof or not prof["Ativo"]:
        erros.append("Profissional inválido ou inativo.")
    if not serv or not serv["Ativo"]:
        erros.append("Serviço inválido ou inativo.")
    if erros:
        return erros

    if animal["ID_cliente"] != cliente["ID_Cliente"]:
        erros.append("Este animal não pertence ao cliente selecionado.")

    habilitado = db.execute(
        "SELECT 1 FROM Profissional_Servico WHERE ID_Profissional=? AND ID_Servico=?",
        (prof_id, servico_id),
    ).fetchone()
    if not habilitado:
        erros.append(f"{prof['Nome']} não está habilitado(a) a realizar o serviço “{serv['Nome_Servico']}”.")

    if dt < datetime.now():
        erros.append("Não é possível agendar em data/horário que já passou.")

    duracao = serv["duracao_min"] or DURACAO_PADRAO_MIN
    fim = dt + timedelta(minutes=duracao)

    funcionamento = HORARIO_FUNCIONAMENTO.get(dt.weekday())
    if not funcionamento:
        erros.append("A clínica não funciona neste dia da semana.")
    else:
        abre, fecha = funcionamento
        limite_abre = dt.replace(hour=abre, minute=0, second=0, microsecond=0)
        limite_fecha = dt.replace(hour=fecha, minute=0, second=0, microsecond=0)
        if dt < limite_abre or fim > limite_fecha:
            erros.append(
                f"Fora do horário de funcionamento ({abre:02d}h às {fecha:02d}h). "
                f"O serviço dura {duracao} min e termina às {fim:%H:%M}."
            )

    # Disponibilidade do profissional: nenhum outro agendamento ativo pode se sobrepor
    outros = db.execute(
        """SELECT a.ID_Agendamento, a.Data_Hora, s.duracao_min
             FROM Agendamento a JOIN Servico s ON s.Id_servico = a.ID_Servico
            WHERE a.ID_Profissional = ? AND a.status <> 'Cancelado'
              AND date(a.Data_Hora) = date(?)""",
        (prof_id, para_banco(dt)),
    ).fetchall()
    for o in outros:
        if ignorar_id and o["ID_Agendamento"] == ignorar_id:
            continue
        o_ini = parse_datahora(o["Data_Hora"])
        o_fim = o_ini + timedelta(minutes=o["duracao_min"] or DURACAO_PADRAO_MIN)
        if dt < o_fim and o_ini < fim:
            erros.append(
                f"{prof['Nome']} já tem um agendamento das {o_ini:%H:%M} às {o_fim:%H:%M} neste dia."
            )
            break
    return erros


# --- Cadastros (RF01 a RF04, RF12) -------------------------------------------
def validar_campos(cfg, form):
    """
    Lê e valida o formulário conforme a configuração da entidade (entidades.py).
    Devolve (valores, erros). `valores` é {coluna: valor já normalizado}.
    """
    valores, erros = {}, []
    for c in cfg["campos"]:
        bruto = str(form.get(c["col"]) or "").strip()
        rotulo = c["label"]

        if not bruto:
            if c.get("obrig"):
                erros.append(f"{rotulo} é obrigatório.")
            valores[c["col"]] = None
            continue

        tipo = c["tipo"]
        if tipo == "cpf":
            val = formatar_cpf(bruto)
            if val is None:
                erros.append("CPF deve ter 11 dígitos.")
        elif tipo == "tel":
            val = formatar_telefone(bruto)
            if val is None:
                erros.append(f"{rotulo} inválido. Use DDD + número, ex.: (31) 99999-9999.")
        elif tipo == "email":
            val = bruto.lower()
            if not email_valido(val):
                erros.append("E-mail inválido.")
        elif tipo == "date":
            try:
                val = date.fromisoformat(bruto)
                if val > date.today():
                    erros.append(f"{rotulo} não pode estar no futuro.")
                val = val.isoformat()
            except ValueError:
                erros.append(f"{rotulo} inválida.")
                val = None
        elif tipo == "decimal":
            try:
                val = float(bruto.replace(",", "."))
                if val <= 0:
                    erros.append(f"{rotulo} deve ser maior que zero.")
            except ValueError:
                erros.append(f"{rotulo} deve ser um número.")
                val = None
        elif tipo == "int":
            if bruto.isdigit() and int(bruto) > 0:
                val = int(bruto)
            else:
                erros.append(f"{rotulo} deve ser um número inteiro maior que zero.")
                val = None
        elif tipo == "select":
            val = bruto
            if val not in [valor for valor, _rotulo in c["opcoes"]]:
                erros.append(f"{rotulo} inválido.")
        elif tipo == "fk":
            val = int(bruto) if bruto.isdigit() else None
            if val is None:
                erros.append(f"{rotulo} inválido.")
        else:  # text, textarea
            val = bruto
            if c.get("max") and len(val) > c["max"]:
                erros.append(f"{rotulo} deve ter no máximo {c['max']} caracteres.")
        valores[c["col"]] = val
    return valores, erros
