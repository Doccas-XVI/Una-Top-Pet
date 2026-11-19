// ============================================================================
// UNA Top Pet - aplicativo do tutor (mobile e web responsiva via /api)
// Compartilhado por static/tutor/index.html e static/web/index.html.
// ============================================================================

const $ = (id) => document.getElementById(id);

// Escapa texto antes de colocar em innerHTML (nomes e descrições vêm do banco)
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => (
  { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
));

// Helper para ícones SVG do sprite da identidade visual
const ico = (name, cls = "") =>
  `<svg class="ico ${cls}" aria-hidden="true"><use href="/static/brand/icons.svg#${name}"/></svg>`;

let estado = { cliente: null, pets: [], servicos: [], profissionais: [], agendamentos: [], historico: [], notificacoes: [] };
let selectedPetId = null;
let editingPetId = null;
let selectedAiSample = null;

const TAB_META = {
  home: { title: "Início", subtitle: "Resumo dos seus pets, avisos e próximos agendamentos" },
  pets: { title: "Meus pets", subtitle: "Perfil, dados gerais e prontuário de saúde" },
  agenda: { title: "Agenda", subtitle: "Acompanhe e solicite serviços no pet shop" },
  ai: { title: "IA Vet • Triagem", subtitle: "Análise preliminar orientativa por imagem" },
};

// ---------------------------------------------------------------- utilidades
async function api(metodo, url, corpo) {
  const opcoes = { method: metodo, headers: { "X-Requested-With": "fetch" }, credentials: "same-origin" };
  if (corpo !== undefined) {
    opcoes.headers["Content-Type"] = "application/json";
    opcoes.body = JSON.stringify(corpo);
  }
  let resp;
  try {
    resp = await fetch(url, opcoes);
  } catch (e) {
    throw new Error("Sem conexão com o servidor.");
  }
  const dados = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    const erro = new Error(dados.erro || "Erro inesperado. Tente novamente.");
    erro.status = resp.status;
    throw erro;
  }
  return dados;
}

function showToast(msg, icon = "✅") {
  const toast = $("toast");
  if (!toast) return;
  $("toast-msg").textContent = msg;
  $("toast-icon").textContent = icon;
  toast.classList.remove("hidden");
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => toast.classList.add("hidden"), Math.max(2800, msg.length * 55));
}
const showError = (e) => showToast(e.message || String(e), "⚠️");

const brl = (n) => (n == null ? "—" : Number(n).toLocaleString("pt-BR", { style: "currency", currency: "BRL" }));

function parseDataHora(txt) { return new Date(String(txt).replace(" ", "T")); }
function fmtDataHora(txt) {
  const [d, h] = String(txt).split(" ");
  const [y, m, dia] = d.split("-");
  return `${dia}/${m}/${y} • ${(h || "").slice(0, 5)}`;
}
function fmtData(txt) {
  const [y, m, d] = String(txt).slice(0, 10).split("-");
  return `${d}/${m}/${y}`;
}

function avatarDe(especie) {
  const e = String(especie || "").toLowerCase();
  if (/(can|cão|cao|cachorro|dog)/.test(e)) return "🐶";
  if (/(fel|gato|cat)/.test(e)) return "🐱";
  if (/(ave|pássaro|passaro)/.test(e)) return "🦜";
  return "🐾";
}

function idadeTexto(nasc) {
  if (!nasc) return "Idade não informada";
  const n = new Date(nasc + "T00:00:00");
  const h = new Date();
  let meses = (h.getFullYear() - n.getFullYear()) * 12 + h.getMonth() - n.getMonth();
  if (h.getDate() < n.getDate()) meses--;
  if (meses < 0) meses = 0;
  if (meses < 12) return meses === 1 ? "1 mês" : `${meses} meses`;
  const anos = Math.floor(meses / 12);
  return anos === 1 ? "1 ano" : `${anos} anos`;
}

const especieLabel = (e) => ({ Canina: "Cão", Felina: "Gato" }[e] || e);

function iniciais(nome) {
  const partes = String(nome || "").trim().split(/\s+/).filter(Boolean);
  if (!partes.length) return "U";
  return (partes[0][0] + (partes.length > 1 ? partes[partes.length - 1][0] : "")).toUpperCase();
}

// ---------------------------------------------------------------- carga dos dados
async function carregar() {
  estado = await api("GET", "/api/dados");
  if (!estado.pets.some((p) => p.id === selectedPetId)) selectedPetId = estado.pets.length ? estado.pets[0].id : null;
  renderAll();
}

function mostrarApp() {
  $("screen-auth").classList.add("hidden");
  $("app-shell").classList.remove("hidden");
  const primeiroNome = estado.cliente.nome.split(" ")[0];
  if ($("tutor-greeting")) $("tutor-greeting").textContent = `Olá, ${primeiroNome}! 👋`;
  if ($("tutor-full-name")) $("tutor-full-name").textContent = estado.cliente.nome;
  if ($("tutor-email")) $("tutor-email").textContent = estado.cliente.email || "";
  if ($("tutor-initials")) $("tutor-initials").textContent = iniciais(estado.cliente.nome);
  switchTab("home");
}

// ---------------------------------------------------------------- autenticação
function toggleAuthMode(mode) {
  const isLogin = mode === "login";
  $("form-login").classList.toggle("hidden", !isLogin);
  $("form-register").classList.toggle("hidden", isLogin);
  $("tab-login").classList.toggle("is-active", isLogin);
  $("tab-register").classList.toggle("is-active", !isLogin);
}

async function handleLogin(e) {
  e.preventDefault();
  try {
    await api("POST", "/api/login", { email: $("login-email").value, senha: $("login-senha").value });
    await carregar();
    mostrarApp();
  } catch (err) { showError(err); }
}

async function handleRegister(e) {
  e.preventDefault();
  try {
    await api("POST", "/api/cadastro", {
      Nome: $("reg-nome").value, CPF: $("reg-cpf").value, Telefone: $("reg-tel").value,
      Endereco: $("reg-end").value, Email: $("reg-email").value, senha: $("reg-senha").value,
    });
    await carregar();
    mostrarApp();
    showToast("Tutor cadastrado com sucesso!");
  } catch (err) { showError(err); }
}

async function logout() {
  try { await api("POST", "/api/logout"); } catch (e) { /* sai mesmo assim */ }
  estado = { cliente: null, pets: [], servicos: [], profissionais: [], agendamentos: [], historico: [], notificacoes: [] };
  selectedPetId = null;
  $("app-shell").classList.add("hidden");
  $("screen-auth").classList.remove("hidden");
}

// Se a sessão ainda estiver ativa, entra direto
async function iniciar() {
  try {
    await carregar();
    mostrarApp();
  } catch (err) {
    if (err.status !== 401) showError(err);
  }
}

// ---------------------------------------------------------------- navegação
function switchTab(tab) {
  ["home", "pets", "agenda", "ai"].forEach((t) => {
    const sec = $(`tab-${t}`);
    if (sec) sec.classList.toggle("hidden", t !== tab);
  });
  document.querySelectorAll("[data-nav]").forEach((btn) => {
    btn.classList.toggle("is-active", btn.dataset.nav === tab);
  });
  if (TAB_META[tab]) {
    if ($("web-page-title")) $("web-page-title").textContent = TAB_META[tab].title;
    if ($("web-page-subtitle")) $("web-page-subtitle").textContent = TAB_META[tab].subtitle;
  }
  const main = $("main-content");
  if (main) main.scrollTop = 0;
}

function togglePetSubtab(sub) {
  const hist = sub === "history";
  $("pet-history-content").classList.toggle("hidden", !hist);
  $("pet-info-content").classList.toggle("hidden", hist);
  $("subtab-history").classList.toggle("is-active", hist);
  $("subtab-info").classList.toggle("is-active", !hist);
}

// ---------------------------------------------------------------- renderização
function renderAll() {
  renderHome();
  renderPetsTab();
  renderAgenda();
}

function renderHome() {
  // Contadores opcionais (usados no cabeçalho/resumo da versão web)
  const abertos = estado.agendamentos.filter((a) => a.status === "Agendado").length;
  const realizados = estado.agendamentos.filter((a) => a.status === "Realizado").length;
  if ($("stat-pets")) $("stat-pets").textContent = estado.pets.length;
  if ($("stat-agendados")) $("stat-agendados").textContent = abertos;
  if ($("stat-realizados")) $("stat-realizados").textContent = realizados;
  if ($("stat-notificacoes")) $("stat-notificacoes").textContent = estado.notificacoes.length;

  // Avisos do pet shop (ex.: animal pronto para buscar)
  $("notificacoes-box").innerHTML = estado.notificacoes.map((n) => `
    <div class="notice animate-fade-in">
      <span class="tile-icon tile-dark w-9 h-9 rounded-xl">${ico("bell", "w-4 h-4")}</span>
      <div class="flex-1 min-w-0">
        <p class="text-xs font-bold text-primary-900">Aviso do pet shop</p>
        <p class="text-xs text-primary-700 mt-0.5 leading-relaxed">${esc(n.mensagem)}</p>
        <p class="text-[10px] text-primary-400 mt-1 flex items-center gap-1">${ico("clock", "w-3 h-3")} ${esc(fmtDataHora(n.data))}</p>
      </div>
      <button onclick="marcarLida(${n.id})" class="btn btn-lime-soft btn-xs shrink-0">Entendi</button>
    </div>`).join("");

  // Próximo agendamento (status Agendado, a partir de agora)
  const agora = new Date();
  const proximo = estado.agendamentos
    .filter((a) => a.status === "Agendado" && parseDataHora(a.data_hora) >= agora)
    .sort((a, b) => a.data_hora.localeCompare(b.data_hora))[0];
  const card = $("next-appointment-card");
  if (proximo) {
    card.innerHTML = `
      <div class="flex items-center justify-between gap-2 mb-3">
        <span class="text-[10px] uppercase tracking-[.16em] font-semibold bg-white/10 border border-white/15 px-2.5 py-1 rounded-full text-primary-100">Próximo agendamento</span>
        <span class="px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-accent text-primary-900">${esc(proximo.status)}</span>
      </div>
      <h4 class="text-base sm:text-lg font-bold text-white leading-snug">${esc(proximo.servico_nome)} • ${esc(proximo.pet_nome)} ${avatarDe(proximo.pet_especie)}</h4>
      <p class="text-xs text-primary-200 mt-1">${esc(proximo.prof_nome)}${proximo.prof_especialidade ? ` (${esc(proximo.prof_especialidade)})` : ""}</p>
      <div class="mt-4 pt-3 border-t border-white/15 flex items-center justify-between gap-2 text-xs font-medium">
        <span class="inline-flex items-center gap-1.5 text-accent-200">${ico("calendar", "w-4 h-4 text-accent")} ${esc(fmtDataHora(proximo.data_hora))}</span>
        <button onclick="switchTab('agenda')" class="inline-flex items-center gap-1 text-white hover:text-accent transition font-semibold">
          Ver todos ${ico("chevron-right", "w-3.5 h-3.5")}
        </button>
      </div>`;
  } else {
    card.innerHTML = `
      <span class="text-[10px] uppercase tracking-[.16em] font-semibold text-accent-300">Próximo agendamento</span>
      <h4 class="text-base sm:text-lg font-bold mt-1 text-white">Nenhum agendamento marcado</h4>
      <p class="text-xs text-primary-200 mt-1">Escolha um serviço e reserve o melhor horário para o seu pet.</p>
      <button onclick="switchTab('agenda'); openBookingModal();" class="btn btn-accent btn-sm mt-4">
        ${ico("calendar-plus")} Agendar agora
      </button>`;
  }

  // Lista de pets (scroll horizontal no mobile, grid na versão web)
  $("home-pets-list").innerHTML = estado.pets.length ? estado.pets.map((p) => `
    <button onclick="selectedPetId=${p.id}; switchTab('pets'); renderPetsTab();" class="pet-tile card card-hover p-3.5 flex flex-col items-center gap-2 text-center">
      <div class="pet-avatar w-12 h-12 text-2xl">${avatarDe(p.especie)}</div>
      <div class="w-full min-w-0">
        <span class="block text-xs font-bold text-primary-900 truncate">${esc(p.nome)}</span>
        <span class="block text-[10px] text-primary-400 truncate">${esc(especieLabel(p.especie))}</span>
        <span class="pet-tile-extra block text-[11px] text-primary-500 mt-1 truncate">${esc(p.raca)} • ${esc(idadeTexto(p.data_nascimento))}</span>
      </div>
    </button>`).join("")
    : `<div class="card p-5 text-center w-full col-span-full">
        <p class="text-xs text-primary-400">Nenhum pet cadastrado ainda. Toque em “+ Novo pet” para começar.</p>
       </div>`;
}

function renderPetsTab() {
  const selector = $("pets-selector");
  selector.innerHTML = estado.pets.map((p) => `
    <button onclick="selectedPetId=${p.id}; renderPetsTab();" class="pill ${p.id === selectedPetId ? "is-active" : ""}">
      <span>${avatarDe(p.especie)}</span>
      <span>${esc(p.nome)}</span>
    </button>`).join("");

  const pet = estado.pets.find((p) => p.id === selectedPetId);
  if (!pet) {
    $("pet-profile-card").innerHTML = `
      <div class="text-center py-6 space-y-3">
        <div class="pet-avatar w-14 h-14 text-2xl mx-auto">🐾</div>
        <p class="text-xs text-primary-400">Nenhum pet cadastrado ainda.</p>
        <button onclick="openPetModal()" class="btn btn-primary btn-sm">${ico("plus")} Cadastrar primeiro pet</button>
      </div>`;
    $("pet-history-content").innerHTML = "";
    $("pet-info-content").innerHTML = "";
    return;
  }

  $("pet-profile-card").innerHTML = `
    <div class="flex items-center gap-3.5">
      <div class="pet-avatar w-14 h-14 text-3xl">${avatarDe(pet.especie)}</div>
      <div class="flex-1 min-w-0">
        <h3 class="text-base font-bold text-primary-900 truncate">${esc(pet.nome)}</h3>
        <p class="text-xs text-primary-500 truncate">${esc(especieLabel(pet.especie))} • ${esc(pet.raca)}</p>
        <div class="flex flex-wrap gap-1.5 mt-2">
          ${pet.porte ? `<span class="chip">Porte: ${esc(pet.porte)}</span>` : ""}
          <span class="chip chip-lime">${esc(idadeTexto(pet.data_nascimento))}</span>
        </div>
      </div>
    </div>
    <div class="flex gap-2 mt-4 pt-3 border-t border-primary-100">
      <button onclick="openPetModal(${pet.id})" class="btn btn-soft btn-sm flex-1">${ico("edit")} Editar</button>
      <button onclick="removePet(${pet.id})" class="btn btn-danger btn-sm flex-1">${ico("trash")} Remover</button>
    </div>`;

  const hist = estado.historico.filter((h) => h.pet_id === pet.id);
  $("pet-history-content").innerHTML = hist.length ? hist.map((h) => `
    <div class="card p-4 space-y-2">
      <div class="flex items-center justify-between gap-2">
        <span class="chip chip-lime">${esc(h.tipo || "Registro")}</span>
        <span class="text-[11px] text-primary-400 inline-flex items-center gap-1">${ico("calendar", "w-3.5 h-3.5")} ${esc(fmtData(h.data))}</span>
      </div>
      <p class="text-xs font-bold text-primary-900">${esc(h.profissional)}</p>
      <p class="text-xs text-primary-600 leading-relaxed">${esc(h.descricao)}</p>
      ${h.anexos.length ? `<div class="pt-1 flex flex-wrap gap-1.5">${h.anexos.map((a) => `<span class="chip break-all">${ico("clip", "w-3 h-3")} ${esc(a)}</span>`).join("")}</div>` : ""}
    </div>`).join("")
    : `<div class="card p-6 text-center"><p class="text-xs text-primary-400">Nenhum registro médico encontrado para ${esc(pet.nome)}.</p></div>`;

  const linha = (rot, val, ultimo) =>
    `<div class="flex justify-between gap-4 py-2.5 ${ultimo ? "" : "border-b border-primary-100"}"><span class="text-primary-400">${rot}</span><span class="font-semibold text-primary-900 text-right">${esc(val)}</span></div>`;
  $("pet-info-content").innerHTML =
    linha("Nome", pet.nome) + linha("Espécie", especieLabel(pet.especie)) + linha("Raça", pet.raca) +
    linha("Sexo", pet.sexo === "M" ? "Macho" : pet.sexo === "F" ? "Fêmea" : "—") +
    linha("Porte", pet.porte || "—") +
    linha("Nascimento", pet.data_nascimento ? fmtData(pet.data_nascimento) : "—", true);
}

function renderAgenda() {
  const ordem = { Agendado: 0, Realizado: 1, Cancelado: 2 };
  const lista = [...estado.agendamentos].sort((a, b) =>
    ordem[a.status] - ordem[b.status] ||
    (a.status === "Agendado" ? a.data_hora.localeCompare(b.data_hora) : b.data_hora.localeCompare(a.data_hora)));

  $("agenda-list").innerHTML = lista.length ? lista.map((a) => {
    const badgeCls = a.status === "Agendado" ? "badge-agendado"
      : a.status === "Realizado" ? "badge-realizado" : "badge-cancelado";
    return `
      <div class="card p-4 flex flex-col justify-between gap-3 ${a.status === "Cancelado" ? "opacity-60" : ""}">
        <div class="space-y-2">
          <div class="flex items-start justify-between gap-2">
            <span class="text-sm font-bold text-primary-900 leading-snug">${esc(a.servico_nome)}</span>
            <span class="badge ${badgeCls}">${esc(a.status)}</span>
          </div>
          <p class="text-xs text-primary-600">
            Pet: <strong class="text-primary-900">${esc(a.pet_nome)}</strong> ${avatarDe(a.pet_especie)} • ${esc(a.prof_nome)}
          </p>
        </div>
        <div class="space-y-2.5">
          <div class="flex items-center justify-between text-xs text-primary-400 pt-2.5 border-t border-primary-100">
            <span class="inline-flex items-center gap-1.5">${ico("calendar", "w-3.5 h-3.5 text-accent-600")} ${esc(fmtDataHora(a.data_hora))}</span>
            <span class="font-bold text-primary-900">${esc(brl(a.preco))}</span>
          </div>
          ${a.status === "Agendado" ? `<button onclick="cancelarAgendamento(${a.id})" class="btn btn-danger btn-sm btn-block">${ico("x")} Cancelar agendamento</button>` : ""}
        </div>
      </div>`;
  }).join("") : `
    <div class="card p-8 text-center col-span-full space-y-3">
      <span class="tile-icon tile-mist w-12 h-12 mx-auto">${ico("calendar")}</span>
      <p class="text-xs text-primary-400">Você ainda não tem agendamentos.</p>
      <button onclick="openBookingModal()" class="btn btn-accent btn-sm">${ico("calendar-plus")} Agendar serviço</button>
    </div>`;
}

// ---------------------------------------------------------------- pets (cadastrar / editar / remover)
function openPetModal(id) {
  editingPetId = id || null;
  const form = $("modal-pet").querySelector("form");
  form.reset();
  $("pet-modal-title").textContent = editingPetId ? "Editar pet" : "Cadastrar novo pet";
  if (editingPetId) {
    const p = estado.pets.find((x) => x.id === editingPetId);
    $("pet-nome").value = p.nome;
    // garante que a espécie atual exista no <select>, mesmo que seja uma não listada
    const sel = $("pet-especie");
    if (![...sel.options].some((o) => o.value === p.especie)) sel.add(new Option(p.especie, p.especie));
    sel.value = p.especie;
    $("pet-raca").value = p.raca;
    if (p.porte) $("pet-porte").value = p.porte;
    if (p.sexo) $("pet-sexo").value = p.sexo;
    $("pet-nasc").value = p.data_nascimento || "";
  }
  $("modal-pet").classList.remove("hidden");
}
function closePetModal() { $("modal-pet").classList.add("hidden"); }

async function handleSavePet(e) {
  e.preventDefault();
  const corpo = {
    nome: $("pet-nome").value, especie: $("pet-especie").value, raca: $("pet-raca").value,
    porte: $("pet-porte").value, sexo: $("pet-sexo").value, data_nascimento: $("pet-nasc").value,
  };
  try {
    if (editingPetId) {
      await api("PUT", `/api/pets/${editingPetId}`, corpo);
    } else {
      const r = await api("POST", "/api/pets", corpo);
      selectedPetId = r.id;
    }
    closePetModal();
    await carregar();
    showToast(editingPetId ? `${corpo.nome} atualizado!` : `${corpo.nome} cadastrado!`);
  } catch (err) { showError(err); }
}

async function removePet(id) {
  const pet = estado.pets.find((p) => p.id === id);
  if (!confirm(`Remover ${pet.nome}? O histórico de saúde fica guardado no pet shop.`)) return;
  try {
    await api("DELETE", `/api/pets/${id}`);
    await carregar();
    showToast(`${pet.nome} removido.`);
  } catch (err) { showError(err); }
}

// ---------------------------------------------------------------- agendamentos
function openBookingModal() {
  if (!estado.pets.length) {
    showToast("Cadastre um pet antes de agendar.", "ℹ️");
    openPetModal();
    return;
  }
  $("book-pet").innerHTML = estado.pets.map((p) =>
    `<option value="${p.id}" ${p.id === selectedPetId ? "selected" : ""}>${avatarDe(p.especie)} ${esc(p.nome)}</option>`).join("");
  $("book-service").innerHTML = estado.servicos.map((s) =>
    `<option value="${s.id}">${esc(s.nome)} (${s.duracao ? s.duracao + "min - " : ""}${esc(brl(s.preco))})</option>`).join("");
  updateBookingProfs();
  // não permite escolher horário no passado
  const agora = new Date();
  agora.setMinutes(agora.getMinutes() - agora.getTimezoneOffset());
  $("book-datetime").min = agora.toISOString().slice(0, 16);
  $("modal-booking").classList.remove("hidden");
}
function closeBookingModal() { $("modal-booking").classList.add("hidden"); }

// Só lista os profissionais habilitados no serviço escolhido
function updateBookingProfs() {
  const sid = Number($("book-service").value);
  const profs = estado.profissionais.filter((p) => p.servicos.includes(sid));
  $("book-prof").innerHTML = profs.length
    ? profs.map((p) => `<option value="${p.id}">${esc(p.nome)}${p.especialidade ? ` (${esc(p.especialidade)})` : ""}</option>`).join("")
    : `<option value="">Nenhum profissional disponível para este serviço</option>`;
}

async function handleAddBooking(e) {
  e.preventDefault();
  try {
    await api("POST", "/api/agendamentos", {
      pet_id: $("book-pet").value, servico_id: $("book-service").value,
      prof_id: $("book-prof").value, data_hora: $("book-datetime").value,
    });
    closeBookingModal();
    e.target.reset();
    await carregar();
    showToast("Agendamento confirmado!");
  } catch (err) { showError(err); }
}

async function cancelarAgendamento(id) {
  if (!confirm("Cancelar este agendamento?")) return;
  try {
    await api("POST", `/api/agendamentos/${id}/cancelar`);
    await carregar();
    showToast("Agendamento cancelado.");
  } catch (err) { showError(err); }
}

async function marcarLida(id) {
  try {
    await api("POST", `/api/notificacoes/${id}/lida`);
    await carregar();
  } catch (err) { showError(err); }
}

// ---------------------------------------------------------------- IA Vet (simulação do protótipo)
function selectAiSample(type) {
  selectedAiSample = type;
  $("ai-upload-placeholder").classList.add("hidden");
  $("ai-preview-box").classList.remove("hidden");
  $("ai-result-card").classList.add("hidden");
  if ($("ai-empty-result")) $("ai-empty-result").classList.remove("hidden");
  if (type === "pele") {
    $("ai-preview-img").src = "https://placehold.co/600x360/EEF5C8/2F3D41?text=Amostra:+Lesao+na+Pele";
    $("ai-preview-label").textContent = "Amostra selecionada: Lesão avermelhada na pele";
  } else {
    $("ai-preview-img").src = "https://placehold.co/600x360/E3E8EA/2F3D41?text=Amostra:+Olho+Irritado";
    $("ai-preview-label").textContent = "Amostra selecionada: Secreção e vermelhidão ocular";
  }
  $("btn-run-ai").disabled = false;
}

function runAiAnalysis() {
  if (!selectedAiSample) return;
  if ($("ai-empty-result")) $("ai-empty-result").classList.add("hidden");
  $("ai-loading").classList.remove("hidden");
  $("ai-result-card").classList.add("hidden");
  setTimeout(() => {
    $("ai-loading").classList.add("hidden");
    $("ai-result-card").classList.remove("hidden");
    if (selectedAiSample === "pele") {
      $("ai-confidence-badge").textContent = "89% confiança";
      $("ai-confidence-bar").style.width = "89%";
      $("ai-result-text").textContent = "Possível quadro de dermatite alérgica ou irritação cutânea localizada. Recomenda-se evitar que o animal lamba a região e agendar avaliação dermatológica.";
    } else {
      $("ai-confidence-badge").textContent = "84% confiança";
      $("ai-confidence-bar").style.width = "84%";
      $("ai-result-text").textContent = "Sinais compatíveis com conjuntivite leve ou corpo estranho ocular. Recomenda-se higienização com soro fisiológico e consulta clínica.";
    }
  }, 1000);
}

// Fecha modais ao pressionar Esc ou clicar no fundo escuro
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") { closePetModal(); closeBookingModal(); }
});
["modal-pet", "modal-booking"].forEach((id) => {
  const el = $(id);
  if (el) el.addEventListener("click", (e) => { if (e.target === el) el.classList.add("hidden"); });
});

iniciar();
