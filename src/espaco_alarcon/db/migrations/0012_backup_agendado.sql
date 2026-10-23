-- 0012 — Backup automático semanal (mantém os 10 mais recentes).
INSERT INTO agenda (tarefa, descricao, intervalo_horas) VALUES ('backup', 'Cria um backup do banco de dados', 168);
