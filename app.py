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

# 1) Configuración inicial
st.set_page_config(
    page_title="Dashboard de Consenso",
    page_icon="🎯",
    layout="wide",
)

# 2) Almacenamiento en memoria
@st.cache_resource
def get_store():
    return {}

store = get_store()

# 3) Utilidades
def make_session(desc: str, scale: str) -> str:
    code = uuid.uuid4().hex[:6].upper()
    store[code] = {"desc": desc, "scale": scale, "votes": [], "comments": [], "ids": []}
    return code

def hash_id(name: str) -> str:
    return hashlib.sha256(name.encode()).hexdigest()[:8]

def record_vote(code: str, vote, comment: str, pid: str):
    s = store[code]
    s["votes"].append(vote)
    s["comments"].append(comment)
    s["ids"].append(pid)

def consensus_pct(votes):
    if not votes: return 0.0
    return sum(1 for v in votes if isinstance(v,int) and v>=7) / len(votes)

def median_ci(votes):
    arr = np.array(votes)
    med = np.median(arr)
    res = stats.bootstrap((arr,), np.median, confidence_level=0.95, n_resamples=1000)
    return med, res.confidence_interval.low, res.confidence_interval.high

def make_qr(code: str):
    base = st.secrets.get("BASE_URL", "http://localhost:8501")
    img = qrcode.make(f"{base}?session={code}")
    buf = io.BytesIO(); img.save(buf, format="PNG"); buf.seek(0)
    return buf

def to_excel(code: str):
    s = store[code]
    df = pd.DataFrame({
        "ID (anónimo)": s["ids"],
        "Recomendación": s["desc"],
        "Voto": s["votes"],
        "Comentario": s["comments"]
    })
    df["Consenso"] = ["Sí" if consensus_pct(s["votes"])>=0.8 else "No"]*len(df)
    buf = io.BytesIO(); df.to_excel(buf, index=False); buf.seek(0)
    return buf

def summarize(comments):
    return "\n".join(comments[:5]) + ("..." if len(comments)>5 else "")

# 4) Página de votación
def voting_page():
    params = st.query_params
    init = params.get("session", [None])[0]
    code = st.text_input("Código de sesión:", value=init or "")
    if not code:
        st.info("Escanea el QR o introduce el código para empezar a votar.")
        return

    if code not in store:
        st.error("Código inválido.")
        return

    s = store[code]
    name = st.text_input("Tu nombre (se anonimiza):")
    pid = hash_id(name or str(uuid.uuid4()))

    st.markdown(f"### Recomendación:\n**{s['desc']}**")
    vote = (st.slider("Tu voto (1–9):", 1, 9, 5)
            if s["scale"].startswith("Likert")
            else st.radio("Tu voto:", ["Sí","No"]))
    comment = st.text_area("Comentario (opcional):")

    if st.button("Enviar voto"):
        record_vote(code, vote, comment, pid)
        pct = int(consensus_pct(s["votes"])*100)
        st.progress(pct)
        st.success("Voto registrado.")

# Si se accede con ?session=XYZ, mostramos solo la votación
if st.query_params.get("session"):
    st.markdown("<style>.css-1d391kg{display:none;}</style>", unsafe_allow_html=True)
    voting_page()
    st.stop()

# 5) Panel de administración
st.sidebar.title("Administración")
page = st.sidebar.radio("Ir a:", ["Inicio","Reportes Finales"])

if page=="Inicio":
    st.header("🔧 Crear nueva sesión")
    with st.form("form_create", clear_on_submit=True):
        desc = st.text_input("Recomendación:")
        scale = st.selectbox("Escala:", ["Likert 1-9","Sí/No"])
        if st.form_submit_button("Crear sesión") and desc:
            code = make_session(desc, scale)
            st.success(f"Código de sesión: **{code}**")
            st.image(make_qr(code), caption="Escanea para votar")
else:
    st.header("📊 Reportes Finales")
    code = st.text_input("Código de sesión:")
    if not code:
        st.info("Introduce un código para ver resultados.")
    elif code not in store:
        st.error("Código no encontrado.")
    else:
        s = store[code]
        votes, comments, ids = s["votes"], s["comments"], s["ids"]
        pct = consensus_pct(votes)
        med, lo, hi = median_ci(votes) if votes else (None,None,None)

        c1,c2,c3 = st.columns(3)
        c1.metric("Total votos", len(votes))
        c2.metric("% Consenso", f"{pct*100:.1f}%")
        if med is not None:
            c3.metric("Mediana (IC95%)", f"{med:.1f} [{lo:.1f},{hi:.1f}]")

        # Interpretación
        if votes:
            if pct>=0.8 and med>=7 and lo>=7:
                st.success("✅ Se aprueba el umbral.")
            elif pct>=0.8 and med<=3 and hi<=3:
                st.error("❌ No se aprueba el umbral.")
            else:
                st.warning("⚠️ Se requiere segunda ronda.")

        # Descargas
        colA, colB = st.columns(2)
        colA.download_button("📥 Descargar Excel", to_excel(code),
                             file_name=f"resultados_{code}.xlsx")
        colB.download_button("📥 Descargar Resumen", summarize(comments),
                             file_name=f"reporte_{code}.txt")

        # Gráfica
        if votes:
            df = pd.DataFrame({"Voto": votes})
            fig = px.histogram(df, x="Voto", nbins=9 if s["scale"].startswith("Likert") else 2)
            st.plotly_chart(fig, use_container_width=True)

        # Comentarios con ID
        if comments:
            st.subheader("Comentarios y IDs")
            for pid, com in zip(ids, comments):
                st.write(f"- {pid}: {com}")
