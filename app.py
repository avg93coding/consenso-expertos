elif menu == "Crear Recomendación":
    st.subheader("Crear Nueva Recomendación")

    st.markdown('<div class="card">', unsafe_allow_html=True)
    with st.form("create_form", clear_on_submit=True):
        nombre_ronda = st.text_input("Nombre de la ronda:")
        desc = st.text_area("Recomendación a evaluar:", height=100)
        scale = st.selectbox("Escala de votación:", ["Likert 1-9", "Sí/No"])
        n_participantes = st.number_input(
            "¿Cuántos participantes están habilitados para votar?", min_value=1, step=1)

        es_privada = st.checkbox("¿Esta sesión es privada?")
        correos_autorizados = []
        archivo_correos = None
        if es_privada:
            archivo_correos = st.file_uploader("Suba un archivo CSV con los correos autorizados (columna: correo)", type=["csv"])
            if archivo_correos:
                df_correos = pd.read_csv(archivo_correos)
                if "correo" in df_correos.columns:
                    correos_autorizados = df_correos["correo"].astype(str).str.lower().tolist()
                else:
                    st.warning("⚠️ El archivo debe tener una columna llamada 'correo'.")

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
                    "correos_autorizados": correos_autorizados if es_privada else []
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
