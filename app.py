import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import uuid
import qrcode
import io
import hashlib
from datetime import datetime
from scipy import stats

# 1. Configuración de la página (debe ir primero)
st.set_page_config(
    page_title='Panel de Consenso',
    page_icon='🎯',
    layout='wide',
    initial_sidebar_state='expanded'
)

# 2. Estilos globales
ACCENT = "#6C63FF"
BG = "#FFFFFF"
CARD_BG = "#F8F8F8"
TEXT = "#333333"
FONT = "'Segoe UI', Tahoma, Verdana, sans-serif"

st.markdown(f"""
<style>
  .stApp {{ background-color: {BG} !important; color: {TEXT}; font-family: {FONT}; }}
  .app-header {{
    background-color: {ACCENT}; padding: 1.5rem; border-radius: 0 0 10px 10px;
    text-align: center; color: white; font-size: 2rem; font-weight: bold;
  }}
  .metric-card {{
    background: {CARD_BG} !important; border-radius: 8px;
    box-shadow: 0 2px 6px rgba(0,0,0,0.1); padding: 1rem; margin-bottom: 1rem;
  }}
  .stButton>button {{
    background-color: {ACCENT} !important; color: white !important;
    padding: 0.6rem 1.2rem !important; border-radius: 6px !important;
  }}
  .stButton>button:hover {{ background-color: #5930c4 !important; }}
  input, textarea {{ background-color: {CARD_BG} !important; color: {TEXT} !important; }}
  .hide-sidebar [data-testid="stSidebar"], .hide-sidebar [data-testid="stToolbar"] {{ display: none; }}
</style>
""", unsafe_allow_html=True)

# 3. Almacenamiento en memoria
@st.cache_resource
def get_store():
    return {}

# 4. Funciones auxiliares
def hash_id(name: str) -> str:
    if not name:
        name = str(uuid.uuid4())
    return hashlib.sha256(name.encode()).hexdigest()[:8]

def new_session(description: str, scale: str):
    store = get_store()
    code = uuid.uuid4().hex[:6].upper()
    store[code] = {
        "description": description,
        "scale": scale,
        "votes": [],
        "comments": [],
        "ids": []
    }
    return code

def save_vote(code: str, vote, comment: str, pid: str):
    sess = get_store()[code]
    sess["votes"].append(vote)
    sess["comments"].append(comment)
    sess["ids"].append(pid)

def consensus_pct(votes):
    if not votes: return 0.0
    return sum(1 for v in votes if isinstance(v, int) and v >= 7) / len(votes)

def median_ci(votes):
    arr = np.array(votes)
    med = np.median(arr)
    res = stats.bootstrap((arr,), np.median, confidence_level=0.95, n_resamples=1000)
    return med, res.confidence_interval.low, res.confidence_interval.high

def make_qr(code: str):
    url = f"{st.secrets.get('BASE_URL','http://localhost:8501')}?session={code}"
    img = qrcode.make(url)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf

def to_excel(code: str):
    sess = get_store()[code]
    df = pd.DataFrame({
        "ID": sess["ids"],
        "Recomendación": sess["description"],
        "Voto": sess["votes"],
        "Comentario": sess["comments"]
    })
    df["Consenso"] = ["Sí" if consensus_pct(sess["votes"])>=0.8 else "No"]*len(df)
    buf = io.BytesIO()
    df.to_excel(buf, index=False)
    buf.seek(0)
    return buf

def summarize(comments: list):
    # Simplificado: sin OpenAI en local
    return "\n".join(comments[:5]) + ("..." if len(comments)>5 else "")

# 5. Página de votación
def voting_page():
    params = st.query_params
    init = params.get("session", [None])[0]
    st.markdown('<div class="hide-sidebar">', unsafe_allow_html=True)

    code = st.text_input("Código de sesión:", value=init or "")
    if not code:
        st.info("Escanea el QR o ingresa el código de sesión.")
        st.stop()

    store = get_store()
    if code not in store:
        st.error("Código inválido.")
        st.stop()

    # Pseudónimo
    name = st.text_input("Nombre de participante:")
    pid = hash_id(name)

    st.markdown(f"<div class='app-header'>Votación de Expertos</div>", unsafe_allow_html=True)
    desc = store[code]["description"]
    st.subheader(desc)

    scale = store[code]["scale"]
    vote = st.slider("Tu voto:", 1, 9, 5) if "Likert" in scale else st.radio("Tu voto:", ["Sí","No"])
    comment = st.text_area("Comentario (opcional):")

    if st.button("Enviar voto"):
        save_vote(code, vote, comment, pid)
        pct = consensus_pct(store[code]["votes"])*100
        st.progress(int(pct))
        st.success("Voto registrado.")
        st.stop()

# Ejecutar votación si param existe
if st.query_params.get("session"):
    voting_page()

# 6. Páginas de administración
st.sidebar.title("Administración")
page = st.sidebar.radio("", ["Inicio","Tablero"])

if page=="Inicio":
    st.markdown("<div class='app-header'>Panel de Consenso</div>", unsafe_allow_html=True)
    with st.form("create", clear_on_submit=True):
        desc = st.text_input("Recomendación:")
        scale = st.selectbox("Escala:", ["Likert 1-9","Sí/No"])
        if st.form_submit_button("Crear sesión") and desc:
            code = new_session(desc, scale)
            st.success(f"Código de sesión: {code}")
            st.image(make_qr(code), width=180)

else:  # Tablero
    st.header("Tablero de Moderador")
    code = st.text_input("Código de sesión:")
    store = get_store()
    if code not in store:
        st.info("Introduce un código válido.")
    else:
        sess = store[code]
        votes, comments, ids = sess["votes"], sess["comments"], sess["ids"]
        pct = consensus_pct(votes)
        med, lo, hi = median_ci(votes) if votes else (None,None,None)

        c1,c2,c3 = st.columns(3)
        c1.metric("Total votos", len(votes))
        c2.metric("% Consenso", f"{pct*100:.1f}%")
        if med is not None:
            c3.metric("Mediana (IC95)", f"{med:.1f} [{lo:.1f},{hi:.1f}]")

        # Interpretación
        if votes:
            if pct>=0.8 and (med or 0)>=7 or (med>=7 and lo>=7):
                st.success("Se aprueba el umbral.")
            elif pct>=0.8 and (med or 0)<=3 or (med<=3 and hi<=3):
                st.error("No se aprueba el umbral.")
            else:
                st.warning("Se requiere segunda ronda.")

        # Descargas
        col1,col2 = st.columns(2)
        col1.download_button("Descargar Excel", to_excel(code), f"res_{code}.xlsx",
                             "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        col2.download_button("Descargar Reporte", summarize(comments), f"rep_{code}.txt", "text/plain")

        # Gráfica
        if votes:
            df = pd.DataFrame({"Voto": votes})
            fig = px.histogram(df, x="Voto", nbins=9 if "Likert" in sess["scale"] else 2)
            fig.update_layout(plot_bgcolor=BG, paper_bgcolor=BG, colorway=[ACCENT])
            st.plotly_chart(fig, use_container_width=True)

        # Comentarios con ID
        if comments:
            st.subheader("Comentarios y IDs")
            for pid, com in zip(ids, comments):
                st.write(f"{pid}: {com}")
