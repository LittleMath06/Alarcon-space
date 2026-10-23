-- 0011 — A Receita passou a publicar os Dados Abertos do CNPJ num compartilhamento Nextcloud (SERPRO+).
-- O endereço antigo (/dados/cnpj/dados_abertos_cnpj/) responde 404 desde 2026. Verificado em 23/10/2026.
UPDATE configuracao SET valor = 'https://arquivos.receitafederal.gov.br/index.php/s/YggdBLfdninEJX9'
WHERE chave = 'receita_url_oficial' AND valor = 'https://arquivos.receitafederal.gov.br/dados/cnpj/dados_abertos_cnpj/';
