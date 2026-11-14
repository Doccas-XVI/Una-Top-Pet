// ============================================================================
// Pets Una - aplicativo do tutor (protótipo mobile ligado ao banco via /api)
// Os dados fictícios do protótipo foram substituídos por chamadas à API Flask.
// ============================================================================

const $ = (id) => document.getElementById(id);

// Escapa texto antes de colocar em innerHTML (nomes e descrições vêm do banco)
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => (
  { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
));

let estado = { cliente: null, pets: [], servicos: [], profissionais: [], agendamentos: [], historico: [], notificacoes: [] };
let selectedPetId = null;
let editingPetId = null;
let selectedAiSample = null;

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

// ---------------------------------------------------------------- carga dos dados
async function carregar() {
  estado = await api("GET", "/api/dados");
  if (!estado.pets.some((p) => p.id === selectedPetId)) selectedPetId = estado.pets.length ? estado.pets[0].id : null;
  renderAll();
}

function mostrarApp() {
  $("screen-auth").classList.add("hidden");
  $("app-shell").classList.remove("hidden");
  $("tutor-greeting").textContent = `Olá, ${estado.cliente.nome.split(" ")[0]}! 👋`;
  switchTab("home");
}

// ---------------------------------------------------------------- autenticação
function toggleAuthMode(mode) {
  const formLogin = $("form-login");
  const formReg = $("form-register");
  const tabLogin = $("tab-login");
  const tabReg = $("tab-register");
  const ativo = "flex-1 py-2 text-sm font-semibold rounded-lg bg-white text-primary shadow-sm transition";
  const inativo = "flex-1 py-2 text-sm font-semibold rounded-lg text-slate-500 transition";
  if (mode === "login") {
    formLogin.classList.remove("hidden"); formReg.classList.add("hidden");
    tabLogin.className = ativo; tabReg.className = inativo;
  } else {
    formLogin.classList.add("hidden"); formReg.classList.remove("hidden");
    tabReg.className = ativo; tabLogin.className = inativo;
  }
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
    $(`tab-${t}`).classList.add("hidden");
    const navBtn = $(`nav-${t}`);
    navBtn.classList.remove("text-primary", "font-semibold");
    navBtn.classList.add("text-slate-400", "font-medium");
  });
  $(`tab-${tab}`).classList.remove("hidden");
  const ativo = $(`nav-${tab}`);
  ativo.classList.remove("text-slate-400", "font-medium");
  ativo.classList.add("text-primary", "font-semibold");
}

function togglePetSubtab(sub) {
  const ativo = "flex-1 py-2 text-xs font-semibold rounded-lg bg-white text-primary shadow-sm transition";
  const inativo = "flex-1 py-2 text-xs font-semibold rounded-lg text-slate-600 transition";
  const hist = sub === "history";
  $("pet-history-content").classList.toggle("hidden", !hist);
  $("pet-info-content").classList.toggle("hidden", hist);
  $("subtab-history").className = hist ? ativo : inativo;
  $("subtab-info").className = hist ? inativo : ativo;
}

// ---------------------------------------------------------------- renderização
function renderAll() {
  renderHome();
  renderPetsTab();
  renderAgenda();
}

function renderHome() {
  // Avisos do pet shop (ex.: animal pronto para buscar)
  $("notificacoes-box").innerHTML = estado.notificacoes.map((n) => `
    <div class="bg-orange-50 border border-orange-200 rounded-2xl p-3.5 flex items-start gap-3">
      <span class="text-xl">🔔</span>
      <div class="flex-1">
        <p class="text-xs font-bold text-orange-900">Aviso do pet shop</p>
        <p class="text-xs text-orange-900 mt-0.5">${esc(n.mensagem)}</p>
        <p class="text-[10px] text-orange-700 mt-1">${esc(fmtDataHora(n.data))}</p>
      </div>
      <button onclick="marcarLida(${n.id})" class="text-[11px] font-bold text-orange-700 underline shrink-0">Entendi</button>
    </div>`).join("");

  // Próximo agendamento (status Agendado, a partir de agora)
  const agora = new Date();
  const proximo = estado.agendamentos
    .filter((a) => a.status === "Agendado" && parseDataHora(a.data_hora) >= agora)
    .sort((a, b) => a.data_hora.localeCompare(b.data_hora))[0];
  const card = $("next-appointment-card");
  if (proximo) {
    card.innerHTML = `
      <div class="flex items-center justify-between mb-2">
        <span class="text-[11px] uppercase tracking-wider font-semibold bg-white/20 px-2.5 py-0.5 rounded-full">Próximo Agendamento</span>
        <span class="text-[11px] font-bold bg-accent px-2.5 py-0.5 rounded-full">${esc(proximo.status)}</span>
      </div>
      <h4 class="text-base font-bold">${esc(proximo.servico_nome)} • ${esc(proximo.pet_nome)} ${avatarDe(proximo.pet_especie)}</h4>
      <p class="text-xs text-teal-100 mt-0.5">${esc(proximo.prof_nome)}${proximo.prof_especialidade ? ` (${esc(proximo.prof_especialidade)})` : ""}</p>
      <div class="mt-3 pt-2.5 border-t border-white/20 flex items-center justify-between text-xs font-medium">
        <span>📅 ${esc(fmtDataHora(proximo.data_hora))}</span>
        <button onclick="switchTab('agenda')" class="underline">Ver todos</button>
      </div>`;
  } else {
    card.innerHTML = `
      <p class="text-[11px] uppercase tracking-wider font-semibold">Próximo Agendamento</p>
      <h4 class="text-base font-bold mt-1">Nenhum agendamento marcado</h4>
      <button onclick="switchTab('agenda'); openBookingModal();" class="mt-3 text-xs font-semibold underline">Agendar agora</button>`;
  }

  // Lista horizontal de pets
  $("home-pets-list").innerHTML = estado.pets.length ? estado.pets.map((p) => `
    <button onclick="selectedPetId=${p.id}; switchTab('pets'); renderPetsTab();" class="shrink-0 w-24 bg-white p-3 rounded-2xl border border-slate-100 shadow-sm flex flex-col items-center gap-1.5 hover:border-primary transition">
      <div class="w-11 h-11 rounded-full bg-teal-50 flex items-center justify-center text-2xl">${avatarDe(p.especie)}</div>
      <span class="text-xs font-bold text-slate-700 truncate w-full text-center">${esc(p.nome)}</span>
      <span class="text-[10px] text-slate-400">${esc(especieLabel(p.especie))}</span>
    </button>`).join("")
    : `<p class="text-xs text-slate-400 py-2">Nenhum pet cadastrado. Toque em “+ Novo Pet”.</p>`;
}

function renderPetsTab() {
  const selector = $("pets-selector");
  selector.innerHTML = estado.pets.map((p) => `
    <button onclick="selectedPetId=${p.id}; renderPetsTab();" class="shrink-0 px-3.5 py-1.5 rounded-full text-xs font-semibold transition ${p.id === selectedPetId ? "bg-primary text-white shadow-sm" : "bg-white text-slate-600 border border-slate-200"}">
      ${avatarDe(p.especie)} ${esc(p.nome)}
    </button>`).join("");

  const pet = estado.pets.find((p) => p.id === selectedPetId);
  if (!pet) {
    $("pet-profile-card").innerHTML = `<p class="text-xs text-slate-400 text-center py-4">Nenhum pet cadastrado ainda.</p>`;
    $("pet-history-content").innerHTML = "";
    $("pet-info-content").innerHTML = "";
    return;
  }

  $("pet-profile-card").innerHTML = `
    <div class="flex items-center gap-3.5">
      <div class="w-14 h-14 rounded-2xl bg-teal-50 flex items-center justify-center text-3xl">${avatarDe(pet.especie)}</div>
      <div class="flex-1">
        <h3 class="text-base font-bold text-slate-800">${esc(pet.nome)}</h3>
        <p class="text-xs text-slate-500">${esc(especieLabel(pet.especie))} • ${esc(pet.raca)}</p>
        <div class="flex gap-2 mt-1.5">
          ${pet.porte ? `<span class="px-2 py-0.5 rounded-md bg-slate-100 text-[10px] font-semibold text-slate-600">Porte: ${esc(pet.porte)}</span>` : ""}
          <span class="px-2 py-0.5 rounded-md bg-slate-100 text-[10px] font-semibold text-slate-600">${esc(idadeTexto(pet.data_nascimento))}</span>
        </div>
      </div>
    </div>
    <div class="flex gap-2 mt-3 pt-3 border-t border-slate-100">
      <button onclick="openPetModal(${pet.id})" class="flex-1 py-2 rounded-xl bg-slate-100 hover:bg-slate-200 text-xs font-semibold text-slate-700">✏️ Editar</button>
      <button onclick="removePet(${pet.id})" class="flex-1 py-2 rounded-xl bg-red-50 hover:bg-red-100 text-xs font-semibold text-red-700">🗑️ Remover</button>
    </div>`;

  const hist = estado.historico.filter((h) => h.pet_id === pet.id);
  $("pet-history-content").innerHTML = hist.length ? hist.map((h) => `
    <div class="bg-white rounded-2xl p-3.5 border border-slate-100 shadow-sm space-y-1.5">
      <div class="flex items-center justify-between">
        <span class="px-2 py-0.5 rounded-md bg-teal-50 text-primary text-[10px] font-bold">${esc(h.tipo || "Registro")}</span>
        <span class="text-[11px] text-slate-400">${esc(fmtData(h.data))}</span>
      </div>
      <p class="text-xs font-semibold text-slate-700">${esc(h.profissional)}</p>
      <p class="text-xs text-slate-600">${esc(h.descricao)}</p>
      ${h.anexos.length ? `<div class="pt-1 flex flex-wrap gap-1.5">${h.anexos.map((a) => `<span class="inline-flex items-center gap-1 px-2 py-1 rounded-lg bg-slate-100 text-[10px] font-medium text-slate-600 break-all">📎 ${esc(a)}</span>`).join("")}</div>` : ""}
    </div>`).join("")
    : `<p class="text-xs text-slate-400 text-center py-6">Nenhum registro médico encontrado.</p>`;

  const linha = (rot, val, ultimo) => `<div class="flex justify-between py-1 ${ultimo ? "" : "border-b border-slate-100"}"><span class="text-slate-500">${rot}:</span><span class="font-semibold">${esc(val)}</span></div>`;
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
    const cor = a.status === "Agendado" ? "bg-orange-50 text-accent"
      : a.status === "Realizado" ? "bg-teal-50 text-primary" : "bg-slate-100 text-slate-500";
    return `
      <div class="bg-white rounded-2xl p-4 border border-slate-100 shadow-sm space-y-2 ${a.status === "Cancelado" ? "opacity-60" : ""}">
        <div class="flex items-center justify-between">
          <span class="text-xs font-bold text-slate-800">${esc(a.servico_nome)}</span>
          <span class="px-2.5 py-0.5 rounded-full text-[10px] font-bold ${cor}">${esc(a.status)}</span>
        </div>
        <p class="text-xs text-slate-600">Pet: <strong>${esc(a.pet_nome)}</strong> ${avatarDe(a.pet_especie)} • ${esc(a.prof_nome)}</p>
        <div class="flex items-center justify-between text-[11px] text-slate-400 pt-1 border-t border-slate-50">
          <span>📅 ${esc(fmtDataHora(a.data_hora))}</span>
          <span class="font-semibold text-slate-700">${esc(brl(a.preco))}</span>
        </div>
        ${a.status === "Agendado" ? `<button onclick="cancelarAgendamento(${a.id})" class="w-full py-2 rounded-xl bg-red-50 hover:bg-red-100 text-red-700 text-xs font-semibold">Cancelar agendamento</button>` : ""}
      </div>`;
  }).join("") : `<p class="text-xs text-slate-400 text-center py-8">Você ainda não tem agendamentos.</p>`;
}

// ---------------------------------------------------------------- pets (cadastrar / editar / remover)
function openPetModal(id) {
  editingPetId = id || null;
  const form = $("modal-pet").querySelector("form");
  form.reset();
  $("pet-modal-title").textContent = editingPetId ? "Editar Pet" : "Cadastrar Novo Pet";
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
  if (type === "pele") {
    $("ai-preview-img").src = "https://placehold.co/400x250/FED7AA/9A3412?text=Imagem:+Lesao+na+Pele";
    $("ai-preview-label").textContent = "Amostra selecionada: Lesão avermelhada na pele";
  } else {
    $("ai-preview-img").src = "https://placehold.co/400x250/CCFBF1/0F766E?text=Imagem:+Olho+Irritado";
    $("ai-preview-label").textContent = "Amostra selecionada: Secreção e vermelhidão ocular";
  }
  $("btn-run-ai").disabled = false;
}

function runAiAnalysis() {
  if (!selectedAiSample) return;
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

iniciar();
