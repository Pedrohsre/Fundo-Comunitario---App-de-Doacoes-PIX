import streamlit as st
import json
import os
import re
import qrcode
from io import BytesIO
from datetime import datetime

# ──────────────────────────────────────────────
# CONFIG PIX (dados técnicos do recebedor)
# ──────────────────────────────────────────────
CHAVE_PIX       = "bc01cf21-b50b-4285-b880-825822031cf3"
NOME_RECEBEDOR  = "Pedro R"
CIDADE_PIX      = "teste"
# ──────────────────────────────────────────────

DATA_FILE   = "campaigns.json"
LEGACY_FILE = "donations.json"

# ── Persistência ──────────────────────────────
def _empty_state():
    return {"active_id": None, "campaigns": []}

def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or datetime.now().strftime("campanha-%Y%m%d%H%M%S")

def load_state():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    # Migração do formato antigo (donations.json)
    if os.path.exists(LEGACY_FILE):
        with open(LEGACY_FILE, "r", encoding="utf-8") as f:
            old = json.load(f)
        campaign = {
            "id":             "palworld-1-0",
            "nome":           "Palworld 1.0",
            "meta":           95.90,
            "mes_referencia": "Julho/2026",
            "status":         "ativa",
            "criada_em":      datetime.now().strftime("%d/%m/%Y %H:%M"),
            "donations":      old,
        }
        state = {"active_id": campaign["id"], "campaigns": [campaign]}
        save_state(state)
        return state
    return _empty_state()

def save_state(state):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def get_active(state):
    for c in state["campaigns"]:
        if c["id"] == state.get("active_id"):
            return c
    return None

def unique_id(state, base_id):
    ids = {c["id"] for c in state["campaigns"]}
    cid, n = base_id, 2
    while cid in ids:
        cid = f"{base_id}-{n}"
        n += 1
    return cid

# ── PIX helpers ───────────────────────────────
def _fmt(id_: str, value: str) -> str:
    return f"{id_}{len(value):02d}{value}"

def _crc16(data: str) -> int:
    crc = 0xFFFF
    for ch in data:
        crc ^= ord(ch) << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if crc & 0x8000 else crc << 1
            crc &= 0xFFFF
    return crc

def build_pix_payload(chave: str, valor: float, nome: str, cidade: str, descricao: str = "Doacao") -> str:
    desc_safe = descricao[:25] if descricao else ""
    merchant  = _fmt("00", "BR.GOV.BCB.PIX") + _fmt("01", chave)
    if desc_safe:
        merchant += _fmt("02", desc_safe)
    merchant = _fmt("26", merchant)

    payload = (
        _fmt("00", "01")
        + "010212"
        + merchant
        + _fmt("52", "0000")
        + _fmt("53", "986")
        + _fmt("54", f"{valor:.2f}")
        + _fmt("58", "BR")
        + _fmt("59", nome[:25])
        + _fmt("60", cidade[:15])
        + _fmt("62", _fmt("05", "DOACAO"))
        + "6304"
    )
    return payload + f"{_crc16(payload):04X}"

def qr_to_bytes(payload: str) -> bytes:
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=4,
    )
    qr.add_data(payload)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#1a1a2e", back_color="white")
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

def render_donation_list(donations):
    for d in reversed(donations):
        obs_html = f' <span style="color:#94a3b8">· {d["observacao"]}</span>' if d.get("observacao") else ""
        st.markdown(f"""
        <div class="donor-card">
            <span class="donor-name">{d['nome']}</span>
            <span class="donor-info"> &nbsp;|&nbsp; R$ {d['valor']:,.2f} &nbsp;|&nbsp; {d['data_hora']}{obs_html}</span>
        </div>
        """, unsafe_allow_html=True)

# ── Página ────────────────────────────────────
st.set_page_config(
    page_title="Fundo Comunitário",
    page_icon=None,
    layout="centered",
)

st.markdown("""
<style>
    html, body, [class*="css"] { font-family: 'Segoe UI', sans-serif; }
    .main-title  { text-align:center; font-size:2.2rem; font-weight:700;
                   color:#16213e; margin-bottom:0; }
    .sub-title   { text-align:center; color:#555; margin-top:4px; }
    .meta-box    { background:#f0fdf4; border:1px solid #86efac;
                   border-radius:12px; padding:18px 24px; margin:16px 0; }
    .meta-label  { font-size:.85rem; color:#166534; font-weight:600;
                   text-transform:uppercase; letter-spacing:.05em; }
    .meta-value  { font-size:2rem; font-weight:800; color:#15803d; }
    .donor-card  { background:#f8fafc; border-left:4px solid #3b82f6;
                   border-radius:8px; padding:10px 16px; margin:6px 0; }
    .donor-name  { font-weight:700; color:#1e3a5f; }
    .donor-info  { font-size:.82rem; color:#64748b; }
</style>
""", unsafe_allow_html=True)

state = load_state()

# ── Sidebar: gestão de campanhas ──────────────
with st.sidebar:
    st.header("Campanhas")
    active = get_active(state)
    if active:
        st.success(f"Ativa: **{active['nome']}**")
    else:
        st.warning("Nenhuma campanha ativa")

    with st.expander("Nova campanha", expanded=(active is None)):
        with st.form("form_nova_campanha", clear_on_submit=True):
            novo_nome = st.text_input("Nome do jogo / campanha", placeholder="Ex.: Palworld 2.0")
            nova_meta = st.number_input("Meta (R$)", min_value=1.0, value=100.0, step=10.0, format="%.2f")
            novo_mes  = st.text_input("Mês de referência", value=datetime.now().strftime("%m/%Y"))
            st.caption("Se já houver campanha ativa, ela será encerrada e permanecerá no histórico.")
            criar = st.form_submit_button("Criar e ativar", use_container_width=True)
        if criar:
            if not novo_nome.strip():
                st.error("Informe o nome da campanha.")
            else:
                if active:
                    active["status"]    = "encerrada"
                    active["fechada_em"] = datetime.now().strftime("%d/%m/%Y %H:%M")
                cid = unique_id(state, _slugify(novo_nome))
                nova = {
                    "id":             cid,
                    "nome":           novo_nome.strip(),
                    "meta":           float(nova_meta),
                    "mes_referencia": novo_mes.strip(),
                    "status":         "ativa",
                    "criada_em":      datetime.now().strftime("%d/%m/%Y %H:%M"),
                    "donations":      [],
                }
                state["campaigns"].append(nova)
                state["active_id"] = cid
                save_state(state)
                st.session_state.pop("pending", None)
                st.rerun()

    if active:
        with st.expander("Editar campanha atual"):
            with st.form("form_edit_campanha"):
                edit_nome = st.text_input("Nome", value=active["nome"])
                edit_meta = st.number_input(
                    "Meta (R$)", min_value=1.0,
                    value=float(active["meta"]), step=10.0, format="%.2f",
                )
                edit_mes  = st.text_input("Mês de referência", value=active["mes_referencia"])
                salvar = st.form_submit_button("Salvar alterações", use_container_width=True)
            if salvar:
                active["nome"]           = edit_nome.strip() or active["nome"]
                active["meta"]           = float(edit_meta)
                active["mes_referencia"] = edit_mes.strip()
                save_state(state)
                st.rerun()

        with st.expander("Encerrar campanha atual"):
            st.caption("As doações continuam salvas no histórico.")
            if st.button("Encerrar agora", use_container_width=True):
                active["status"]     = "encerrada"
                active["fechada_em"] = datetime.now().strftime("%d/%m/%Y %H:%M")
                state["active_id"]   = None
                save_state(state)
                st.session_state.pop("pending", None)
                st.rerun()

# ── Área principal ────────────────────────────
active = get_active(state)

if not active:
    st.markdown('<h1 class="main-title">Fundo Comunitário</h1>', unsafe_allow_html=True)
    st.info("Nenhuma campanha ativa. Crie uma na barra lateral para começar a receber doações.")
else:
    donations = active["donations"]
    meta      = float(active["meta"])
    total     = sum(d["valor"] for d in donations)
    restante  = max(meta - total, 0)
    progresso = min(total / meta, 1.0) if meta > 0 else 0.0

    st.markdown(f'<h1 class="main-title">{active["nome"]}</h1>', unsafe_allow_html=True)
    st.markdown(f'<p class="sub-title">Arrecadação de {active["mes_referencia"]}</p>', unsafe_allow_html=True)
    st.divider()

    st.markdown(f"""
    <div class="meta-box">
        <div class="meta-label">Meta</div>
        <div class="meta-value">R$ {meta:,.2f}</div>
    </div>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns(3)
    col1.metric("Arrecadado", f"R$ {total:,.2f}")
    col2.metric("Faltando",   f"R$ {restante:,.2f}")
    col3.metric("Doadores",   len(donations))
    st.progress(progresso, text=f"{progresso*100:.1f}% da meta")
    st.divider()

    # ── Formulário de doação ──────────────────
    st.subheader("Fazer uma doação")
    with st.form("form_doacao", clear_on_submit=True):
        nome_doador = st.text_input("Seu nome *", placeholder="Ex.: Fulaninho 123")

        col_val, col_data = st.columns([1, 1])
        with col_val:
            valor_doacao = st.number_input(
                "Valor (R$) *",
                min_value=1.0,
                max_value=float(max(restante, 1)),
                value=min(50.0, float(max(restante, 1))),
                step=5.0,
                format="%.2f",
            )
        with col_data:
            data_hora = st.text_input(
                "Data / hora",
                value=datetime.now().strftime("%d/%m/%Y %H:%M"),
                placeholder="dd/mm/aaaa hh:mm",
            )

        observacao = st.text_input("Observação (opcional)", placeholder="Ex.: tomai a esmola")
        submitted  = st.form_submit_button("Gerar QR Code PIX", use_container_width=True)

    if submitted:
        if not nome_doador.strip():
            st.error("Por favor, informe seu nome antes de gerar o QR Code.")
        elif valor_doacao <= 0:
            st.error("O valor deve ser maior que zero.")
        else:
            payload  = build_pix_payload(
                CHAVE_PIX, valor_doacao, NOME_RECEBEDOR, CIDADE_PIX,
                descricao=f"Doacao {nome_doador[:15]}",
            )
            qr_bytes = qr_to_bytes(payload)

            st.success(f"QR Code gerado para **{nome_doador}** — R$ {valor_doacao:.2f}")

            col_qr, col_info = st.columns([1, 1])
            with col_qr:
                st.image(qr_bytes, caption="Escaneie no app do banco", use_container_width=True)
            with col_info:
                st.markdown("**Copia e Cola PIX:**")
                st.code(payload, language=None)
                st.caption("Cole este código no seu aplicativo bancário caso o QR não funcione.")

            st.info("Após realizar o pagamento, clique no botão abaixo para registrar sua contribuição.")

            st.session_state["pending"] = {
                "nome":        nome_doador.strip(),
                "valor":       valor_doacao,
                "data_hora":   data_hora.strip() or datetime.now().strftime("%d/%m/%Y %H:%M"),
                "observacao":  observacao.strip(),
                "campaign_id": active["id"],
            }

    # ── Confirmação (fora do form) ────────────
    pending = st.session_state.get("pending")
    if pending and pending.get("campaign_id") == active["id"]:
        if st.button(
            f"Confirmar pagamento de R$ {pending['valor']:.2f} — {pending['nome']}",
            use_container_width=True,
            type="primary",
        ):
            active["donations"].append({
                "nome":       pending["nome"],
                "valor":      pending["valor"],
                "data_hora":  pending["data_hora"],
                "observacao": pending["observacao"],
            })
            save_state(state)
            del st.session_state["pending"]
            st.success(f"Obrigado, **{pending['nome']}**! Sua doação foi registrada.")
            st.balloons()
            st.rerun()

    st.divider()

    # ── Histórico da campanha ativa ───────────
    st.subheader(f"Histórico de contribuições — {active['mes_referencia']}")
    if donations:
        render_donation_list(donations)
    else:
        st.info("Nenhuma contribuição registrada ainda. Seja o primeiro!")

# ── Campanhas anteriores ──────────────────────
encerradas = [c for c in state["campaigns"] if c["id"] != state.get("active_id")]
if encerradas:
    st.divider()
    st.subheader("Campanhas anteriores")
    for c in reversed(encerradas):
        total_c = sum(d["valor"] for d in c["donations"])
        meta_c  = float(c.get("meta", 0))
        titulo  = (
            f"{c['nome']} — {c.get('mes_referencia','')}  |  "
            f"R$ {total_c:,.2f} de R$ {meta_c:,.2f}  ·  {len(c['donations'])} doadores"
        )
        with st.expander(titulo):
            if c.get("fechada_em"):
                st.caption(f"Encerrada em {c['fechada_em']}")
            if c["donations"]:
                render_donation_list(c["donations"])
            else:
                st.caption("Sem doações registradas.")

# ── Rodapé ────────────────────────────────────
st.divider()
st.markdown(
    "<p style='text-align:center;color:#94a3b8;font-size:.8rem;'>"
    "Gerado com carinho · Chave PIX registrada em nome de <b>" + NOME_RECEBEDOR + "</b></p>",
    unsafe_allow_html=True,
)
