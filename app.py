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
NOME_RECEBEDOR  = "Pedro"
CIDADE_PIX      = "teste"
# ──────────────────────────────────────────────

LEGACY_FILE = "donations.json"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
SHEET_CAMPAIGNS = "campaigns"
SHEET_DONATIONS = "donations"
CAMPAIGNS_HEADER = ["id", "nome", "meta", "dia_referencia", "status", "criada_em", "fechada_em", "ativa"]
DONATIONS_HEADER = ["campaign_id", "nome", "valor", "data_hora", "observacao"]

# ── Google Sheets backend ─────────────────────
def _secrets_ready() -> bool:
    try:
        return (
            "gcp_service_account" in st.secrets
            and "gsheets" in st.secrets
            and "spreadsheet_id" in st.secrets["gsheets"]
        )
    except Exception:
        return False

@st.cache_resource(show_spinner=False)
def _open_book():
    from google.oauth2.service_account import Credentials
    import gspread
    creds = Credentials.from_service_account_info(
        dict(st.secrets["gcp_service_account"]), scopes=SCOPES,
    )
    client = gspread.authorize(creds)
    return client.open_by_key(st.secrets["gsheets"]["spreadsheet_id"])

def _ensure_ws(book, title, header):
    try:
        ws = book.worksheet(title)
    except Exception:
        ws = book.add_worksheet(title=title, rows=1000, cols=len(header))
        ws.update(values=[header], range_name="A1")
        return ws
    # Rewrite header if it changed (data rows below untouched)
    if ws.row_values(1) != header:
        ws.update(values=[header], range_name="A1")
    return ws

def _row_ativa(v) -> bool:
    return str(v).strip().lower() in ("sim", "true", "1", "yes", "y", "x")

def load_state() -> dict:
    book = _open_book()
    ws_c = _ensure_ws(book, SHEET_CAMPAIGNS, CAMPAIGNS_HEADER)
    ws_d = _ensure_ws(book, SHEET_DONATIONS, DONATIONS_HEADER)

    rows_c = ws_c.get_all_records()
    rows_d = ws_d.get_all_records()

    campaigns, active_id = [], None
    for r in rows_c:
        cid = str(r.get("id", "")).strip()
        if not cid:
            continue
        campaigns.append({
            "id":             cid,
            "nome":           str(r.get("nome", "")),
            "meta":           float(r.get("meta") or 0),
            "dia_referencia": str(r.get("dia_referencia", "")),
            "status":         str(r.get("status", "ativa")),
            "criada_em":      str(r.get("criada_em", "")),
            "fechada_em":     str(r.get("fechada_em", "")) or None,
            "donations":      [],
        })
        if _row_ativa(r.get("ativa", "")):
            active_id = cid

    by_id = {c["id"]: c for c in campaigns}
    for r in rows_d:
        cid = str(r.get("campaign_id", "")).strip()
        if cid in by_id:
            by_id[cid]["donations"].append({
                "nome":       str(r.get("nome", "")),
                "valor":      float(r.get("valor") or 0),
                "data_hora":  str(r.get("data_hora", "")),
                "observacao": str(r.get("observacao", "")),
            })

    # Migração one-shot do donations.json antigo, se existir e sheet estiver vazio
    if not campaigns and os.path.exists(LEGACY_FILE):
        with open(LEGACY_FILE, "r", encoding="utf-8") as f:
            old = json.load(f)
        cid = "palworld-1-0"
        campaigns = [{
            "id":             cid,
            "nome":           "Palworld 1.0",
            "meta":           95.90,
            "dia_referencia": "Julho/2026",
            "status":         "ativa",
            "criada_em":      datetime.now().strftime("%d/%m/%Y %H:%M"),
            "fechada_em":     None,
            "donations":      list(old),
        }]
        active_id = cid
        save_state({"active_id": active_id, "campaigns": campaigns})

    return {"active_id": active_id, "campaigns": campaigns}

def save_state(state: dict) -> None:
    book = _open_book()
    ws_c = _ensure_ws(book, SHEET_CAMPAIGNS, CAMPAIGNS_HEADER)
    ws_d = _ensure_ws(book, SHEET_DONATIONS, DONATIONS_HEADER)

    rows_c = [CAMPAIGNS_HEADER]
    for c in state["campaigns"]:
        rows_c.append([
            c.get("id", ""),
            c.get("nome", ""),
            c.get("meta", 0),
            c.get("dia_referencia", ""),
            c.get("status", ""),
            c.get("criada_em", ""),
            c.get("fechada_em") or "",
            "sim" if c["id"] == state.get("active_id") else "",
        ])

    rows_d = [DONATIONS_HEADER]
    for c in state["campaigns"]:
        for d in c.get("donations", []):
            rows_d.append([
                c["id"],
                d.get("nome", ""),
                d.get("valor", 0),
                d.get("data_hora", ""),
                d.get("observacao", ""),
            ])

    ws_c.clear()
    ws_c.update(values=rows_c, range_name="A1")
    ws_d.clear()
    ws_d.update(values=rows_d, range_name="A1")

# ── Admin auth ────────────────────────────────
def _admin_password() -> str | None:
    try:
        pwd = st.secrets["admin"]["password"]
        return str(pwd) if pwd else None
    except Exception:
        return None

def is_admin() -> bool:
    return bool(st.session_state.get("is_admin"))

# ── Helpers de estado ─────────────────────────
def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or datetime.now().strftime("campanha-%Y%m%d%H%M%S")

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

# ── Guard: credenciais do Google Sheets ───────
if not _secrets_ready():
    st.markdown('<h1 class="main-title">Fundo Comunitário</h1>', unsafe_allow_html=True)
    st.error("Google Sheets não configurado.")
    st.markdown("""
Configure `.streamlit/secrets.toml` (localmente) ou os *Secrets* no Streamlit Cloud com:

```toml
[admin]
password = "escolha-uma-senha-forte"

[gsheets]
spreadsheet_id = "ID_DA_SUA_PLANILHA"

[gcp_service_account]
type = "service_account"
project_id = "..."
private_key_id = "..."
private_key = "-----BEGIN PRIVATE KEY-----\\n...\\n-----END PRIVATE KEY-----\\n"
client_email = "...@....iam.gserviceaccount.com"
client_id = "..."
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "..."
universe_domain = "googleapis.com"
```

Passos rápidos:
1. Crie um projeto em [console.cloud.google.com](https://console.cloud.google.com) e ative as APIs **Google Sheets** e **Google Drive**.
2. Crie uma *Service Account*, gere uma chave JSON e cole os campos acima em `secrets.toml`.
3. Crie uma planilha no Google Sheets, copie o `spreadsheet_id` da URL, e compartilhe a planilha com o `client_email` da service account (permissão de Editor).
4. Reinicie o app.
""")
    st.stop()

# ── Carregar estado ───────────────────────────
try:
    state = load_state()
except Exception as e:
    st.error(f"Falha ao ler Google Sheets: {e}")
    st.stop()

# ── Sidebar: gestão de campanhas ──────────────
with st.sidebar:
    st.header("Campanhas")
    active = get_active(state)
    if active:
        st.success(f"Ativa: **{active['nome']}**")
    else:
        st.warning("Nenhuma campanha ativa")

    admin_pwd = _admin_password()

    if not is_admin():
        with st.expander("Login admin", expanded=False):
            if admin_pwd is None:
                st.error("Senha de admin não configurada em `secrets.toml` (`[admin] password = ...`).")
            else:
                with st.form("form_admin_login", clear_on_submit=True):
                    pwd = st.text_input("Senha", type="password")
                    entrar = st.form_submit_button("Entrar", use_container_width=True)
                if entrar:
                    if pwd == admin_pwd:
                        st.session_state["is_admin"] = True
                        st.rerun()
                    else:
                        st.error("Senha incorreta.")
    else:
        st.info("Modo admin")
        if st.button("Sair do admin", use_container_width=True):
            st.session_state.pop("is_admin", None)
            st.rerun()

        with st.expander("Nova campanha", expanded=(active is None)):
            with st.form("form_nova_campanha", clear_on_submit=True):
                novo_nome = st.text_input("Nome do jogo / campanha", placeholder="Ex.: Palworld 2.0")
                nova_meta = st.number_input("Meta (R$)", min_value=1.0, value=100.0, step=10.0, format="%.2f")
                novo_dia  = st.text_input("Dia de referência", value=datetime.now().strftime("%d/%m/%Y"))
                st.caption("Se já houver campanha ativa, ela será encerrada e permanecerá no histórico.")
                criar = st.form_submit_button("Criar e ativar", use_container_width=True)
            if criar:
                if not novo_nome.strip():
                    st.error("Informe o nome da campanha.")
                else:
                    if active:
                        active["status"]     = "encerrada"
                        active["fechada_em"] = datetime.now().strftime("%d/%m/%Y %H:%M")
                    cid = unique_id(state, _slugify(novo_nome))
                    state["campaigns"].append({
                        "id":             cid,
                        "nome":           novo_nome.strip(),
                        "meta":           float(nova_meta),
                        "dia_referencia": novo_dia.strip(),
                        "status":         "ativa",
                        "criada_em":      datetime.now().strftime("%d/%m/%Y %H:%M"),
                        "fechada_em":     None,
                        "donations":      [],
                    })
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
                    edit_dia  = st.text_input("Dia de referência", value=active["dia_referencia"])
                    salvar = st.form_submit_button("Salvar alterações", use_container_width=True)
                if salvar:
                    active["nome"]           = edit_nome.strip() or active["nome"]
                    active["meta"]           = float(edit_meta)
                    active["dia_referencia"] = edit_dia.strip()
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

    st.caption("Armazenamento: Google Sheets")

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
    st.markdown(f'<p class="sub-title">Arrecadação de {active["dia_referencia"]}</p>', unsafe_allow_html=True)
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

    st.subheader(f"Histórico de contribuições — {active['dia_referencia']}")
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
            f"{c['nome']} — {c.get('dia_referencia','')}  |  "
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
