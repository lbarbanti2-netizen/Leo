import streamlit as st
import sqlite3
import pandas as pd
import os
import re
import csv
import math
import time
from datetime import datetime, timedelta

st.set_page_config(
    page_title="SpeedMax & Digitire | Portal Corporativo de Frotas",
    page_icon="🚛",
    layout="wide",
    initial_sidebar_state="expanded"
)

PASTA_DRIVE = "/content/drive/MyDrive/SPEEDMAX_APP_SQLITE"
if not os.path.exists(PASTA_DRIVE):
    PASTA_DRIVE = "."

PASTA_CARTEIRAS = os.path.join(PASTA_DRIVE, "CARTEIRAS_VENDEDORES")
os.makedirs(PASTA_CARTEIRAS, exist_ok=True)

DB_FROTAS_PATH = "/content/speedmax_frotas.db"
if not os.path.exists(DB_FROTAS_PATH):
    DB_FROTAS_PATH = os.path.join(PASTA_DRIVE, "speedmax_frotas.db")
if not os.path.exists(DB_FROTAS_PATH):
    DB_FROTAS_PATH = "speedmax_frotas.db"

DB_CRM_PATH = os.path.join(PASTA_DRIVE, "speedmax_crm_persistente.db")

ESTADOS_PRIORITARIOS = ["NJ", "NY", "PA", "CT", "DE", "FL", "GA", "IL", "IN", "MA", "MD", "MI", "NC", "OH", "SC", "VA"]
TODOS_ESTADOS_EUA = ESTADOS_PRIORITARIOS + [
    "AL", "AK", "AZ", "AR", "CA", "CO", "DC", "HI", "ID", "IA", "KS", "KY", "LA", "ME",
    "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NM", "ND", "OK", "OR", "PR", "RI", "SD",
    "TN", "TX", "UT", "VT", "WA", "WV", "WI", "WY", "ON", "QC", "AB", "BC", "MB", "MX"
]

MEDIDAS_PNEUS = [
    "295/75R22.5 (Low Pro - Steer/Drive/Trailer)",
    "11R22.5 (Standard - Regional/OTR)",
    "11R24.5 (Tall - Heavy Duty)",
    "285/75R24.5 (Low Pro 24.5)",
    "315/80R22.5 (Heavy Steer / Waste / Concrete)",
    "255/70R22.5 (Regional / Drop Deck Trailer)",
    "275/80R22.5 (All Position)",
    "385/65R22.5 (Super Single / Wide Base)",
    "225/70R19.5 (Medium Duty / Box Truck)",
    "245/70R19.5 (Medium Duty)",
    "Mista / Outras Medidas"
]

STATUS_CRM = [
    "🆕 Novo Lead (Para Ligar)",
    "📞 Em Contato / Qualificando Decisor",
    "🛞 Cotação SpeedMax Enviada",
    "📅 Follow-up / Retorno Agendado",
    "✅ Cliente Fechado / Recorrente",
    "❄️ Sem Interesse / Revisar Futuramente"
]

# ==============================================================================
# CONEXÕES SQLITE OTIMIZADAS PARA 15+ USUÁRIOS SIMULTÂNEOS (MODO WAL)
# ==============================================================================
def get_frotas_conn():
    conn = sqlite3.connect(DB_FROTAS_PATH, timeout=30.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA cache_size = -64000;")
    conn.execute("PRAGMA temp_store = MEMORY;")
    return conn

def get_crm_conn():
    conn = sqlite3.connect(DB_CRM_PATH, timeout=30.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
    except Exception:
        pass
    return conn

def init_crm_tables():
    conn = get_crm_conn()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            email TEXT PRIMARY KEY,
            nome TEXT,
            pin TEXT,
            status TEXT,
            estados_liberados TEXT,
            permissoes TEXT DEFAULT 'BUSCAR,FAVORITAR,EXPORTAR',
            pasta_vendedor TEXT DEFAULT ''
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS favoritos_crm (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data_inclusao TEXT,
            email_vendedor TEXT,
            usdot TEXT,
            empresa TEXT,
            uf_cidade TEXT,
            decisor TEXT,
            contato TEXT,
            power_units INTEGER,
            consumo_est TEXT,
            status_crm TEXT,
            medida_pneu TEXT,
            aplicacao TEXT,
            resumo_conversa TEXT,
            data_retorno TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS historico_buscas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data_hora TEXT,
            email_vendedor TEXT,
            tipo_acao TEXT,
            criterio TEXT,
            resultado TEXT
        )
    """)
    cur.execute("""
        INSERT OR IGNORE INTO usuarios (email, nome, pin, status, estados_liberados, permissoes, pasta_vendedor)
        VALUES ('lbarbanti2@gmail.com', 'Leonardo Barbanti (Admin Master)', '000000', 'APROVADO', 'TODOS', 'ADMIN,BUSCAR,FAVORITAR,EXPORTAR', '')
    """)
    conn.commit()
    conn.close()

init_crm_tables()

if "logado" not in st.session_state:
    st.session_state.update({
        "logado": False, "email": "", "nome": "", "is_admin": False,
        "ufs": [], "permissoes": [], "ficha_atual": None,
        "pagina_atual": 0, "uf_reg": "", "cid_reg": "", "apenas_ativas_reg": False,
        "buscar_regional_ativo": False, "tentativas_pin": 0, "bloqueado_ate": 0.0,
        "login_timestamp": None,
        "cor_primaria": "#4A148C", "cor_secundaria": "#6B21A8",
        "cor_fundo": "#F4F5F9", "tam_fonte": "15.5px"
    })

# ==============================================================================
# PAINEL DE CUSTOMIZAÇÃO VISUAL NA BARRA LATERAL
# ==============================================================================
with st.sidebar.expander("🎨 Personalizar Layout & Fonte", expanded=False):
    tema_escolhido = st.selectbox(
        "Paleta Corporativa:",
        ["Violeta SpeedMax (Oficial)", "Azul Marinho Executivo", "Grafite Ultra-Contraste"]
    )
    tam_escolhido = st.selectbox(
        "Tamanho das Letras:",
        ["Médio Padrão (14px)", "Grande Confortável (16px)", "Extra Grande (18px)"],
        index=1
    )
    fundo_escolhido = st.selectbox(
        "Fundo da Página:",
        ["Cinza Executivo (#F4F5F9)", "Branco Puro (#FFFFFF)", "Lavanda Suave (#FAF5FF)"]
    )

    if "Azul" in tema_escolhido:
        st.session_state["cor_primaria"], st.session_state["cor_secundaria"] = "#0F172A", "#1E3A8A"
    elif "Grafite" in tema_escolhido:
        st.session_state["cor_primaria"], st.session_state["cor_secundaria"] = "#18181B", "#3F3F46"
    else:
        st.session_state["cor_primaria"], st.session_state["cor_secundaria"] = "#4A148C", "#6B21A8"

    st.session_state["tam_fonte"] = "15.5px" if "16px" in tam_escolhido else ("17.5px" if "18px" in tam_escolhido else "14px")
    st.session_state["cor_fundo"] = "#FFFFFF" if "Branco" in fundo_escolhido else ("#FAF5FF" if "Lavanda" in fundo_escolhido else "#F4F5F9")

COR_PRI = st.session_state["cor_primaria"]
COR_SEC = st.session_state["cor_secundaria"]
COR_BG = st.session_state["cor_fundo"]
TAM_F = st.session_state["tam_fonte"]

st.markdown(f"""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
    html, body, [class*="css"] {{
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
        font-size: {TAM_F} !important;
        color: #0F172A !important;
    }}
    .stApp {{ background-color: {COR_BG} !important; color: #0F172A !important; }}
    [data-testid="stDeployButton"] {{ display: none !important; }}
    [data-testid="stSidebar"] {{
        background: linear-gradient(180deg, {COR_PRI} 0%, {COR_SEC} 100%) !important;
        border-right: 2px solid {COR_PRI} !important;
    }}
    [data-testid="stSidebar"] p, [data-testid="stSidebar"] span,
    [data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2,
    [data-testid="stSidebar"] h3, [data-testid="stSidebar"] label {{
        color: #FFFFFF !important;
    }}
    .sidebar-box {{
        background-color: rgba(255, 255, 255, 0.16) !important;
        border: 1px solid rgba(255, 255, 255, 0.35) !important;
        color: #FFFFFF !important; padding: 10px 12px !important;
        border-radius: 8px !important; font-size: 13.5px !important;
        font-weight: 600 !important; margin-bottom: 10px !important;
    }}
    [data-testid="stSidebar"] [data-testid="stExpander"] {{
        background-color: rgba(0, 0, 0, 0.22) !important;
        border: 1px solid rgba(255, 255, 255, 0.3) !important;
        border-radius: 8px !important;
    }}
    label, [data-testid="stWidgetLabel"] p, [data-testid="stWidgetLabel"] span,
    .stTextInput label, .stSelectbox label, .stMultiSelect label,
    .stDateInput label, .stTextArea label, .stNumberInput label {{
        color: #0F172A !important; font-weight: 800 !important; font-size: {TAM_F} !important;
    }}
    input, textarea, [data-baseweb="input"] > div, [data-baseweb="base-input"],
    [data-baseweb="select"] > div, [data-baseweb="textarea"] {{
        background-color: #FFFFFF !important; color: #000000 !important;
        -webkit-text-fill-color: #000000 !important;
        border: 2px solid #94A3B8 !important; border-radius: 8px !important; font-weight: 700 !important;
    }}
    input::placeholder, textarea::placeholder {{
        color: #64748B !important; -webkit-text-fill-color: #64748B !important;
    }}
    [data-baseweb="popover"] div, [data-baseweb="menu"] li, ul[role="listbox"] li {{
        background-color: #FFFFFF !important; color: #0F172A !important; font-weight: 600 !important;
    }}
    [data-baseweb="tag"] {{
        background-color: {COR_PRI} !important; color: #FFFFFF !important;
        border-radius: 6px !important; font-weight: 700 !important;
    }}
    [data-baseweb="tag"] span {{ color: #FFFFFF !important; }}
    .stTabs [data-baseweb="tab-list"] {{ gap: 8px !important; background-color: transparent !important; padding-bottom: 6px !important; }}
    .stTabs [data-baseweb="tab"] {{
        background-color: #FFFFFF !important; color: #1E293B !important;
        border: 2px solid #CBD5E1 !important; border-radius: 10px 10px 0 0 !important;
        padding: 10px 18px !important; font-weight: 800 !important;
    }}
    .stTabs [data-baseweb="tab"] p {{ color: #1E293B !important; font-weight: 800 !important; }}
    .stTabs [aria-selected="true"] {{
        background: linear-gradient(135deg, {COR_PRI} 0%, {COR_SEC} 100%) !important;
        color: #FFFFFF !important; border-color: {COR_PRI} !important;
    }}
    .stTabs [aria-selected="true"] p {{ color: #FFFFFF !important; }}
    div.stButton > button, [data-testid="stFormSubmitButton"] > button, [data-testid="stDownloadButton"] > button {{
        background: linear-gradient(135deg, {COR_PRI} 0%, {COR_SEC} 100%) !important;
        color: #FFFFFF !important; border-radius: 8px !important; font-weight: 800 !important;
        border: none !important; padding: 0.65rem 1.4rem !important; width: 100% !important;
    }}
    div.stButton > button *, [data-testid="stFormSubmitButton"] > button *, [data-testid="stDownloadButton"] > button * {{
        color: #FFFFFF !important; font-weight: 800 !important;
    }}
    [data-testid="stForm"] {{
        background-color: #FFFFFF !important; border: 2px solid #CBD5E1 !important;
        border-radius: 12px !important; padding: 20px !important;
    }}
    .hero-banner {{
        background: linear-gradient(135deg, {COR_PRI} 0%, {COR_SEC} 100%);
        color: #FFFFFF !important; padding: 20px 26px; border-radius: 14px;
        margin-bottom: 18px; display: flex; justify-content: space-between; align-items: center;
    }}
    .hero-title {{ font-size: 22px; font-weight: 800; color: #FFFFFF !important; margin: 0; }}
    .hero-subtitle {{ font-size: 13.5px; color: #F3E8FF !important; margin-top: 4px; }}
    .hero-badge {{
        background-color: rgba(255, 255, 255, 0.2); border: 1px solid rgba(255, 255, 255, 0.4);
        padding: 8px 16px; border-radius: 30px; font-size: 12.5px; font-weight: 800; color: #FFFFFF !important;
    }}
    .kpi-card {{
        background: #FFFFFF !important; border-radius: 12px; padding: 16px;
        border: 2px solid #CBD5E1; border-top: 5px solid {COR_PRI};
        text-align: center; margin-bottom: 14px;
    }}
    .kpi-title {{ font-size: 12px; font-weight: 800; text-transform: uppercase; color: #475569 !important; margin-bottom: 6px; }}
    .kpi-value {{ font-size: 26px; font-weight: 800; color: {COR_PRI} !important; margin: 0; }}
    .kpi-sub {{ font-size: 12.5px; color: #1E293B !important; margin-top: 4px; font-weight: 600; }}
    .sec-header {{
        background: linear-gradient(90deg, {COR_PRI} 0%, {COR_SEC} 100%);
        color: #FFFFFF !important; padding: 11px 18px; border-radius: 10px 10px 0 0;
        font-weight: 800; font-size: 14.5px; margin-top: 14px;
    }}
    .sec-body {{
        background-color: #FFFFFF !important; border: 2px solid #CBD5E1;
        border-top: none; border-radius: 0 0 10px 10px; padding: 16px; margin-bottom: 12px;
    }}
    .clean-table {{ width: 100%; border-collapse: collapse; }}
    .clean-table tr {{ border-bottom: 1px solid #CBD5E1; }}
    .clean-table th {{
        text-align: left; padding: 10px 12px; color: {COR_PRI} !important;
        font-size: {TAM_F}; font-weight: 800; width: 35%;
        background-color: #F8FAFC !important; border-right: 1px solid #CBD5E1;
    }}
    .clean-table td {{
        text-align: left; padding: 10px 14px; color: #0F172A !important;
        font-size: {TAM_F}; font-weight: 700; background-color: #FFFFFF !important;
    }}
    .badge-ativo {{ background-color: #DCFCE7; color: #14532D !important; padding: 4px 10px; border-radius: 20px; font-size: 12px; font-weight: 800; }}
    .badge-inativo {{ background-color: #FEE2E2; color: #7F1D1D !important; padding: 4px 10px; border-radius: 20px; font-size: 12px; font-weight: 800; }}
    .badge-info {{ background-color: #F3E8FF; color: #3B0764 !important; padding: 4px 10px; border-radius: 6px; font-size: 12.5px; font-weight: 800; }}
</style>
""", unsafe_allow_html=True)

def limpar_num(v):
    if v is None: return 0
    s = re.sub(r"[^\d]", "", str(v).split(".")[0])
    return int(s) if s else 0

def fmt_tel(v):
    if not v or str(v).strip().lower() in ("nan", "none", ""): return "-"
    s = re.sub(r"[^\d]", "", str(v).split(".")[0])
    if len(s) == 10:
        return f"({s[:3]}) {s[3:6]}-{s[6:]}"
    return s if s else "-"

def fmt_data(v):
    s = re.sub(r"[^\d]", "", str(v or "").split(".")[0])
    if len(s) == 8:
        return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return s if s else "-"

def val_limpo(v, padrao="-"):
    if v is None: return padrao
    s = str(v).strip()
    if s.lower() in ("nan", "none", "null", ""): return padrao
    if s.endswith(".0"): s = s[:-2]
    return s

def obter_ou_criar_pasta_vendedor(email):
    nome_seguro = re.sub(r"[^a-zA-Z0-9_.-]", "_", email.strip().lower())
    caminho = os.path.join(PASTA_CARTEIRAS, nome_seguro)
    os.makedirs(caminho, exist_ok=True)

    arq_logins = os.path.join(caminho, "logins.csv")
    if not os.path.exists(arq_logins):
        with open(arq_logins, "w", newline="", encoding="utf-8-sig") as f:
            csv.writer(f).writerow(["DATA_HORA", "EMAIL_VENDEDOR", "NOME", "ESTADOS_LIBERADOS", "EVENTO"])

    arq_consultas = os.path.join(caminho, "consultas.csv")
    if not os.path.exists(arq_consultas):
        with open(arq_consultas, "w", newline="", encoding="utf-8-sig") as f:
            csv.writer(f).writerow(["DATA_HORA", "EMAIL_VENDEDOR", "TIPO_BUSCA", "TERMO_PESQUISADO", "STATUS_RESULTADO", "USDOT_ENCONTRADO"])

    arq_favs = os.path.join(caminho, "favoritos_crm.csv")
    if not os.path.exists(arq_favs):
        with open(arq_favs, "w", newline="", encoding="utf-8-sig") as f:
            csv.writer(f).writerow([
                "DATA_INCLUSAO", "EMAIL_VENDEDOR", "USDOT", "EMPRESA", "UF_CIDADE",
                "DECISOR", "CONTATO", "POWER_UNITS", "CONSUMO_EST", "STATUS_CRM",
                "MEDIDA_PNEU", "APLICACAO", "RESUMO_CONVERSA", "DATA_RETORNO"
            ])
    return caminho

def registrar_evento_vendedor(email, nome_vend, ufs_vend, tipo_evento, dados):
    agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    pasta = obter_ou_criar_pasta_vendedor(email)
    try:
        if tipo_evento == "LOGIN":
            with open(os.path.join(pasta, "logins.csv"), "a", newline="", encoding="utf-8-sig") as f:
                csv.writer(f).writerow([agora, email, nome_vend, ufs_vend, dados.get("evento", "LOGIN_SUCESSO")])
        elif tipo_evento == "CONSULTA":
            with open(os.path.join(pasta, "consultas.csv"), "a", newline="", encoding="utf-8-sig") as f:
                csv.writer(f).writerow([
                    agora, email, dados.get("tipo_busca", ""), dados.get("termo", ""),
                    dados.get("status", ""), dados.get("usdot", "")
                ])
        elif tipo_evento == "ATUALIZAR_FAVORITOS":
            conn = get_crm_conn()
            rows = conn.execute("SELECT * FROM favoritos_crm WHERE lower(email_vendedor) = ? ORDER BY id DESC", (email.lower(),)).fetchall()
            conn.close()
            df_f = pd.DataFrame([dict(r) for r in rows]) if rows else pd.DataFrame()
            if not df_f.empty:
                df_f.to_csv(os.path.join(pasta, "favoritos_crm.csv"), index=False, encoding="utf-8-sig")

        conn = get_crm_conn()
        conn.execute(
            "INSERT INTO historico_buscas (data_hora, email_vendedor, tipo_acao, criterio, resultado) VALUES (?, ?, ?, ?, ?)",
            (agora, email.lower(), tipo_evento, str(dados.get("termo", dados.get("evento", ""))), str(dados.get("status", dados.get("usdot", ""))))
        )
        conn.commit()
        conn.close()
    except Exception:
        pass

def calcular_telemetria_sessoes(df_logs, lista_usuarios):
    """Calcula automaticamente Total de Logins, Total de Buscas e Tempo Logado (em minutos) por usuário."""
    resumo = []
    for u in lista_usuarios:
        em = u["email"].lower().strip()
        nome = u["nome"]
        status = u["status"]
        ufs = u["estados_liberados"]

        if df_logs.empty:
            resumo.append({
                "Vendedor": nome, "E-mail": em, "Status": status, "Carteira": ufs,
                "Logins": 0, "Total Pesquisas": 0, "Favoritos Salvos": 0,
                "Tempo Logado (Min)": 0, "Tempo Formatado": "0 min",
                "Primeiro Acesso": "-", "Último Acesso": "-"
            })
            continue

        sub = df_logs[df_logs["email_vendedor"].str.lower() == em].copy()
        if sub.empty:
            resumo.append({
                "Vendedor": nome, "E-mail": em, "Status": status, "Carteira": ufs,
                "Logins": 0, "Total Pesquisas": 0, "Favoritos Salvos": 0,
                "Tempo Logado (Min)": 0, "Tempo Formatado": "0 min",
                "Primeiro Acesso": "-", "Último Acesso": "-"
            })
            continue

        sub["dt"] = pd.to_datetime(sub["data_hora"], errors="coerce")
        sub = sub.dropna(subset=["dt"]).sort_values("dt")

        qtd_logins = len(sub[(sub["tipo_acao"] == "LOGIN") & (sub["criterio"].str.contains("LOGIN", na=False))])
        if qtd_logins == 0 and len(sub) > 0:
            qtd_logins = 1
        qtd_buscas = len(sub[sub["tipo_acao"] == "CONSULTA"])
        qtd_favs = len(sub[sub["tipo_acao"] == "ATUALIZAR_FAVORITOS"])

        # Calcula tempo ativo somando intervalos entre ações consecutivas na mesma sessão (até 45 min entre cliques)
        tempos = sub["dt"].tolist()
        minutos_totais = 0.0
        if len(tempos) == 1:
            minutos_totais = 5.0
        else:
            sessoes_ativas = 1
            for i in range(1, len(tempos)):
                diff_min = (tempos[i] - tempos[i - 1]).total_seconds() / 60.0
                if diff_min <= 45.0:
                    minutos_totais += diff_min
                else:
                    minutos_totais += 5.0  # Tempo base da sessão anterior
                    sessoes_ativas += 1
            minutos_totais += 5.0  # Margem final de leitura da última ação

        min_int = max(int(round(minutos_totais)), qtd_logins * 3)
        horas = min_int // 60
        mins = min_int % 60
        tempo_fmt = f"{horas}h {mins}m" if horas > 0 else f"{mins} min"

        resumo.append({
            "Vendedor": nome,
            "E-mail": em,
            "Status": status,
            "Carteira": ufs,
            "Logins": qtd_logins,
            "Total Pesquisas": qtd_buscas,
            "Favoritos Salvos": qtd_favs,
            "Tempo Logado (Min)": min_int,
            "Tempo Formatado": tempo_fmt,
            "Primeiro Acesso": sub["dt"].min().strftime("%d/%m/%Y %H:%M"),
            "Último Acesso": sub["dt"].max().strftime("%d/%m/%Y %H:%M")
        })
    return pd.DataFrame(resumo)

# ==============================================================================
# TELA DE LOGIN
# ==============================================================================
if not st.session_state["logado"]:
    c1, c2, c3 = st.columns([1, 1.35, 1])
    with c2:
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("""
        <div class='hero-banner' style='display:block; text-align:center;'>
            <div class='hero-title'>🚛 SPEEDMAX & DIGITIRE</div>
            <div class='hero-subtitle'>Portal Corporativo de Inteligência e Prospecção de Frotas (FMCSA EUA)</div>
        </div>
        """, unsafe_allow_html=True)
        with st.form("form_login_exec"):
            st.markdown("#### 🔐 Autenticação Segura de Colaborador")
            em = st.text_input("E-mail Corporativo:", placeholder="Ex: lbarbanti2@gmail.com")
            pin = st.text_input("Senha PIN (6 dígitos):", type="password", placeholder="••••••")
            entrar = st.form_submit_button("🔓 Acessar Portal de Frotas")
            if entrar:
                agora_ts = time.time()
                if agora_ts < st.session_state["bloqueado_ate"]:
                    restante = int(st.session_state["bloqueado_ate"] - agora_ts)
                    st.error(f"🛡️ Muitas tentativas incorretas. Aguarde {restante} segundos.")
                else:
                    conn = get_crm_conn()
                    row = conn.execute(
                        "SELECT * FROM usuarios WHERE lower(email) = ? AND pin = ? AND upper(status) = 'APROVADO'",
                        (em.strip().lower(), pin.strip())
                    ).fetchone()
                    conn.close()
                    if row:
                        u = dict(row)
                        st.session_state["tentativas_pin"] = 0
                        st.session_state["logado"] = True
                        st.session_state["login_timestamp"] = time.time()
                        st.session_state["email"] = u["email"].lower()
                        st.session_state["nome"] = u["nome"]
                        raw_ufs = str(u.get("estados_liberados", "")).upper().strip()
                        perms = str(u.get("permissoes") or "BUSCAR,FAVORITAR,EXPORTAR").upper()
                        st.session_state["permissoes"] = [p.strip() for p in perms.split(",") if p.strip()]

                        # Exclusivo Admin Master vs Vendedor em Modo Trial (TODOS) vs Vendedor Restrito
                        if u["email"].lower() == "lbarbanti2@gmail.com" or "ADMIN" in st.session_state["permissoes"]:
                            st.session_state["is_admin"] = True
                            st.session_state["ufs"] = TODOS_ESTADOS_EUA
                        elif raw_ufs == "TODOS":
                            st.session_state["is_admin"] = False
                            st.session_state["ufs"] = TODOS_ESTADOS_EUA
                        else:
                            st.session_state["is_admin"] = False
                            st.session_state["ufs"] = [x.strip() for x in raw_ufs.split(",") if x.strip()][:6]

                        registrar_evento_vendedor(
                            st.session_state["email"], st.session_state["nome"],
                            raw_ufs, "LOGIN", {"evento": "LOGIN_APROVADO"}
                        )
                        st.rerun()
                    else:
                        st.session_state["tentativas_pin"] += 1
                        if st.session_state["tentativas_pin"] >= 5:
                            st.session_state["bloqueado_ate"] = time.time() + 60
                            st.error("🛡️ 5 tentativas incorretas! Acesso bloqueado por 60 segundos.")
                        else:
                            st.error("❌ E-mail, Senha PIN incorretos ou usuário bloqueado.")
    st.stop()

# ==============================================================================
# BARRA LATERAL COM CRONÔMETRO DE SESSÃO
# ==============================================================================
ufs_exib = "TODOS OS ESTADOS (MODO FULL)" if len(st.session_state["ufs"]) > 10 else ", ".join(st.session_state["ufs"])
perfil_txt = "👑 Administrador Master" if st.session_state["is_admin"] else "💼 Executivo de Vendas"
min_sessao_atual = int((time.time() - (st.session_state.get("login_timestamp") or time.time())) // 60)

st.sidebar.markdown("## 🚛 SPEEDMAX CRM")
st.sidebar.markdown(f"""
<div class='sidebar-box'>
    👤 <b>Usuário:</b><br>{st.session_state['nome']}<br><br>
    📧 <b>E-mail:</b><br>{st.session_state['email']}<br><br>
    🛡️ <b>Nível de Acesso:</b><br>{perfil_txt}<br><br>
    🗺️ <b>Carteira Liberada:</b><br>{ufs_exib}<br><br>
    ⏱️ <b>Sessão Atual:</b> {min_sessao_atual} min conectado
</div>
""", unsafe_allow_html=True)

if st.sidebar.button("🚪 Encerrar Sessão (Sair)"):
    registrar_evento_vendedor(st.session_state["email"], st.session_state["nome"], ufs_exib, "LOGIN", {"evento": f"LOGOUT ({min_sessao_atual}m)"})
    st.session_state["logado"] = False
    st.session_state["ficha_atual"] = None
    st.rerun()

st.markdown(f"""
<div class='hero-banner'>
    <div>
        <div class='hero-title'>🚛 PORTAL DE INTELIGÊNCIA DE FROTAS — SPEEDMAX / DIGITIRE</div>
        <div class='hero-subtitle'>Base Nacional Consolidada FMCSA (4,36 Milhões de Registros) • Suporte Multi-Usuário Simultâneo (WAL)</div>
    </div>
    <div class='hero-badge'>⚡ Motor SQLite Ultra-Fast</div>
</div>
""", unsafe_allow_html=True)

abas_titulos = [
    "🔎 1. CONSULTA RAIO-X COMPLETA",
    "🗺️ 2. FILTRO POR ESTADO E CIDADE (50 EM 50)",
    "⭐ 3. MEUS FAVORITOS & CRM DE PNEUS"
]
if st.session_state["is_admin"] or st.session_state["email"] == "lbarbanti2@gmail.com":
    abas_titulos.append("📊 4. MEU DASHBOARD DE GRÁFICOS & ACESSOS (ADMIN)")

tabs = st.tabs(abas_titulos)

# ==============================================================================
# ABA 1: CONSULTA RAIO-X COMPLETA + CALCULADORA DE PNEUS
# ==============================================================================
with tabs[0]:
    c_uf, c_tipo, c_val, c_btn = st.columns([1.2, 1.4, 2.4, 1])
    with c_uf:
        lista_uf_busca = ["🌎 TODA MINHA CARTEIRA"] + st.session_state["ufs"]
        uf_alvo = st.selectbox("Estado (UF):", lista_uf_busca)
    with c_tipo:
        tipo_busca = st.selectbox("Critério de Pesquisa:", ["Número USDOT", "Telefone / Celular", "Razão Social / DBA"])
    with c_val:
        termo_busca = st.text_input("Digite para pesquisar:", placeholder="Ex: 4488532 ou (215) 452-6239 ou Nome da Transportadora")
    with c_btn:
        st.write("")
        st.write("")
        disparar_busca = st.button("🔍 Consultar Ficha")

    if disparar_busca and termo_busca.strip():
        t_ini = datetime.now()
        conn = get_frotas_conn()
        uf_especifica = None if uf_alvo.startswith("🌎") else uf_alvo
        acesso_total = (len(st.session_state["ufs"]) > 10) or st.session_state["is_admin"]
        placeholders = ",".join(["?"] * len(st.session_state["ufs"]))

        if tipo_busca == "Número USDOT":
            num_dot = limpar_num(termo_busca)
            if uf_especifica:
                row = conn.execute("SELECT * FROM frotas WHERE DOT_CLEAN = ? AND UF_CLEAN = ? LIMIT 1", (num_dot, uf_especifica)).fetchone()
            elif acesso_total:
                row = conn.execute("SELECT * FROM frotas WHERE DOT_CLEAN = ? LIMIT 1", (num_dot,)).fetchone()
            else:
                row = conn.execute(f"SELECT * FROM frotas WHERE DOT_CLEAN = ? AND UF_CLEAN IN ({placeholders}) LIMIT 1", (num_dot, *st.session_state["ufs"])).fetchone()

        elif tipo_busca == "Telefone / Celular":
            num_tel = re.sub(r"[^\d]", "", termo_busca)
            if uf_especifica:
                row = conn.execute("SELECT * FROM frotas WHERE (PHONE_CLEAN = ? OR CELL_CLEAN = ?) AND UF_CLEAN = ? LIMIT 1", (num_tel, num_tel, uf_especifica)).fetchone()
            elif acesso_total:
                row = conn.execute("SELECT * FROM frotas WHERE (PHONE_CLEAN = ? OR CELL_CLEAN = ?) LIMIT 1", (num_tel, num_tel)).fetchone()
            else:
                row = conn.execute(f"SELECT * FROM frotas WHERE (PHONE_CLEAN = ? OR CELL_CLEAN = ?) AND UF_CLEAN IN ({placeholders}) LIMIT 1", (num_tel, num_tel, *st.session_state["ufs"])).fetchone()

        else:
            like_str = f"%{termo_busca.strip().upper()}%"
            if uf_especifica:
                row = conn.execute("SELECT * FROM frotas WHERE UF_CLEAN = ? AND (LEGAL_NAME LIKE ? OR DBA_NAME LIKE ?) ORDER BY POWER_UNITS_INT DESC LIMIT 1", (uf_especifica, like_str, like_str)).fetchone()
            elif acesso_total:
                row = conn.execute("SELECT * FROM frotas WHERE (LEGAL_NAME LIKE ? OR DBA_NAME LIKE ?) ORDER BY POWER_UNITS_INT DESC LIMIT 1", (like_str, like_str)).fetchone()
            else:
                row = conn.execute(f"SELECT * FROM frotas WHERE UF_CLEAN IN ({placeholders}) AND (LEGAL_NAME LIKE ? OR DBA_NAME LIKE ?) ORDER BY POWER_UNITS_INT DESC LIMIT 1", (*st.session_state["ufs"], like_str, like_str)).fetchone()

        conn.close()
        tempo_ms = (datetime.now() - t_ini).total_seconds() * 1000

        if row:
            d = dict(row)
            st.session_state["ficha_atual"] = d
            dot_achado = val_limpo(d.get("DOT_CLEAN") or d.get("DOT_NUMBER"))
            st.success(f"⚡ Ficha localizada em **{tempo_ms:.2f} ms**! Empresa: **{val_limpo(d.get('LEGAL_NAME'))}** (USDOT: **{dot_achado}** | UF: **{val_limpo(d.get('UF_CLEAN'))}**)")
            registrar_evento_vendedor(
                st.session_state["email"], st.session_state["nome"], ufs_exib,
                "CONSULTA", {"tipo_busca": tipo_busca, "termo": termo_busca, "status": f"ENCONTRADO ({val_limpo(d.get('UF_CLEAN'))})", "usdot": dot_achado}
            )
        else:
            st.session_state["ficha_atual"] = None
            st.error("❌ Nenhuma transportadora localizada nos seus estados autorizados com este critério.")
            registrar_evento_vendedor(
                st.session_state["email"], st.session_state["nome"], ufs_exib,
                "CONSULTA", {"tipo_busca": tipo_busca, "termo": termo_busca, "status": "NAO_ENCONTRADO", "usdot": ""}
            )

    if st.session_state.get("ficha_atual"):
        d = st.session_state["ficha_atual"]
        pwr = limpar_num(d.get("POWER_UNITS_INT") or d.get("POWER_UNITS"))
        milhas = limpar_num(d.get("MCS150_MILEAGE"))
        ano_milhas = val_limpo(d.get("MCS150_MILEAGE_YEAR"))

        own_tract = limpar_num(d.get("OWNTRACT"))
        trm_tract = limpar_num(d.get("TRMTRACT"))
        trp_tract = limpar_num(d.get("TRPTRACT"))
        tot_tract = own_tract + trm_tract + trp_tract

        own_truck = limpar_num(d.get("OWNTRUCK"))
        trm_truck = limpar_num(d.get("TRMTRUCK"))
        trp_truck = limpar_num(d.get("TRPTRUCK"))
        tot_truck = own_truck + trm_truck + trp_truck

        own_trail = limpar_num(d.get("OWNTRAIL"))
        trm_trail = limpar_num(d.get("TRMTRAIL"))
        trp_trail = limpar_num(d.get("TRPTRAIL"))
        tot_trail = own_trail + trm_trail + trp_trail

        posicoes_pneus = (tot_tract * 10) + (tot_truck * 6) + (tot_trail * 8)
        if posicoes_pneus == 0 and pwr > 0:
            posicoes_pneus = pwr * 10
        consumo_anual_pneus = max(round(posicoes_pneus * 0.65), round(pwr * 4))

        k1, k2, k3, k4 = st.columns(4)
        k1.markdown(f"<div class='kpi-card'><div class='kpi-title'>🚛 Power Units (Frota Motriz)</div><div class='kpi-value'>{pwr:,}</div><div class='kpi-sub'>Cavalos: {tot_tract} | Trucks Rígidos: {tot_truck}</div></div>", unsafe_allow_html=True)
        k2.markdown(f"<div class='kpi-card'><div class='kpi-title'>📦 Reboques / Carretas (Trailers)</div><div class='kpi-value'>{tot_trail:,}</div><div class='kpi-sub'>Próprios: {own_trail} | Arrendados: {trm_trail + trp_trail}</div></div>", unsafe_allow_html=True)
        k3.markdown(f"<div class='kpi-card'><div class='kpi-title'>🛞 Posições de Pneus Rodantes</div><div class='kpi-value'>{posicoes_pneus:,}</div><div class='kpi-sub'>Pneus calçados na operação</div></div>", unsafe_allow_html=True)
        k4.markdown(f"<div class='kpi-card'><div class='kpi-title'>💰 Potencial Reposição Anual</div><div class='kpi-value'>~{consumo_anual_pneus:,} pneus</div><div class='kpi-sub'>Estimativa B2B (~${consumo_anual_pneus * 320:,} USD/ano)</div></div>", unsafe_allow_html=True)

        col_esq, col_dir = st.columns(2)
        with col_esq:
            st_raw = val_limpo(d.get("STATUS_CODE"), "")
            badge_st = "<span class='badge-ativo'>🟢 ATIVO (ACTIVE - A)</span>" if st_raw.upper() == "A" else f"<span class='badge-inativo'>🔴 INATIVO ({st_raw or 'N/A'})</span>"
            mc_docket = f"{val_limpo(d.get('DOCKET1PREFIX'), '')} {val_limpo(d.get('DOCKET1'), '-')}"

            st.markdown("<div class='sec-header'>📋 1. IDENTIFICAÇÃO SOCIETÁRIA & CREDENCIAIS FMCSA</div>", unsafe_allow_html=True)
            st.markdown(f"""
            <div class='sec-body'>
                <table class='clean-table'>
                    <tr><th>Razão Social (Legal Name)</th><td>{val_limpo(d.get('LEGAL_NAME'))}</td></tr>
                    <tr><th>Nome Fantasia (DBA)</th><td>{val_limpo(d.get('DBA_NAME'))}</td></tr>
                    <tr><th>Número USDOT / Status</th><td><span class='badge-info'>USDOT {val_limpo(d.get('DOT_CLEAN') or d.get('DOT_NUMBER'))}</span> &nbsp; {badge_st}</td></tr>
                    <tr><th>MC / Docket & D&B</th><td>MC: {mc_docket} &nbsp;|&nbsp; D&B: {val_limpo(d.get('DUN_BRADSTREET_NO'))}</td></tr>
                    <tr><th>Data de Cadastro (ADD_DATE)</th><td>{fmt_data(d.get('ADD_DATE'))}</td></tr>
                    <tr><th>Última Atualização MCS-150</th><td>{fmt_data(d.get('MCS150_DATE'))}</td></tr>
                </table>
            </div>
            """, unsafe_allow_html=True)

            off1 = val_limpo(d.get("COMPANY_OFFICER_1"))
            off2 = val_limpo(d.get("COMPANY_OFFICER_2"), "")
            tel_prin = fmt_tel(d.get("PHONE") or d.get("TELEPHONE") or d.get("PHONE_CLEAN"))
            cel_prin = fmt_tel(d.get("CELL_PHONE") or d.get("CELL_CLEAN"))
            fax_prin = fmt_tel(d.get("FAX"))
            email_corp = val_limpo(d.get("EMAIL_ADDRESS")).lower()

            st.markdown("<div class='sec-header'>📞 2. DECISORES (OFFICERS) & CANAIS DE CONTATO</div>", unsafe_allow_html=True)
            st.markdown(f"""
            <div class='sec-body'>
                <table class='clean-table'>
                    <tr><th>1º Decisor (Officer 1)</th><td>👤 {off1}</td></tr>
                    <tr><th>2º Decisor (Officer 2)</th><td>👤 {off2 if off2 else '-'}</td></tr>
                    <tr><th>Telefone Principal</th><td>📞 {tel_prin}</td></tr>
                    <tr><th>Celular Direto / Fax</th><td>📱 Cel: {cel_prin} &nbsp;|&nbsp; 📠 Fax: {fax_prin}</td></tr>
                    <tr><th>E-mail Corporativo</th><td>✉️ {email_corp}</td></tr>
                </table>
            </div>
            """, unsafe_allow_html=True)

        with col_dir:
            end_fisico = f"{val_limpo(d.get('PHY_STREET'), '')}, {val_limpo(d.get('PHY_CITY'), '')}, {val_limpo(d.get('PHY_STATE'), '')} {val_limpo(d.get('PHY_ZIP'), '')}".strip(", ")
            end_postal = f"{val_limpo(d.get('CARRIER_MAILING_STREET') or d.get('MAILING_STREET'), '')}, {val_limpo(d.get('CARRIER_MAILING_CITY') or d.get('MAILING_CITY'), '')}, {val_limpo(d.get('CARRIER_MAILING_STATE') or d.get('MAILING_STATE'), '')} {val_limpo(d.get('CARRIER_MAILING_ZIP') or d.get('MAILING_ZIP'), '')}".strip(", ")

            mapa_cargas = {
                "CRGO_GENFREIGHT": "General Freight", "CRGO_HOUSEHOLD": "Household Goods", "CRGO_METALSHEET": "Metal Sheets/Coils",
                "CRGO_MOTOVEH": "Motor Vehicles", "CRGO_DRIVETOW": "Drive/Tow Away", "CRGO_LOGPOLE": "Logs/Poles/Lumber",
                "CRGO_BLDGMAT": "Building Materials", "CRGO_MACHLRG": "Machinery/Large Objects", "CRGO_PRODUCE": "Fresh Produce",
                "CRGO_LIQGAS": "Liquids/Gases", "CRGO_INTERMODAL": "Intermodal", "CRGO_COLDFOOD": "Refrigerated Food",
                "CRGO_BEVERAGES": "Beverages", "CRGO_PAPERPROD": "Paper Products", "CRGO_CONSTRUCT": "Construction",
                "CRGO_GARBAGE": "Garbage/Refuse", "CRGO_CHEM": "Chemicals", "CRGO_DRYBULK": "Dry Bulk"
            }
            cargas_ativas = [nome for col, nome in mapa_cargas.items() if str(d.get(col, "")).strip().upper() in ("X", "Y")]
            if val_limpo(d.get("CRGO_CARGOOTHR_DESC"), "") != "":
                cargas_ativas.append(f"Outros ({val_limpo(d.get('CRGO_CARGOOTHR_DESC'))})")

            st.markdown("<div class='sec-header'>📍 3. LOCALIZAÇÃO, OPERAÇÃO, CARGAS & COMPLIANCE</div>", unsafe_allow_html=True)
            st.markdown(f"""
            <div class='sec-body'>
                <table class='clean-table'>
                    <tr><th>Endereço Físico (Pátio)</th><td>📍 {end_fisico or '-'}</td></tr>
                    <tr><th>Endereço Correspondência</th><td>📬 {end_postal or '-'}</td></tr>
                    <tr><th>Classificação / Operação</th><td>{val_limpo(d.get('CLASSDEF') or d.get('CARRIER_OPERATION'))}</td></tr>
                    <tr><th>Cargas Transportadas</th><td>📦 {' | '.join(cargas_ativas) if cargas_ativas else 'General Freight / Não especificado'}</td></tr>
                    <tr><th>Segurança & Hazmat</th><td>Safety Rating: <b>{val_limpo(d.get('SAFETY_RATING'))}</b> &nbsp;|&nbsp; Hazmat: <b>{val_limpo(d.get('HM_Ind'), 'N')}</b></td></tr>
                </table>
            </div>
            """, unsafe_allow_html=True)

            drv_tot = limpar_num(d.get("TOTAL_DRIVERS"))
            drv_cdl = limpar_num(d.get("TOTAL_CDL"))
            curta_dist = limpar_num(d.get("INTERSTATE_WITHIN_100_MILES")) + limpar_num(d.get("INTRASTATE_WITHIN_100_MILES"))
            longa_dist = limpar_num(d.get("INTERSTATE_BEYOND_100_MILES")) + limpar_num(d.get("INTRASTATE_BEYOND_100_MILES"))
            media_cam = round(milhas / max(pwr, 1)) if milhas > 0 else 0

            st.markdown("<div class='sec-header'>🚜 4. COMPOSIÇÃO DA FROTA, MOTORISTAS & MILHAGEM</div>", unsafe_allow_html=True)
            st.markdown(f"""
            <div class='sec-body'>
                <table class='clean-table'>
                    <tr><th>Cavalos Mecânicos (Tractors)</th><td>Total: <b>{tot_tract}</b> &nbsp;(Próprios: {own_tract} | Arrendados: {trm_tract + trp_tract})</td></tr>
                    <tr><th>Caminhões Rígidos (Straight)</th><td>Total: <b>{tot_truck}</b> &nbsp;(Próprios: {own_truck} | Arrendados: {trm_truck + trp_truck})</td></tr>
                    <tr><th>Reboques / Carretas (Trailers)</th><td>Total: <b>{tot_trail}</b> &nbsp;(Próprios: {own_trail} | Arrendados: {trm_trail + trp_trail})</td></tr>
                    <tr><th>Motoristas & Raio de Rota</th><td>Total: <b>{drv_tot}</b> (CDL: {drv_cdl}) &nbsp;|&nbsp; Curta (&lt;100 mi): <b>{curta_dist}</b> &nbsp;|&nbsp; Longa OTR (&gt;100 mi): <b>{longa_dist}</b></td></tr>
                    <tr><th>Milhagem Oficial (MCS-150)</th><td>🛣️ <b>{milhas:,} milhas/ano</b> (Base: {ano_milhas}) &nbsp;|&nbsp; Média: <b>{media_cam:,} mi/veículo</b></td></tr>
                </table>
            </div>
            """, unsafe_allow_html=True)

        if "FAVORITAR" in st.session_state["permissoes"] or st.session_state["is_admin"]:
            st.markdown("<div class='sec-header'>⭐ 5. SALVAR TRANSPORTADORA NA MINHA CARTEIRA CRM DE PNEUS</div>", unsafe_allow_html=True)
            with st.form("form_crm_completo"):
                f1, f2, f3 = st.columns(3)
                med_pneu = f1.selectbox("Medida Principal de Pneu Utilizada:", MEDIDAS_PNEUS)
                status_neg = f2.selectbox("Status Comercial no Funil:", STATUS_CRM)
                dt_retorno = f3.date_input("Data de Retorno (Follow-up):", datetime.now() + timedelta(days=3))
                obs_vendedor = st.text_area("Anotações da Ligação / Cotação / Preço Oferecido:", placeholder="Ex: Falei com o gestor de frota, compram 295/75R22.5...")
                if st.form_submit_button("💾 Salvar Cliente nos Meus Favoritos & Gravar na Minha Pasta do Drive"):
                    conn = get_crm_conn()
                    agora_fmt = datetime.now().strftime("%Y-%m-%d %H:%M")
                    dot_str = val_limpo(d.get("DOT_CLEAN") or d.get("DOT_NUMBER"))
                    conn.execute("""
                        INSERT INTO favoritos_crm (
                            data_inclusao, email_vendedor, usdot, empresa, uf_cidade, decisor,
                            contato, power_units, consumo_est, status_crm, medida_pneu,
                            aplicacao, resumo_conversa, data_retorno
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        agora_fmt, st.session_state["email"], dot_str,
                        val_limpo(d.get("LEGAL_NAME")), f"{val_limpo(d.get('PHY_STATE'))} - {val_limpo(d.get('PHY_CITY'))}",
                        off1, f"{tel_prin} | {email_corp}", pwr, f"~{consumo_anual_pneus} pneus/ano",
                        status_neg, med_pneu, "Steer / Drive / Trailer", obs_vendedor, str(dt_retorno)
                    ))
                    conn.commit()
                    conn.close()
                    registrar_evento_vendedor(
                        st.session_state["email"], st.session_state["nome"], ufs_exib,
                        "ATUALIZAR_FAVORITOS", {"termo": val_limpo(d.get("LEGAL_NAME")), "usdot": dot_str}
                    )
                    st.success("✅ Transportadora salva com sucesso no seu CRM!")

# ==============================================================================
# ABA 2: BUSCA REGIONAL EXATA POR CIDADE COM PAGINAÇÃO DE 50 EM 50
# ==============================================================================
with tabs[1]:
    st.markdown("<div class='sec-header'>🗺️ FILTRO REGIONAL EXATO POR ESTADO E CIDADE (PAGINAÇÃO DE 50 EM 50)</div>", unsafe_allow_html=True)
    r1, r2, r3, r4 = st.columns([1.1, 2.0, 1.3, 1.0])
    with r1:
        uf_escolhida = st.selectbox("1. Estado (UF):", st.session_state["ufs"], key="sel_uf_aba2")
    with r2:
        cid_digitada = st.text_input("2. Nome Exato da Cidade (em Inglês):", placeholder="Ex: PHILADELPHIA")
    with r3:
        filtro_status = st.selectbox("3. Filtro de Status:", ["Todas da Cidade (ex: 14.000+)", "Apenas Ativas (STATUS = A)"])
    with r4:
        st.write("")
        st.write("")
        btn_pesquisar_cid = st.button("🔎 Pesquisar Cidade")

    if btn_pesquisar_cid:
        if not cid_digitada.strip():
            st.warning("⚠️ Digite o nome exato da cidade em inglês (ex: PHILADELPHIA) antes de pesquisar.")
            st.session_state["buscar_regional_ativo"] = False
        else:
            st.session_state["uf_reg"] = uf_escolhida
            st.session_state["cid_reg"] = cid_digitada.strip().upper()
            st.session_state["apenas_ativas_reg"] = (filtro_status.startswith("Apenas"))
            st.session_state["pagina_atual"] = 0
            st.session_state["buscar_regional_ativo"] = True

            registrar_evento_vendedor(
                st.session_state["email"], st.session_state["nome"], ufs_exib,
                "CONSULTA", {
                    "tipo_busca": "CIDADE_EXATA",
                    "termo": f"{st.session_state['cid_reg']} - {uf_escolhida}",
                    "status": "PESQUISADO", "usdot": ""
                }
            )

    if st.session_state.get("buscar_regional_ativo") and st.session_state.get("cid_reg"):
        uf_q = st.session_state["uf_reg"]
        cid_q = st.session_state["cid_reg"]
        cid_sem_espaco = cid_q.replace(" ", "")
        so_ativas = st.session_state["apenas_ativas_reg"]

        conn = get_frotas_conn()
        cond_status = " AND STATUS_CODE = 'A'" if so_ativas else ""

        sql_count = f"""
            SELECT COUNT(*) FROM frotas
            WHERE UF_CLEAN = ? AND (UPPER(TRIM(PHY_CITY)) = ? OR CITY_CLEAN = ?){cond_status}
        """
        total_empresas = conn.execute(sql_count, (uf_q, cid_q, cid_sem_espaco)).fetchone()[0]

        if total_empresas > 0:
            total_paginas = math.ceil(total_empresas / 50)
            pag_atual = min(st.session_state["pagina_atual"], total_paginas - 1)
            st.session_state["pagina_atual"] = max(0, pag_atual)
            offset = st.session_state["pagina_atual"] * 50

            sql_page = f"""
                SELECT * FROM frotas
                WHERE UF_CLEAN = ? AND (UPPER(TRIM(PHY_CITY)) = ? OR CITY_CLEAN = ?){cond_status}
                ORDER BY POWER_UNITS_INT DESC
                LIMIT 50 OFFSET ?
            """
            rows_cid = conn.execute(sql_page, (uf_q, cid_q, cid_sem_espaco, offset)).fetchall()
            conn.close()

            ini_n = offset + 1
            fim_n = min(offset + 50, total_empresas)
            st.success(f"✅ Localizadas **{total_empresas:,}** empresas exatamente em **{cid_q}, {uf_q}**! Exibindo **{ini_n:,} a {fim_n:,}** (Página **{st.session_state['pagina_atual'] + 1} de {total_paginas}**).")

            nav1, nav2, nav3, nav4 = st.columns([1.2, 1.6, 1.4, 1.2])
            with nav1:
                if st.button("⬅️ 50 Anteriores", disabled=(st.session_state["pagina_atual"] <= 0)):
                    st.session_state["pagina_atual"] -= 1
                    st.rerun()
            with nav2:
                st.markdown(f"<div style='text-align:center; padding-top:8px; font-weight:800; color:#0F172A;'>Página {st.session_state['pagina_atual'] + 1} de {total_paginas} ({total_empresas:,} empresas)</div>", unsafe_allow_html=True)
            with nav3:
                ir_para = st.number_input("Ir para página:", min_value=1, max_value=total_paginas, value=st.session_state["pagina_atual"] + 1, label_visibility="collapsed")
                if ir_para - 1 != st.session_state["pagina_atual"]:
                    st.session_state["pagina_atual"] = ir_para - 1
                    st.rerun()
            with nav4:
                if st.button("Próximas 50 ➡️", disabled=((st.session_state["pagina_atual"] + 1) >= total_paginas)):
                    st.session_state["pagina_atual"] += 1
                    st.rerun()

            lista_tabela = []
            for idx_r, r_obj in enumerate(rows_cid, start=ini_n):
                dr = dict(r_obj)
                lista_tabela.append({
                    "#": idx_r,
                    "USDOT": val_limpo(dr.get("DOT_CLEAN") or dr.get("DOT_NUMBER")),
                    "RAZÃO SOCIAL (LEGAL NAME)": val_limpo(dr.get("LEGAL_NAME")),
                    "DBA (FANTASIA)": val_limpo(dr.get("DBA_NAME")),
                    "STATUS": val_limpo(dr.get("STATUS_CODE")),
                    "POWER UNITS (FROTA)": limpar_num(dr.get("POWER_UNITS_INT") or dr.get("POWER_UNITS")),
                    "REBOQUES (TRAILERS)": limpar_num(dr.get("OWNTRAIL")) + limpar_num(dr.get("TRMTRAIL")),
                    "DECISOR (OFFICER 1)": val_limpo(dr.get("COMPANY_OFFICER_1")),
                    "TELEFONE": fmt_tel(dr.get("PHONE") or dr.get("TELEPHONE") or dr.get("PHONE_CLEAN")),
                    "CELULAR": fmt_tel(dr.get("CELL_PHONE") or dr.get("CELL_CLEAN")),
                    "CIDADE EXATA": val_limpo(dr.get("PHY_CITY")),
                    "UF": val_limpo(dr.get("PHY_STATE"))
                })

            df_cid = pd.DataFrame(lista_tabela)
            st.dataframe(df_cid, use_container_width=True, hide_index=True, height=620)
        else:
            conn.close()
            st.error(f"⚠️ Nenhuma empresa localizada exatamente com o nome de cidade **'{cid_q}'** no estado **{uf_q}**.")

# ==============================================================================
# ABA 3: FAVORITOS & CRM DE PNEUS DO VENDEDOR
# ==============================================================================
with tabs[2]:
    st.markdown("<div class='sec-header'>⭐ MINHA CARTEIRA DE CLIENTES FAVORITOS & COTAÇÕES DE PNEUS</div>", unsafe_allow_html=True)
    conn = get_crm_conn()
    if st.session_state["is_admin"]:
        rows_fav = conn.execute("SELECT * FROM favoritos_crm ORDER BY id DESC").fetchall()
    else:
        rows_fav = conn.execute("SELECT * FROM favoritos_crm WHERE lower(email_vendedor) = ? ORDER BY id DESC", (st.session_state["email"],)).fetchall()
    conn.close()

    if rows_fav:
        df_fav = pd.DataFrame([dict(r) for r in rows_fav])
        st.dataframe(df_fav, use_container_width=True, hide_index=True)

        col_dl, col_del = st.columns([2, 2])
        with col_dl:
            if "EXPORTAR" in st.session_state["permissoes"] or st.session_state["is_admin"]:
                csv_bytes = df_fav.to_csv(index=False).encode("utf-8-sig")
                st.download_button(
                    "📥 Baixar Planilha Completa do Meu CRM (CSV/Excel)",
                    data=csv_bytes,
                    file_name=f"CRM_SpeedMax_{st.session_state['email']}.csv",
                    mime="text/csv"
                )
        with col_del:
            id_excluir = st.selectbox("Selecione o ID de um registro para remover:", [r["id"] for r in rows_fav])
            if st.button("🗑️ Remover Registro Selecionado"):
                conn = get_crm_conn()
                conn.execute("DELETE FROM favoritos_crm WHERE id = ?", (id_excluir,))
                conn.commit()
                conn.close()
                registrar_evento_vendedor(st.session_state["email"], st.session_state["nome"], ufs_exib, "ATUALIZAR_FAVORITOS", {"termo": f"ID {id_excluir} removido", "usdot": ""})
                st.rerun()
    else:
        st.info("💡 Você ainda não adicionou clientes ao seu CRM. Pesquise uma transportadora na Aba 1 e salve no bloco 5.")

# ==============================================================================
# ABA 4 (EXCLUSIVA ADMIN): DASHBOARD DE GRÁFICOS, TEMPO LOGADO E GESTÃO DE ACESSOS
# ==============================================================================
if (st.session_state["is_admin"] or st.session_state["email"] == "lbarbanti2@gmail.com") and len(tabs) > 3:
    with tabs[3]:
        conn = get_crm_conn()
        lista_usr = [dict(r) for r in conn.execute("SELECT email, nome, pin, status, estados_liberados, permissoes, pasta_vendedor FROM usuarios ORDER BY nome").fetchall()]
        rows_logs = [dict(r) for r in conn.execute("SELECT * FROM historico_buscas ORDER BY id ASC").fetchall()]
        conn.close()

        df_logs_all = pd.DataFrame(rows_logs) if rows_logs else pd.DataFrame(columns=["id", "data_hora", "email_vendedor", "tipo_acao", "criterio", "resultado"])
        df_telemetria = calcular_telemetria_sessoes(df_logs_all, lista_usr)

        # KPIs Gerais de Produtividade e Uso da Equipe
        tot_usuarios = len(lista_usr)
        tot_logins_eq = int(df_telemetria["Logins"].sum()) if not df_telemetria.empty else 0
        tot_buscas_eq = int(df_telemetria["Total Pesquisas"].sum()) if not df_telemetria.empty else 0
        tot_min_eq = int(df_telemetria["Tempo Logado (Min)"].sum()) if not df_telemetria.empty else 0

        m1, m2, m3, m4 = st.columns(4)
        m1.markdown(f"<div class='kpi-card'><div class='kpi-title'>👥 Usuários Cadastrados</div><div class='kpi-value'>{tot_usuarios}</div><div class='kpi-sub'>Suporta 15+ simultâneos</div></div>", unsafe_allow_html=True)
        m2.markdown(f"<div class='kpi-card'><div class='kpi-title'>🔑 Total de Logins</div><div class='kpi-value'>{tot_logins_eq:,}</div><div class='kpi-sub'>Acessos autenticados</div></div>", unsafe_allow_html=True)
        m3.markdown(f"<div class='kpi-card'><div class='kpi-title'>🔎 Total de Pesquisas</div><div class='kpi-value'>{tot_buscas_eq:,}</div><div class='kpi-sub'>Consultas realizadas pela equipe</div></div>", unsafe_allow_html=True)
        m4.markdown(f"<div class='kpi-card'><div class='kpi-title'>⏱️ Tempo Total Conectado</div><div class='kpi-value'>{tot_min_eq // 60}h {tot_min_eq % 60}m</div><div class='kpi-sub'>{tot_min_eq:,} minutos ativos em sessão</div></div>", unsafe_allow_html=True)

        # BLOCO 1: GRÁFICOS EXECUTIVOS DE MOVIMENTAÇÃO, DATAS E TEMPO LOGADO
        st.markdown("<div class='sec-header'>📊 1. DASHBOARD EXECUTIVO: GRÁFICOS DE PESQUISAS, DATAS E TEMPO LOGADO</div>", unsafe_allow_html=True)

        f_col1, f_col2 = st.columns([1.5, 2.5])
        with f_col1:
            opcoes_periodo = ["Todo o Período", "Últimos 7 Dias", "Últimos 30 Dias", "Apenas Hoje"]
            periodo_sel = st.selectbox("📅 Filtrar Gráficos por Período:", opcoes_periodo)
        with f_col2:
            vendedores_sel = st.multiselect(
                "👤 Filtrar Vendedores Específicos:",
                options=[u["email"] for u in lista_usr],
                default=[u["email"] for u in lista_usr]
            )

        df_logs_filt = df_logs_all.copy()
        if not df_logs_filt.empty:
            df_logs_filt["dt"] = pd.to_datetime(df_logs_filt["data_hora"], errors="coerce")
            df_logs_filt = df_logs_filt.dropna(subset=["dt"])
            agora_dt = datetime.now()
            if periodo_sel == "Apenas Hoje":
                df_logs_filt = df_logs_filt[df_logs_filt["dt"].dt.date == agora_dt.date()]
            elif periodo_sel == "Últimos 7 Dias":
                df_logs_filt = df_logs_filt[df_logs_filt["dt"] >= (agora_dt - timedelta(days=7))]
            elif periodo_sel == "Últimos 30 Dias":
                df_logs_filt = df_logs_filt[df_logs_filt["dt"] >= (agora_dt - timedelta(days=30))]
            if vendedores_sel:
                df_logs_filt = df_logs_filt[df_logs_filt["email_vendedor"].str.lower().isin([v.lower() for v in vendedores_sel])]

        df_tel_filt = calcular_telemetria_sessoes(df_logs_filt, [u for u in lista_usr if u["email"] in vendedores_sel])

        g1, g2, g3 = st.columns(3)
        with g1:
            st.markdown("<div class='sec-body'><b>🔎 Quantidade de Pesquisas por Vendedor</b>", unsafe_allow_html=True)
            if not df_tel_filt.empty:
                chart_buscas = df_tel_filt.set_index("Vendedor")[["Total Pesquisas"]]
                st.bar_chart(chart_buscas, color=COR_PRI)
            else:
                st.info("Sem dados no período.")
            st.markdown("</div>", unsafe_allow_html=True)

        with g2:
            st.markdown("<div class='sec-body'><b>⏱️ Tempo Logado por Vendedor (Minutos)</b>", unsafe_allow_html=True)
            if not df_tel_filt.empty:
                chart_tempo = df_tel_filt.set_index("Vendedor")[["Tempo Logado (Min)"]]
                st.bar_chart(chart_tempo, color="#6B21A8")
            else:
                st.info("Sem dados no período.")
            st.markdown("</div>", unsafe_allow_html=True)

        with g3:
            st.markdown("<div class='sec-body'><b>📅 Evolução Diária (Logins vs. Pesquisas por Data)</b>", unsafe_allow_html=True)
            if not df_logs_filt.empty:
                df_logs_filt["Data"] = df_logs_filt["dt"].dt.strftime("%Y-%m-%d")
                diario_buscas = df_logs_filt[df_logs_filt["tipo_acao"] == "CONSULTA"].groupby("Data").size().rename("Pesquisas")
                diario_logins = df_logs_filt[df_logs_filt["tipo_acao"] == "LOGIN"].groupby("Data").size().rename("Logins")
                df_diario = pd.concat([diario_buscas, diario_logins], axis=1).fillna(0)
                st.line_chart(df_diario)
            else:
                st.info("Sem movimentação por data ainda.")
            st.markdown("</div>", unsafe_allow_html=True)

        # TABELA RESUMO DE TELEMETRIA (QUANDO LOGARAM, TEMPO LOGADO E QUANTAS PESQUISAS FIZERAM)
        st.markdown("<div class='sec-header'>📋 2. RELATÓRIO DE TELEMETRIA POR VENDEDOR (DATAS DE LOGIN, TEMPO CONECTADO E VOLUME DE PESQUISAS)</div>", unsafe_allow_html=True)
        st.dataframe(
            df_tel_filt[[
                "Vendedor", "E-mail", "Status", "Carteira",
                "Logins", "Total Pesquisas", "Favoritos Salvos",
                "Tempo Formatado", "Primeiro Acesso", "Último Acesso"
            ]],
            use_container_width=True,
            hide_index=True
        )

        # BLOCO 3: CHAVE GERAL DE MODO TRIAL (LIBERAR PAÍS INTEIRO PARA TODOS OS VENDEDORES)
        st.markdown("<div class='sec-header'>🎁 3. CONTROLE RÁPIDO DE MODO TRIAL (LIBERAR TODOS OS ESTADOS PARA TESTE DA EQUIPE)</div>", unsafe_allow_html=True)
        t_col1, t_col2 = st.columns(2)
        with t_col1:
            if st.button("🌎 ATIVAR MODO TRIAL: Liberar Todos os Estados (EUA) para Todos os Vendedores"):
                conn = get_crm_conn()
                conn.execute("UPDATE usuarios SET estados_liberados = 'TODOS' WHERE upper(status) = 'APROVADO'")
                conn.commit()
                conn.close()
                st.success("✅ Modo Trial Ativado! Todos os vendedores aprovados agora podem testar o país inteiro!")
                st.rerun()
        with t_col2:
            if st.button("🔒 ENCERRAR TRIAL PADRÃO: Voltar Vendedores Comuns para Carteira Padrão (NJ, NY, PA)"):
                conn = get_crm_conn()
                conn.execute("UPDATE usuarios SET estados_liberados = 'NJ, NY, PA' WHERE lower(email) != 'lbarbanti2@gmail.com' AND permissoes NOT LIKE '%ADMIN%'")
                conn.commit()
                conn.close()
                st.success("🔒 Vendedores comuns retornaram para a carteira restrita (NJ, NY, PA). Você pode ajustar cada um individualmente abaixo.")
                st.rerun()

        # BLOCO 4: GERENCIAMENTO DE CREDENCIAIS, SENHA PIN, BLOQUEIO E CADASTRO DE USUÁRIOS
        st.markdown("<div class='sec-header'>🔐 4. GERENCIAR ACESSOS, MUDAR CREDENCIAIS (SENHA PIN) OU CADASTRAR VENDEDOR</div>", unsafe_allow_html=True)
        with st.form("form_admin_usuarios"):
            opcoes_edicao = ["➕ Cadastrar Novo Vendedor"] + [f"{u['email']} ({u['nome']})" for u in lista_usr]
            usuario_selecionado = st.selectbox("Selecione um usuário existente para carregar/editar ou escolha 'Cadastrar Novo':", opcoes_edicao)

            a1, a2, a3 = st.columns(3)
            u_email = a1.text_input("E-mail do Usuário (Login):", placeholder="vendedor@gmail.com")
            u_nome = a2.text_input("Nome Completo do Vendedor:", placeholder="Ex: Beatriz Silva")
            u_pin = a3.text_input("Nova Senha PIN de 6 Dígitos:", value="123456")

            a4, a5, a6 = st.columns([1.1, 1.4, 2.3])
            u_status = a4.selectbox("Status de Acesso:", ["APROVADO", "BLOQUEADO", "PENDENTE"])
            u_modo_trial = a5.selectbox("Modo de Território:", ["🎁 Modo Trial (TODOS OS ESTADOS)", "🔒 Carteira Restrita (Até 6 UFs)"])
            u_ufs = a6.multiselect(
                "Estados da Carteira Restrita (se não estiver em Modo Trial):",
                TODOS_ESTADOS_EUA,
                default=["NJ", "NY", "PA"]
            )

            u_perms = st.multiselect(
                "Permissões do Usuário no Sistema:",
                ["BUSCAR", "FAVORITAR", "EXPORTAR", "ADMIN"],
                default=["BUSCAR", "FAVORITAR", "EXPORTAR"]
            )

            if st.form_submit_button("💾 Salvar / Atualizar Credenciais e Permissões do Usuário"):
                email_alvo = u_email.strip().lower()
                if not email_alvo and not usuario_selecionado.startswith("➕"):
                    email_alvo = usuario_selecionado.split(" (")[0].strip().lower()

                if not email_alvo or not u_nome.strip():
                    st.error("⚠️ Preencha o E-mail e o Nome do vendedor.")
                else:
                    eh_adm = ("ADMIN" in u_perms) or (email_alvo == "lbarbanti2@gmail.com")
                    liberar_tudo = eh_adm or u_modo_trial.startswith("🎁")
                    if not liberar_tudo and len(u_ufs) > 6:
                        st.error("⚠️ No modo de Carteira Restrita, selecione no máximo 6 estados.")
                    else:
                        ufs_gravar = "TODOS" if liberar_tudo else ", ".join(u_ufs[:6])
                        perms_gravar = ", ".join(u_perms) if u_perms else "BUSCAR"
                        pasta_criada = obter_ou_criar_pasta_vendedor(email_alvo)

                        conn = get_crm_conn()
                        conn.execute("""
                            INSERT OR REPLACE INTO usuarios (email, nome, pin, status, estados_liberados, permissoes, pasta_vendedor)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                        """, (email_alvo, u_nome.strip(), u_pin.strip()[:6], u_status, ufs_gravar, perms_gravar, pasta_criada))
                        conn.commit()
                        conn.close()
                        st.success(f"✅ Credenciais de **{u_nome}** (`{email_alvo}`) salvas! PIN: `{u_pin[:6]}` | Status: `{u_status}` | Estados: `{ufs_gravar}`.")
                        st.rerun()
