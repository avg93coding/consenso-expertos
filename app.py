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
from scipy import stats

# 1) Configuración de la página
st.set_page_config(
    page_title="ODDS Epidemiology - Dashboard de Consenso",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# 2) Almacenamiento persistente utilizando session_state
# Esto asegura que las sesiones persistan incluso cuando Streamlit se reinicia
if "sessions" not in st.session_state:
    st.session_state.sessions = {}
if "history" not in st.session_state:
    st.session_state.history = {}

# 3) Utilidades
def make_session(desc: str, scale: str) -> str:
    code = uuid.uuid4().hex[:6].upper()
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    session_data = {
        "desc": desc, 
        "scale": scale, 
        "votes": [], 
        "comments": [], 
        "ids": [], 
        "names": [],
        "created_at": timestamp,
        "round": 1
    }
    
    st.session_state.sessions[code] = session_data
    # Inicializar historial para esta sesión
    st.session_state.history[code] = [session_data.copy()]
    return code

def hash_id(name: str) -> str:
    return hashlib.sha256(name.encode()).hexdigest()[:8]

def record_vote(code: str, vote, comment: str, name: str):
    if code not in st.session_state.sessions:
        return None
    
    s = st.session_state.sessions[code]
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
    # Intenta obtener la URL base desde secretos o usa un valor predeterminado
    try:
        return st.secrets.get("BASE_URL", "http://localhost:8501")
    except:
        return "http://localhost:8501"  # URL predeterminada si no hay secretos

def create_qr_code_url(code: str):
    base_url = get_base_url()
    # Asegura que la URL sea absoluta y tenga el formato correcto
    if not base_url.startswith(('http://', 'https://')):
        base_url = f"http://{base_url}"
    # Usa la estructura correcta para parámetros de URL
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
    if code not in st.session_state.sessions:
        return io.BytesIO()
    
    s = st.session_state.sessions[code]
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
    if code in st.session_state.history:
        for past_round in st.session_state.history[code][:-1]:  # Excluir la ronda actual
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
    if code not in st.session_state.sessions:
        return "Sesión inválida"
    
    s = st.session_state.sessions[code]
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
    if code in st.session_state.history and len(st.session_state.history[code]) > 1:
        report += "\nHISTORIAL DE RONDAS ANTERIORES:\n"
        for i, past_round in enumerate(st.session_state.history[code][:-1]):
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
        <div class="odds-subtitle">Sistema de Votación por Consenso</div>
    </div>
    """
    st.markdown(header_html, unsafe_allow_html=True)

# Aplicar estilos
inject_css()

# 5) Página de votación solo si ?session=
params = st.query_params
if "session" in params:
    code = params["session"][0]
    odds_header()
    
    st.markdown('<div class="hide-sidebar">', unsafe_allow_html=True)
    st.markdown('<div class="card">', unsafe_allow_html=True)
    
    if code not in st.session_state.sessions:
        st.error(f"Sesión inválida o expirada: '{code}'")
        st.info("Por favor, contacte al administrador para obtener un nuevo código de sesión.")
        # Añadir un botón para depuración
        if st.button("Ver sesiones disponibles"):
            st.write("Sesiones activas:", list(st.session_state.sessions.keys()))
        st.stop()
    
    s = st.session_state.sessions[code]
    
    st.subheader(f"Panel de Votación - Ronda {s['round']}")
    st.markdown(f'<div class="session-badge">Sesión: {code}</div>', unsafe_allow_html=True)
    
    name = st.text_input("Nombre del participante:")
    
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
                pct = int(consensus_pct(s["votes"]) * 100)
                st.success(f"Voto registrado correctamente.")
                st.markdown(f"**ID de su voto:** {pid}")
                st.markdown(f"**Consenso actual:** {pct}%")
                st.progress(pct/100)
                
                # Estatus actual del consenso
                if pct >= 80:
                    st.success("El grupo está alcanzando consenso.")
                elif pct >= 50:
                    st.info("El grupo está progresando hacia un consenso.")
                else:
                    st.warning("Aún no hay consenso en el grupo.")
            else:
                st.error("Error al registrar el voto. La sesión puede haber expirado.")
    
    st.markdown("</div>", unsafe_allow_html=True)
    st.stop()

# 6) Panel de administración
odds_header()

st.sidebar.title("Panel de Control")
st.sidebar.markdown("### ODDS Epidemiology")
menu = st.sidebar.radio("Navegación", ["Inicio", "Crear Sesión", "Dashboard", "Historial"])

if menu == "Inicio":
    st.markdown("## Bienvenido al Sistema de Consenso de ODDS Epidemiology")
    
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
    
    if st.session_state.sessions:
        st.subheader("Sesiones Activas")
        for code, session in st.session_state.sessions.items():
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
        
        st.markdown("""
        <div class="helper-text">
        La escala Likert 1-9 permite evaluar el grado de acuerdo donde:
        - 1-3: Desacuerdo
        - 4-6: Neutral
        - 7-9: Acuerdo
        
        Se considera consenso cuando ≥80% de los votos son ≥7.
        </div>
        """, unsafe_allow_html=True)
        
        if st.form_submit_button("Crear sesión"):
            if desc:
                code = make_session(desc, scale)
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
                    # Usar HTML embebido para el QR con la URL visible
                    st.markdown(get_qr_code_image_html(code), unsafe_allow_html=True)
                
                st.info(f"URL para compartir: {create_qr_code_url(code)}")
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
    
    if not st.session_state.sessions:
        st.info("No hay sesiones activas. Cree una nueva sesión para comenzar.")
    else:
        code = st.selectbox("Seleccionar sesión activa:", list(st.session_state.sessions.keys()))
        
        if code:
            s = st.session_state.sessions[code]
            votes, comments, ids = s["votes"], s["comments"], s["ids"]
            
            st.markdown(f"""
            <div class="card">
                <strong>Recomendación:</strong> {s["desc"]}<br>
                <strong>Ronda actual:</strong> {s["round"]}<br>
                <strong>Creada:</strong> {s["created_at"]}
            </div>
            """, unsafe_allow_html=True)
            
            # Link para votación 
            st.markdown(f"""
            <div class="card">
                <h4>Enlace para votantes</h4>
                <p>Comparta este enlace o el código QR para que los participantes voten:</p>
                <code>{create_qr_code_url(code)}</code>
                {get_qr_code_image_html(code)}
            </div>
            """, unsafe_allow_html=True)
            
            # Métricas principales
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
            
            # Estado del consenso
            st.markdown('<div class="card">', unsafe_allow_html=True)
            if votes:
                if pct >= 80 and lo >= 7:
                    st.success("✅ CONSENSO ALCANZADO: Se aprueba la recomendación.")
                elif pct >= 80 and hi <= 3:
                    st.error("❌ CONSENSO ALCANZADO: No se aprueba la recomendación.")
                else:
                    st.warning("⚠️ CONSENSO NO ALCANZADO: Se recomienda realizar otra ronda.")
                    
                    # Opción para iniciar nueva ronda
                    if st.button("Iniciar nueva ronda"):
                        st.session_state["modify_recommendation"] = True
                        st.session_state["current_code"] = code
            
            # UI para modificar la recomendación y crear nueva ronda
            if st.session_state.get("modify_recommendation", False) and st.session_state.get("current_code") == code:
                with st.form("new_round_form"):
                    new_desc = st.text_area("Modificar recomendación:", value=s["desc"])
                    if st.form_submit_button("Iniciar nueva ronda de votación"):
                        # Guardar la ronda actual en el historial
                        if code in st.session_state.history:
                            st.session_state.history[code].append(s.copy())
                        
                        # Crear nueva ronda
                        st.session_state.sessions[code].update({
                            "desc": new_desc,
                            "votes": [],
                            "comments": [],
                            "ids": [],
                            "names": [],
                            "created_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "round": s["round"] + 1
                        })
                        
                        st.success(f"Nueva ronda iniciada. Ronda actual: {s['round'] + 1}")
                        st.session_state["modify_recommendation"] = False
                        st.experimental_rerun()
            st.markdown("</div>", unsafe_allow_html=True)
            
            # Visualización de resultados
            st.markdown('<div class="card">', unsafe_allow_html=True)
            st.subheader("Resultados")
            
            if votes:
                # Crear DataFrame para gráficos
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
                    # Para escala Sí/No
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
            else:
                st.info("No hay votos registrados para esta sesión.")
            st.markdown("</div>", unsafe_allow_html=True)
            
            # Exportar datos
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
                    "Descargar Reporte", 
                    create_report(code), 
                    file_name=f"reporte_{code}_ronda{s['round']}.txt",
                    help="Genera un reporte detallado con métricas y comentarios"
                )
            st.markdown("</div>", unsafe_allow_html=True)
            
            # Comentarios
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
    
    if not st.session_state.history:
        st.info("No hay historial de sesiones disponible.")
    else:
        code = st.selectbox("Seleccionar sesión:", list(st.session_state.history.keys()))
        
        if code and code in st.session_state.history:
            history = st.session_state.history[code]
            
            st.markdown('<div class="card">', unsafe_allow_html=True)
            st.write(f"Total de rondas: {len(history)}")
            
            for i, round_data in enumerate(history):
                with st.expander(f"Ronda {round_data['round']} - {round_data['created_at']}"):
                    st.write(f"**Recomendación:** {round_data['desc']}")
                    st.write(f"**Votos totales:** {len(round_data['votes'])}")
                    
                    pct = consensus_pct(round_data['votes']) * 100
                    st.write(f"**% Consenso:** {pct:.1f}%")
                    
                    if round_data['votes']:
                        med, lo, hi = median_ci(round_data['votes'])
                        st.write(f"**Mediana (IC 95%):** {med:.1f} [{lo:.1f}, {hi:.1f}]")
                        
                        # Estado del consenso
                        if pct >= 80 and lo >= 7:
                            st.success("CONSENSO: Se aprobó la recomendación.")
                        elif pct >= 80 and hi <= 3:
                            st.error("CONSENSO: No se aprobó la recomendación.")
                        else:
                            st.warning("No se alcanzó consenso en esta ronda.")
                    
                    # Mostrar los comentarios de esta ronda
                    if round_data['comments']:
                        st.subheader("Comentarios")
                        for pid, name, vote, comment in zip(round_data['ids'], round_data['names'], round_data['votes'], round_data['comments']):
                            if comment:
                                st.markdown(f"**{name} (ID: {pid})** - Voto: {vote}\n>{comment}")
            st.markdown("</div>", unsafe_allow_html=True)
