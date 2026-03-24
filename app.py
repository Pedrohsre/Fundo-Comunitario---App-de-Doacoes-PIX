import streamlit as st
import json
import os
import qrcode
from io import BytesIO
from datetime import datetime

# ──────────────────────────────────────────────
# CONFIG
# ──────────────────────────────────────────────
CHAVE_PIX       = "bc01cf21-b50b-4285-b880-825822031cf3"          # CPF, CNPJ, e-mail, telefone ou chave aleatória
NOME_RECEBEDOR  = "Pedro R"    # max 25 caracteres
CIDADE_PIX      = "teste"            # max 15 caracteres
META_MENSAL     = 1000.0                # valor total que precisa ser arrecadado
MES_REFERENCIA  = "Abril/2026"           # aparece no cabeçalho
# ──────────────────────────────────────────────

DONATIONS_FILE = "donations.json"

# ── Persistência ──────────────────────────────
def load_data():
    if os.path.exists(DONATIONS_FILE):
        with open(DONATIONS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save_data(data):
    with open(DONATIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

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

# ── Página ────────────────────────────────────
st.set_page_config(
    page_title="Servidor de Mine",
    page_icon=None,
    layout="centered",
)

# CSS customizado
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

# Cabeçalho
st.markdown(f'<h1 class="main-title">Servidor de Mine</h1>', unsafe_allow_html=True)
st.markdown(f'<p class="sub-title">Arrecadação de {MES_REFERENCIA}</p>', unsafe_allow_html=True)
st.divider()

# Carregar dados
donations = load_data()
total_arrecadado = sum(d["valor"] for d in donations)
restante = max(META_MENSAL - total_arrecadado, 0)
progresso = min(total_arrecadado / META_MENSAL, 1.0)

# ── Barra de progresso ────────────────────────
st.markdown(f"""
<div class="meta-box">
    <div class="meta-label">Meta</div>
    <div class="meta-value">R$ {META_MENSAL:,.2f}</div>
</div>
""", unsafe_allow_html=True)

col1, col2, col3 = st.columns(3)
col1.metric("Arrecadado",  f"R$ {total_arrecadado:,.2f}")
col2.metric("Faltando",    f"R$ {restante:,.2f}")
col3.metric("Doadores",    len(donations))

st.progress(progresso, text=f"{progresso*100:.1f}% da meta")
st.divider()

# ── Formulário de doação ──────────────────────
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
    submitted = st.form_submit_button("Gerar QR Code PIX", use_container_width=True)

# ── Gerar QR Code ─────────────────────────────
if submitted:
    if not nome_doador.strip():
        st.error("Por favor, informe seu nome antes de gerar o QR Code.")
    elif valor_doacao <= 0:
        st.error("O valor deve ser maior que zero.")
    else:
        payload  = build_pix_payload(CHAVE_PIX, valor_doacao, NOME_RECEBEDOR, CIDADE_PIX,
                                     descricao=f"Doacao {nome_doador[:15]}")
        qr_bytes = qr_to_bytes(payload)

        st.success(f"QR Code gerado para **{nome_doador}** — R$ {valor_doacao:.2f}")

        col_qr, col_info = st.columns([1, 1])
        with col_qr:
            st.image(qr_bytes, caption="Escaneie no app do banco", use_container_width=True)
        with col_info:
            st.markdown("**Copia e Cola PIX:**")
            st.code(payload, language=None)
            st.caption("Cole este código no seu aplicativo bancário caso o QR não funcione.")

        # ── Confirmar pagamento ────────────────
        st.info("Após realizar o pagamento, clique no botão abaixo para registrar sua contribuição.")

        # Guarda no session_state para confirmar depois
        st.session_state["pending"] = {
            "nome":       nome_doador.strip(),
            "valor":      valor_doacao,
            "data_hora":  data_hora.strip() or datetime.now().strftime("%d/%m/%Y %H:%M"),
            "observacao": observacao.strip(),
        }

# ── Botão de confirmação (fora do form) ───────
if "pending" in st.session_state:
    p = st.session_state["pending"]
    if st.button(
        f"Confirmar pagamento de R$ {p['valor']:.2f} — {p['nome']}",
        use_container_width=True,
        type="primary",
    ):
        donations.append(p)
        save_data(donations)
        del st.session_state["pending"]
        st.success(f"Obrigado, **{p['nome']}**! Sua doação foi registrada.")
        st.balloons()
        st.rerun()

st.divider()

# ── Histórico de doações ──────────────────────
st.subheader(f"Histórico de contribuições — {MES_REFERENCIA}")

if donations:
    # Mais recentes primeiro
    for d in reversed(donations):
        obs_html = f' <span style="color:#94a3b8">· {d["observacao"]}</span>' if d.get("observacao") else ""
        st.markdown(f"""
        <div class="donor-card">
            <span class="donor-name">{d['nome']}</span>
            <span class="donor-info"> &nbsp;|&nbsp; R$ {d['valor']:,.2f} &nbsp;|&nbsp; {d['data_hora']}{obs_html}</span>
        </div>
        """, unsafe_allow_html=True)
else:
    st.info("Nenhuma contribuição registrada ainda. Seja o primeiro!")

# ── Rodapé ────────────────────────────────────
st.divider()
st.markdown(
    "<p style='text-align:center;color:#94a3b8;font-size:.8rem;'>"
    "Gerado com carinho · Chave PIX registrada em nome de <b>" + NOME_RECEBEDOR + "</b></p>",
    unsafe_allow_html=True,
)
