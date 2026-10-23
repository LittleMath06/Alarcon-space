# Guia rápido do Espaço Alarcon

O Espaço Alarcon ajuda a encontrar empresas que podem comprar os fios e cabos da Condvolt, usando a base pública de
empresas da Receita Federal. Tudo fica no seu computador. O sistema mostra **oportunidades possíveis**, nunca
garantia de compra.

## 1. Instalar (uma vez)

1. Dê dois cliques em **EspacoAlarcon-Instalador**.
2. Se aparecer a tela azul **"O Windows protegeu o computador"** (SmartScreen): clique em **Mais informações** e
   depois em **Executar assim mesmo**. Isso acontece porque o programa ainda não tem assinatura digital paga; não é vírus.
3. Siga o instalador. Marque "Criar atalhos na área de trabalho".
   - Marque "Permitir acesso pela rede local" só se for usar o sistema também em outro computador ou celular da casa/escritório.
4. Precisa de cerca de **8 GB livres** no disco para a primeira importação da base. Depois, o sistema ocupa uns 5 GB, mais até 3 backups de ~1 GB cada.

## 2. Abrir e fechar

- Para abrir: dois cliques em **Iniciar Sistema**. O navegador abre sozinho no endereço `http://localhost:8765/`.
- Para fechar de verdade: dois cliques em **Encerrar Sistema**. (Fechar o navegador não desliga o sistema.)
- Se aparecer uma mensagem de erro, ela mostra onde está o arquivo de registro (log). Envie esse arquivo para quem dá suporte.

## 3. Primeiro acesso

1. Na primeira vez, o sistema pede para criar seu usuário: nome, login e uma senha de pelo menos 10 caracteres.
2. Depois disso, é só entrar com login e senha.
3. **Esqueceu a senha?** No computador onde o sistema está instalado, abra **Menu Iniciar → Espaço Alarcon →
   Redefinir Senha**, digite a nova senha duas vezes e pronto. Isso não funciona pela rede, por segurança.
4. Errou a senha 5 vezes? Espere 15 minutos ou use o Redefinir Senha.

## 4. Primeira importação da base de empresas

1. Vá em **Status das fontes** e clique em **Importar / atualizar agora** (deixe marcado "Oficial").
2. O sistema baixa cerca de 8 GB da Receita, **um arquivo por vez** (cada um é apagado logo depois de lido), e guarda só as empresas do seu perfil (Brasil inteiro).
   Leva de 30 minutos a algumas horas, conforme a internet. Você pode continuar usando o computador.
3. Se a internet cair ou o computador desligar, clique de novo em "Importar / atualizar agora": ele continua de onde parou.
4. Depois, a cada mês, o sistema confere sozinho se saiu base nova e atualiza.

## 5. Lista de clientes já atendidos

1. Vá em **Importação**, escolha o arquivo (`.txt` com um nome por linha, ou a planilha `.xlsx`) e clique em **Importar e conciliar**.
2. O sistema acha as empresas na base. As que ele não tiver certeza aparecem em **Pendências**:
   abra **Revisar** e clique em **É esta**, **Não é esta empresa** ou digite o CNPJ.
3. Essas empresas **não aparecem como leads novos** na busca.

## 6. Buscar empresas

1. Vá em **Busca**. Escolha, por exemplo, um **segmento** e uma **UF**, e clique em **Buscar**.
2. A lista já vem ordenada pelo **índice de compatibilidade** (0 a 100). Passe o mouse sobre o número para ver os motivos.
3. Clique no nome para abrir a **ficha**: dados da Receita, contatos, sócios, linha de produto sugerida.
4. Botão **Copiar** copia o CNPJ ou o contato. Se não der para copiar automaticamente, o sistema mostra o texto
   selecionado: aperte **Ctrl+C**.
5. **Exportar Excel** salva a lista numa planilha.

## 7. Contatos, IE/ICMS e site

- Na ficha, **Buscar contatos no site** visita o site da empresa e traz e-mails e telefones públicos, com a área
  (Compras, Vendas…) e o endereço da página de onde vieram.
- Telefones e e-mails da Receita podem ser do **contador** da empresa: confira.
- **Consultar IE/ICMS** copia o CNPJ e abre a página oficial do estado. Depois de consultar, registre o resultado
  (habilitado / não habilitado / não localizado). O sistema nunca adivinha isso.

## 8. Organizar os leads

- **Salvar lead** na busca ou na ficha. Em **Leads e pipeline**, mude a etapa: Novo → Para analisar → Contato realizado
  → Em negociação → Cliente confirmado.
- Marque ★ favoritos, escreva notas e coloque a data do **próximo contato**: o Dashboard avisa os lembretes do dia.
- Para descartar, informe o motivo.

## 9. Ajustar o índice

Em **Configurações → Índice de compatibilidade**, mude os pesos (por exemplo, para dar mais importância a indústrias),
marque estados prioritários e clique em **Salvar e recalcular**.

## 10. Backup (cópia de segurança)

- O sistema faz um backup automático por semana e guarda os 3 mais recentes (cerca de 1 GB cada). Para fazer na hora: **Configurações → Backup → Criar backup agora**.
- De vez em quando, copie o arquivo de backup (botão **Baixar**) para um pendrive ou HD externo.
- Para voltar um backup: **Restaurar** (só no computador onde o sistema está instalado). O estado atual é guardado antes.

## 11. Usar em outro computador ou celular da mesma rede

1. Em **Configurações → Rede local**, clique em **Ativar acesso pela rede**, depois **Encerrar Sistema** e **Iniciar Sistema**.
2. A tela mostra o endereço, por exemplo `http://192.168.0.15:8765/`. Abra esse endereço no outro aparelho e faça login.
3. Se não abrir: confira se o instalador criou a regra do firewall e se a rede do Windows está como **Privada**.
4. Se o endereço mudar de um dia para outro, peça a quem cuida do roteador uma "reserva de IP" para este computador.
5. Nunca libere o sistema para a internet.

## 12. Privacidade (LGPD)

- Os dados ficam só neste computador.
- Se uma pessoa pedir para ter os dados apagados: na ficha, quadro de sócios, **Excluir a pedido**.
- Se uma empresa pedir para não ser contatada: na ficha, **Marcar "não contatar"**.
- A base legal (legítimo interesse para prospecção B2B) deve ser confirmada com o jurídico da Condvolt.

## Onde ficam as coisas

| O quê | Onde |
|---|---|
| Programa | `C:\Program Files\EspacoAlarcon\` |
| Seus dados (banco, backups, exportações, registros) | `%LOCALAPPDATA%\EspacoAlarcon\` (digite isso na barra do Explorador de Arquivos) |
| Planilhas exportadas | `%LOCALAPPDATA%\EspacoAlarcon\exports\` |
| Backups | `%LOCALAPPDATA%\EspacoAlarcon\backups\` |
