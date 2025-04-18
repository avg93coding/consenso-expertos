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

import os
import docx
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL

# Crear carpeta para guardar datos si no existe
DATA_DIR = "registro_data"
os.makedirs(DATA_DIR, exist_ok=True)

# Función: cargar registros desde CSV
def cargar_registros(nombre):
    path = os.path.join(DATA_DIR, f"{nombre}.csv")
    if os.path.exists(path):
        return pd.read_csv(path).to_dict("records")
    return []

# Función: guardar registros en CSV
def guardar_registros(nombre, registros):
    df = pd.DataFrame(registros)
    df.to_csv(os.path.join(DATA_DIR, f"{nombre}.csv"), index=False)

# Inicializar en session_state
if "registro_conflicto" not in st.session_state:
    st.session_state["registro_conflicto"] = cargar_registros("registro_conflicto")

if "registro_confidencialidad" not in st.session_state:
    st.session_state["registro_confidencialidad"] = cargar_registros("registro_confidencialidad")

# Lógica si la URL tiene ?registro=...
params = st.query_params
if "registro" in params:
    tipo = params.get("registro")
    st.set_page_config(page_title="Registro de Expertos", layout="centered")

    if tipo == "conflicto":
        st.title("🔐 Registro: Declaración de Conflictos de Interés")
        with st.form("form_conflicto_externo"):
            nombre = st.text_input("Nombre completo")
            institucion = st.text_input("Institución o afiliación")
            cargo = st.text_input("Cargo profesional")
            participa_en = st.multiselect("¿Participa actualmente en alguno de los siguientes?", [
                "Industria farmacéutica", "Investigación patrocinada", "Consultoría médica", "Autoría de guías clínicas", "Otro", "Ninguno"])
            tiene_conflicto = st.radio("¿Tiene un posible conflicto que pueda influir en esta recomendación?", ["No", "Sí"])
            detalle_conflicto = st.text_area("Describa brevemente su conflicto") if tiene_conflicto == "Sí" else ""
            confirma = st.checkbox("Declaro que la información es verídica y completa", value=False)
            submit = st.form_submit_button("Enviar")

            if submit:
                if not nombre or not confirma:
                    st.warning("Debe completar todos los campos obligatorios y aceptar la declaración.")
                else:
                    nuevo = {
                        "id": str(uuid.uuid4())[:8],
                        "nombre": nombre,
                        "institucion": institucion,
                        "cargo": cargo,
                        "participa_en": "; ".join(participa_en),
                        "conflicto": tiene_conflicto,
                        "detalle": detalle_conflicto,
                        "fecha": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    }
                    st.session_state["registro_conflicto"].append(nuevo)
                    guardar_registros("registro_conflicto", st.session_state["registro_conflicto"])
                    st.success("✅ Registro enviado correctamente. Puede cerrar esta ventana.")
        st.stop()

    elif tipo == "confidencialidad":
        st.title("📄 Registro: Acuerdo de Confidencialidad")
        with st.form("form_confidencialidad_externo"):
            nombre = st.text_input("Nombre completo")
            acepta1 = st.checkbox("Me comprometo a mantener la confidencialidad del contenido discutido y votado.")
            acepta2 = st.checkbox("Entiendo que no tengo derechos de autor sobre los productos resultantes del consenso.")
            submit = st.form_submit_button("Aceptar y registrar")

            if submit:
                if not nombre or not (acepta1 and acepta2):
                    st.warning("Debe completar el formulario y aceptar todas las condiciones.")
                else:
                    nuevo = {
                        "id": str(uuid.uuid4())[:8],
                        "nombre": nombre,
                        "fecha": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "acepta": True
                    }
                    st.session_state["registro_confidencialidad"].append(nuevo)
                    guardar_registros("registro_confidencialidad", st.session_state["registro_confidencialidad"])
                    st.success("✅ Registro enviado correctamente. Puede cerrar esta ventana.")
        st.stop()



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

# Función para validar si un correo está autorizado para votar en una sesión privada
def correo_autorizado(correo: str, code: str) -> bool:
    if code in store:
        sesion = store[code]
        if sesion.get("privado", False):
            lista = sesion.get("correos_autorizados", [])
            return correo.lower().strip() in [c.lower().strip() for c in lista]
    return True

# Función para validar si un correo está autorizado para votar en una sesión privada
def correo_autorizado(correo: str, code: str) -> bool:
    if code in store:
        sesion = store[code]
        if sesion.get("privado", False):
            lista = sesion.get("correos_autorizados", [])
            return correo and correo.lower().strip() in [c.lower().strip() for c in lista]
    return True  # Si la sesión no es privada, siempre es autorizado

# Función para registrar el voto
def record_vote(code: str, vote, comment: str, name: str, correo: str = None):
    if code not in store:
        return None

    if not correo_autorizado(correo, code):
        return None

    s = store[code]
    pid = hashlib.sha256(name.encode()).hexdigest()[:8]

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


# Función para crear un documento Word a partir de los datos de una sesión
def crear_reporte_word(code, titulo_personalizado=None):
    if code not in store:
        return None
    
    # Crear un nuevo documento
    doc = docx.Document()
    
    # Estilos y configuración
    sections = doc.sections
    for section in sections:
        section.page_height = Cm(29.7)  # A4
        section.page_width = Cm(21.0)
        section.left_margin = Cm(2.5)
        section.right_margin = Cm(2.5)
        section.top_margin = Cm(2.5)
        section.bottom_margin = Cm(2.5)
    
    # Título del reporte
    titulo = doc.add_heading(level=0)
    if titulo_personalizado:
        titulo.add_run(f"{titulo_personalizado}").bold = True
    else:
        titulo.add_run("Reporte de Consenso de Expertos").bold = True
    titulo.alignment = WD_ALIGN_PARAGRAPH.CENTER
    
    # Información general
    doc.add_paragraph().add_run(f"Fecha de generación: {datetime.datetime.now().strftime('%d-%m-%Y %H:%M:%S')}").italic = True
    doc.add_paragraph().add_run(f"Código de sesión: {code}").bold = True
    
    # Añadir historial completo de la sesión
    todas_las_rondas = []
    
    # Añadir la sesión actual (si está activa)
    if code in store:
        todas_las_rondas.append(store[code])
    
    # Añadir rondas históricas
    if code in history:
        todas_las_rondas.extend(history[code])
    
    # Ordenar por número de ronda
    todas_las_rondas.sort(key=lambda x: x.get('round', 0))
    
    # Sección de resumen
    doc.add_heading("Resumen de la Sesión", level=1)
    resumen_paragraph = doc.add_paragraph()
    resumen_paragraph.add_run(f"Total de rondas realizadas: {len(todas_las_rondas)}\n")
    
    ultima_ronda = todas_las_rondas[-1] if todas_las_rondas else None
    if ultima_ronda:
        pct = consensus_pct(ultima_ronda['votes']) * 100
        estado = "APROBADO" if pct >= 80 else "NO APROBADO"
        resumen_paragraph.add_run(f"Estado final: {estado}\n")
        resumen_paragraph.add_run(f"Porcentaje final de consenso: {pct:.1f}%\n")
    
    # Crear tabla resumen de todas las rondas
    doc.add_heading("Vista General de Rondas", level=1)
    table = doc.add_table(rows=1, cols=5)
    table.style = 'Table Grid'
    hdr_cells = table.rows[0].cells
    hdr_cells[0].text = 'Nº Ronda'
    hdr_cells[1].text = 'Fecha'
    hdr_cells[2].text = 'Total Votantes'
    hdr_cells[3].text = '% Consenso'
    hdr_cells[4].text = 'Resultado'
    
    # Aplicar estilo al encabezado
    for cell in table.rows[0].cells:
        cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = cell.paragraphs[0].runs[0]
        run.bold = True
        run.font.size = Pt(11)
    
    # Añadir datos de cada ronda a la tabla resumen
    for ronda in todas_las_rondas:
        row_cells = table.add_row().cells
        row_cells[0].text = str(ronda.get('round', 'N/A'))
        row_cells[1].text = ronda.get('created_at', 'N/A')
        row_cells[2].text = str(len(ronda.get('votes', [])))
        
        pct = consensus_pct(ronda.get('votes', [])) * 100
        row_cells[3].text = f"{pct:.1f}%"
        
        estado = "APROBADO" if pct >= 80 else "NO APROBADO"
        row_cells[4].text = estado

        # Centrar contenido de la tabla
        for cell in row_cells:
            cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
    
    # Añadir sección detallada para cada ronda
    doc.add_heading("Detalle por Ronda", level=1)
    
    for i, ronda in enumerate(todas_las_rondas):
        doc.add_heading(f"Ronda {ronda.get('round', 'N/A')}", level=2)
        
        # Información de la ronda
        p = doc.add_paragraph()
        p.add_run("Recomendación evaluada: ").bold = True
        p.add_run(ronda.get('desc', 'N/A'))
        
        p = doc.add_paragraph()
        p.add_run("Fecha de votación: ").bold = True
        p.add_run(ronda.get('created_at', 'N/A'))
        
        p = doc.add_paragraph()
        p.add_run("Escala utilizada: ").bold = True
        p.add_run(ronda.get('scale', 'N/A'))
        
        # Resultados
        votes = ronda.get('votes', [])
        if votes:
            p = doc.add_paragraph()
            p.add_run("Resultados de la votación:").bold = True
            
            # Tabla de resultados
            if ronda.get('scale', '').startswith('Likert'):
                # Para escala Likert, muestra distribución por valor
                table = doc.add_table(rows=2, cols=9)
                table.style = 'Table Grid'
                
                # Encabezados (valores 1-9)
                for i in range(9):
                    table.rows[0].cells[i].text = str(i+1)
                    table.rows[0].cells[i].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
                    table.rows[0].cells[i].paragraphs[0].runs[0].bold = True
                
                # Conteo de votos por valor
                for i in range(9):
                    count = votes.count(i+1)
                    table.rows[1].cells[i].text = str(count)
                    table.rows[1].cells[i].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
            else:
                # Para Si/No
                table = doc.add_table(rows=2, cols=2)
                table.style = 'Table Grid'
                
                table.rows[0].cells[0].text = "Sí"
                table.rows[0].cells[1].text = "No"
                
                table.rows[1].cells[0].text = str(votes.count("Sí"))
                table.rows[1].cells[1].text = str(votes.count("No"))
                
                for row in table.rows:
                    for cell in row.cells:
                        cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
                        if row == table.rows[0]:
                            cell.paragraphs[0].runs[0].bold = True
            
            # Métricas
            p = doc.add_paragraph()
            p.add_run("\nMétricas de consenso:").bold = True
            
            # Lista de métricas
            pct = consensus_pct(votes) * 100
            med, lo, hi = median_ci(votes)
            
            metrics_list = doc.add_paragraph(style='List Bullet')
            metrics_list.add_run(f"Porcentaje de consenso: {pct:.1f}%")
            
            metrics_list = doc.add_paragraph(style='List Bullet')
            metrics_list.add_run(f"Mediana (IC 95%): {med:.1f} [{lo:.1f}, {hi:.1f}]")
            
            metrics_list = doc.add_paragraph(style='List Bullet')
            if pct >= 80:
                result_text = f"Resultado: APROBADO (consenso: {pct:.1f}%)"
                metrics_list.add_run(result_text)
            else:
                result_text = f"Resultado: NO APROBADO (consenso: {pct:.1f}%)"
                metrics_list.add_run(result_text)
            
            # Comentarios
            comments = ronda.get('comments', [])
            if any(comments):
                doc.add_heading("Comentarios de los participantes", level=3)
                
                for i, (pid, name, vote, comment) in enumerate(zip(ronda.get('ids', []), 
                                                                 ronda.get('names', []), 
                                                                 votes, 
                                                                 comments)):
                    if comment:
                        p = doc.add_paragraph(style='List Bullet')
                        p.add_run(f"Participante {name} (ID: {pid}) - Voto: {vote}\n").bold = True
                        p.add_run(comment)
        
        # Separador entre rondas
        if i < len(todas_las_rondas) - 1:
            doc.add_paragraph()
            doc.add_paragraph("---")
    
    # Pie de página
    section = doc.sections[0]
    footer = section.footer
    paragraph = footer.paragraphs[0]
    paragraph.text = f"Reporte generado por ODDS Epidemiology · {datetime.datetime.now().strftime('%d-%m-%Y')}"
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    
    # Guardar temporalmente y devolver el buffer
    file_buffer = io.BytesIO()
    doc.save(file_buffer)
    file_buffer.seek(0)
    
    return file_buffer

# Ahora añade una sección para integrar esta funcionalidad en el Dashboard
def integrar_seccion_word_report():
    # Esta función sería llamada desde el menú principal
    st.subheader("Generación de Reporte Word")
    
    st.markdown("""
    <div class="card">
    <p>Genere reportes profesionales en formato Word con detalles de todas las rondas de votación.</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Selección de sesión
    active_sessions = [k for k, v in store.items()]
    if not active_sessions:
        st.info("No hay sesiones disponibles para generar reportes.")
    else:
        code = st.selectbox("Seleccionar sesión:", active_sessions)
        
        if code:
            # Formulario para generar el reporte
            with st.form("reporte_word_form"):
                titulo_personalizado = st.text_input(
                    "Título personalizado para el reporte:", 
                    value=f"Reporte de Consenso - Sesión {code}"
                )
                
                submit = st.form_submit_button("Generar Reporte Word")
                
                if submit:
                    try:
                        # Generar el reporte Word
                        word_buffer = crear_reporte_word(code, titulo_personalizado)
                        
                        if word_buffer:
                            fecha_actual = datetime.datetime.now().strftime("%Y%m%d")
                            st.download_button(
                                label="⬇️ Descargar Reporte Word",
                                data=word_buffer,
                                file_name=f"reporte_consenso_{code}_{fecha_actual}.docx",
                                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                            )
                            st.success("✅ Reporte generado exitosamente.")
                        else:
                            st.error("No se pudo generar el reporte. La sesión puede no existir.")
                    except Exception as e:
                        st.error(f"Error al generar el reporte: {str(e)}")
                        st.error("Asegúrese de tener la biblioteca python-docx instalada: pip install python-docx")
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
    PRIMARY = "#662D91"    # Morado principal
    SECONDARY = "#F1592A"  # Naranja vibrante
    LIGHT_BG = "#F7F7F7"   # Fondo claro
    TEXT = "#333333"
    FONT = "'Segoe UI', Tahoma, Verdana, sans-serif"

    css = f"""
    <style>
      .stApp {{background-color:{LIGHT_BG} !important; color:{TEXT}; font-family:{FONT};}}

      .app-header {{
        background-color:{PRIMARY};
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

      .metric-card {{
        text-align: center;
        padding: 15px;
        background: linear-gradient(to bottom right, {PRIMARY}, {SECONDARY});
        color: white;
        border-radius: 8px;
      }}

      .metric-value {{
        font-size: 1.8rem;
        font-weight: bold;
      }}

      .stButton>button {{
        background-color: {PRIMARY};
        color: white;
        border: none;
        padding: 0.5rem 1rem;
        border-radius: 5px;
      }}

      .stButton>button:hover {{
        background-color: {SECONDARY};
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
        correo = st.text_input("Correo electrónico (obligatorio para sesiones privadas):")


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
                pid = record_vote(code, vote, comment, name, correo)
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
menu = st.sidebar.radio("Navegación", ["Inicio", "Crear Recomendación", "Dashboard",  "Registro Previo", "Generar Reporte"])

if menu == "Inicio":
    st.markdown("## Bienvenido al Sistema de votación para Consenso de expertos de ODDS Epidemiology")
    
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown("""
    
    
    Utilice el panel de navegación para comenzar.
    """)
    st.markdown("</div>", unsafe_allow_html=True)
    
    

elif menu == "Crear Recomendación":
    st.subheader("Crear Nueva Recomendación")

    st.markdown('<div class="card">', unsafe_allow_html=True)
    with st.form("create_form", clear_on_submit=True):
        nombre_ronda = st.text_input("Nombre de la ronda:")
        desc = st.text_area("Recomendación a evaluar:", height=100)
        scale = st.selectbox("Escala de votación:", ["Likert 1-9", "Sí/No"])
        n_participantes = st.number_input(
            "¿Cuántos participantes están habilitados para votar?", min_value=1, step=1)
        es_privada = st.checkbox("¿Esta recomendación será privada?")

        correos_autorizados = []
        archivo_correos = st.file_uploader("📧 Subir lista de correos autorizados (CSV con columna 'correo')", type=["csv"])
        if archivo_correos is not None:
            try:
                df_correos = pd.read_csv(archivo_correos)
                if 'correo' in df_correos.columns:
                    correos_autorizados = df_correos['correo'].astype(str).str.strip().tolist()
                    st.success(f"Se cargaron {len(correos_autorizados)} correos autorizados correctamente.")
                else:
                    st.error("El archivo debe contener una columna llamada 'correo'.")
            except Exception as e:
                st.error(f"Error al leer el archivo: {str(e)}")

        st.markdown("""
        <div class="helper-text">
        La escala Likert 1-9 permite evaluar el grado de acuerdo donde:
        - 1-3: Desacuerdo
        - 4-6: Neutral
        - 7-9: Acuerdo

        Se considera consenso cuando ≥80% de los votos son ≥7, y se ha alcanzado el quórum mínimo (mitad + 1 de los votantes esperados).
        </div>
        """, unsafe_allow_html=True)

        if st.form_submit_button("Crear Recomendación"):
            if desc:
                code = uuid.uuid4().hex[:6].upper()
                timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                descripcion_final = f"{desc} ({nombre_ronda})" if nombre_ronda else desc
                store[code] = {
                    "desc": descripcion_final,
                    "scale": scale,
                    "votes": [],
                    "comments": [],
                    "ids": [],
                    "names": [],
                    "created_at": timestamp,
                    "round": 1,
                    "is_active": True,
                    "n_participantes": int(n_participantes),
                    "privado": es_privada,
                    "correos_autorizados": correos_autorizados
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

            col1, col2 = st.columns(2)
            with col1:
                if st.button("Finalizar esta sesión"):
                    store[code]["is_active"] = False
                    old_round = copy.deepcopy(s)
                    history.setdefault(code, []).append(old_round)
                    st.success("✅ La sesión ha sido finalizada y guardada en el historial.")
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

            # Métricas
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
                        nombre_ronda = st.text_input("Nombre de la ronda:")
                        new_desc = st.text_area("Modificar recomendación:", value=s["desc"])
                        submit_button = st.form_submit_button("Confirmar nueva ronda")
                        if submit_button:
                            next_round = s["round"] + 1
                            descripcion_final = f"{new_desc} ({nombre_ronda})" if nombre_ronda else new_desc
                            store[code].update({
                                "desc": descripcion_final,
                                "votes": [],
                                "comments": [],
                                "ids": [],
                                "names": [],
                                "created_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                "round": next_round
                            })

                            st.success(f"✅ Nueva ronda iniciada: Ronda {next_round} - {nombre_ronda if nombre_ronda else 'sin nombre asignado'}")

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

elif menu == "Registro Previo":
    st.title("📋 Registro Previo - Panel de Consenso")
    st.markdown("Comparta los siguientes enlaces con los participantes para que completen sus registros antes de iniciar el consenso.")

    # 🔐 Conflictos de Interés
    st.markdown("### 🔐 Declaración de Conflictos de Interés")
    url_conflicto = "https://consenso-expertos-sfpqj688ihbl7m6tgrdmwb.streamlit.app/?registro=conflicto"
    st.code(url_conflicto)
    qr_conflicto = qrcode.make(url_conflicto)
    buf1 = io.BytesIO()
    qr_conflicto.save(buf1, format="PNG")
    img1 = base64.b64encode(buf1.getvalue()).decode()
    st.markdown(f'<img src="data:image/png;base64,{img1}" width="180">', unsafe_allow_html=True)

    # 📄 Confidencialidad
    st.markdown("---")
    st.markdown("### 📄 Compromiso de Confidencialidad")
    url_confid = "https://consenso-expertos-sfpqj688ihbl7m6tgrdmwb.streamlit.app/?registro=confidencialidad"
    st.code(url_confid)
    qr_confid = qrcode.make(url_confid)
    buf2 = io.BytesIO()
    qr_confid.save(buf2, format="PNG")
    img2 = base64.b64encode(buf2.getvalue()).decode()
    st.markdown(f'<img src="data:image/png;base64,{img2}" width="180">', unsafe_allow_html=True)

    # 📥 Exportar datos recibidos
    st.markdown("---")
    st.subheader("📥 Exportar registros recibidos")

    col1, col2 = st.columns(2)

    if st.session_state["registro_conflicto"]:
        df1 = pd.DataFrame(st.session_state["registro_conflicto"])
        with col1:
            st.download_button("⬇️ Descargar Conflictos", df1.to_csv(index=False).encode(), file_name="conflictos.csv")
    else:
        with col1:
            st.info("Sin registros aún.")

    if st.session_state["registro_confidencialidad"]:
        df2 = pd.DataFrame(st.session_state["registro_confidencialidad"])
        with col2:
            st.download_button("⬇️ Descargar Confidencialidad", df2.to_csv(index=False).encode(), file_name="confidencialidad.csv")
    else:
        with col2:
            st.info("Sin registros aún.")

    # 🗑️ Borrar registros (SOLO dentro del menú Registro Previo)
    st.markdown("---")
    st.subheader("🗑️ Borrar registros")

    if st.button("❌ Borrar todos los registros de conflicto y confidencialidad"):
        st.session_state["registro_conflicto"] = []
        st.session_state["registro_confidencialidad"] = []

        try:
            os.remove(os.path.join(DATA_DIR, "registro_conflicto.csv"))
            os.remove(os.path.join(DATA_DIR, "registro_confidencialidad.csv"))
        except FileNotFoundError:
            pass

        st.success("Registros eliminados correctamente.")




# Créditos
st.sidebar.markdown("---")
st.sidebar.markdown("**ODDS Epidemiology**")
st.sidebar.markdown("v1.0.0 - 2025")
st.sidebar.markdown("© Todos los derechos reservados")
