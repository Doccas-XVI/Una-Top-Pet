-- ============================================================================
-- Script de Migração v3 - Clínica Veterinária (UnaTopPet)
-- Aplica sobre um banco já na versão 2 (script_criacao_banco.sql + migração v2).
-- É executado automaticamente pelo sistema (db.py) na primeira inicialização,
-- controlado por PRAGMA user_version (só roda uma vez).
--
-- Alterações:
--   1. Coluna Ativo em Cliente, Animal, Profissional, Servico e Historico_saude.
--      O banco bloqueia DELETE por trigger (RNF02), então "excluir" no sistema
--      é uma EXCLUSÃO LÓGICA (Ativo = 0), conforme RF01/RF02 ("inativar").
--   2. Coluna Senha_hash em Cliente (login do tutor no aplicativo).
--   3. Status do agendamento padronizado: Agendado | Realizado | Cancelado
--      ('Concluído' vira 'Realizado'). Triggers validam os valores.
--   4. Tabela Profissional_Servico (RF03): serviços que cada profissional pode
--      realizar. Carga inicial a partir dos agendamentos já existentes.
--   5. Tabela Usuario_admin: usuários da área administrativa.
--   6. Tabela Log_alteracao (RF11): data e usuário de toda alteração.
--   7. Tabela Notificacao: aviso ao tutor de que o animal está pronto para buscar.
-- ============================================================================

PRAGMA foreign_keys = ON;

BEGIN TRANSACTION;

-- 1. Exclusão lógica -------------------------------------------------------
ALTER TABLE Cliente         ADD COLUMN Ativo INTEGER NOT NULL DEFAULT 1;
ALTER TABLE Animal          ADD COLUMN Ativo INTEGER NOT NULL DEFAULT 1;
ALTER TABLE Profissional    ADD COLUMN Ativo INTEGER NOT NULL DEFAULT 1;
ALTER TABLE Servico         ADD COLUMN Ativo INTEGER NOT NULL DEFAULT 1;
ALTER TABLE Historico_saude ADD COLUMN Ativo INTEGER NOT NULL DEFAULT 1;

-- 2. Login do tutor --------------------------------------------------------
ALTER TABLE Cliente ADD COLUMN Senha_hash TEXT;
-- E-mail não pode repetir entre clientes (é o login do tutor)
CREATE UNIQUE INDEX IF NOT EXISTS uq_cliente_email ON Cliente(lower(Email)) WHERE Email IS NOT NULL;

-- 3. Status do agendamento -------------------------------------------------
UPDATE Agendamento SET status = 'Realizado' WHERE status = 'Concluído';

CREATE TRIGGER IF NOT EXISTS trg_agendamento_status_insert
BEFORE INSERT ON Agendamento
WHEN NEW.status NOT IN ('Agendado', 'Realizado', 'Cancelado')
BEGIN
    SELECT RAISE(ABORT, 'Status invalido. Use: Agendado, Realizado ou Cancelado.');
END;

CREATE TRIGGER IF NOT EXISTS trg_agendamento_status_update
BEFORE UPDATE OF status ON Agendamento
WHEN NEW.status NOT IN ('Agendado', 'Realizado', 'Cancelado')
BEGIN
    SELECT RAISE(ABORT, 'Status invalido. Use: Agendado, Realizado ou Cancelado.');
END;

-- 4. Serviços que cada profissional realiza (N:N) --------------------------
CREATE TABLE IF NOT EXISTS Profissional_Servico (
    ID_Profissional INT NOT NULL,
    ID_Servico      INT NOT NULL,
    PRIMARY KEY (ID_Profissional, ID_Servico),
    FOREIGN KEY (ID_Profissional) REFERENCES Profissional(ID_Profissional)
        ON DELETE RESTRICT ON UPDATE CASCADE,
    FOREIGN KEY (ID_Servico) REFERENCES Servico(Id_servico)
        ON DELETE RESTRICT ON UPDATE CASCADE
);

INSERT OR IGNORE INTO Profissional_Servico (ID_Profissional, ID_Servico)
SELECT DISTINCT ID_Profissional, ID_Servico FROM Agendamento;

-- 5. Usuários da área administrativa --------------------------------------
CREATE TABLE IF NOT EXISTS Usuario_admin (
    ID_Usuario INTEGER PRIMARY KEY AUTOINCREMENT,
    Nome       VARCHAR(100) NOT NULL,
    Login      VARCHAR(30)  NOT NULL UNIQUE,
    Senha_hash TEXT         NOT NULL,
    Ativo      INTEGER      NOT NULL DEFAULT 1
);

-- 6. Auditoria (RF11) ------------------------------------------------------
CREATE TABLE IF NOT EXISTS Log_alteracao (
    ID_Log       INTEGER PRIMARY KEY AUTOINCREMENT,
    Data_Hora    DATETIME NOT NULL DEFAULT (datetime('now', 'localtime')),
    Usuario      VARCHAR(100) NOT NULL,
    Tabela       VARCHAR(30)  NOT NULL,
    ID_Registro  INT,
    Acao         VARCHAR(20)  NOT NULL,
    Detalhes     TEXT
);
CREATE INDEX IF NOT EXISTS idx_log_data ON Log_alteracao(Data_Hora);

-- 7. Notificação ao tutor (animal pronto para buscar) ----------------------
CREATE TABLE IF NOT EXISTS Notificacao (
    ID_Notificacao INTEGER PRIMARY KEY AUTOINCREMENT,
    ID_Agendamento INT NOT NULL,
    ID_Cliente     INT NOT NULL,
    Canal          VARCHAR(15) NOT NULL DEFAULT 'app',
    Mensagem       TEXT NOT NULL,
    Data_Envio     DATETIME NOT NULL DEFAULT (datetime('now', 'localtime')),
    Lida           INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (ID_Agendamento) REFERENCES Agendamento(ID_Agendamento)
        ON DELETE RESTRICT ON UPDATE CASCADE,
    FOREIGN KEY (ID_Cliente) REFERENCES Cliente(ID_Cliente)
        ON DELETE RESTRICT ON UPDATE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_notificacao_cliente ON Notificacao(ID_Cliente, Lida);

COMMIT;
