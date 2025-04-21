# Básicos y manejo de datos
import streamlit as st
import pandas as pd
import numpy as np
import uuid
import io
import hashlib
import datetime
import base64
import copy
import os
from io import BytesIO
import requests

# Visualización y gráficos
import plotly.express as px
import qrcode

# Estadísticas
from scipy import stats

# Auto-refresh (solo usado en dashboard)
from streamlit_autorefresh import st_autorefresh

# Manipulación de documentos Word (optimizado)
from docx import Document
from docx.shared import Cm  # Solo este se usa realmente
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.enum.text import WD_ALIGN_PARAGRAPH

# 1) set_page_config debe ir primero
st.set_page_config(
    page_title="ODDS Epidemiology – Dashboard Consenso de expertos",
    page_icon="https://www.oddsepidemiology.com/favicon.ico",
    layout="wide",
    initial_sidebar_state="collapsed"
)

def inject_css():
    css = """
    <style>
      /* Mantener estos selectores principales */
      .stApp { background-color:#F7F7F7 !important; color:#333333; font-family:'Segoe UI', Tahoma, Verdana, sans-serif; }
      .app-header { background-color:#662D91; padding:1.5rem; border-radius:0 0 10px 10px; text-align:center; color:white; margin-bottom:20px; }
      
      /* Optimizar estas clases */
      .metric-card {
        width:140px; 
        padding:12px; 
        margin-bottom:10px; 
        background: linear-gradient(to bottom right, #662D91, #F1592A); 
        color:white; 
        border-radius:8px; 
        box-sizing:border-box; 
        white-space:normal !important; 
        word-wrap:break-word !important; 
      }
      .stButton>button { 
        background-color:#662D91; 
        color:white; 
        border:none; 
        padding:0.5rem 1rem; 
        border-radius:5px; 
        transition: background-color 0.3s ease; /* Agregado para mejor hover */
      }
      .stButton>button:hover { background-color:#F1592A; }
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)

inject_css()

def odds_header():
    st.markdown("""
    <div class="app-header">
      <div style="font-size:2rem; font-weight:bold; letter-spacing:1px; 
           padding-bottom:5px; border-bottom:2px solid #F1592A; display:inline-block;">
        ODDS EPIDEMIOLOGY
      </div>
      <div style="margin-top:10px; font-size:1.1rem;">
        Sistema de Votación
      </div>
    </div>
    """, unsafe_allow_html=True)

DOMINIOS_GRADE = {
    "prioridad_problema": [
        "No", "Probablemente no", "Probablemente sí", "Sí", "Varía", "No sabemos"
    ],
    "efectos_deseables": [
        "No importante", "Pequeña", "Moderada", "Grande", "Varía", "No se sabe"
    ],
    "efectos_indeseables": [
        "No importante", "Pequeña", "Moderada", "Grande", "Varía", "No se sabe"
    ],
    "certeza_evidencia": [
        "Muy baja", "Baja", "Moderada", "Alta", "No hay estudios incluidos"
    ],
    "balance_efectos": [
        "Favorece al comparador",
        "Probablemente favorece al comparador",
        "No favorece ni al comparador ni a la intervención",
        "Probablemente favorece a la intervención",
        "Favorece la intervención",
        "Es variable",
        "No es posible saber"
    ],
    "recursos": [
        "Costos altos/recursos",
        "Costos moderados/recursos",
        "Costos o ahorro mínimo/recursos insignificantes",
        "Ahorro moderado",
        "Gran ahorro",
        "Variable",
        "No se sabe"
    ],
    "aceptabilidad": [
        "No", "Probablemente no", "Probablemente sí", "Sí", "Varía", "No se sabe"
    ],
    "factibilidad": [
        "No", "Probablemente no", "Probablemente sí", "Sí", "Varía", "No se sabe"
    ],
    "equidad": [
        "Reducido", "Probablemente reducido", "Probablemente no impacta",
        "Probablemente incrementa", "Incrementa", "Varía", "No se sabe"
    ],
}

PREGUNTAS_GRADE = {
    "prioridad_problema":   "¿Constituye el problema una prioridad?",
    "efectos_deseables":    "¿Cuál es la magnitud de los efectos deseados que se prevén?",
    "efectos_indeseables":  "¿Cuál es la magnitud de los efectos no deseados que se prevén?",
    "certeza_evidencia":    "¿Cuál es la certeza global de la evidencia de los efectos?",
    "balance_efectos":      "¿Qué balance entre efectos deseables y no deseables favorece?",
    "recursos":             "¿Cuál es la magnitud de los recursos necesarios (costos)?",
    "aceptabilidad":        "¿Es aceptable la intervención para los grupos clave?",
    "factibilidad":         "¿Es factible la implementación de la intervención?",
    "equidad":              "¿Cuál sería el impacto sobre la equidad en salud?",
}
# ------------------------------------------------------------


def shade_cell(cell, fill_hex: str):
    """
    Aplica un fondo de color (hex sin ‘#’) a una celda de python-docx.
    """
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    shd = OxmlElement('w:shd')
    shd.set(qn('w:val'), 'clear')
    shd.set(qn('w:fill'), fill_hex)
    tcPr.append(shd)


# Define tus colores corporativos al inicio del fichero
PRIMARY = "#662D91"   # Morado ODDS
SECONDARY = "#F1592A" # Naranja ODDS (opcional)


def to_excel(code: str) -> io.BytesIO:
    if code not in store:
        return io.BytesIO()

    s = store[code]

    # —— A. Sesión estándar ——
    if s.get("tipo", "STD") == "STD":
        df = pd.DataFrame({
            "ID anónimo":    s["ids"],
            "Nombre real":   s["names"],
            "Recomendación": [s["desc"]] * len(s["ids"]),
            "Ronda":         [s["round"]] * len(s["ids"]),
            "Voto":          s["votes"],
            "Comentario":    s["comments"],
            "Fecha":         [s["created_at"]] * len(s["ids"])
        })

    # —— B. Paquete GRADE (filas=participantes, columnas=dominios) ——
    elif s.get("tipo") == "GRADE_PKG":
        dominios = list(s["dominios"].keys())
        # supongo que cada dominio tuvo el mismo # de envíos
        primero = s["dominios"][dominios[0]]
        n_envios = len(primero["votes"])

        filas = []
        for i in range(n_envios):
            fila = {
                "ID":    primero["ids"][i],
                "Nombre":primero["names"][i],
                "Fecha": s["created_at"]
            }
            # por cada dominio metemos voto + comentario
            for d in dominios:
                meta = s["dominios"][d]
                fila[d] = meta["votes"][i]
                fila[f"{d}_comentario"] = meta["comments"][i]
            filas.append(fila)

        df = pd.DataFrame(filas)

    # —— Guardar en buffer y devolver ——
    buf = io.BytesIO()
    df.to_excel(buf, index=False)
    buf.seek(0)
    return buf



def create_report(code: str) -> str:
    """
    Genera un reporte de texto plano con métricas y comentarios de la sesión actual
    (incluye también el historial de rondas anteriores si lo hay).
    """
    if code not in store:
        return "Sesión inválida"
    s = store[code]
    pct = consensus_pct(s["votes"]) * 100
    med, lo, hi = median_ci(s["votes"])
    # Cabecera
    lines = [
        f"REPORTE DE CONSENSO - Sesión {code}",
        f"Fecha de generación: {datetime.datetime.now():%Y-%m-%d %H:%M:%S}",
        "",
        f"Recomendación: {s['desc']}",
        f"Ronda actual: {s['round']}",
        f"Votos totales: {len(s['votes'])}",
        f"% Consenso: {pct:.1f}%",
        f"Mediana (IC95%): {med:.1f} [{lo:.1f}, {hi:.1f}]",
        "",
        "Comentarios:",
    ]
    # Comentarios de la ronda actual
    for pid, name, vote, com in zip(s["ids"], s["names"], s["votes"], s["comments"]):
        if com:
            lines.append(f"- {name} (ID {pid}): “{com}”")
    # Historial de rondas anteriores
    if code in history and history[code]:
        lines.append("\nHistorial de rondas anteriores:")
        for past in history[code]:
            ppct = consensus_pct(past["votes"]) * 100
            lines.append(
                f"  * Ronda {past['round']} [{past['created_at']}]: "
                f"%Consenso={ppct:.1f}%, Mediana={median_ci(past['votes'])[0]:.1f}"
            )
    return "\n".join(lines)


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



def crear_reporte_consolidado_recomendaciones(store: dict, history: dict) -> io.BytesIO:
    """
    Genera un .docx con, para cada recomendación:
      - Logo alineado a la derecha en la cabecera
      - Encabezado con el código
      - Descripción
      - Fecha de creación
      - Tabla de métricas (Total votos, % Consenso, Mediana, IC95%)
      - Estado de consenso
    """
    doc = Document()


    # 1. Descargar el logo
    logo_url = (
        "https://static.wixstatic.com/media/89a9c2_ddc57311fc734357b9ea2b699e107ae2"
        "~mv2.png/v1/fill/w_90,h_54,al_c,q_85,usm_0.66_1.00_0.01/"
        "Logo%20versión%20principal.png"
    )
    resp = requests.get(logo_url)
    if resp.status_code == 200:
        img_stream = BytesIO(resp.content)
        # 2. Obtener (o crear) el párrafo del encabezado
        header = doc.sections[0].header
        if header.paragraphs:
            header_para = header.paragraphs[0]
        else:
            header_para = header.add_paragraph()
        # 3. Insertar la imagen y alinearla a la derecha
        run = header_para.add_run()
        run.add_picture(img_stream, width=Cm(4))
        header_para.alignment = WD_ALIGN_PARAGRAPH.RIGHT

    # 4. Ajustar márgenes A4
    for sec in doc.sections:
        sec.page_height = Cm(29.7)
        sec.page_width  = Cm(21.0)
        sec.left_margin = Cm(2.5)
        sec.right_margin = Cm(2.5)
        sec.top_margin = Cm(2.5)
        sec.bottom_margin = Cm(2.5)

    # 5. Iterar cada recomendación
    for code, rec in store.items():
        # 5.1 Encabezado de recomendación
        h = doc.add_heading(level=1)
        h.add_run(f"Recomendación {code}").bold = True
        h.alignment = WD_ALIGN_PARAGRAPH.LEFT

        # 5.2 Descripción
        doc.add_paragraph().add_run("Descripción: ").bold = True
        doc.add_paragraph(rec["desc"])

        # 5.3 Fecha de creación
        doc.add_paragraph().add_run("Fecha de creación: ").bold = True
        doc.add_paragraph(rec["created_at"])

        # 5.4 Tabla de métricas
        votos = rec["votes"]
        pct = consensus_pct(votos) * 100
        med, lo, hi = median_ci(votos)

        tbl = doc.add_table(rows=1, cols=4, style="Table Grid")
        hdr_cells = tbl.rows[0].cells
        titles = ["Total votos", "% Consenso", "Mediana", "IC95%"]
        for idx, title in enumerate(titles):
            cell = hdr_cells[idx]
            cell.text = ""
            p = cell.paragraphs[0]
            run = p.add_run(title)
            run.bold = True
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER

        values = [str(len(votos)), f"{pct:.1f}%", f"{med:.1f}", f"[{lo:.1f}, {hi:.1f}]"]
        row_cells = tbl.add_row().cells
        for idx, val in enumerate(values):
            cell = row_cells[idx]
            cell.text = val
            cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER

        doc.add_paragraph()

        # 5.5 Estado de consenso
        total = len(votos)
        if pct >= 80 and 7 <= med <= 9 and 7 <= lo <= 9 and 7 <= hi <= 9:
            estado = "✅ CONSENSO ALCANZADO (por mediana + IC95%)."
        elif pct >= 80:
            estado = "✅ CONSENSO ALCANZADO (por porcentaje)."
        elif pct <= 20 and 1 <= med <= 3 and 1 <= lo <= 3 and 1 <= hi <= 3:
            estado = "❌ NO APROBADO (por mediana + IC95%)."
        elif sum(1 for v in votos if isinstance(v, (int, float)) and v <= 3) >= 0.8 * total:
            estado = "❌ NO APROBADO (por porcentaje)."
        else:
            estado = "⚠️ NO SE ALCANZÓ CONSENSO."

        doc.add_paragraph().add_run("Estado de consenso: ").bold = True
        doc.add_paragraph(estado)

        doc.add_page_break()

    # 6. Guardar y devolver buffer
    buffer = io.BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer

# ——————————————————————————————
#  Integración en Streamlit
# ——————————————————————————————
def integrar_reporte_todas_recomendaciones():
    st.subheader(" Descargar Reporte Consolidado de Recomendaciones")

    if not store:
        st.info("No hay recomendaciones registradas aún.")
        return

    if st.button("⬇️ Generar y Descargar .docx"):
        buf = crear_reporte_consolidado_recomendaciones(store, history)
        nombre = f"reporte_recomendaciones_{datetime.datetime.now():%Y%m%d}.docx"
        st.download_button(
            label="Descargar Documento",
            data=buf,
            file_name=nombre,
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )



# ─────────────────────────────────────────────────────────────
# 5)  Página de votación (se adapta al tipo de sesión)
# ─────────────────────────────────────────────────────────────
# 5) Página de votación (adaptable al tipo de sesión)
# ─────────────────────────────────────────────────────────────
params = st.query_params
if "session" in params:
    raw  = params.get("session")
    code = raw[0] if isinstance(raw, list) else raw
    code = str(code).strip().upper()

    odds_header()
    st.markdown('<div class="hide-sidebar">', unsafe_allow_html=True)

    s = store.get(code)
    if not s:
        st.error(f"Sesión inválida: {code}")
        st.stop()
    tipo = s.get("tipo", "STD")

    st.subheader(f"Panel de votación — Sesión {code}")

    # Pedimos el nombre antes de todo
    name = st.text_input("Nombre del participante:")
    if not name:
        st.warning("Ingrese su nombre para continuar.")
        st.stop()

    # Evita doble voto
    if (tipo == "STD" and name in s["names"]) \
    or (tipo == "GRADE_PKG" and name in s["dominios"]["prioridad_problema"]["names"]):
        st.success("✅ Ya registró su participación.")
        st.stop()

    # ——— SESIÓN ESTÁNDAR ———
    if tipo == "STD":
        st.markdown("### Recomendación a evaluar")
        st.markdown(f"**{s['desc']}**")
        if s["scale"].startswith("Likert"):
            st.markdown("1‑3 Desacuerdo • 4‑6 Neutral • 7‑9 Acuerdo")
            vote = st.slider("Su voto:", 1, 9, 5)
        else:
            vote = st.radio("Su voto:", ["Sí", "No"])
        comment = st.text_area("Comentario (opcional):")

        if st.button("Enviar voto"):
            pid = record_vote(code, vote, comment, name)
            if pid:
                st.balloons()
                st.success(f"🎉 Gracias. ID de voto: `{pid}`")
            else:
                st.error("No se pudo registrar el voto.")
        st.stop()

    # ——— PAQUETE GRADE ———
    elif tipo == "GRADE_PKG":
        st.write(f"### Evaluación GRADE (paquete de {len(s['recs'])} recomendaciones)")
        st.markdown("**Recomendaciones incluidas:**")
        for rc in s["recs"]:
            st.markdown(f"- **{rc}** — {store[rc]['desc']}")

        votos, comentarios = {}, {}
        for dom in PREGUNTAS_GRADE:
            st.markdown(f"**{PREGUNTAS_GRADE[dom]}**")
            votos[dom] = st.radio(
                "",
                DOMINIOS_GRADE[dom],
                key=f"{code}-vote-{dom}"
            )
            comentarios[dom] = st.text_area(
                "Comentario (opcional):",
                key=f"{code}-com-{dom}",
                height=60
            )

        if st.button("Enviar votos GRADE"):
            pid = hashlib.sha256(name.encode()).hexdigest()[:8]
            for dom in PREGUNTAS_GRADE:
                meta = s["dominios"][dom]
                meta["ids"].append(pid)
                meta["names"].append(name)
                meta["votes"].append(votos[dom])
                meta["comments"].append(comentarios[dom])
            st.balloons()
            st.success(f"🎉 Votos registrados. ID: `{pid}`")
            # no st.stop() para que salga el botón de descarga

        buf = to_excel(code)
        st.download_button(
            "⬇️ Descargar Excel (dominios × participantes)",
            data=buf,
            file_name=f"GRADE_{code}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        st.stop()


# 6) Panel de administración
odds_header()
# Logo en la barra lateral
logo_url = "https://static.wixstatic.com/media/89a9c2_ddc57311fc734357b9ea2b699e107ae2~mv2.png/v1/fill/w_90,h_54,al_c,q_85,usm_0.66_1.00_0.01/Logo%20versi%C3%B3n%20principal.png"
st.sidebar.image(logo_url, width=80)

st.sidebar.title("Panel de Control")
st.sidebar.markdown("### ODDS Epidemiology")
menu = st.sidebar.selectbox("Navegación", ["Inicio", "Crear Recomendación", "Dashboard", "Crear Paquete GRADE", "Reporte Consolidado"])

if menu == "Inicio":
    st.markdown("## Bienvenido al Sistema de votación para Consenso de expertos de ODDS Epidemiology")
    
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown("""
    
    
    Utilice el panel de navegación para comenzar.
    """)
    st.markdown("</div>", unsafe_allow_html=True)
    
    

# ──────────────────────────────────────────────────────────────────────────────
#  BLOQUE DEL PANEL: "Crear Recomendación"
# ──────────────────────────────────────────────────────────────────────────────
elif menu == "Crear Recomendación":
    st.subheader("Crear Nueva Recomendación")
    
    # --- Sección 1: Carga desde Excel ---
    with st.expander("📤 Cargar desde Excel", expanded=False):
        if "uploader_key" not in st.session_state:
            st.session_state.uploader_key = 0
            
        uploaded_file = st.file_uploader(
            "Subir archivo Excel (columnas 'ronda' y 'recomendacion')",
            type=["xlsx", "xls"],
            key=f"excel_upload_{st.session_state.uploader_key}"
        )
        
        if uploaded_file:
            try:
                df = pd.read_excel(uploaded_file, engine="openpyxl")
                df.columns = df.columns.str.strip().str.lower()
                
                if not {"ronda", "recomendacion"}.issubset(df.columns):
                    st.error("El archivo debe contener las columnas requeridas")
                else:
                    st.session_state.excel_data = df.dropna(subset=["ronda", "recomendacion"])
                    st.success(f"{len(st.session_state.excel_data)} recomendaciones cargadas")
                    
                    if st.button("Limpiar datos cargados"):
                        del st.session_state.excel_data
                        st.session_state.uploader_key += 1
                        st.rerun()
                        
            except Exception as e:
                st.error(f"Error al procesar el archivo: {str(e)}")

    # --- Sección 2: Formulario de creación ---
    with st.form("recommendation_form"):
        # Precargar datos si existen
        if "excel_data" in st.session_state:
            selected = st.selectbox(
                "Seleccionar recomendación precargada",
                options=[""] + list(st.session_state.excel_data.itertuples()),
                format_func=lambda x: f"{x.ronda}: {x.recomendacion[:60]}..." if x else ""
            )
            
            if selected:
                default_round = selected.ronda
                default_desc = selected.recomendacion
            else:
                default_round = ""
                default_desc = ""
        else:
            default_round = ""
            default_desc = ""
        
        # Campos del formulario
        round_name = st.text_input("Nombre de la ronda", value=default_round)
        recommendation_text = st.text_area(
            "Texto de la recomendación", 
            value=default_desc,
            height=100
        )
        
        col1, col2 = st.columns(2)
        with col1:
            voting_scale = st.selectbox(
                "Escala de votación",
                options=["Likert 1-9", "Sí/No"]
            )
        with col2:
            participants = st.number_input(
                "Número de participantes",
                min_value=1,
                value=5
            )
        
        is_private = st.checkbox("Sesión privada (requiere lista de correos)")
        if is_private:
            emails = st.text_area(
                "Correos autorizados (separados por comas o saltos de línea)",
                placeholder="usuario1@mail.com, usuario2@mail.com\nusuario3@mail.com"
            )
            authorized_emails = [e.strip() for e in emails.replace("\n", ",").split(",") if e.strip()]
        
        if st.form_submit_button("Crear Recomendación"):
            if not recommendation_text:
                st.error("El texto de la recomendación es obligatorio")
                st.stop()
                
            # Generar ID y timestamp
            session_id = uuid.uuid4().hex[:6].upper()
            created_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # Guardar en el store
            store[session_id] = {
                "desc": f"{recommendation_text} ({round_name})" if round_name else recommendation_text,
                "scale": voting_scale,
                "votes": [],
                "comments": [],
                "ids": [],
                "names": [],
                "created_at": created_at,
                "round": 1,
                "is_active": True,
                "n_participantes": participants,
                "privado": is_private,
                "correos_autorizados": authorized_emails if is_private else []
            }
            
            # Mostrar resultados
            st.success("Recomendación creada exitosamente")
            
            with st.container():
                st.subheader("Detalles de la sesión")
                cols = st.columns([1, 2])
                with cols[0]:
                    st.metric("Código", session_id)
                    st.image(make_qr(session_id), width=150)
                with cols[1]:
                    st.code(f"URL de acceso: {create_qr_code_url(session_id)}")
                    
elif menu == "Dashboard":
    st.subheader("Dashboard en Tiempo Real")
    st_autorefresh(interval=5000, key="dashboard_refresh")

    # 1) Filtrado de sesiones activas con información enriquecida
    active_sessions = {
        k: v for k, v in store.items() 
        if v.get("is_active", True)
    }
    
    if not active_sessions:
        st.info("No hay sesiones activas disponibles")
        st.stop()

    # 2) Selector mejorado con métricas clave
    selected_session = st.selectbox(
        "Seleccionar sesión:",
        options=list(active_sessions.keys()),
        format_func=lambda k: (
            f"{k} - {active_sessions[k]['desc'][:30]}... | "
            f"Votos: {len(active_sessions[k]['votes'])}/{active_sessions[k]['n_participantes']}"
        )
    )
    
    session_data = active_sessions[selected_session]
    votes = session_data["votes"]
    comments = session_data["comments"]
    participants = session_data["names"]

    # 3) Cálculo de métricas (con manejo de casos vacíos)
    consensus = consensus_pct(votes) * 100 if votes else 0
    median_data = median_ci(votes) if votes else (None, None, None)
    quorum = session_data["n_participantes"] // 2 + 1
    current_votes = len(votes)

    # 4) Layout mejorado con pestañas
    tab_main, tab_data, tab_comments = st.tabs(["Resumen", "Datos", "Comentarios"])

    with tab_main:
        # Sección de estado
        status_col, action_col = st.columns([3, 1])
        
        with status_col:
            st.markdown(f"""
            ### {session_data['desc']}
            **Ronda:** {session_data['round']} | **Creada:** {session_data['created_at']}
            **Participación:** {current_votes}/{session_data['n_participantes']} | **Quórum:** {quorum}
            """)
            
        with action_col:
            if st.button("Finalizar sesión", type="primary"):
                store[selected_session]["is_active"] = False
                history.setdefault(selected_session, []).append(copy.deepcopy(session_data))
                st.success("Sesión finalizada")
                st.rerun()
                
            if st.button("Nueva ronda"):
                history.setdefault(selected_session, []).append(copy.deepcopy(session_data))
                st.session_state.edit_session = selected_session
                st.rerun()

        # Métricas visuales
        metric_col1, metric_col2, metric_col3 = st.columns(3)
        
        with metric_col1:
            st.metric("Votos registrados", f"{current_votes}/{session_data['n_participantes']}")
            
        with metric_col2:
            st.metric("% Consenso", f"{consensus:.1f}%")
            
        with metric_col3:
            if votes:
                st.metric("Mediana (IC95%)", 
                         f"{median_data[0]:.1f} [{median_data[1]:.1f}, {median_data[2]:.1f}]")

        # Gráfico y estado de consenso
        st.markdown("---")
        
        if votes:
            # Histograma mejorado
            fig = px.histogram(
                pd.DataFrame({"Voto": votes}),
                x="Voto",
                nbins=9,
                range_x=[1,9],
                color_discrete_sequence=[PRIMARY],
                labels={"Voto": "Escala de votación", "count": "Participantes"}
            )
            fig.update_layout(
                bargap=0.2,
                xaxis=dict(tickmode='linear', dtick=1),
                yaxis_title="Número de votos",
                margin=dict(t=20),
                height=300
            )
            st.plotly_chart(fig, use_container_width=True)
            
            # Estado de consenso
            if current_votes < quorum:
                st.warning(f"Quórum no alcanzado ({current_votes}/{quorum})")
            elif consensus >= 80 and all(7 <= x <= 9 for x in median_data if x is not None):
                st.success("CONSENSO ALCANZADO (mediana + IC95%)")
            elif consensus >= 80:
                st.success("CONSENSO ALCANZADO (% votos)")
            elif consensus <= 20 and all(1 <= x <= 3 for x in median_data if x is not None):
                st.error("NO APROBADO (mediana + IC95%)")
            else:
                st.info("No se alcanzó consenso")
        else:
            st.info("Aún no hay votos registrados")

    with tab_data:
        # Exportación de datos
        st.download_button(
            "Descargar Excel completo",
            data=to_excel(selected_session),
            file_name=f"consenso_{selected_session}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        
        st.download_button(
            "Descargar reporte ejecutivo",
            data=create_report(selected_session),
            file_name=f"reporte_{selected_session}.txt"
        )
        
        if votes:
            st.dataframe(pd.DataFrame({
                "Participante": session_data["names"],
                "ID": session_data["ids"],
                "Voto": votes,
                "Comentario": comments
            }), hide_index=True)

    with tab_comments:
        if comments:
            for name, pid, vote, comment in zip(participants, session_data["ids"], votes, comments):
                if comment:
                    with st.expander(f"{name} (ID: {pid}) - Voto: {vote}"):
                        st.write(comment)
        else:
            st.info("No hay comentarios registrados")
                
elif menu == "Crear Paquete GRADE":
    st.subheader("Creación de Paquete GRADE")
    
    # 1) Filtrado avanzado de recomendaciones disponibles
    recomendaciones_disponibles = [
        (codigo, datos) for codigo, datos in store.items()
        if (datos.get("tipo", "STD") == "STD" and                    # Solo sesiones estándar
           not datos.get("is_active", True) and                      # Sesiones finalizadas
           len(datos.get("votes", [])) >= 3 and                      # Mínimo 3 votos
           consensus_pct(datos.get("votes", [])) >= 0.5              # Algo de consenso (50%)
    )
    
    if not recomendaciones_disponibles:
        st.warning("""
        No hay recomendaciones elegibles para paquetes GRADE. Requisitos:
        - Sesiones finalizadas
        - Mínimo 3 votos registrados
        - Al menos 50% de consenso inicial
        """)
        st.stop()

    # 2) Interfaz de selección mejorada
    with st.expander("📋 Recomendaciones disponibles", expanded=True):
        cols = st.columns(2)
        selected_codes = []
        
        for idx, (codigo, datos) in enumerate(recomendaciones_disponibles):
            with cols[idx % 2]:
                if st.checkbox(
                    f"**{codigo}** - {datos['desc'][:50]}...\n"
                    f"Votos: {len(datos['votes'])} | "
                    f"Consenso: {consensus_pct(datos['votes']) * 100:.1f}%",
                    key=f"pkg_{codigo}"
                ):
                    selected_codes.append(codigo)

    if not selected_codes:
        st.stop()

    # 3) Configuración del paquete
    with st.form("grade_package_form"):
        st.write("**Configuración del paquete**")
        
        col1, col2 = st.columns(2)
        with col1:
            num_expertos = st.number_input(
                "Número de evaluadores:",
                min_value=3,
                max_value=50,
                value=10,
                help="Mínimo 3 expertos para evaluación GRADE"
            )
            
        with col2:
            pkg_name = st.text_input(
                "Nombre descriptivo:",
                value=f"Paquete GRADE {datetime.date.today().strftime('%Y-%m-%d')}",
                help="Ej: 'Evaluación estrategias prevención COVID-19'"
            )
        
        if st.form_submit_button("🛠️ Crear Paquete GRADE"):
            # Validación final
            if len(selected_codes) < 1:
                st.error("Seleccione al menos una recomendación")
                st.stop()
                
            # Generación del código
            pkg_code = uuid.uuid4().hex[:6].upper()
            
            # Estructura de datos del paquete
            store[pkg_code] = {
                "tipo": "GRADE_PKG",
                "desc": pkg_name,
                "recs": selected_codes,
                "dominios": {
                    dominio: {
                        "ids": [],
                        "names": [],
                        "votes": [],
                        "comments": [],
                        "opciones": DOMINIOS_GRADE[dominio]
                    } for dominio in DOMINIOS_GRADE
                },
                "n_participantes": num_expertos,
                "created_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "is_active": True,
                "metadata": {
                    "recomendaciones_incluidas": selected_codes,
                    "votos_previos": {code: len(store[code]["votes"]) for code in selected_codes}
                }
            }
            
            history[pkg_code] = []
            
            # Generación de enlace
            voting_url = create_qr_code_url(pkg_code)
            
            # Visualización de resultados
            st.success(f"Paquete creado con código: **{pkg_code}**")
            
            tab1, tab2 = st.tabs(["Código QR", "Enlace directo"])
            with tab1:
                st.image(make_qr(pkg_code), width=250)
                st.caption("Escanee este código para acceder a la evaluación")
                
            with tab2:
                st.code(voting_url, language="text")
                st.download_button(
                    "Copiar enlace",
                    data=voting_url,
                    file_name=f"enlace_GRADE_{pkg_code}.txt",
                    mime="text/plain"
                )

elif menu == "Registro Previo":
    st.title("Registro Previo - Panel de Consenso")
    st.markdown("Comparta los siguientes enlaces con los participantes para que completen sus registros antes de iniciar el consenso.")

    #  Conflictos de Interés
    st.markdown("###  Declaración de Conflictos de Interés")
    url_conflicto = "https://consenso-expertos-sfpqj688ihbl7m6tgrdmwb.streamlit.app/?registro=conflicto"
    st.code(url_conflicto)
    qr_conflicto = qrcode.make(url_conflicto)
    buf1 = io.BytesIO()
    qr_conflicto.save(buf1, format="PNG")
    img1 = base64.b64encode(buf1.getvalue()).decode()
    st.markdown(f'<img src="data:image/png;base64,{img1}" width="180">', unsafe_allow_html=True)

    # 📄 Confidencialidad
    st.markdown("---")
    st.markdown("###  Compromiso de Confidencialidad")
    url_confid = "https://consenso-expertos-sfpqj688ihbl7m6tgrdmwb.streamlit.app/?registro=confidencialidad"
    st.code(url_confid)
    qr_confid = qrcode.make(url_confid)
    buf2 = io.BytesIO()
    qr_confid.save(buf2, format="PNG")
    img2 = base64.b64encode(buf2.getvalue()).decode()
    st.markdown(f'<img src="data:image/png;base64,{img2}" width="180">', unsafe_allow_html=True)

    # 📥 Exportar datos recibidos
    st.markdown("---")
    st.subheader(" Exportar registros recibidos")

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
