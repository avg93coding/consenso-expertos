import streamlit as st

# 📌 PRIMERA llamada a Streamlit
st.set_page_config(
    page_title='Odds Expert Consensus',
    page_icon='🎯',
    layout='wide',
    initial_sidebar_state='expanded'
)

import pandas as pd
import plotly.express as px
import uuid
import qrcode
import io
from datetime import datetime
import openai

# ----------------------------------------
# URL BASE PARA QR
BASE_URL = st.secrets.get("BASE_URL", "http://localhost:8501")

# ----------------------------------------
# PALETA OSCURA
DARK_BG = "#1e1e2f"
CARD_BG = "#2d0c5e"
ACCENT = "#6C63FF"
TEXT_COLOR = "#FFFFFF"
FONT = "'Segoe UI', Tahoma, Geneva, Verdana, sans-serif"

# ----------------------------------------
# CSS GLOBAL (modo oscuro)
CSS = f"""
<style>
  html, body, [class*="css"] {{
    background-color: {DARK_BG} !important;
    color: {TEXT_COLOR} !important;
    font-family: {FONT} !important;
  }}
  .app-header {{
    background: {ACCENT};
    padding: 2rem;
    border-radius: 0 0 15px 15px;
    text-align: center;
    color: {TEXT_COLOR};
    font-size: 2.5rem;
    font-weight: bold;
  }}
  .metric-card {{
    background: {CARD_BG} !important;
    border-radius: 12px;
    box-shadow: 0 6px 20px rgba(0,0,0,0.5);
    padding: 1.2rem 1.8rem;
    margin-bottom: 1.2rem;
    transition: transform 0.2s;
  }}
  .metric-card:hover {{
    transform: translateY(-4px);
    box-shadow: 0 8px 30px rgba(0,0,0,0.7);
  }}
  .stButton>button {{
    background-color: {ACCENT} !important;
    color: {TEXT_COLOR} !important;
    padding: 0.9rem 1.8rem !important;
    font-size: 1.1rem !important;
    border-radius: 10px !important;
    transition: background 0.2s;
  }}
  .stButton>button:hover {{
    background-color: {CARD_BG} !important;
  }}
  input, textarea {{
    background-color: {CARD_BG} !important;
    color: {TEXT_COLOR} !important;
    border-radius: 6px !important;
    padding: 0.5rem !important;
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
        'Item': get_current_item(session)['name'],
        'Vote': session['votes'],
        'Comment': session['comments']
    })
    consensus_pct = compute_consensus(session)
    df['Consensus'] = ['Yes' if consensus_pct >= session['settings']['consensus_threshold'] else 'No'] * len(df)
    fname = f"results_{code}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    df.to_excel(fname, index=False)
    return fname


def summarize_comments(comments: list) -> str:
    if 'OPENAI_API_KEY' in st.secrets:
        openai.api_key = st.secrets['OPENAI_API_KEY']
        prompt = "Summarize these expert comments briefly:\n" + "\n".join(comments)
        resp = openai.ChatCompletion.create(
            model='gpt-4o-mini',
            messages=[{'role': 'user', 'content': prompt}]
        )
        return resp.choices[0].message.content
    return "OpenAI API key not configured."

# ----------------------------------------
# VOTACIÓN DEDICADA
params = st.query_params
if 'session' in params:
    st.markdown('<div class="hide-sidebar">', unsafe_allow_html=True)
    code = params['session'][0]
    st.markdown("<div class='app-header'>Expert Voting</div>", unsafe_allow_html=True)
    sessions = get_data_store()['sessions']
    if code in sessions:
        session = sessions[code]
        item = get_current_item(session)
        st.subheader(item['name'], anchor=False)
        vote = st.slider("Your vote:", 1, 9, 5) if 'Likert' in item['scale'] else st.radio("Your vote:", ['Yes', 'No'])
        if st.button("Submit Vote"):
            record_vote(code, vote, '')
            st.progress(int(compute_consensus(session) * 100))
            st.success("Thank you for voting!")
    else:
        st.error("Invalid session code.")
    st.stop()

# ----------------------------------------
# PÁGINAS DE ADMIN

def page_start():
    st.markdown("<div class='app-header'>Consensus Dashboard</div>", unsafe_allow_html=True)
    st.markdown(f"<h3 style='text-align:center; color:{ACCENT};'>Odds Epidemiology</h3>", unsafe_allow_html=True)
    with st.form("create_form", clear_on_submit=True):
        item = st.text_input("Voting Item:")
        scale = st.selectbox("Scale:", ['Likert 1-9', 'Yes/No'])
        submit = st.form_submit_button("Create Session")
        if submit and item:
            code = create_new_session(item, scale)
            st.success(f"Session code: {code}")
            st.image(generate_qr_code(code), width=180)


def page_dashboard():
    st.header("Admin Dashboard")
    code = st.text_input("Session Code:")
    sessions = get_data_store()['sessions']
    if code in sessions:
        session = sessions[code]
        votes = session['votes']
        comments = session['comments']
        # Metrics cards
        c1, c2 = st.columns(2)
        with c1:
            st.markdown(f"<div class='metric-card'><h4>Total Votes</h4><p style='font-size:2rem;'>{len(votes)}</p></div>", unsafe_allow_html=True)
        with c2:
            pct = compute_consensus(session)
            st.markdown(f"<div class='metric-card'><h4>Consensus %</h4><p style='font-size:2rem;'>{pct*100:.1f}%</p></div>", unsafe_allow_html=True)
        # Controls
        ctrl1, ctrl2, ctrl3 = st.columns(3)
        if ctrl1.button("End Session"):
            del sessions[code]
            st.warning("Session ended.")
        if ctrl2.button("Next Item"):
            session['current_index'] += 1
            st.experimental_rerun()
        if ctrl3.button("Export to Excel"):
            fname = export_to_excel(code)
            st.success(f"Saved: {fname}")
        # Chart
        if votes:
            df = pd.DataFrame({'Vote': votes})
            fig = px.histogram(df, x='Vote', nbins=9 if 'Likert' in get_current_item(session)['scale'] else 2)
            fig.update_layout(plot_bgcolor=DARK_BG, paper_bgcolor=DARK_BG, colorway=[ACCENT])
            st.plotly_chart(fig, use_container_width=True)
        # Comments
        if comments:
            st.subheader("Comments")
            for c in comments:
                st.write(f"- {c}")
            st.subheader("Comments Summary")
            st.write(summarize_comments(comments))
    else:
        st.info("Enter a valid session code.")

# ----------------------------------------
# NAVEGACIÓN LATERAL
pages = {'Home': page_start, 'Dashboard': page_dashboard}
st.sidebar.title("Admin Panel")
selection = st.sidebar.radio("", list(pages.keys()))
pages[selection]()
