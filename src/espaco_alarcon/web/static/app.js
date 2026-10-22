/* Espaço Alarcon — utilidades da interface.
 *
 * Cópia para a área de transferência com fallback obrigatório (seção 5.4):
 * 1) navigator.clipboard em contexto seguro (localhost/HTTPS);
 * 2) textarea temporário + document.execCommand('copy') (acesso pela LAN em HTTP);
 * 3) mostra o texto já selecionado com "Pressione Ctrl+C para copiar".
 * Sempre informa visualmente o resultado; nunca falha em silêncio.
 */
(function () {
  "use strict";

  function aviso(mensagem, tipo, textoParaCopiar) {
    var antigo = document.querySelector(".toast");
    if (antigo) antigo.remove();
    var el = document.createElement("div");
    el.className = "toast" + (tipo === "erro" ? " erro" : "");
    el.setAttribute("role", tipo === "erro" ? "alert" : "status");
    el.textContent = mensagem;
    if (textoParaCopiar !== undefined) {
      var campo = document.createElement("input");
      campo.value = textoParaCopiar;
      campo.readOnly = true;
      el.appendChild(campo);
      document.body.appendChild(el);
      campo.focus();
      campo.select();
      setTimeout(function () { el.remove(); }, 15000);
      return;
    }
    document.body.appendChild(el);
    setTimeout(function () { el.remove(); }, 3000);
  }

  function copiarComExecCommand(texto) {
    var area = document.createElement("textarea");
    area.value = texto;
    area.setAttribute("readonly", "");
    area.style.position = "fixed";
    area.style.top = "-1000px";
    document.body.appendChild(area);
    area.select();
    var ok = false;
    try { ok = document.execCommand("copy"); } catch (e) { ok = false; }
    area.remove();
    return ok;
  }

  function copiar(texto) {
    var concluido = function () { aviso("Copiado: " + texto, "ok"); };
    var manual = function () { aviso("Não foi possível copiar automaticamente. Pressione Ctrl+C para copiar.", "erro", texto); };
    var fallback = function () { if (copiarComExecCommand(texto)) { concluido(); } else { manual(); } };
    if (window.isSecureContext && navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(texto).then(concluido, fallback);
    } else {
      fallback();
    }
  }

  window.EspacoAlarcon = { copiar: copiar };

  document.addEventListener("click", function (ev) {
    var botao = ev.target.closest("[data-copiar]");
    if (!botao) return;
    ev.preventDefault();
    copiar(botao.getAttribute("data-copiar"));
  });
})();
