import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import uuid
import qrcode
import io
import hashlib
from scipy import stats

# 1) Configuración de la página
st.set_page_config(
    page_title="Dashboard de Consenso",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# 2) Store global
@st.cache_resource
def get_store():
    return {}
store = get_store()

# 3) Utilidades
def make_session(desc: str, scale: str) -> str:
    code = uuid.uuid4().hex[:6].upper()
    store[code] = {"desc": desc, "scale": scale, "votes": [], "comments": [], "ids": [], "names": []}
    return code

def hash_id(name: str) -> str:
    return hashlib.sha256(name.encode()).hexdigest()[:8]

def record_vote(code: str, vote, comment: str, name: str):
    s = store[code]
    pid = hash_id(name or str(uuid.uuid4()))
    s["votes"].append(vote)
    s["comments"].append(comment)
    s["ids"].append(pid)
    s["names"].append(name)
    return pid

def consensus_pct(votes):
    return sum(1 for v in votes if isinstance(v,int) and v>=7)/len(votes) if votes else 0.0

def median_ci(votes):
    arr = np.array(votes)
    med = np.median(arr)
    res = stats.bootstrap((arr,), np.median, confidence_level=0.95, n_resamples=1000)
    return med, res.confidence_interval.low, res.confidence_interval.high

def make_qr(code: str) -> io.BytesIO:
    base = st.secrets.get("BASE_URL", "http://localhost:8501")
    buf = io.BytesIO()
    qrcode.make(f"{base}?session={code}").save(buf, format="PNG")
    buf.seek(0)
    return buf

def to_excel(code: str) -> io.BytesIO:
    s = store[code]
    df = pd.DataFrame({
        "ID anónimo": s["ids"],
        "Nombre real": s["names"],
        "Recomendación": s["desc"],
        "Voto": s["votes"],
        "Comentario": s["comments"]
    })
    df["Consenso"] = ["Sí" if consensus_pct(s["votes"])>=0.8 else "No" for _ in s["votes"]]
    buf = io.BytesIO(); df.to_excel(buf,index=False); buf.seek(0)
    return buf

def summarize_comments(comments: list) -> str:
    if not comments: return "Sin comentarios."
    return "\n".join(comments[:5]) + ("..." if len(comments)>5 else "")

# 4) CSS global
def inject_css():
    ACCENT = "#6C63FF"
    BG = "#FFFFFF"
    CARD_BG = "#F8F8F8"
    TEXT = "#333333"
    FONT = "'Segoe UI', Tahoma, Verdana, sans-serif"
    css = f"""
    <style>
      .stApp {{background-color:{BG} !important; color:{TEXT}; font-family:{FONT};}}
      .app-header {{background-color:{ACCENT}; padding:1rem; border-radius:0 0 10px 10px; text-align:center; color:white; font-size:1.75rem;}}
      .hide-sidebar [data-testid=\"stSidebar\"], .hide-sidebar [data-testid=\"stToolbar\"] {{display:none;}}
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)
inject_css()

# 5) Página de votación sólo si ?session=
params = st.query_params
if "session" in params:
    code = params["session"][0]
    st.markdown('<div class="hide-sidebar">', unsafe_allow_html=True)
    st.header("Votación de Expertos")
    if code not in store:
        st.error("Sesión inválida.")
        st.stop()
    s = store[code]
    name = st.text_input("Nombre de participante:")
    pid = hash_id(name or str(uuid.uuid4()))
    st.subheader(s["desc"])
    vote = (st.slider("Tu voto (1–9):",1,9,5) if s["scale"].startswith("Likert") else st.radio("Tu voto:",["Sí","No"]))
    comment = st.text_area("Comentario (opcional):")
    if st.button("Enviar voto"):
        record_vote(code, vote, comment, name)
        pct = int(consensus_pct(s["votes"]) * 100)
        st.progress(pct)
        st.success(f"Voto registrado (ID: {pid})")
    st.stop()

# 6) Panel de administración
st.sidebar.title("Administración")
menu = st.sidebar.radio("", ["Inicio","Dashboard"])

if menu == "Inicio":
    st.header("Crear Nueva Sesión")
    with st.form("create_form", clear_on_submit=True):
        desc = st.text_input("Recomendación:")
        scale = st.selectbox("Escala:",["Likert 1-9","Sí/No"])
        if st.form_submit_button("Crear sesión") and desc:
            code = make_session(desc, scale)
            st.success(f"Sesión creada: **{code}**")
            st.image(make_qr(code), caption="Escanea para votar", width=180)
else:
    st.header("Dashboard en Vivo")
    if not store:
        st.info("No hay sesiones activas.")
    else:
        code = st.selectbox("Selecciona sesión:", list(store.keys()))
        s = store[code]
        votes, comments, ids = s["votes"], s["comments"], s["ids"]
        c1,c2,c3 = st.columns(3)
        c1.metric("Total votos", len(votes))
        pct = consensus_pct(votes)*100
        c2.metric("% Consenso", f"{pct:.1f}%")
        if votes:
            med,lo,hi = median_ci(votes)
            c3.metric("Mediana (IC95)", f"{med:.1f} [{lo:.1f},{hi:.1f}]")
        if votes:
            if pct>=80 and lo>=7:
                st.success("Se aprueba el umbral.")
            elif pct>=80 and hi<=3:
                st.error("No se aprueba el umbral.")
            else:
                st.warning("Segunda ronda necesaria.")
        colA,colB = st.columns(2)
        colA.download_button("Descargar Excel", to_excel(code), file_name=f"res_{code}.xlsx")
        colB.download_button("Descargar reporte", summarize_comments(comments), file_name=f"rep_{code}.txt")
        if votes:
            df = pd.DataFrame({"Voto":votes})
            fig = px.histogram(df,x="Voto",nbins=9 if s["scale"].startswith("Likert") else 2)
            st.plotly_chart(fig,use_container_width=True)
        if comments:
            st.subheader("Comentarios (ID anónimo)")
            for pid, com in zip(ids, comments): st.write(f"{pid}: {com}")
