import streamlit as st

# 📌 PRIMERA llamada a Streamlit
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
from scipy import stats

# ----------------------------------------
# URL BASE PARA QR (defínela en .streamlit/secrets.toml)
BASE_URL = st.secrets.get("BASE_URL", "http://localhost:8501")

# ----------------------------------------
# PALETA OSCURA EN TONOS MORADOS
FONDO = "#1e1e2f"
CARD_BG = "#2d0c5e"
ACCENT = "#6C63FF"
TEXTO = "#FFFFFF"
FUENTE = "'Segoe UI', Tahoma, Geneva, Verdana, sans-serif"

# ----------------------------------------
# CSS GLOBAL (modo oscuro completo)
CSS = f"""
<style>
  .stApp {{ background-color: {FONDO} !important; }}
  body, .css-18e3th9, .main {{ background-color: {FONDO} !important; color: {TEXTO} !important; font-family: {FUENTE}; }}
  .app-header {{
    background: {ACCENT}; padding: 2rem; border-radius: 0 0 20px 20px;
    text-align: center; color: {TEXTO}; font-size: 2.5rem; font-weight: bold;
  }}
  .metric-card {{
    background: {CARD_BG} !important; border-radius: 12px;
    box-shadow: 0 6px 20px rgba(0,0,0,0.5); padding: 1.2rem 1.8rem;
    margin-bottom: 1.2rem; transition: transform 0.2s;
  }}
  .metric-card:hover {{
    transform: translateY(-4px); box-shadow: 0 8px 30px rgba(0,0,0,0.7);
  }}
  .stButton>button {{
    background-color: {ACCENT} !important; color: {TEXTO} !important;
    padding: 0.9rem 1.8rem !important; font-size: 1.1rem !important;
    border-radius: 10px !important; transition: background 0.2s;
  }}
  .stButton>button:hover {{ background-color: {CARD_BG} !important; }}
  input, textarea, .stTextInput>div>div>input, .stSelectbox>div>div>div>div {{
    background-color: {CARD_BG} !important; color: {TEXTO} !important;
    border-radius: 6px !important;
  }}
  .hide-sidebar [data-testid="stSidebar"] {{ display: none; }}
  .hide-sidebar [data-testid="stToolbar"] {{ display: none; }}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

# ----------------------------------------
# DATOS EN MEMORIA
@st.cache_resource
def get_data_store():
    return {'sessions': {}}

# ----------------------------------------
# FUNCIONES AUXILIARES

def generar_codigo():
    return uuid.uuid4().hex[:6].upper()


def crear_sesion(item: str, escala: str) -> str:
    store = get_data_store()
    code = generar_codigo()
    store['sessions'][code] = {
        'items': [{'nombre': item, 'escala': escala}],
        'indice_actual': 0,
        'votos': [],
        'comentarios': []
    }
    return code


def obtener_item(session: dict) -> dict:
    return session['items'][session['indice_actual']]


def registrar_voto(code: str, voto, comentario: str):
    sess = get_data_store()['sessions'][code]
    sess['votos'].append(voto)
    sess['comentarios'].append(comentario)


def calcular_consenso(session: dict) -> float:
    votos = session['votos']
    if not votos:
        return 0.0
    item = obtener_item(session)
    if 'Likert' in item['escala']:
        return sum(1 for v in votos if isinstance(v, int) and v >= 7)/len(votos)
    else:
        return votos.count('Sí')/len(votos)


def estadistica_mediana_ic(votos: list) -> tuple:
    arr = np.array(votos)
    mediana = np.median(arr)
    ci = stats.bootstrap((arr,), np.median, confidence_level=0.95, n_resamples=1000).confidence_interval
    return mediana, ci.low, ci.high


def generar_qr(code: str) -> bytes:
    url = f"{BASE_URL}?session={code}"
    img = qrcode.make(url)
    buf = io.BytesIO(); img.save(buf, format='PNG'); return buf.getvalue()


def exportar_excel(code: str) -> bytes:
    session = get_data_store()['sessions'][code]
    df = pd.DataFrame({
        'Ítem': obtener_item(session)['nombre'],
        'Voto': session['votos'],
        'Comentario': session['comentarios']
    })
    df['Consenso'] = ['Sí' if calcular_consenso(session)>=0.8 else 'No']*len(df)
    buf = io.BytesIO(); df.to_excel(buf, index=False); buf.seek(0); return buf.getvalue()


def resumen_comentarios(comments: list) -> str:
    if 'OPENAI_API_KEY' in st.secrets:
        openai.api_key = st.secrets['OPENAI_API_KEY']
        prompt = "Resume estos comentarios de expertos:\n"+"\n".join(comments)
        resp = openai.ChatCompletion.create(model='gpt-4',messages=[{'role':'user','content':prompt}])
        return resp.choices[0].message.content
    return "API de OpenAI no configurada."

# ----------------------------------------
# VOTACIÓN DEDICADA
params = st.query_params
if 'session' in params:
    st.markdown('<div class="hide-sidebar">', unsafe_allow_html=True)
    code = params['session'][0]
    st.markdown("<div class='app-header'>Votación de Expertos</div>", unsafe_allow_html=True)
    sessions = get_data_store()['sessions']
    if code in sessions:
        session = sessions[code]
        item = obtener_item(session)
        st.subheader(item['nombre'])
        voto = st.slider("Tu voto:",1,9,5) if 'Likert' in item['escala'] else st.radio("Tu voto:",['Sí','No'])
        comentario = st.text_area("Comentario (opcional):")
        if st.button("Enviar voto"):
            registrar_voto(code, voto, comentario)
            st.progress(int(calcular_consenso(session)*100))
            st.success("¡Gracias! Voto registrado.")
    else:
        st.error("Código de sesión no válido.")
    st.stop()

# ----------------------------------------
# PÁGINAS ADMIN

def pagina_inicio():
    st.markdown("<div class='app-header'>Panel de Consenso</div>", unsafe_allow_html=True)
    st.markdown(f"<h3 style='text-align:center; color:{ACCENT};'>Odds Epidemiology</h3>", unsafe_allow_html=True)
    with st.form("formulario_crear", clear_on_submit=True):
        item = st.text_input("Ítem de votación:")
        escala = st.selectbox("Escala:",['Likert 1-9','Sí/No'])
        if st.form_submit_button("Crear sesión") and item:
            code = crear_sesion(item,escala)
            st.success(f"Código de sesión: {code}")
            st.image(generar_qr(code),width=180)


def pagina_tablero():
    st.header("Tablero de Moderador")
    code = st.text_input("Código de sesión:")
    sessions = get_data_store()['sessions']
    if code in sessions:
        session = sessions[code]
        votos = session['votos']; comentarios = session['comentarios']
        # Cálculo estadístico
        med, low, high = estadistica_mediana_ic(votos) if votos else (None,None,None)
        cons = calcular_consenso(session)
        # Métricas
        c1,c2,c3 = st.columns(3)
        with c1:
            st.markdown(f"<div class='metric-card'><h4>Total de votos</h4><p style='font-size:2rem;'>{len(votos)}</p></div>",unsafe_allow_html=True)
        with c2:
            st.markdown(f"<div class='metric-card'><h4>% Consenso</h4><p style='font-size:2rem;'>{cons*100:.1f}%</p></div>",unsafe_allow_html=True)
        with c3:
            if med is not None:
                st.markdown(f"<div class='metric-card'><h4>Mediana (IC95%)</h4><p>{med:.1f} [{low:.1f}, {high:.1f}]</p></div>",unsafe_allow_html=True)
        # Interpretación
        if votos:
            aprobado = (cons>=0.8 and np.median(votos)>=7) or (med>=7 and low>=7)
            desaprobado = (cons>=0.8 and np.median(votos)<=3) or (med<=3 and high<=3)
            if aprobado:
                st.success("✅ Se aprueba el valor del umbral.")
            elif desaprobado:
                st.error("❌ No se aprueba el valor del umbral.")
            else:
                st.warning("⚠️ No se alcanza consenso; se requiere segunda ronda.")
        # Exportar y reporte final
        dl1,dl2 = st.columns(2)
        with dl1:
            st.download_button("🔽 Descargar Excel", data=exportar_excel(code),file_name=f"resultados_{code}.xlsx",mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        with dl2:
            reporte = resumen_comentarios(comentarios) if comentarios else "No hay comentarios." 
            st.download_button("🔽 Descargar Reporte Texto",data=reporte,file_name=f"reporte_{code}.txt",mime='text/plain')
        # Gráfica
        if votos:
            df = pd.DataFrame({'Voto':votos})
            fig = px.histogram(df,x='Voto',nbins=9 if 'Likert' in obtener_item(session)['escala'] else 2)
            fig.update_layout(plot_bgcolor=FONDO,paper_bgcolor=FONDO,colorway=[ACCENT])
            st.plotly_chart(fig,use_container_width=True)
        # Comentarios
        if comentarios:
            st.subheader("Comentarios")
            for c in comentarios:
                st.write(f"- {c}")
    else:
        st.info("Introduce un código válido.")

# ----------------------------------------
# NAVEGACIÓN LATERAL
PAGINAS = {'Inicio':pagina_inicio,'Tablero':pagina_tablero}
st.sidebar.title("Panel de Administración")
seleccion = st.sidebar.radio("",list(PAGINAS.keys()))
PAGINAS[seleccion]()
