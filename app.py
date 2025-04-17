import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import uuid
import qrcode
import io
import hashlib
import datetime
import base64
import copy
import os
from scipy import stats
from streamlit_autorefresh import st_autorefresh


# 1) Configuración de la página
st.set_page_config(
    page_title="ODDS Epidemiology - Dashboard Consenso de expertos",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# 2) Almacenamiento persistente utilizando session_state
# Esto asegura que las sesiones persistan incluso cuando Streamlit se reinicia
# Diccionario compartido en todo el servidor
@st.cache_resource
def get_store():
    return {}

store = get_store()
# Historia en memoria:
history = {}


# 3) Utilidades
def make_session(desc: str, scale: str) -> str:
    code = uuid.uuid4().hex[:6].upper()
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    store[code] = {
        "desc": desc,
        "scale": scale,
        "votes": [],
        "comments": [],
        "ids": [],
        "names": [],
        "created_at": timestamp,
        "round": 1
    }
    history[code] = []  # inicializamos el historial
    return code


def hash_id(name: str) -> str:
    return hashlib.sha256(name.encode()).hexdigest()[:8]

def record_vote(code: str, vote, comment: str, name: str):
    if code not in store:
        return None
    
    s = store[code]
    pid = hash_id(name or str(uuid.uuid4()))
    
    # Evitar votos duplicados por nombre
    if name and name in s["names"]:
        idx = s["names"].index(name)
        s["votes"][idx] = vote
        s["comments"][idx] = comment
        return pid
    
    s["votes"].append(vote)
    s["comments"].append(comment)
    s["ids"].append(pid)
    s["names"].append(name)
    return pid

def consensus_pct(votes):
    int_votes = [v for v in votes if isinstance(v, (int, float))]
    if not int_votes:
        return 0.0
    return sum(1 for v in int_votes if v >= 7) / len(int_votes)

def median_ci(votes):
    if not votes:
        return 0, 0, 0
    arr = np.array([v for v in votes if isinstance(v, (int, float))])
    if len(arr) == 0:
        return 0, 0, 0
    med = np.median(arr)
    res = stats.bootstrap((arr,), np.median, confidence_level=0.95, n_resamples=1000)
    return med, res.confidence_interval.low, res.confidence_interval.high

def get_base_url():
    # URL específica para aplicación en Streamlit Cloud
    return "https://consenso-expertos-sfpqj688ihbl7m6tgrdmwb.streamlit.app"

def create_qr_code_url(code: str):
    base_url = get_base_url()
    # Elimina slashes finales para evitar doble slash
    base_url = base_url.rstrip('/')
    # Construye URL correctamente
    return f"{base_url}/?session={code}"

def make_qr(code: str) -> io.BytesIO:
    url = create_qr_code_url(code)
    
    buf = io.BytesIO()
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,  # Nivel más alto de corrección de errores
        box_size=10,
        border=4,
    )
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf

def get_qr_code_image_html(code):
    buf = make_qr(code)
    img_str = base64.b64encode(buf.getvalue()).decode("utf-8")
    url = create_qr_code_url(code)
    html = f"""
    <div style="text-align: center; margin-bottom: 20px;">
        <img src="data:image/png;base64,{img_str}" width="200">
        <p style="margin-top: 10px; font-size: 0.8rem;">URL: <a href="{url}" target="_blank">{url}</a></p>
    </div>
    """
    return html

def to_excel(code: str) -> io.BytesIO:
    if code not in store:
        return io.BytesIO()
    
    s = store[code]
    df = pd.DataFrame({
        "ID anónimo": s["ids"],
        "Nombre real": s["names"],
        "Recomendación": [s["desc"]] * len(s["ids"]),
        "Ronda": [s["round"]] * len(s["ids"]),
        "Voto": s["votes"],
        "Comentario": s["comments"],
        "Fecha": [s["created_at"]] * len(s["ids"])
    })
    
    # Añadir datos de rondas anteriores del historial
    if code in history:
        for past_round in history[code]:  # Todas las rondas pasadas
            hist_df = pd.DataFrame({
                "ID anónimo": past_round["ids"],
                "Nombre real": past_round["names"],
                "Recomendación": [past_round["desc"]] * len(past_round["ids"]),
                "Ronda": [past_round["round"]] * len(past_round["ids"]),
                "Voto": past_round["votes"],
                "Comentario": past_round["comments"],
                "Fecha": [past_round["created_at"]] * len(past_round["ids"])
            })
            df = pd.concat([df, hist_df])
    
    pct = consensus_pct(s["votes"])
    df["Consenso"] = ["Sí" if pct >= 0.8 else "No"] * len(df)
    
    buf = io.BytesIO()
    df.to_excel(buf, index=False)
    buf.seek(0)
    return buf

def create_report(code: str) -> str:
    if code not in store:
        return "Sesión inválida"
    
    s = store[code]
    pct = consensus_pct(s["votes"]) * 100
    med, lo, hi = median_ci(s["votes"])
    
    report = f"""REPORTE DE CONSENSO - ODDS EPIDEMIOLOGY
Código de sesión: {code}
Fecha: {s["created_at"]}
Ronda: {s['round']}
Recomendación: {s["desc"]}
    
MÉTRICAS:
- Votos totales: {len(s["votes"])}
- Porcentaje de consenso: {pct:.1f}%
- Mediana (IC 95%): {med:.1f} [{lo:.1f}, {hi:.1f}]
- Resultado: {"APROBADO" if pct >= 80 and lo >= 7 else "NO APROBADO" if pct >= 80 and hi <= 3 else "REQUIERE SEGUNDA RONDA"}

COMENTARIOS:
"""
    for i, (pid, comment) in enumerate(zip(s["ids"], s["comments"])):
        if comment:
            report += f"{i+1}. {pid}: {comment}\n"
    
    # Añadir historial de rondas anteriores
    if code in history and len(history[code]) > 0:
        report += "\nHISTORIAL DE RONDAS ANTERIORES:\n"
        for i, past_round in enumerate(history[code]):
            round_pct = consensus_pct(past_round["votes"]) * 100
            report += f"\nRonda {past_round['round']} - {past_round['created_at']}\n"
            report += f"Recomendación: {past_round['desc']}\n"
            report += f"Consenso: {round_pct:.1f}%\n"
    
    return report

# 4) CSS y estilo visual para ODDS Epidemiology
def inject_css():
    ACCENT = "#006B7F"  # Color principal ODDS (azul oscuro)
    SECONDARY = "#3BAFDA"  # Color secundario (azul claro)
    BG = "#FFFFFF"
    CARD_BG = "#F8F8F8"
    TEXT = "#333333"
    FONT = "'Segoe UI', Tahoma, Verdana, sans-serif"
    
    css = f"""
    <style>
      .stApp {{background-color:{BG} !important; color:{TEXT}; font-family:{FONT};}}
      
      .app-header {{
        background-color:{ACCENT}; 
        padding:1.5rem; 
        border-radius:0 0 10px 10px; 
        text-align:center; 
        color:white; 
        margin-bottom: 20px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
      }}
      
      .odds-logo {{
        font-size: 2rem;
        font-weight: bold;
        letter-spacing: 1px;
        padding-bottom: 5px;
        border-bottom: 2px solid {SECONDARY};
        display: inline-block;
      }}
      
      .odds-subtitle {{
        font-size: 1.2rem;
        margin-top: 5px;
        opacity: 0.9;
      }}
      
      .card {{
        background-color: {CARD_BG};
        padding: 20px;
        border-radius: 10px;
        box-shadow: 0 2px 5px rgba(0,0,0,0.05);
        margin-bottom: 20px;
      }}
      
      .metric-card {{
        text-align: center;
        padding: 15px;
        background: linear-gradient(to bottom right, {ACCENT}, {SECONDARY});
        color: white;
        border-radius: 8px;
      }}
      
      .metric-value {{
        font-size: 1.8rem;
        font-weight: bold;
      }}
      
      .metric-label {{
        font-size: 0.9rem;
        opacity: 0.9;
      }}
      
      .stButton>button {{
        background-color: {ACCENT};
        color: white;
        border: none;
        padding: 0.5rem 1rem;
        border-radius: 5px;
      }}
      
      .stButton>button:hover {{
        background-color: {SECONDARY};
      }}
      
      .hide-sidebar [data-testid="stSidebar"], 
      .hide-sidebar [data-testid="stToolbar"] {{
        display: none;
      }}
      
      .session-badge {{
        display: inline-block;
        background-color: {SECONDARY};
        color: white;
        padding: 5px 10px;
        border-radius: 15px;
        font-weight: bold;
      }}
      
      /* Estilizar el slider de votación */
      div[data-testid="stSlider"] {{
        padding: 20px 0;
      }}
      
      /* Estilizar el texto de ayuda */
      .helper-text {{
        font-size: 0.9rem;
        color: #666;
        font-style: italic;
      }}
      
      /* QR code container */
      .qr-container {{
        text-align: center;
        padding: 15px;
        background-color: white;
        border-radius: 8px;
        box-shadow: 0 2px 5px rgba(0,0,0,0.05);
      }}
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)

def odds_header():
    header_html = """
    <div class="app-header">
        <div class="odds-logo">ODDS EPIDEMIOLOGY</div>
        <div class="odds-subtitle">Sistema de Votación</div>
    </div>
    """
    st.markdown(header_html, unsafe_allow_html=True)

# Aplicar estilos
inject_css()

# 5) Página de votación solo si ?session=
params = st.query_params
if "session" in params:
    try:
        code = params["session"][0] if isinstance(params.get("session"), list) else params.get("session")
        code = str(code).strip().upper()

        odds_header()
        st.markdown('<div class="hide-sidebar">', unsafe_allow_html=True)

        if code not in store:
            st.error(f"Sesión inválida o expirada: '{code}'")
            st.info("Por favor, contacte al administrador.")
            st.stop()

        s = store[code]
        st.subheader(f"Panel de Votación - Ronda {s['round']}")
        st.markdown(f'<div class="session-badge">Sesión: {code}</div>', unsafe_allow_html=True)

        name = st.text_input("Nombre del participante:")

        # Bloqueo si ya votó
        if name and name in s["names"]:
            st.balloons()
            st.success("✅ Gracias, su voto ya ha sido registrado.")
            st.markdown("Puede cerrar esta ventana. 🙌")
            st.stop()

        st.markdown('<div class="card">', unsafe_allow_html=True)

        st.markdown("### Recomendación a evaluar:")
        st.markdown(f"**{s['desc']}**")
        st.markdown('<div class="helper-text">Evalúe si está de acuerdo con la recomendación según la escala proporcionada.</div>', unsafe_allow_html=True)

        if s["scale"].startswith("Likert"):
            st.markdown("""
            **Escala de votación:**
            - 1-3: Desacuerdo
            - 4-6: Neutral
            - 7-9: Acuerdo
            """)
            vote = st.slider("Su voto:", 1, 9, 5)
        else:
            vote = st.radio("Su voto:", ["Sí", "No"])

        comment = st.text_area("Comentario o justificación (opcional):")

        if st.button("Enviar voto"):
            if not name:
                st.warning("Por favor, ingrese su nombre para registrar su voto.")
            else:
                pid = record_vote(code, vote, comment, name)
                if pid:
                    st.balloons()
                    st.success("🎉 Gracias por su participación.")
                    st.markdown(f"**ID de su voto:** `{pid}`")
                    st.markdown("Puede cerrar esta ventana. 🙏")
                    st.stop()
                else:
                    st.error("Error al registrar el voto. La sesión puede haber expirado.")

        st.markdown("</div>", unsafe_allow_html=True)
        st.stop()

    except Exception as e:
        st.error(f"Error al procesar la sesión: {str(e)}")
        st.info("Por favor, intente escanear el código QR nuevamente o contacte al administrador.")


# 6) Panel de administración
odds_header()

st.sidebar.title("Panel de Control")
st.sidebar.markdown("### ODDS Epidemiology")
menu = st.sidebar.radio("Navegación", ["Inicio", "Crear Sesión", "Dashboard", "Historial"])

if menu == "Inicio":
    st.markdown("## Bienvenido al Sistema de votación para Consenso de expertos de ODDS Epidemiology")
    
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown("""
    Esta herramienta le permite:
    - Crear sesiones de votación para recomendaciones
    - Monitorear resultados en tiempo real
    - Generar reportes detallados
    - Realizar múltiples rondas de votación
    
    Utilice el panel de navegación para comenzar.
    """)
    st.markdown("</div>", unsafe_allow_html=True)
    
    if store:
        st.subheader("Sesiones Activas")
        for code, session in store.items():
            st.markdown(f"""
            <div class="card">
                <strong>Código:</strong> {code} | 
                <strong>Creada:</strong> {session['created_at']} | 
                <strong>Ronda:</strong> {session['round']} | 
                <strong>Votos:</strong> {len(session['votes'])}
            </div>
            """, unsafe_allow_html=True)

elif menu == "Crear Sesión":
    st.subheader("Crear Nueva Sesión de Consenso")

    st.markdown('<div class="card">', unsafe_allow_html=True)
    with st.form("create_form", clear_on_submit=True):
        desc = st.text_area("Recomendación a evaluar:", height=100)
        scale = st.selectbox("Escala de votación:", ["Likert 1-9", "Sí/No"])
        n_participantes = st.number_input(
            "¿Cuántos participantes están habilitados para votar?", min_value=1, step=1)

        st.markdown("""
        <div class="helper-text">
        La escala Likert 1-9 permite evaluar el grado de acuerdo donde:
        - 1-3: Desacuerdo
        - 4-6: Neutral
        - 7-9: Acuerdo

        Se considera consenso cuando ≥80% de los votos son ≥7, y se ha alcanzado el quórum mínimo (mitad + 1 de los votantes esperados).
        </div>
        """, unsafe_allow_html=True)

        if st.form_submit_button("Crear sesión"):
            if desc:
                code = uuid.uuid4().hex[:6].upper()
                timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                store[code] = {
                    "desc": desc,
                    "scale": scale,
                    "votes": [],
                    "comments": [],
                    "ids": [],
                    "names": [],
                    "created_at": timestamp,
                    "round": 1,
                    "is_active": True,
                    "n_participantes": int(n_participantes)
                }
                history[code] = []
                st.success(f"Sesión creada exitosamente")

                col1, col2 = st.columns(2)
                with col1:
                    st.markdown(f"""
                    <div class="metric-card">
                        <div class="metric-label">Código de sesión</div>
                        <div class="metric-value">{code}</div>
                    </div>
                    """, unsafe_allow_html=True)

                with col2:
                    st.markdown(get_qr_code_image_html(code), unsafe_allow_html=True)

                url = create_qr_code_url(code)
                st.info(f"URL para compartir: {url}")
                st.write(f"Para probar: [Abrir página de votación]({url})")
                st.markdown("""
                <div class="helper-text">
                <strong>Instrucciones:</strong> Comparta el código QR o la URL con los participantes. 
                La URL debe incluir el parámetro de sesión exactamente como se muestra arriba.
                </div>
                """, unsafe_allow_html=True)
            else:
                st.warning("Por favor, ingrese una recomendación.")
    st.markdown("</div>", unsafe_allow_html=True)


elif menu == "Dashboard":
    st.subheader("Dashboard en Tiempo Real")
    st_autorefresh(interval=5000, key="refresh_dashboard")

    active_sessions = [k for k, v in store.items() if v.get("is_active", True)]
    if not active_sessions:
        st.info("No hay sesiones activas. Cree una nueva sesión para comenzar.")
    else:
        code = st.selectbox("Seleccionar sesión activa:", active_sessions)

        if code:
            s = store[code]
            votes, comments, ids = s["votes"], s["comments"], s["ids"]

            if st.button("Finalizar esta sesión"):
                store[code]["is_active"] = False
                st.success("✅ La sesión ha sido finalizada. Ya no aceptará más votos.")
                st.rerun()

            quorum = s.get("n_participantes", 0) // 2 + 1
            votos_actuales = len(votes)

            st.markdown(f"""
            <div class="card">
                <strong>Recomendación:</strong> {s["desc"]}<br>
                <strong>Ronda actual:</strong> {s["round"]}<br>
                <strong>Creada:</strong> {s["created_at"]}<br>
                <strong>Votos esperados:</strong> {s.get("n_participantes", '?')} | 
                <strong>Quórum mínimo:</strong> {quorum}<br>
                <strong>Votos recibidos:</strong> {votos_actuales}
            </div>
            """, unsafe_allow_html=True)

            col1, col2, col3 = st.columns(3)
            with col1:
                st.markdown(f"""
                <div class="metric-card">
                    <div class="metric-label">Total votos</div>
                    <div class="metric-value">{len(votes)}</div>
                </div>
                """, unsafe_allow_html=True)

            pct = consensus_pct(votes) * 100
            with col2:
                st.markdown(f"""
                <div class="metric-card">
                    <div class="metric-label">% Consenso</div>
                    <div class="metric-value">{pct:.1f}%</div>
                </div>
                """, unsafe_allow_html=True)

            if votes:
                med, lo, hi = median_ci(votes)
                with col3:
                    st.markdown(f"""
                    <div class="metric-card">
                        <div class="metric-label">Mediana (IC 95%)</div>
                        <div class="metric-value">{med:.1f} [{lo:.1f}, {hi:.1f}]</div>
                    </div>
                    """, unsafe_allow_html=True)

            st.markdown('<div class="card">', unsafe_allow_html=True)
            if votos_actuales < quorum:
                st.info(f"🕒 Aún no se alcanza el quórum mínimo requerido de {quorum} votos.")
            else:
                if pct >= 80 and all([not np.isnan(lo), not np.isnan(hi), 7 <= med <= 9, 7 <= lo <= 9, 7 <= hi <= 9]):
                    st.success("✅ CONSENSO ALCANZADO: Se aprueba la recomendación (por mediana + IC95%).")
                elif pct >= 80:
                    st.success("✅ CONSENSO ALCANZADO: Se aprueba la recomendación (por porcentaje).")
                elif pct <= 20 and all([not np.isnan(lo), not np.isnan(hi), 1 <= med <= 3, 1 <= lo <= 3, 1 <= hi <= 3]):
                    st.error("❌ CONSENSO ALCANZADO: No se aprueba la recomendación (por mediana + IC95%).")
                elif votes.count(1) + votes.count(2) + votes.count(3) >= 0.8 * votos_actuales:
                    st.error("❌ CONSENSO ALCANZADO: No se aprueba la recomendación (por porcentaje).")
                else:
                    st.warning("⚠️ CONSENSO NO ALCANZADO: Se recomienda realizar otra ronda.")

                st.subheader("Administrar Rondas")
                if st.button("Iniciar nueva ronda"):
                    old_round = copy.deepcopy(s)
                    history.setdefault(code, []).append(old_round)
                    st.session_state["modify_recommendation"] = True
                    st.session_state["current_code"] = code

                if st.session_state.get("modify_recommendation", False) and st.session_state.get("current_code") == code:
                    with st.form("new_round_form"):
                        new_desc = st.text_area("Modificar recomendación:", value=s["desc"])
                        submit_button = st.form_submit_button("Confirmar nueva ronda")
                        if submit_button:
                            next_round = s["round"] + 1
                            store[code].update({
                                "desc": new_desc,
                                "votes": [],
                                "comments": [],
                                "ids": [],
                                "names": [],
                                "created_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                "round": next_round
                            })

                            st.success(f"✅ Nueva ronda iniciada: Ronda {next_round}")

                            st.markdown('<div class="card">', unsafe_allow_html=True)
                            st.subheader("Nuevo enlace de votación")
                            st.markdown(f"<code>{create_qr_code_url(code)}</code>", unsafe_allow_html=True)
                            st.markdown(get_qr_code_image_html(code), unsafe_allow_html=True)
                            st.markdown("</div>", unsafe_allow_html=True)

                            st.session_state["modify_recommendation"] = False
                            st.stop()

            st.markdown("</div>", unsafe_allow_html=True)

            if votes:
                st.markdown('<div class="card">', unsafe_allow_html=True)
                st.subheader("Resultados")

                if s["scale"].startswith("Likert"):
                    df = pd.DataFrame({"Voto": votes})
                    fig = px.histogram(
                        df,
                        x="Voto",
                        nbins=9,
                        title="Distribución de Votos",
                        color_discrete_sequence=["#006B7F"],
                        labels={"Voto": "Escala Likert (1-9)", "count": "Frecuencia"}
                    )
                    fig.update_layout(
                        xaxis=dict(tickmode='linear', tick0=1, dtick=1),
                        bargap=0.1,
                        plot_bgcolor='rgba(0,0,0,0)',
                        paper_bgcolor='rgba(0,0,0,0)',
                    )
                else:
                    counts = {"Sí": votes.count("Sí"), "No": votes.count("No")}
                    df = pd.DataFrame(list(counts.items()), columns=["Respuesta", "Conteo"])
                    fig = px.pie(
                        df,
                        values="Conteo",
                        names="Respuesta",
                        title="Distribución de Votos",
                        color_discrete_sequence=["#006B7F", "#3BAFDA"]
                    )

                st.plotly_chart(fig, use_container_width=True)
                st.markdown("</div>", unsafe_allow_html=True)

            st.markdown('<div class="card">', unsafe_allow_html=True)
            st.subheader("Exportar Datos")
            col1, col2 = st.columns(2)
            with col1:
                st.download_button(
                    "Descargar Excel Completo",
                    to_excel(code),
                    file_name=f"consenso_{code}_ronda{s['round']}.xlsx",
                    help="Descarga todos los datos de esta sesión incluyendo rondas anteriores"
                )
            with col2:
                st.download_button(
                    "Descargar Reporte Completo",
                    create_report(code),
                    file_name=f"reporte_completo_{code}_ronda{s['round']}.txt",
                    help="Genera un reporte detallado con métricas, comentarios e historial de todas las rondas"
                )
            st.markdown("</div>", unsafe_allow_html=True)

            if comments:
                st.markdown('<div class="card">', unsafe_allow_html=True)
                st.subheader("Comentarios de los participantes")
                for i, (pid, name, vote, com) in enumerate(zip(ids, s["names"], votes, comments)):
                    if com:
                        st.markdown(f"""
                        **Participante {name} (ID: {pid})** - Voto: {vote}
                        > {com}
                        """)
                st.markdown("</div>", unsafe_allow_html=True)

elif menu == "Historial":
    st.subheader("Historial de Sesiones")

    if not history:
        st.info("No hay historial de sesiones disponible.")
    else:
        code = st.selectbox("Seleccionar sesión:", list(history.keys()))

        if code and code in history:
            rounds_history = history[code]
            st.markdown('<div class="card">', unsafe_allow_html=True)
            st.write(f"Total de rondas: {len(rounds_history)}")

            for i, round_data in enumerate(rounds_history):
                with st.expander(f"Ronda {round_data['round']} - {round_data['created_at']}"):
                    st.write(f"**Recomendación:** {round_data['desc']}")
                    st.write(f"**Votos totales:** {len(round_data['votes'])}")
                    pct = consensus_pct(round_data['votes']) * 100
                    st.write(f"**% Consenso:** {pct:.1f}%")

                    if round_data['votes']:
                        med, lo, hi = median_ci(round_data['votes'])
                        st.write(f"**Mediana (IC 95%):** {med:.1f} [{lo:.1f}, {hi:.1f}]")

                        if pct >= 80 and lo >= 7:
                            st.success("CONSENSO: Se aprobó la recomendación.")
                        elif pct >= 80 and hi <= 3:
                            st.error("CONSENSO: No se aprobó la recomendación.")
                        else:
                            st.warning("No se alcanzó consenso en esta ronda.")

                    if round_data['comments']:
                        st.subheader("Comentarios")
                        for pid, name, vote, comment in zip(round_data['ids'], round_data['names'], round_data['votes'], round_data['comments']):
                            if comment:
                                st.markdown(f"**{name} (ID: {pid})** - Voto: {vote}\n>{comment}")

            st.markdown("</div>", unsafe_allow_html=True)

            st.download_button(
                "Descargar Historial Completo",
                to_excel(code),
                file_name=f"historial_completo_{code}.xlsx",
                help="Descarga todas las rondas de esta sesión en un solo archivo"
            )

            if len(rounds_history) > 1:
                st.markdown('<div class="card">', unsafe_allow_html=True)
                st.subheader("Evolución del Consenso")
                round_data_list = []
                for r in rounds_history:
                    pct = consensus_pct(r['votes']) * 100
                    med, _, _ = median_ci(r['votes'])
                    round_data_list.append({
                        "Ronda": r['round'],
                        "% Consenso": pct,
                        "Mediana": med if r['votes'] else 0
                    })
                round_df = pd.DataFrame(round_data_list)
                fig = px.line(
                    round_df,
                    x="Ronda",
                    y=["% Consenso", "Mediana"],
                    title="Evolución del Consenso por Ronda",
                    markers=True,
                    color_discrete_sequence=["#006B7F", "#3BAFDA"]
                )
                fig.update_layout(
                    xaxis=dict(tickmode='linear', tick0=1, dtick=1),
                    yaxis=dict(title="Valor"),
                    hovermode="x unified",
                    plot_bgcolor='rgba(0,0,0,0)',
                    paper_bgcolor='rgba(0,0,0,0)',
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
                )
                fig.add_shape(
                    type="line",
                    x0=0,
                    y0=80,
                    x1=len(rounds_history) + 1,
                    y1=80,
                    line=dict(color="#FF4B4B", width=2, dash="dash"),
                    name="Umbral de Consenso (80%)"
                )
                st.plotly_chart(fig, use_container_width=True)
                st.markdown("</div>", unsafe_allow_html=True)

                st.markdown('<div class="card">', unsafe_allow_html=True)
                st.subheader("Análisis Comparativo de Rondas")
                first_round = rounds_history[0]
                last_round = rounds_history[-1]
                first_pct = consensus_pct(first_round['votes']) * 100
                last_pct = consensus_pct(last_round['votes']) * 100
                st.write(f"**Cambio en % de consenso:** {first_pct:.1f}% → {last_pct:.1f}% ({last_pct - first_pct:+.1f}%)")
                if first_round['votes'] and last_round['votes']:
                    first_med, _, _ = median_ci(first_round['votes'])
                    last_med, _, _ = median_ci(last_round['votes'])
                    st.write(f"**Cambio en mediana:** {first_med:.1f} → {last_med:.1f} ({last_med - first_med:+.1f})")
                if last_pct >= 80:
                    st.success("Se alcanzó consenso al final del proceso.")
                else:
                    st.warning("No se alcanzó consenso a pesar de múltiples rondas.")
                st.markdown("</div>", unsafe_allow_html=True)


# Guardar y Cargar Estado - Administración
st.sidebar.markdown("---")
st.sidebar.subheader("Administración")

# Guardar estado
if st.sidebar.button("Guardar Estado"):
    try:
        state_data = {
            "sessions": copy.deepcopy(store),
            "history": copy.deepcopy(history)
        }
        state_b64 = base64.b64encode(str(state_data).encode()).decode()
        st.sidebar.markdown("### Datos de Respaldo")
        st.sidebar.code(state_b64, language=None)
        st.sidebar.download_button(
            label="Descargar Backup",
            data=state_b64,
            file_name=f"odds_backup_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
            help="Guarde este archivo para restaurar sus sesiones en el futuro"
        )
        st.sidebar.success("Estado guardado correctamente.")
    except Exception as e:
        st.sidebar.error(f"Error al guardar el estado: {str(e)}")

# Cargar estado
state_upload = st.sidebar.file_uploader("Cargar Estado", type=["txt"])
if state_upload is not None:
    try:
        content = state_upload.read().decode()
        decoded = base64.b64decode(content).decode()
        import ast
        state_data = ast.literal_eval(decoded)

        if "sessions" in state_data and "history" in state_data:
            store.clear()
            store.update(state_data["sessions"])
            history.clear()
            history.update(state_data["history"])
            st.sidebar.success("Estado restaurado correctamente.")
            st.rerun()
        else:
            st.sidebar.error("El archivo no contiene datos válidos.")
    except Exception as e:
        st.sidebar.error(f"Error al cargar el estado: {str(e)}")

# Créditos
st.sidebar.markdown("---")
st.sidebar.markdown("**ODDS Epidemiology**")
st.sidebar.markdown("v1.0.0 - 2025")
st.sidebar.markdown("© Todos los derechos reservados")
