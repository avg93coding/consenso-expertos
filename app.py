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

# Configuración de la página
st.set_page_config(
    page_title="Panel de Consenso",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Almacenamiento en memoria
def get_store():
    if 'store' not in st.session_state:
        st.session_state.store = {}
    return st.session_state.store

store = get_store()

# Utilidades
def make_session(desc: str, scale: str) -> str:
    code = uuid.uuid4().hex[:6].upper()
    store[code] = {
        "desc": desc,
        "scale": scale,
        "votes": [],
        "comments": [],
        "ids": [],
        "names": []
    }
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

# Estadísticas
def consensus_pct(votes):
    if not votes: return 0.0
    return sum(1 for v in votes if isinstance(v,int) and v>=7)/len(votes)

def median_ci(votes):
    arr = np.array(votes)
    med = np.median(arr)
    res = stats.bootstrap((arr,), np.median, confidence_level=0.95, n_resamples=1000)
    return med, res.confidence_interval.low, res.confidence_interval.high

# Generación QR
def make_qr(code: str):
    base = st.secrets.get("BASE_URL", "http://localhost:8501")
    url = f"{base}?session={code}"
    img = qrcode.make(url)
    buf = io.BytesIO(); img.save(buf, format="PNG"); buf.seek(0)
    return buf

# Exportar Excel con nombres reales
def to_excel(code: str):
    s = store[code]
    df = pd.DataFrame({
        "ID anónimo": s["ids"],
        "Nombre real": s["names"],
        "Recomendación": s["desc"],
        "Voto": s["votes"],
        "Comentario": s["comments"]
    })
    df["Consenso"] = ["Sí" if consensus_pct(s["votes"])>=0.8 else "No"] * len(df)
    buf = io.BytesIO(); df.to_excel(buf, index=False); buf.seek(0)
    return buf

# Formularios y paginación
params = st.query_params

# Página de votación (expertos)
if params.get("session"):
    code = params.get("session")[0]
    st.markdown("## Votación de Expertos")
    if code in store:
        sess = store[code]
        # Pedir nombre
        name = st.text_input("Nombre de participante:")
        pid_display = hash_id(name) if name else None
        st.subheader(sess["desc"])
        vote = st.slider("Tu voto:", 1, 9, 5) if sess["scale"].startswith("Likert") else st.radio("Tu voto:", ["Sí","No"])
        comment = st.text_area("Comentario (opcional):")
        if st.button("Enviar voto"):
            pid = record_vote(code, vote, comment, name)
            st.success(f"Gracias, voto registrado (ID: {pid}).")
            st.experimental_rerun()
    else:
        st.error("Código de sesión inválido.")
    st.stop()

# Panel de moderador
st.sidebar.title("Moderador")
page = st.sidebar.radio("", ["Inicio","Dashboard"])

if page == "Inicio":
    st.header("Crear Nueva Sesión")
    with st.form("form_create", clear_on_submit=True):
        desc = st.text_input("Recomendación:")
        scale = st.selectbox("Escala:", ["Likert 1-9","Sí/No"])
        if st.form_submit_button("Crear sesión") and desc:
            code = make_session(desc, scale)
            st.success(f"Sesión creada: **{code}**")
            st.image(make_qr(code), caption="Escanea para votar", width=200)

else:
    st.header("Dashboard en Vivo")
    # Seleccionar sesión activa
    codes = list(store.keys())
    if not codes:
        st.info("No hay sesiones activas.")
    else:
        sel = st.selectbox("Selecciona Sesión:", codes)
        sess = store[sel]
        votes = sess["votes"]
        comments = sess["comments"]
        ids = sess["ids"]
        names = sess["names"]
        # Métricas
        c1,c2,c3 = st.columns(3)
        c1.metric("Total votos", len(votes))
        pct = consensus_pct(votes)
        c2.metric("% Consenso", f"{pct*100:.1f}%")
        if votes:
            med, lo, hi = median_ci(votes)
            c3.metric("Mediana (IC95)", f"{med:.1f} [{lo:.1f}, {hi:.1f}]")
        # Interpretación
        if votes:
            if pct>=0.8 and med>=7 and lo>=7:
                st.success("Se aprueba el umbral.")
            elif pct>=0.8 and med<=3 and hi<=3:
                st.error("No se aprueba el umbral.")
            else:
                st.warning("No hay consenso; segunda ronda necesaria.")
        # Descargas
        d1,d2 = st.columns(2)
        d1.download_button("Descargar Excel", to_excel(sel), f"res_{sel}.xlsx")
        d2.download_button("Descargar reporte texto", summarize(comments), f"report_{sel}.txt")
        # Gráfica
        if votes:
            df = pd.DataFrame({"Voto": votes})
            fig = px.histogram(df, x="Voto", nbins=9 if sess["scale"].startswith("Likert") else 2)
            st.plotly_chart(fig, use_container_width=True)
        # Trazabilidad en pantalla
        if comments:
            st.subheader("Comentarios (ID anónimo)")
            for pid, com in zip(ids, comments):
                st.write(f"{pid}: {com}")

        # Reporte final resumido
        st.markdown("---")
        st.subheader("Reporte Final Resumido")
        st.write(summarize(comments))
