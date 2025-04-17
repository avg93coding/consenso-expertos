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
)

# 2) Store global compartido (cache_resource para todos los usuarios)
@st.cache_resource
def get_store():
    return {}
store = get_store()

# 3) Utilidades
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

def consensus_pct(votes):
    return sum(1 for v in votes if isinstance(v,int) and v>=7) / len(votes) if votes else 0.0

def median_ci(votes):
    arr = np.array(votes)
    med = np.median(arr)
    res = stats.bootstrap((arr,), np.median, confidence_level=0.95, n_resamples=1000)
    return med, res.confidence_interval.low, res.confidence_interval.high

def make_qr(code: str):
    base = st.secrets["BASE_URL"]
    img = qrcode.make(f"{base}?session={code}")
    buf = io.BytesIO(); img.save(buf, format="PNG"); buf.seek(0)
    return buf

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

def summarize(comments):
    return "\n".join(comments[:5]) + ("..." if len(comments)>5 else "")

# 4) VOTACIÓN (solo si hay ?session=)
params = st.query_params
if "session" in params:
    code = params["session"][0]
    st.markdown("## Votación de Expertos")
    if code not in store:
        st.error("Sesión no válida.")
        st.stop()
    s = store[code]
    name = st.text_input("Nombre de participante:")
    pid = hash_id(name or str(uuid.uuid4()))
    st.write(f"**Recomendación:** {s['desc']}")
    vote = (st.slider("Tu voto (1–9):", 1, 9, 5)
            if s["scale"].startswith("Likert")
            else st.radio("Tu voto:", ["Sí","No"]))
    comment = st.text_area("Comentario (opcional):")
    if st.button("Enviar voto"):
        record_vote(code, vote, comment, name)
        pct = int(consensus_pct(s["votes"])*100)
        st.progress(pct)
        st.success(f"Voto registrado (ID: {pid}).")
    st.stop()

# 5) PANEL DE MODERADOR
st.sidebar.title("Moderador")
mode = st.sidebar.radio("Ir a:", ["Inicio","Dashboard"])

if mode=="Inicio":
    st.header("🔧 Crear Sesión")
    with st.form("form"):
        desc = st.text_input("Recomendación:")
        scale = st.selectbox("Escala:", ["Likert 1-9","Sí/No"])
        if st.form_submit_button("Crear sesión") and desc:
            code = make_session(desc, scale)
            st.success(f"Código: **{code}**")
            st.image(make_qr(code), caption="Escanea para votar", width=200)

else:
    st.header("📊 Dashboard en Vivo")
    codes = list(store.keys())
    if not codes:
        st.info("No hay sesiones activas.")
    else:
        sel = st.selectbox("Sesión activa:", codes)
        s = store[sel]
        votes, comments, ids = s["votes"], s["comments"], s["ids"]
        pct = consensus_pct(votes)
        med, lo, hi = median_ci(votes) if votes else (None,None,None)

        c1,c2,c3 = st.columns(3)
        c1.metric("Votos totales", len(votes))
        c2.metric("% Consenso", f"{pct*100:.1f}%")
        if med is not None:
            c3.metric("Mediana (IC95%)", f"{med:.1f} [{lo:.1f},{hi:.1f}]")

        if votes:
            if pct>=0.8 and med>=7 and lo>=7:
                st.success("✅ Umbral aprobado")
            elif pct>=0.8 and med<=3 and hi<=3:
                st.error("❌ Umbral no aprobado")
            else:
                st.warning("⚠️ Segunda ronda necesaria")

        d1,d2 = st.columns(2)
        d1.download_button("📥 Descargar Excel", to_excel(sel),
                           file_name=f"res_{sel}.xlsx")
        d2.download_button("📥 Descargar Resumen", summarize(comments),
                           file_name=f"rep_{sel}.txt")

        if votes:
            df = pd.DataFrame({"Voto": votes})
            fig = px.histogram(df, x="Voto", nbins=9 if s["scale"].startswith("Likert") else 2)
            st.plotly_chart(fig, use_container_width=True)

        if comments:
            st.subheader("Comentarios (ID anónimo)")
            for pid, com in zip(ids, comments):
                st.write(f"- {pid}: {com}")
