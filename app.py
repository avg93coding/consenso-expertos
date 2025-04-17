import streamlit as st

# 📌 set_page_config debe ser la primera llamada
st.set_page_config(page_title='Consenso Expertos', page_icon='🎯', layout='wide')

import pandas as pd
import plotly.express as px
import uuid
import qrcode
import io
from datetime import datetime
import openai

# ----------------------------------------
# CONFIGURACIÓN BASE_URL (para QR accesible desde cualquier móvil)
# Define en .streamlit/secrets.toml:
# BASE_URL = "https://tu-dominio-o-streamlit-app"
BASE_URL = st.secrets.get("BASE_URL", "http://localhost:8501")

# ----------------------------------------
# PALETA Y CSS GLOBAL
# ----------------------------------------
PRIMARY = "#6C63FF"
SECONDARY = "#FF9900"
BACKGROUND = "#F5F5F5"
CARD_BG = "#FFFFFF"
TEXT = "#333333"
FONT_FAMILY = "'Segoe UI', Tahoma, Geneva, Verdana, sans-serif"

st.markdown(f"""
<style>
  /* Tipografía global */
  html, body, [class*="css"]  {{ font-family: {FONT_FAMILY}; background-color: {BACKGROUND}; color: {TEXT}; }}
  /* Header gradient */
  .app-header {{
    background: linear-gradient(90deg, {PRIMARY}, {SECONDARY});
    padding: 1rem 2rem;
    border-radius: 0 0 12px 12px;
    color: white;
    font-size: 2.2rem;
    text-align: center;
    font-weight: bold;
  }}
  /* Tarjetas métricas */
  .metric-card {{
    background: {CARD_BG};
    border-radius: 8px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.1);
    padding: 1rem;
    margin-bottom: 1rem;
  }}
  /* Botones grandes */
  .stButton>button {{
    background-color: {PRIMARY} !important;
    color: white !important;
    padding: 0.6rem 1.2rem !important;
    font-size: 1rem !important;
    border-radius: 6px !important;
    margin: 0.5rem 0;
  }}
  /* Inputs estilizados */
  input, textarea {{
    border-radius: 6px !important;
    padding: 0.5rem !important;
  }}
</style>
""", unsafe_allow_html=True)

# ----------------------------------------
# ALMACENAMIENTO (cache resource)
# ----------------------------------------
@st.cache_resource
def get_data_store():
    return {'sessions': {}}

# ----------------------------------------
# FUNCIONES AUXILIARES
# ----------------------------------------
def generate_session_code():
    return uuid.uuid4().hex[:6].upper()


def create_new_session(item_name: str, scale_type: str) -> str:
    store = get_data_store()
    code = generate_session_code()
    store['sessions'][code] = {
        'items': [{'name': item_name, 'scale': scale_type}],
        'current_index': 0,
        'votes': [],
        'comments': [],
        'settings': {'consensus_threshold': 0.8}
    }
    return code


def get_current_item(session: dict) -> dict:
    return session['items'][session['current_index']]


def record_vote(code: str, vote, comment: str):
    sess = get_data_store()['sessions'][code]
    sess['votes'].append(vote)
    sess['comments'].append(comment)


def compute_consensus(session: dict) -> float:
    votes = session['votes']
    if not votes:
        return 0.0
    item = get_current_item(session)
    if 'Likert' in item['scale']:
        count = sum(1 for v in votes if isinstance(v, int) and v >= 7)
    else:
        count = votes.count('Yes')
    return count / len(votes)


def generate_qr_code(code: str) -> bytes:
    url = f"{BASE_URL}?session={code}"
    img = qrcode.make(url)
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return buf.getvalue()


def export_to_excel(code: str) -> str:
    session = get_data_store()['sessions'][code]
    df = pd.DataFrame({
        'item': get_current_item(session)['name'],
        'vote': session['votes'],
        'comment': session['comments']
    })
    consensus_pct = compute_consensus(session)
    df['consensus'] = ['Yes' if consensus_pct >= session['settings']['consensus_threshold'] else 'No'] * len(df)
    fname = f'results_{code}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
    df.to_excel(fname, index=False)
    return fname


def summarize_comments(comments: list) -> str:
    if 'OPENAI_API_KEY' in st.secrets:
        openai.api_key = st.secrets['OPENAI_API_KEY']
        prompt = "Resume brevemente estos comentarios de expertos de salud:\n" + "\n".join(comments)
        resp = openai.ChatCompletion.create(
            model='gpt-4o-mini',
            messages=[{'role':'user','content': prompt}]
        )
        return resp.choices[0].message.content
    return "OpenAI API key no configurada."

# ----------------------------------------
# PÁGINAS
# ----------------------------------------
def page_start():
    st.markdown("<div class='app-header'>⚖️ Consenso Expertos</div>", unsafe_allow_html=True)
    st.markdown("<h3 style='text-align:center; color:{PRIMARY};'>Odds Epidemiology</h3>", unsafe_allow_html=True)
    with st.form("form_start", clear_on_submit=True):
        item = st.text_input("Ítem de votación:")
        scale = st.selectbox("Escala:", ['Likert 1-9', 'Sí/No'])
        submitted = st.form_submit_button("Crear votación")
        if submitted:
            if not item:
                st.error("Debe indicar el ítem.")
            else:
                code = create_new_session(item, scale)
                st.success(f"Sesión creada: **{code}**")
                st.image(generate_qr_code(code), width=160, caption="Escanea para votar")


def page_vote():
    st.header("🗳️ Votación Expertos")
    params = st.experimental_get_query_params()
    code = params.get('session', [None])[0] or st.text_input("Código de sesión:")
    sessions = get_data_store()['sessions']
    if code and code in sessions:
        session = sessions[code]
        st.info(f"Votando en sesión: **{code}**")
        item = get_current_item(session)
        st.subheader(item['name'])
        vote = st.slider("Tu voto:", 1, 9, 5) if 'Likert' in item['scale'] else st.radio("Tu voto:", ['Yes', 'No'])
        comment = st.text_area("Comentario (opcional):")
        if st.button("Enviar"): record_vote(code, vote, comment); st.balloons(); st.success("Gracias por tu voto.")
    else:
        st.warning("Código inexistente o vacío.")


def page_dashboard():
    st.header("📊 Dashboard Moderador")
    code = st.text_input("Código de sesión:")
    sessions = get_data_store()['sessions']
    if code and code in sessions:
        session = sessions[code]
        votes, comments = session['votes'], session['comments']
        col1, col2 = st.columns([2,1])
        with col1:
            st.markdown("<div class='metric-card'><h4>Votos recibidos</h4><p style='font-size:2rem;'>{}</p></div>".format(len(votes)), unsafe_allow_html=True)
            pct = compute_consensus(session)
            st.markdown("<div class='metric-card'><h4>% Consenso</h4><p style='font-size:2rem;'>{:.1f}%</p></div>".format(pct*100), unsafe_allow_html=True)
        with col2:
            if st.button("Cerrar votación"): del sessions[code]; st.warning("Sesión cerrada.")
            if st.button("Siguiente ítem"): session['current_index']+=1; st.experimental_rerun()
            if st.button("Exportar Excel"): fname=export_to_excel(code); st.success(f"Guardado: {fname}")
        if votes:
            df = pd.DataFrame({'vote': votes})
            fig = px.histogram(df, x='vote', nbins=9 if 'Likert' in get_current_item(session)['scale'] else 2)
            fig.update_layout(plot_bgcolor=BACKGROUND, colorway=[PRIMARY, SECONDARY])
            st.plotly_chart(fig, use_container_width=True)
        if comments:
            st.subheader("Comentarios recibidos")
            for c in comments: st.write(f"- {c}")
            st.subheader("Resumen")
            st.write(summarize_comments(comments))
    else:
        st.info("Introduce un código válido.")

# ----------------------------------------
# NAVEGACIÓN LATERAL
# ----------------------------------------
pages = {'Inicio': page_start, 'Votar': page_vote, 'Dashboard': page_dashboard}
st.sidebar.title("Navegación")
choice = st.sidebar.radio("", list(pages.keys()))
pages[choice]()
