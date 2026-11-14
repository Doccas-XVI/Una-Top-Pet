"""
entidades.py - Descrição dos cadastros simples (clientes, animais, profissionais
e serviços). As telas de listagem/formulário da área administrativa são geradas
a partir destas configurações, evitando repetir código para cada tabela.

Agendamentos e histórico de saúde têm regras próprias e ficam em app.py.

Chaves de cada entidade:
  tabela, pk        -> tabela e chave primária
  titulo/singular   -> textos da interface
  lista_sql, alias  -> SELECT base da listagem (alias é usado em Alias.Ativo)
  busca             -> colunas pesquisadas pela caixa de busca
  ordem             -> ORDER BY
  colunas           -> (cabeçalho, chave, formato) exibidos na tabela
  campos            -> campos do formulário (validados em regras.validar_campos)
  bloqueios         -> (SQL com contagem, motivo): impedem inativar (RNF02)
"""

OPCOES_SEXO = [("M", "Macho"), ("F", "Fêmea")]
OPCOES_PORTE = [("Pequeno", "Pequeno"), ("Médio", "Médio"), ("Grande", "Grande")]

ENTIDADES = {
    "clientes": {
        "tabela": "Cliente",
        "pk": "ID_Cliente",
        "titulo": "Clientes (tutores)",
        "singular": "cliente",
        "lista_sql": "SELECT c.* FROM Cliente c",
        "alias": "c",
        "busca": ["c.Nome", "c.CPF", "c.Telefone", "c.Email"],
        "ordem": "c.Nome",
        "colunas": [
            ("Nome", "Nome", None),
            ("CPF", "CPF", None),
            ("Telefone", "Telefone", None),
            ("E-mail", "Email", None),
        ],
        "campos": [
            {"col": "Nome", "label": "Nome completo", "tipo": "text", "obrig": True, "max": 100},
            {"col": "CPF", "label": "CPF", "tipo": "cpf", "obrig": True, "placeholder": "000.000.000-00"},
            {"col": "Telefone", "label": "Telefone", "tipo": "tel", "obrig": True, "placeholder": "(31) 99999-9999"},
            {"col": "Email", "label": "E-mail", "tipo": "email", "max": 100},
            {"col": "Endereco", "label": "Endereço", "tipo": "text", "max": 150},
        ],
        "campo_senha": True,  # senha de acesso do tutor ao aplicativo (opcional)
        "bloqueios": [
            ("SELECT COUNT(*) FROM Animal WHERE ID_cliente=? AND Ativo=1", "possui animais ativos"),
            ("SELECT COUNT(*) FROM Agendamento WHERE ID_Cliente=? AND status='Agendado'",
             "possui agendamentos em aberto"),
        ],
    },
    "animais": {
        "tabela": "Animal",
        "pk": "ID_animal",
        "titulo": "Animais",
        "singular": "animal",
        "lista_sql": "SELECT a.*, c.Nome AS tutor FROM Animal a JOIN Cliente c ON c.ID_Cliente = a.ID_cliente",
        "alias": "a",
        "busca": ["a.nome", "a.raca", "a.especie", "c.Nome"],
        "ordem": "a.nome",
        "colunas": [
            ("Animal", "nome", None),
            ("Espécie", "especie", None),
            ("Raça", "raca", None),
            ("Porte", "porte", None),
            ("Nascimento", "data_nascimento", "data"),
            ("Tutor", "tutor", None),
        ],
        "acoes_extra": [("Histórico", "/admin/historico?animal={id}")],
        "campos": [
            {"col": "ID_cliente", "label": "Tutor (cliente)", "tipo": "fk", "fk": "clientes", "obrig": True},
            {"col": "nome", "label": "Nome do animal", "tipo": "text", "obrig": True, "max": 50},
            {"col": "especie", "label": "Espécie", "tipo": "text", "obrig": True, "max": 30,
             "sugestoes": ["Canina", "Felina", "Ave", "Roedor", "Réptil"]},
            {"col": "raca", "label": "Raça", "tipo": "text", "obrig": True, "max": 50},
            {"col": "data_nascimento", "label": "Data de nascimento", "tipo": "date"},
            {"col": "sexo", "label": "Sexo", "tipo": "select", "opcoes": OPCOES_SEXO},
            {"col": "porte", "label": "Porte", "tipo": "select", "opcoes": OPCOES_PORTE},
        ],
        "bloqueios": [
            ("SELECT COUNT(*) FROM Agendamento WHERE ID_Animal=? AND status='Agendado'",
             "possui agendamentos em aberto"),
        ],
    },
    "profissionais": {
        "tabela": "Profissional",
        "pk": "ID_Profissional",
        "titulo": "Profissionais",
        "singular": "profissional",
        "lista_sql": (
            "SELECT p.*, (SELECT group_concat(s.Nome_Servico, ', ') "
            "FROM Profissional_Servico ps JOIN Servico s ON s.Id_servico = ps.ID_Servico "
            "WHERE ps.ID_Profissional = p.ID_Profissional) AS servicos FROM Profissional p"
        ),
        "alias": "p",
        "busca": ["p.Nome", "p.CRMV", "p.Especialidade"],
        "ordem": "p.Nome",
        "colunas": [
            ("Nome", "Nome", None),
            ("CRMV", "CRMV", None),
            ("Especialidade", "Especialidade", None),
            ("Telefone", "Telefone", None),
            ("Serviços habilitados", "servicos", None),
        ],
        "campos": [
            {"col": "Nome", "label": "Nome", "tipo": "text", "obrig": True, "max": 100},
            {"col": "CRMV", "label": "Registro profissional (CRMV)", "tipo": "text", "obrig": True, "max": 20,
             "placeholder": "CRMV-MG 00000"},
            {"col": "Especialidade", "label": "Especialidade", "tipo": "text", "max": 50},
            {"col": "Telefone", "label": "Telefone", "tipo": "tel", "placeholder": "(31) 99999-9999"},
        ],
        "servicos_habilitados": True,  # checkboxes de serviços (tabela Profissional_Servico)
        "bloqueios": [
            ("SELECT COUNT(*) FROM Agendamento WHERE ID_Profissional=? AND status='Agendado'",
             "possui agendamentos em aberto"),
        ],
    },
    "servicos": {
        "tabela": "Servico",
        "pk": "Id_servico",
        "titulo": "Serviços",
        "singular": "serviço",
        "lista_sql": "SELECT s.* FROM Servico s",
        "alias": "s",
        "busca": ["s.Nome_Servico", "s.Categoria", "s.Descricao"],
        "ordem": "s.Nome_Servico",
        "colunas": [
            ("Serviço", "Nome_Servico", None),
            ("Categoria", "Categoria", None),
            ("Duração", "duracao_min", "min"),
            ("Valor", "Preco", "moeda"),
        ],
        "campos": [
            {"col": "Nome_Servico", "label": "Nome do serviço", "tipo": "text", "obrig": True, "max": 100},
            {"col": "Categoria", "label": "Categoria", "tipo": "text", "max": 15,
             "sugestoes": ["Consulta", "Vacina", "Especialidade", "Exame", "Estética"]},
            {"col": "duracao_min", "label": "Duração (minutos)", "tipo": "int"},
            {"col": "Preco", "label": "Valor (R$)", "tipo": "decimal", "obrig": True, "placeholder": "150,00"},
            {"col": "Descricao", "label": "Descrição", "tipo": "text", "max": 100},
        ],
        "bloqueios": [
            ("SELECT COUNT(*) FROM Agendamento WHERE ID_Servico=? AND status='Agendado'",
             "possui agendamentos em aberto"),
        ],
    },
}

# Como montar o <select> de uma chave estrangeira (inativos aparecem no fim, marcados)
FK_OPCOES = {
    "clientes": "SELECT ID_Cliente AS id, Nome || CASE WHEN Ativo=0 THEN ' (inativo)' ELSE '' END AS rotulo "
                "FROM Cliente ORDER BY Ativo DESC, Nome",
}
