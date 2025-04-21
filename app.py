import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import uuid, qrcode, io, hashlib, datetime, base64, copy, os
from scipy import stats
from streamlit_autorefresh import st_autorefresh
import requests
from io import BytesIO
# Reemplaza tus líneas de import de docx por esto:
from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL


# 1) set_page_config debe ir primero
st.set_page_config(
    page_title="ODDS Epidemiology – Dashboard Consenso de expertos",
    page_icon="https://www.oddsepidemiology.com/favicon.ico",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# 2) Único inject_css() con metric‑cards y botones
def inject_css():
    css = """
    <style>
      .stApp { background-color:#F7F7F7 !important; color:#333333; font-family:'Segoe UI', Tahoma, Verdana, sans-serif; }
      .app-header { background-color:#662D91; padding:1.5rem; border-radius:0 0 10px 10px; text-align:center; color:white; margin-bottom:20px; }
      .odds-logo { font-size:2rem; font-weight:bold; letter-spacing:1px; padding-bottom:5px; border-bottom:2px solid #F1592A; display:inline-block; }
      .metric-card { width:140px; padding:12px; margin-bottom:10px; background: linear-gradient(to bottom right, #662D91, #F1592A); color:white; border-radius:8px; box-sizing:border-box; white-space:normal !important; word-wrap:break-word !important; }
      .metric-label { font-size:0.9rem; opacity:0.8; text-align:center; }
      .metric-value { font-size:1.4rem; font-weight:bold; text-align:center; margin-top:4px; }
      .stButton>button { background-color:#662D91; color:white; border:none; padding:0.5rem 1rem; border-radius:5px; }
      .stButton>button:hover { background-color:#F1592A; }
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)

inject_css()

# 3) odds_header(), para mostrar logo y título
def odds_header():
    header_html = """
    <div class="app-header">
      <div class="odds-logo">ODDS EPIDEMIOLOGY</div>
      <div class="odds-subtitle">Sistema de Votación</div>
    </div>
    """
    st.markdown(header_html, unsafe_allow_html=True)

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
# ─────────────────────────────────────────────────────────────
# 5) Página de votación (adaptable al tipo de sesión)
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
            # No st.stop() para que aparezca el botón de descarga

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
    st.markdown('<div class="card">', unsafe_allow_html=True)

    # ─────────── 1.  Cargar banco de Excel (opcional) ────────────
    st.markdown("### Cargar recomendaciones desde Excel")

    # key dinámico → permite “vaciar” el uploader sin recargar la página
    if "uploader_key" not in st.session_state:
        st.session_state.uploader_key = 0

    excel_file = st.file_uploader(
        "Suba archivo .xlsx/.xls con columnas 'ronda' y 'recomendacion'",
        type=["xlsx", "xls"],
        key=f"excel_{st.session_state.uploader_key}"
    )

    # Si se sube un archivo por primera vez (o con la nueva key)
    if excel_file and "df_rec" not in st.session_state:
        try:
            df = pd.read_excel(excel_file, engine="openpyxl")
            df.columns = df.columns.str.strip().str.lower()
            req = {"ronda", "recomendacion"}
            if not req.issubset(df.columns):
                st.error("El Excel debe tener columnas 'ronda' y 'recomendacion'.")
            else:
                df = df.dropna(subset=["ronda", "recomendacion"])
                st.session_state["df_rec"] = df
                st.success(f"✅ {len(df)} recomendaciones cargadas.")
        except Exception as e:
            st.error(f"Error al leer el archivo: {e}")

    # Muestra selector si el DataFrame está en memoria
    if "df_rec" in st.session_state:
        df_rec = st.session_state["df_rec"]

        # Botón para quitar el archivo cargado y resetear el uploader
        if st.button("❌ Quitar archivo cargado"):
            for k in ["df_rec", "ronda_precargada", "recomendacion_precargada"]:
                st.session_state.pop(k, None)
            st.session_state.uploader_key += 1  # fuerza un uploader nuevo vacío
            st.experimental_rerun()

        opciones = (
            ["Seleccione una…"] +
            [f"{r.ronda}: {r.recomendacion[:60]}" for r in df_rec.itertuples()]
        )
        sel = st.selectbox("Elegir recomendación precargada:", opciones)

        if sel != opciones[0]:
            fila = df_rec.iloc[opciones.index(sel) - 1]
            st.session_state["ronda_precargada"] = fila.ronda
            st.session_state["recomendacion_precargada"] = fila.recomendacion
            st.success("Recomendación precargada. Complete el formulario y cree la sesión.")

    st.markdown("<hr>", unsafe_allow_html=True)

    # ─────────── 2.  Formulario de creación (manual o precargado) ────────────
    with st.form("create_form", clear_on_submit=True):
        nombre_ronda = st.text_input(
            "Nombre de la ronda:",
            value=st.session_state.pop("ronda_precargada", "")
        )
        desc = st.text_area(
            "Recomendación a evaluar:",
            value=st.session_state.pop("recomendacion_precargada", ""),
            height=100
        )
        scale = st.selectbox("Escala de votación:", ["Likert 1-9", "Sí/No"])
        n_participantes = st.number_input(
            "¿Cuántos participantes están habilitados para votar?",
            min_value=1, step=1
        )
        es_privada = st.checkbox("¿Esta recomendación será privada?")

        # —— Lista de correos autorizados (opcional) ——
        correos_autorizados = []
        archivo_correos = st.file_uploader(
            "📧 Lista de correos autorizados (CSV con columna 'correo')",
            type=["csv"]
        )
        if archivo_correos:
            try:
                df_correos = pd.read_csv(archivo_correos)
                if "correo" in df_correos.columns:
                    correos_autorizados = (
                        df_correos["correo"].astype(str).str.strip().tolist()
                    )
                    st.success(f"{len(correos_autorizados)} correos cargados.")
                else:
                    st.error("El CSV debe contener una columna llamada 'correo'.")
            except Exception as e:
                st.error(f"No se pudo leer el CSV: {e}")

        st.markdown("""
        <div class="helper-text">
        Escala Likert 1‑9:<br>
        • 1‑3 Desacuerdo • 4‑6 Neutral • 7‑9 Acuerdo<br>
        Se alcanza consenso cuando ≥80 % de votos son ≥7 y hay quórum (mitad + 1).
        </div>
        """, unsafe_allow_html=True)

        # ———  Botón de creación  ———
        if st.form_submit_button("Crear Recomendación"):
            if not desc:
                st.warning("Por favor, ingrese la recomendación.")
                st.stop()

            code = uuid.uuid4().hex[:6].upper()
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            descripcion_final = (
                f"{desc} ({nombre_ronda})" if nombre_ronda else desc
            )

            store[code] = {
                "desc": descripcion_final,
                "scale": scale,
                "votes": [], "comments": [],
                "ids": [], "names": [],
                "created_at": timestamp, "round": 1,
                "is_active": True,
                "n_participantes": int(n_participantes),
                "privado": es_privada,
                "correos_autorizados": correos_autorizados
            }
            history[code] = []

            st.success("Sesión creada exitosamente.")
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
            st.write(f"[Abrir página de votación]({url})")

    st.markdown("</div>", unsafe_allow_html=True)



elif menu == "Dashboard":
    st.subheader("Dashboard en Tiempo Real")
    st_autorefresh(interval=5000, key="refresh_dashboard")

    # 1) Seleccionar sesión activa
    active_sessions = [k for k, v in store.items() if v.get("is_active", True)]
    if not active_sessions:
        st.info("No hay sesiones activas. Cree una nueva sesión para comenzar.")
        st.stop()

    code = st.selectbox("Seleccionar sesión activa:", active_sessions)
    if not code:
        st.stop()

    # 2) Cálculo de métricas
    s = store[code]
    votes, comments, ids = s["votes"], s["comments"], s["ids"]
    pct = consensus_pct(votes) * 100
    med, lo, hi = (None, None, None)
    if votes:
        med, lo, hi = median_ci(votes)
    quorum = s.get("n_participantes", 0) // 2 + 1
    votos_actuales = len(votes)

    # 3) Tres columnas: Resumen | Metric‑Cards | Gráfico
    col_res, col_kpi, col_chart = st.columns([2, 1, 3])

    # Columna 1: Resumen
    with col_res:
        if st.button("Finalizar esta sesión"):
            store[code]["is_active"] = False
            history.setdefault(code, []).append(copy.deepcopy(s))
            st.success("✅ Sesión finalizada.")
            st.rerun()

        st.markdown(f"""
        **Recomendación:** {s['desc']}  
        **Ronda actual:** {s['round']}  
        **Creada:** {s['created_at']}  
        **Votos esperados:** {s.get('n_participantes','?')} | **Quórum:** {quorum}  
        **Votos recibidos:** {votos_actuales}
        """)

    # Columna 2: Metric‑Cards (degradado morado→naranja)
    with col_kpi:
        st.markdown(f"""
        <div class="metric-card">
          <div class="metric-label">Total votos</div>
          <div class="metric-value">{votos_actuales}</div>
        </div>
        <div class="metric-card">
          <div class="metric-label">% Consenso</div>
          <div class="metric-value">{pct:.1f}%</div>
        </div>
        {f'''
        <div class="metric-card">
          <div class="metric-label">Mediana (IC95%)</div>
          <div class="metric-value">{med:.1f} [{lo:.1f}, {hi:.1f}]</div>
        </div>''' if votes else ''}
        """, unsafe_allow_html=True)

    # Columna 3: Histograma morado estrecho
    with col_chart:
        if votes:
            df = pd.DataFrame({"Voto": votes})
            fig = px.histogram(
                df,
                x="Voto",
                nbins=9,
                labels={"Voto":"Escala 1–9","count":"Frecuencia"},
                color_discrete_sequence=[PRIMARY]
            )
            fig.update_traces(marker_line_width=0)
            fig.update_layout(
                bargap=0.4,
                xaxis=dict(tickmode='linear', tick0=1, dtick=1),
                margin=dict(t=30, b=0, l=0, r=0),
                height=300,
                plot_bgcolor='rgba(0,0,0,0)',
                paper_bgcolor='rgba(0,0,0,0)'
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("🔍 Aún no hay votos para mostrar.")

    # 4) Estado de consenso bajo las columnas
    st.markdown("---")
    if votos_actuales < quorum:
        st.info(f"🕒 Quórum no alcanzado ({votos_actuales}/{quorum})")
    else:
        if pct >= 80 and votes and 7 <= med <= 9 and 7 <= lo <= 9 and 7 <= hi <= 9:
            st.success("✅ CONSENSO ALCANZADO (mediana + IC95%)")
        elif pct >= 80:
            st.success("✅ CONSENSO ALCANZADO (% votos)")
        elif pct <= 20 and votes and 1 <= med <= 3 and 1 <= lo <= 3 and 1 <= hi <= 3:
            st.error("❌ NO APROBADO (mediana + IC95%)")
        elif sum(1 for v in votes if isinstance(v, (int, float)) and v <= 3) >= 0.8 * votos_actuales:
            st.error("❌ NO APROBADO (% votos)")
        else:
            st.warning("⚠️ NO SE ALCANZÓ CONSENSO")

    # 5) Acciones y exportes
    st.subheader("Acciones y Exportación")
    if st.button("Iniciar nueva ronda"):
        history.setdefault(code, []).append(copy.deepcopy(s))
        st.session_state.modify_recommendation = True
        st.session_state.current_code = code

    c1, c2 = st.columns(2)
    with c1:
        st.download_button("⬇️ Descargar Excel", to_excel(code),
                           file_name=f"consenso_{code}.xlsx")
    with c2:
        st.download_button("⬇️ Descargar TXT", create_report(code),
                           file_name=f"reporte_{code}.txt")

    # 6) Comentarios
    if comments:
        st.subheader("Comentarios de Participantes")
        for pid, name, vote, com in zip(ids, s["names"], votes, comments):
            if com:
                st.markdown(f"**{name}** (ID:{pid}) — Voto: {vote}\n> {com}")
                
elif menu == "Evaluar con GRADE":
    st.subheader("Evaluación GRADE (paquete de recomendaciones)")

    # 1) Paquetes activos
    elegibles = {
        k: v for k, v in store.items()
        if v.get("tipo") == "GRADE_PKG" and v.get("is_active", True)
    }
    if not elegibles:
        st.info("No hay paquetes GRADE activos.")
        st.stop()

    # 2) Selección de paquete
    code = st.selectbox(
        "Elige el paquete GRADE:",
        options=list(elegibles.keys()),
        format_func=lambda k: f"{k} – {store[k]['desc']}"
    )
    s = store[code]

    # 3) Contador de participantes que ya han votado
    primer_dom = next(iter(s["dominios"].values()))
    registrados = len(primer_dom["ids"])
    st.markdown(f"**Participantes que ya han votado:** {registrados}/{s['n_participantes']}")

    # 4) Pedimos el nombre ANTES de las preguntas
    name = st.text_input("Nombre del participante:")
    if not name:
        st.warning("Por favor ingresa tu nombre para continuar.")
        st.stop()

    # 5) Formulario dinámico de preguntas y opciones
    votos, comentarios = {}, {}
    for dom in PREGUNTAS_GRADE:
        # Mostramos la pregunta
        st.markdown(f"**{PREGUNTAS_GRADE[dom]}**")
        # Radio con sus opciones
        votos[dom] = st.radio(
            "", DOMINIOS_GRADE[dom],
            key=f"vote_{dom}"
        )
        # Textarea para comentario
        comentarios[dom] = st.text_area(
            "Comentario (opcional):",
            key=f"com_{dom}",
            height=60
        )

    # 6) Botón de envío
    if st.button("Enviar votos GRADE"):
        pid = hashlib.sha256(name.encode()).hexdigest()[:8]
        for dom in s["dominios"]:
            s["dominios"][dom]["ids"].append(pid)
            s["dominios"][dom]["names"].append(name)
            s["dominios"][dom]["votes"].append(votos[dom])
            s["dominios"][dom]["comments"].append(comentarios[dom])
        st.balloons()
        st.success(f"🎉 Votos registrados. ID: `{pid}`")

    # 7) Botón de descarga transpuesta
    buf = to_excel(code)
    st.download_button(
        "⬇️ Descargar Excel (dominios × participantes)",
        data=buf,
        file_name=f"GRADE_{code}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

elif menu == "Crear Paquete GRADE":
    st.subheader("Crear Paquete GRADE")
    # 1) Selecciona las recomendaciones existentes
    options = list(store.keys())
    sel = st.multiselect(
        "Elige los códigos de recomendación para el paquete GRADE:",
        options,
        format_func=lambda c: f"{c} – {store[c]['desc']}"
    )
    n_part = st.number_input("¿Cuántos expertos?", min_value=1, step=1)
    if st.button("Crear Paquete"):
        code = uuid.uuid4().hex[:6].upper()
        # inicializa dominios con listas vacías
        dominios = {
            dom: {"ids":[], "names":[], "votes":[], "comments":[], "opciones": DOMINIOS_GRADE[dom]}
            for dom in DOMINIOS_GRADE
        }
        store[code] = {
            "tipo": "GRADE_PKG",
            "desc": f"Paquete de {len(sel)} recomendaciones",
            "recs": sel,
            "dominios": dominios,
            "n_participantes": n_part,
            "created_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "is_active": True
        }
        history[code] = []
        st.success(f"Paquete GRADE creado con código {code}")
        st.markdown(get_qr_code_image_html(code), unsafe_allow_html=True)

elif menu == "Reporte Consolidado":
     integrar_reporte_todas_recomendaciones()
    
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
