# 08 — Contatos, IE/ICMS e LGPD

## Contatos

Cada contato mostra **tipo**, **área**, **como a área foi determinada**, **origem** (com a URL exata da página, quando
veio do site) e **data**.

| Origem | Como entra | Área |
|---|---|---|
| Receita (Dados Abertos) | telefones, fax e e-mail do estabelecimento, sempre atualizados pela importação | "Cadastral (Receita) — pode ser do contador" |
| Site da empresa | botão "Buscar contatos no site" na ficha | declarada (texto "Compras:", "Vendas:"… logo antes do contato) ou inferida (prefixo do e-mail: compras@, vendas@, rh@…) |
| Manual | formulário na ficha | informada pelo usuário |

Áreas: Geral/institucional, Comercial/Vendas, Compras/Suprimentos, Engenharia/Técnico, Financeiro, RH, SAC, Não identificada.
Tipos: telefone, celular/WhatsApp, e-mail, formulário de contato, LinkedIn da empresa, outras redes corporativas.

### Coleta no site (regras)

- Só o **site da própria empresa**: deduzido do domínio do e-mail cadastral (exceto provedores gratuitos e prováveis
  escritórios contábeis) ou informado pelo usuário. A ficha avisa quando o site foi deduzido.
- Respeita o **robots.txt**; se ele não puder ser lido (erro de rede ou 401/403), **não coleta**.
- Agente identificado (`EspacoAlarcon/0.1 …`), 1 segundo entre páginas, no máximo 6 páginas e 40 segundos, só no
  mesmo domínio, só páginas HTML até 2 MB.
- Segue apenas links de contato/sobre/atendimento (palavras inteiras do endereço; "contactors" de um catálogo não conta).
- **Nunca** acessa endereços internos (localhost, rede local, 169.254.x.x, `.local`), inclusive após redirecionamento.
- Não entra em plataformas com login, não burla CAPTCHA, não inventa contatos: se nada for encontrado, a ficha diz "Nenhum contato localizado".
- Logotipo: não coletado nesta versão.

## Consulta pontual por CNPJ

**BrasilAPI** (gratuita, sem chave; verificada respondendo em 22/10/2026): botão na ficha e na revisão da lista de referência
(para CNPJ informado fora da base). Intervalo mínimo de 3 s entre consultas, até 3 tentativas com espera progressiva em
429/5xx, cache local de 7 dias (`consulta_cnpj`). Não serve para descobrir empresas.
Conectores pagos (CNPJá comercial, Econodata): previstos como configuração `conector_*_ativo = 0`; nenhum contratado.

## IE/ICMS

- Botão **"Consultar IE/ICMS (UF)"**: copia o CNPJ (com os três níveis de fallback) e abre a página oficial da UF;
  botão **"Consultar no CCC nacional"**.
- A consulta automática não é feita: o CCC exige login gov.br (confirmado em 22/10/2026: redireciona para o login) e os
  SINTEGRAs costumam ter CAPTCHA. O sistema não burla nenhum dos dois.
- Links por UF em **Configurações → Links de IE/ICMS** (editáveis). Padrão: portal nacional do SINTEGRA
  (`http://www.sintegra.gov.br/`, onde se escolhe a UF) e CCC. O portal do SINTEGRA **não respondeu a este ambiente
  de nuvem** (fora do Brasil); a validação dos links e a troca pelo link direto de cada SEFAZ devem ser feitas no PC do
  Paulo e anotadas na coluna "Observação".
- Registro em poucos cliques: situação (habilitado / não habilitado / não localizado), IE, data da consulta e observação;
  a ficha mostra "confirmado pelo usuário em DD/MM/AAAA". Filtro de busca por situação de IE.
- O sistema **nunca** infere contribuinte ou não contribuinte e **nunca** afirma benefício fiscal.
- Certificado digital A1 (web service `NfeConsultaCadastro`): opcional, desativado (`ie_certificado_a1_ativo = 0`).
  Para ativar no futuro seria preciso: certificado A1 da empresa, senha guardada fora do código e implementação do
  cliente SOAP; não implementado nesta versão.

## LGPD

**Finalidade:** prospecção comercial B2B de empresas que possam comprar fios e cabos da Condvolt.
**Base legal pretendida:** legítimo interesse (art. 7º, IX, da LGPD), com dados tornados públicos pela Receita Federal.
**O Paulo deve validar esta base legal com o jurídico ou o DPO da Condvolt.**

Salvaguardas implementadas:
- QSA importado **como a Receita publica** (CPF já mascarado). Não há tentativa de desmascarar CPF nem cruzamento com
  outras fontes para obter endereço, telefone ou redes pessoais.
- Empresários individuais/MEI: nomes com provável nome de pessoa são marcados na lista de referência; a natureza
  jurídica "empresário individual" também marca.
- **Exclusão a pedido do titular:** botão "Excluir a pedido" no quadro de sócios anonimiza todas as ocorrências da pessoa.
  O pedido fica guardado só como **hash** (sem o nome) e é reaplicado automaticamente a cada importação da Receita.
- **Não contatar:** marcação na ficha (com motivo); a empresa some da busca por padrão e aparece com aviso.
- Dados pessoais ficam **só no banco local**: nunca em logs (a auditoria registra apenas o evento), no repositório, em
  serviços de nuvem ou em exportações automáticas.
- Logs com retenção definida (5 arquivos × 2 MB).
