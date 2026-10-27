import streamlit as st
import pandas as pd
import os
import re
import csv
import math
import time
from datetime import datetime, timedelta
import sqlalchemy
from sqlalchemy import text

st.set_page_config(
    page_title="SpeedMax & Digitire | Portal Corporativo de Frotas",
    page_icon="🚛",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==============================================================================
# CONEXÕES POSTGRESQL (CLOUD SQL & SQLALCHEMY)
# ==============================================================================
DB_USER = os.environ.get("DB_USER", "postgres")
DB_PASS = os.environ.get("DB_PASS", "")
DB_NAME = os.environ.get("db_CLOUD_SQL_DATABASE_NAME", "postgres")
INSTANCE_CONNECTION_NAME = os.environ.get("db_CLOUD_SQL_DATABASE_CONNECTION_NAME", "")

@st.cache_resource
def get_engine():
    if os.environ.get("K_SERVICE"): # Ambiente Cloud Run
        socket_path = f"/cloudsql/{INSTANCE_CONNECTION_NAME}"
        database_url = f"postgresql+pg8000://{DB_USER}:{DB_PASS}@/{DB_NAME}?unix_sock={socket_path}/.s.PGSQL.5432"
    else:
        # Local/Fallback
        database_url = f"postgresql+pg8000://{DB_USER}:{DB_PASS}@localhost:5432/{DB_NAME}"
    return sqlalchemy.create_engine(database_url)

engine = get_engine()

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
# FUNÇÕES UTILITÁRIAS
# ==============================================================================
def limpar_num(v):
    if pd.isna(v) or v is None: return 0
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
    if pd.isna(v) or v is None: return padrao
    s = str(v).strip()
    if s.lower() in ("nan", "none", "null", ""): return padrao
    if s.endswith(".0"): s = s[:-2]
    return s

def registrar_evento_vendedor(email, nome_vend, ufs_vend, tipo_evento, dados):
    agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with engine.connect() as conn:
            conn.execute(text("""
                INSERT INTO historico_buscas (data_hora, email_vendedor, tipo_acao, criterio, resultado)
                VALUES (:d, :e, :t, :c, :r)
            """), {
                "d": agora, "e": email.lower(), "t": tipo_evento,
                "c": str(dados.get("termo", dados.get("evento", ""))),
                "r": str(dados.get("status", dados.get("usdot", "")))
            })
            conn.commit()
    except Exception as e:
        st.error(f"Erro ao registrar evento: {e}")

@st.cache_data(ttl=1800)
def listar_todas_ufs_banco():
    try:
        with engine.connect() as conn:
            rows = conn.execute(text("SELECT DISTINCT UF_CLEAN FROM frotas WHERE UF_CLEAN IS NOT NULL AND UF_CLEAN != '' ORDER BY UF_CLEAN")).fetchall()
            todas = [r[0] for r in rows if r[0]]
            prio = [u for u in ESTADOS_PRIORITARIOS if u in todas]
            resto = [u for u in todas if u not in prio]
            return prio + resto
    except Exception:
        return ESTADOS_PRIORITARIOS

# ==============================================================================
# INICIALIZAÇÃO E CSS
# ==============================================================================
if "logado" not in st.session_state:
    st.session_state.update({
        "logado": False, "email": "", "nome": "", "is_admin": False,
        "ufs": [], "permissoes": [], "ficha_atual": None,
        "pagina_atual": 0, "uf_reg": "", "cid_reg": "", "apenas_ativas_reg": False,
        "buscar_regional_ativo": False, "tentativas_pin": 0, "bloqueado_ate": 0.0,
        "login_timestamp": None
    })

st.markdown("""
<style>
    .stApp { background-color: #F4F5F9; }
    [data-testid="stSidebar"] { background: linear-gradient(180deg, #4A148C 0%, #6B21A8 100%); }
    [data-testid="stSidebar"] * { color: #FFFFFF !important; }
    div.stButton > button:first-child { background: linear-gradient(135deg, #4A148C 0%, #6B21A8 100%); color: white; border-radius: 8px; font-weight: bold; border: none; }
    .hero-banner { background: linear-gradient(135deg, #4A148C 0%, #6B21A8 100%); color: white; padding: 20px; border-radius: 14px; margin-bottom: 20px; }
    .kpi-card { background: white; border-radius: 12px; padding: 16px; border-top: 5px solid #4A148C; text-align: center; box-shadow: 0 4px 12px rgba(0,0,0,0.05); }
    .kpi-value { font-size: 26px; font-weight: 800; color: #4A148C; margin: 0; }
    .kpi-title { font-size: 12px; font-weight: 800; color: #475569; text-transform: uppercase; }
    .sec-header { background: linear-gradient(90deg, #4A148C 0%, #6B21A8 100%); color: white; padding: 10px 15px; border-radius: 8px 8px 0 0; font-weight: bold; margin-top: 15px; }
    .sec-body { background: white; padding: 15px; border: 1px solid #CBD5E1; border-top: none; border-radius: 0 0 8px 8px; }
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# LOGIN
# ==============================================================================
if not st.session_state["logado"]:
    st.markdown("<div class='hero-banner'><h2 style='margin:0;'>🚛 SPEEDMAX & DIGITIRE</h2><p style='margin:0;'>Portal Corporativo de Inteligência de Frotas (PostgreSQL)</p></div>", unsafe_allow_html=True)
    with st.form("form_login_exec"):
        st.markdown("#### 🔐 Autenticação Segura")
        em = st.text_input("E-mail Corporativo:")
        pin = st.text_input("Senha PIN (6 dígitos):", type="password")
        if st.form_submit_button("🔓 Acessar Portal"):
            agora_ts = time.time()
            if agora_ts < st.session_state["bloqueado_ate"]:
                st.error(f"Muitas tentativas. Aguarde {int(st.session_state['bloqueado_ate'] - agora_ts)} segundos.")
            else:
                with engine.connect() as conn:
                    res = conn.execute(text("SELECT * FROM usuarios WHERE lower(email) = :e AND pin = :p AND upper(status) = 'APROVADO'"), {"e": em.strip().lower(), "p": pin.strip()}).fetchone()
                if res:
                    u = dict(res._mapping)
                    st.session_state["tentativas_pin"] = 0
                    st.session_state["logado"] = True
                    st.session_state["login_timestamp"] = time.time()
                    st.session_state["email"] = u["email"].lower()
                    st.session_state["nome"] = u["nome"]
                    raw_ufs = str(u.get("estados_liberados", "")).upper().strip()
                    perms = str(u.get("permissoes") or "BUSCAR,FAVORITAR,EXPORTAR").upper()
                    st.session_state["permissoes"] = [p.strip() for p in perms.split(",") if p.strip()]

                    if u["email"].lower() == "lbarbanti2@gmail.com" or "ADMIN" in st.session_state["permissoes"] or raw_ufs == "TODOS":
                        st.session_state["is_admin"] = True
                        st.session_state["ufs"] = TODOS_ESTADOS_EUA
                    else:
                        st.session_state["is_admin"] = False
                        st.session_state["ufs"] = [x.strip() for x in raw_ufs.split(",") if x.strip()][:6]

                    registrar_evento_vendedor(st.session_state["email"], st.session_state["nome"], raw_ufs, "LOGIN", {"evento": "LOGIN_APROVADO"})
                    st.rerun()
                else:
                    st.session_state["tentativas_pin"] += 1
                    if st.session_state["tentativas_pin"] >= 5:
                        st.session_state["bloqueado_ate"] = time.time() + 60
                        st.error("Acesso bloqueado por 60 segundos.")
                    else:
                        st.error("Credenciais inválidas.")
    st.stop()

# ==============================================================================
# APLICAÇÃO PRINCIPAL
# ==============================================================================
st.sidebar.markdown(f"### 👤 {st.session_state['nome']}")
st.sidebar.caption(f"📧 {st.session_state['email']}")
if st.sidebar.button("🚪 Sair"):
    st.session_state["logado"] = False
    st.rerun()

st.markdown("<div class='hero-banner'><h2 style='margin:0;'>🚛 SPEEDMAX & DIGITIRE</h2><p style='margin:0;'>Base Nacional Consolidada FMCSA • PostgreSQL Cloud SQL</p></div>", unsafe_allow_html=True)

tabs = st.tabs(["🔎 1. CONSULTA RAIO-X", "🗺️ 2. FILTRO REGIONAL (50/50)", "⭐ 3. CRM"] + (["🔐 4. ADMIN"] if st.session_state["is_admin"] else []))

with tabs[0]:
    c_uf, c_tipo, c_val, c_btn = st.columns([1.2, 1.4, 2.4, 1])
    uf_alvo = c_uf.selectbox("Estado (UF):", ["🌎 TODA MINHA CARTEIRA"] + st.session_state["ufs"])
    tipo_busca = c_tipo.selectbox("Critério:", ["Número USDOT", "Telefone / Celular", "Razão Social / DBA"])
    termo_busca = c_val.text_input("Digite para pesquisar:")
    disparar = c_btn.button("🔍 Consultar")

    if disparar and termo_busca.strip():
        with engine.connect() as conn:
            ufs = st.session_state["ufs"]
            if tipo_busca == "Número USDOT":
                query = "SELECT * FROM frotas WHERE DOT_CLEAN = :t"
                params = {"t": limpar_num(termo_busca)}
            elif tipo_busca == "Telefone / Celular":
                t = re.sub(r"[^\d]", "", termo_busca)
                query = "SELECT * FROM frotas WHERE (PHONE_CLEAN = :t OR CELL_CLEAN = :t)"
                params = {"t": t}
            else:
                query = "SELECT * FROM frotas WHERE (LEGAL_NAME ILIKE :t OR DBA_NAME ILIKE :t)"
                params = {"t": f"%{termo_busca.strip()}%"}
            
            if uf_alvo != "🌎 TODA MINHA CARTEIRA":
                query += " AND UF_CLEAN = :uf"
                params["uf"] = uf_alvo
            elif not st.session_state["is_admin"]:
                query += " AND UF_CLEAN = ANY(:ufs)"
                params["ufs"] = ufs
                
            query += " ORDER BY POWER_UNITS_INT DESC LIMIT 1"
            res = conn.execute(text(query), params).fetchone()
            
            if res:
                st.session_state["ficha_atual"] = dict(res._mapping)
                st.success("✅ Localizado!")
            else:
                st.session_state["ficha_atual"] = None
                st.error("❌ Não encontrado.")

    if st.session_state.get("ficha_atual"):
        d = st.session_state["ficha_atual"]
        pwr = limpar_num(d.get("POWER_UNITS_INT"))
        
        st.markdown(f"<h3 style='color:#4A148C;'>🚛 {val_limpo(d.get('LEGAL_NAME'))}</h3>", unsafe_allow_html=True)
        st.write(f"**USDOT:** {d.get('DOT_NUMBER')} | **Estado:** {d.get('PHY_STATE')}")
        st.write(f"**Telefone:** {fmt_tel(d.get('TELEPHONE'))}")
        st.write(f"**Frota Ativa:** {pwr} Power Units")
        
        st.markdown("<div class='sec-header'>⭐ Adicionar ao CRM</div>", unsafe_allow_html=True)
        with st.form("fav_form"):
            medida = st.selectbox("Medida de Pneu:", MEDIDAS_PNEUS)
            status = st.selectbox("Status:", STATUS_CRM)
            if st.form_submit_button("💾 Salvar"):
                with engine.connect() as conn:
                    conn.execute(text("""
                        INSERT INTO favoritos_crm (data_inclusao, email_vendedor, usdot, empresa, uf_cidade, decisor, contato, power_units, status_crm, medida_pneu)
                        VALUES (:d, :e, :u, :emp, :ufc, :dec, :cont, :pwr, :st, :med)
                    """), {
                        "d": datetime.now().strftime("%Y-%m-%d"), "e": st.session_state["email"], "u": d.get("DOT_NUMBER"),
                        "emp": d.get("LEGAL_NAME"), "ufc": f"{d.get('PHY_STATE')} - {d.get('PHY_CITY')}", "dec": d.get("COMPANY_OFFICER"),
                        "cont": fmt_tel(d.get("TELEPHONE")), "pwr": pwr, "st": status, "med": medida
                    })
                    conn.commit()
                st.success("Salvo no banco de dados!")

with tabs[1]:
    st.subheader("🗺️ Filtro Regional")
    uf_reg = st.selectbox("UF:", st.session_state["ufs"])
    cid_reg = st.text_input("Cidade (exato):")
    if st.button("Pesquisar") and cid_reg:
        with engine.connect() as conn:
            rows = conn.execute(text("SELECT DOT_NUMBER, LEGAL_NAME, PHY_CITY, PHY_STATE, TELEPHONE, POWER_UNITS_INT FROM frotas WHERE UF_CLEAN = :uf AND (PHY_CITY ILIKE :cid OR CITY_CLEAN = :cid2) ORDER BY POWER_UNITS_INT DESC LIMIT 50"), {"uf": uf_reg, "cid": cid_reg.strip(), "cid2": cid_reg.strip().replace(" ", "").upper()}).fetchall()
            if rows:
                st.dataframe(pd.DataFrame([dict(r._mapping) for r in rows]), use_container_width=True)
            else:
                st.warning("Nenhuma empresa encontrada.")

with tabs[2]:
    st.subheader("⭐ Meus Favoritos")
    with engine.connect() as conn:
        if st.session_state["is_admin"]:
            favs = conn.execute(text("SELECT * FROM favoritos_crm ORDER BY id DESC")).fetchall()
        else:
            favs = conn.execute(text("SELECT * FROM favoritos_crm WHERE lower(email_vendedor) = :e ORDER BY id DESC"), {"e": st.session_state["email"]}).fetchall()
        if favs:
            st.dataframe(pd.DataFrame([dict(r._mapping) for r in favs]), use_container_width=True)
        else:
            st.info("Nenhum favorito salvo.")

if st.session_state["is_admin"] and len(tabs) > 3:
    with tabs[3]:
        st.subheader("🔐 Painel Administrativo")
        with engine.connect() as conn:
            usrs = conn.execute(text("SELECT email, nome, status, estados_liberados FROM usuarios")).fetchall()
            st.dataframe(pd.DataFrame([dict(r._mapping) for r in usrs]))
