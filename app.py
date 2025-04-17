import streamlit as st

# == Configuración inicial ==
st.set_page_config(
    page_title='Panel de Consenso',
    page_icon='🎯',
    layout='wide',
    initial_sidebar_state='expanded'
)

import pandas as pd
import numpy as np
import plotly.express as px
import uuid
import qrcode
import io
from datetime import datetime
import openai
import hashlib
from scipy import stats

# == Parámetros de estilo ==
BASE_URL = st.secrets.get("BASE_URL", "http://localhost:8501")
ACCENT = "#6C63FF"
BG_COLOR = "#FFFFFF"
CARD_BG = "#F8F8F8"
TEXT_COLOR = "#333333"
FONT = "'Segoe UI', Tahoma, Verdana, sans-serif"

# == CSS Global claro ==
CSS = f"""
<style>
  .stApp {{ background-color: {BG_COLOR} !important; color: {TEXT_COLOR}; font-family: {FONT}; }}
  .app-header {{ background-color: {ACCENT}; padding: 2rem; border-radius: 0 0 15px 15px; text-align: center; color: white; font-size: 2.5rem; font-weight: bold; }}
  .metric-card {{ background: {CARD_BG} !important; border-radius: 10px; box-shadow: 0 2px 6px rgba(0,0,0,0.1); padding: 1rem 1.5rem; margin-bottom: 1rem; transition: transform 0.2s; }}
  .metric-card:hover {{ transform: translateY(-3px); box-shadow: 0 4px 12px rgba(0,0,0,0.15); }}
  .stButton>button {{ background-color: {ACCENT} !important; color: white !important; padding: 0.8rem 1.5rem !important; font-size: 1rem !important; border-radius: 8px !important; transition: background 0.2s; }}
  .stButton>button:hover {{ background-color: #5930c4 !important; }}
  input, textarea, .stTextInput>div>div>input, .stSelectbox>div>div>div>div {{ background-color: {CARD_BG} !important; color: {TEXT_COLOR} !important; border-radius: 6px !important; }}
  .hide-sidebar [data-testid="stSidebar"], .hide-sidebar [data-testid="stToolbar"] {{ display: none; }}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

# == Almacenamiento en memoria ==
@st.cache_resource
def get_data_store():
    return {'sessions': {}}

# == Funciones Auxiliares ==

def generar_codigo():
    return uuid.uuid4().hex[:6].upper()

def crear_sesion(recomendacion: str, escala: str) -> str:
    store = get_data_store()
    code = generar_codigo()
    store['sessions'][code] = {
        'recomendacion': recomendacion,
        'escala': escala,
        'votos': [],
        'comentarios': [],
        'ids': []
    }
    return code

def anonimizar_nombre(nombre: str) -> str:
    return hashlib.sha256(nombre.encode()).hexdigest()[:8]

def registrar_voto(code: str, voto, comentario: str, pid: str):
    sess = get_data_store()['sessions'][code]
    sess['votos'].append(voto)
    sess['comentarios'].append(comentario)
    sess['ids'].append(pid)

def calcular_consenso(votos: list) -> float:
    if not votos:
        return 0.0
    return sum(1 for v in votos if isinstance(v,int) and v>=7)/len(votos)

def estadistica_mediana_ic(votos: list) -> tuple:
    arr = np.array(votos)
    mediana = np.median(arr)
    res = stats.bootstrap((arr,), np.median, confidence_level=0.95, n_resamples=1000)
    return mediana, res.confidence_interval.low, res.confidence_interval.high

def generar_qr(code: str) -> bytes:
    url = f"{BASE_URL}?session={code}"
    img = qrcode.make(url)
    buf = io.BytesIO(); img.save(buf,format='PNG'); buf.seek(0)
    return buf.getvalue()

def exportar_excel(code: str) -> bytes:
    sess = get_data_store()['sessions'][code]
    df = pd.DataFrame({
        'ID Anónimo': sess['ids'],
        'Recomendación': sess['recomendacion'],
        'Voto': sess['votos'],
        'Comentario': sess['comentarios']
    })
    df['Consenso'] = ['Sí' if calcular_consenso(sess['votos'])>=0.8 else 'No'] * len(df)
    buf = io.BytesIO(); df.to_excel(buf, index=False); buf.seek(0)
    return buf.getvalue()

def resumen_comentarios(comments: list) -> str:
    if 'OPENAI_API_KEY' in st.secrets:
        openai.api_key = st.secrets['OPENAI_API_KEY']
        prompt = "Resume estos comentarios de expertos:\n" + "\n".join(comments)
        resp = openai.ChatCompletion.create(model='gpt-4', messages=[{'role':'user','content':prompt}])
        return resp.choices[0].message.content
    return "API de OpenAI no configurada."

# == Página de Votación ==
# Detecta session en query params una sola vez
def pagina_votacion():
    params = st.experimental_get_query_params()
    initial = params.get('session', [None])[0]
    st.markdown('<div class="hide-sidebar">',unsafe_allow_html=True)

    code = st.text_input("Código de sesión:", value=initial or "")
    if not code:
        st.info("Escanea el QR o ingresa el código de sesión para comenzar.")
        return

    store = get_data_store()['sessions']
    if code not in store:
        st.error("Código inválido.")
        return

    sess = store[code]
    st.text_input("Nombre de participante:", key='name')
    nombre = st.session_state.get('name', '')
    pid = anonimizar_nombre(nombre) if nombre else anonimizar_nombre(str(uuid.uuid4()))

    st.markdown(f"<div class='app-header'>Votación de Expertos</div>", unsafe_allow_html=True)
    st.subheader(sess['recomendacion'])
    voto = st.slider("Tu voto:", 1, 9, 5) if 'Likert' in sess['escala'] else st.radio("Tu voto:", ['Sí', 'No'])
    comentario = st.text_area("Comentario (opcional):")
    if st.button("Enviar voto"):
        registrar_voto(code, voto, comentario, pid)
        st.progress(int(calcular_consenso(sess['votos']) * 100))
        st.success("Voto registrado.")

# Ejecutar votación si hay session en URL
pagina_votacion()

# == Páginas de Administración ==
def pagina_inicio():
    st.markdown("<div class='app-header'>Panel de Consenso</div>",unsafe_allow_html=True)
    with st.form("crear_form", clear_on_submit=True):
        recomendacion = st.text_input("Recomendación:")
        escala = st.selectbox("Escala:", ['Likert 1-9', 'Sí/No'])
        if st.form_submit_button("Crear sesión") and recomendacion:
            code = crear_sesion(recomendacion, escala)
            st.success(f"Código de sesión: {code}")
            st.image(generar_qr(code), width=180, caption="Escanea para votar")


def pagina_tablero():
    st.header("Tablero de Moderador")
    code = st.text_input("Código de sesión:")
    store = get_data_store()['sessions']
    if code not in store:
        st.info("Introduce un código válido.")
        return
    sess = store[code]
    votos, comentarios, ids = sess['votos'], sess['comentarios'], sess['ids']
    med, low, high = estadistica_mediana_ic(votos) if votos else (None, None, None)
    cons = calcular_consenso(votos)

    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(f"<div class='metric-card'><h4>Total votos</h4><p style='font-size:2rem;'>{len(votos)}</p></div>",unsafe_allow_html=True)
    with c2:
        st.markdown(f"<div class='metric-card'><h4>% Consenso</h4><p style='font-size:2rem;'>{cons*100:.1f}%</p></div>",unsafe_allow_html=True)
    with c3:
        if med is not None:
            st.markdown(f"<div class='metric-card'><h4>Mediana (IC95%)</h4><p>{med:.1f} [{low:.1f}, {high:.1f}]</p></div>",unsafe_allow_html=True)

    # Interpretación
    if votos:
        if (cons >= 0.8 and np.median(votos) >= 7) or (med >= 7 and low >= 7):
            st.success("Se aprueba el umbral.")
        elif (cons >= 0.8 and np.median(votos) <= 3) or (med <= 3 and high <= 3):
            st.error("No se aprueba el umbral.")
        else:
            st.warning("Se requiere segunda ronda.")

    # Descargas
    d1, d2 = st.columns(2)
    d1.download_button("Descargar Excel", data=exportar_excel(code), file_name=f"resultados_{code}.xlsx", mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    reporte = resumen_comentarios(comentarios) if comentarios else "Sin comentarios"
    d2.download_button("Descargar Reporte", data=reporte, file_name=f"reporte_{code}.txt", mime='text/plain')

    # Gráfica y comentarios
    if votos:
        df = pd.DataFrame({'Voto': votos})
        fig = px.histogram(df, x='Voto', nbins=9 if 'Likert' in sess['escala'] else 2)
        fig.update_layout(plot_bgcolor=BG_COLOR, paper_bgcolor=BG_COLOR, colorway=[ACCENT])
        st.plotly_chart(fig, use_container_width=True)
    if comentarios:
        st.subheader("Comentarios y IDs anónimos")
        for pid, c in zip(ids, comentarios):
            st.write(f"{pid}: {c}")

# == Navegación Lateral ==
pag = {'Inicio': pagina_inicio, 'Tablero': pagina_tablero}
st.sidebar.title("Administración")
opt = st.sidebar.radio("", list(pag.keys()))
pag[opt]()
