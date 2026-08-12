import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import sqlite3
from datetime import datetime

# 0. Configurar la base de datos persistente SQLite para el Control de Horno
def inicializar_db():
    conn = sqlite3.connect("inventario.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS control_horno (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT NOT NULL,
            producto TEXT NOT NULL,
            kilos_crudos REAL NOT NULL,
            kilos_cocidos REAL NOT NULL,
            rendimiento REAL NOT NULL,
            merma REAL NOT NULL,
            notas TEXT
        )
    """)
    conn.commit()
    conn.close()

# Inicializar la base de datos al arrancar
inicializar_db()

def guardar_registro_horno(producto, kilos_crudos, kilos_cocidos, rendimiento, merma, notas=""):
    conn = sqlite3.connect("inventario.db")
    cursor = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("""
        INSERT INTO control_horno (fecha, producto, kilos_crudos, kilos_cocidos, rendimiento, merma, notas)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (fecha_actual, producto, kilos_crudos, kilos_cocidos, rendimiento, merma, notas))
    conn.commit()
    conn.close()

def obtener_historial_horno():
    conn = sqlite3.connect("inventario.db")
    df = pd.read_sql_query("SELECT * FROM control_horno ORDER BY id DESC", conn)
    conn.close()
    return df

def eliminar_registro_horno(id_registro):
    conn = sqlite3.connect("inventario.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM control_horno WHERE id = ?", (id_registro,))
    conn.commit()
    conn.close()

st.set_page_config(page_title="Hijos del Maíz Prieto", page_icon="🌽", layout="centered")
st.title("🌽 Hijos del Maíz Prieto")
st.subheader("Inventario en la Nube (Pestañas)")

# 1. Configurar la conexión segura con Google Sheets
@st.cache_resource
def iniciar_conexion():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name("llave.json", scope)
    client = gspread.authorize(creds)
    return client

try:
    client = iniciar_conexion()
    spreadsheet = client.open("Inventario Hijos del Maíz Prieto")
except Exception as e:
    st.error("⚠️ Error de conexión con Google Sheets")
    st.info("Revisa lo siguiente:\n1. Que tu archivo de credenciales en VS Code se llame exactamente 'llave.json'.\n2. Que tu archivo en Drive se llame exactamente 'Inventario Hijos del Maíz Prieto'.\n3. Que compartieras el archivo de Drive con el correo largo como 'Editor'.")
    st.stop()

# Obtener la lista de pestañas dinámicamente desde Google Sheets
try:
    lista_pestanas = [sheet.title for sheet in spreadsheet.worksheets()]
except Exception as e:
    st.error("No se pudieron obtener las pestañas del archivo de Google Sheets.")
    st.stop()

# Configuración de pestañas principales
tab1, tab2, tab3, tab4, tab5 = st.tabs(["📊 Dashboard", "📝 Gestión", "🔥 Control de Horno", "🍖 Calculadora de Merma", "🛒 Lista de Compras"])

with tab5:
    st.header("🛒 Lista de Compras Automática")
    st.write("Esta sección analiza todo el inventario y genera una lista de los productos que necesitan reabastecimiento.")
    
    if st.button("Generar Lista de Compras"):
        with st.spinner("Escaneando todas las categorías..."):
            lista_faltantes = []
            
            for p in lista_pestanas:
                try:
                    temp_sheet = spreadsheet.worksheet(p)
                    temp_df = pd.DataFrame(temp_sheet.get_all_records())
                    if not temp_df.empty:
                        for _, row in temp_df.iterrows():
                            # Usar los mismos umbrales que en las alertas
                            umbral = 5 if "Kg" not in str(row["Producto"]) else 2.0
                            if row["Cantidad"] <= umbral:
                                lista_faltantes.append({
                                    "Categoría": p,
                                    "Producto": row["Producto"],
                                    "Cantidad Actual": row["Cantidad"],
                                    "Estado": "CRÍTICO" if row["Cantidad"] <= umbral else "BAJO"
                                })
                except:
                    continue
            
            if lista_faltantes:
                df_faltantes = pd.DataFrame(lista_faltantes)
                st.warning(f"Se encontraron {len(df_faltantes)} productos que requieren atención.")
                st.table(df_faltantes)
                
                # Opción para descargar
                csv = df_faltantes.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="📥 Descargar Lista de Compras (CSV)",
                    data=csv,
                    file_name='lista_compras_hijos_maiz.csv',
                    mime='text/csv',
                )
            else:
                st.success("✅ ¡Todo está en orden! No se encontraron productos con stock bajo.")

with tab4:
    st.header("Calculadora de Rendimiento (Merma)")
    st.write("Registra la carne que entra al hoyo y lo que sale para calcular el rendimiento real.")
    
    col_m1, col_m2 = st.columns(2)
    with col_m1:
        peso_crudo = st.number_input("Peso Crudo (Kg):", min_value=0.0, step=0.1)
    with col_m2:
        peso_cocido = st.number_input("Peso Cocido (Kg):", min_value=0.0, step=0.1)
    
    if peso_crudo > 0:
        rendimiento = (peso_cocido / peso_crudo) * 100
        merma = 100 - rendimiento
        
        st.info(f"**Rendimiento:** {rendimiento:.2f}% | **Merma:** {merma:.2f}%")
        
        if st.button("Actualizar Stock de Barbacoa con este resultado"):
            try:
                # Intentar buscar la pestaña 'Carnes'
                sheet_carnes = spreadsheet.worksheet("Carnes")
                data_carnes = sheet_carnes.get_all_records()
                
                # Buscar la fila de 'Barbacoa (Kg)'
                fila_idx = -1
                for i, row in enumerate(data_carnes):
                    if "Barbacoa" in row.get("Producto", ""):
                        fila_idx = i + 2
                        break
                
                if fila_idx != -1:
                    sheet_carnes.update_cell(fila_idx, 2, peso_cocido)
                    st.success(f"¡Stock de Barbacoa actualizado a {peso_cocido} Kg!")
                else:
                    st.warning("No se encontró el producto 'Barbacoa' en la pestaña 'Carnes'.")
            except Exception as e:
                st.error("Asegúrate de tener una pestaña llamada 'Carnes' con una columna 'Producto' y 'Cantidad'.")

with tab3:
    st.header("🔥 Control de Horno")
    st.write("Registra y analiza los procesos de cocción de carnes para monitorear el rendimiento real y la merma.")

    # Formulario para registrar nueva cocción
    with st.form("registro_coccion", clear_on_submit=True):
        st.subheader("📝 Registrar Nueva Cocción")
        
        # Obtener nombres de productos de carnes del Sheets para sugerirlos si están disponibles,
        # si no, dar una lista por defecto.
        productos_sugeridos = ["Barbacoa", "Pork Belly", "Birria", "Costilla", "Pollo", "Arrachera", "Otro..."]
        try:
            # Intentar leer productos de Carnes para poblar el dropdown de forma dinámica y amigable
            sheet_carnes = spreadsheet.worksheet("Carnes")
            data_carnes = sheet_carnes.get_all_records()
            carnes_list = [row["Producto"] for row in data_carnes if "Producto" in row]
            if carnes_list:
                # Filtrar duplicados o vacíos y agregar "Otro..." al final
                productos_sugeridos = sorted(list(set(carnes_list))) + ["Otro..."]
        except Exception as e:
            # Si no se puede, se usa la lista por defecto
            pass

        col_f1, col_f2 = st.columns(2)
        with col_f1:
            producto_sel = st.selectbox("Producto / Insumo:", productos_sugeridos)
        with col_f2:
            producto_otro = st.text_input("Si seleccionaste 'Otro...', escríbelo aquí:", placeholder="Ej. Lechón")

        col_w1, col_w2 = st.columns(2)
        with col_w1:
            peso_crudo = st.number_input("Peso Crudo (Kg):", min_value=0.0, step=0.1, value=10.0, help="Kilos de carne cruda ingresados al horno.")
        with col_w2:
            peso_cocido = st.number_input("Peso Cocido (Kg):", min_value=0.0, step=0.1, value=6.0, help="Kilos de carne cocida retirados del horno.")

        notas_coccion = st.text_area("Notas / Observaciones:", placeholder="Ej. Cocción lenta de 12 horas con leña de mezquite, lote de proveedor local X.")

        guardar_btn = st.form_submit_button("💾 Guardar en Base de Datos", use_container_width=True)

        if guardar_btn:
            if peso_crudo <= 0:
                st.error("❌ El peso crudo debe ser mayor a 0 Kg.")
            elif peso_cocido > peso_crudo:
                st.warning("⚠️ El peso cocido es mayor que el peso crudo. ¿Estás seguro de que es correcto?")
                # De todos modos permitimos guardar si el usuario lo decide, pero alertamos.
            else:
                # Determinar el nombre definitivo del producto
                producto_final = producto_sel
                if producto_sel == "Otro...":
                    if not producto_otro.strip():
                        st.error("❌ Por favor especifica el nombre del producto en el campo de texto.")
                        st.stop()
                    producto_final = producto_otro.strip()
                
                # Calcular rendimiento y merma
                rend = (peso_cocido / peso_crudo) * 100
                merma_porc = 100 - rend
                
                # Guardar en SQLite
                guardar_registro_horno(producto_final, peso_crudo, peso_cocido, rend, merma_porc, notas_coccion)
                
                # Sincronizar stock con Google Sheets si el usuario lo desea y coincide con 'Carnes'
                sincronizado_msg = ""
                try:
                    sheet_carnes = spreadsheet.worksheet("Carnes")
                    data_carnes = sheet_carnes.get_all_records()
                    
                    fila_idx = -1
                    for idx_c, row in enumerate(data_carnes):
                        if producto_final.lower() in row.get("Producto", "").lower() or row.get("Producto", "").lower() in producto_final.lower():
                            fila_idx = idx_c + 2
                            producto_final = row.get("Producto") # Usar el nombre exacto de Sheets
                            break
                    
                    if fila_idx != -1:
                        sheet_carnes.update_cell(fila_idx, 2, peso_cocido)
                        sincronizado_msg = f" ¡Y se actualizó automáticamente el stock de '{producto_final}' en Google Sheets a {peso_cocido} Kg!"
                    else:
                        sincronizado_msg = f" (No se encontró un producto exacto en la pestaña 'Carnes' de Google Sheets para sincronizar el stock, pero quedó registrado localmente)."
                except Exception as e:
                    sincronizado_msg = " (Nota: No se pudo sincronizar automáticamente con Google Sheets, asegúrate de tener una pestaña llamada 'Carnes')."

                st.success(f"✅ ¡Registro guardado exitosamente!{sincronizado_msg}")
                
                # Resumen vistoso
                st.info(f"📊 **Resultados de esta cocción:**\n"
                        f"- **Peso Crudo:** {peso_crudo:.2f} Kg\n"
                        f"- **Peso Cocido:** {peso_cocido:.2f} Kg\n"
                        f"- **Rendimiento:** {rend:.2f}%\n"
                        f"- **Merma:** {merma_porc:.2f}% ({peso_crudo - peso_cocido:.2f} Kg mermados)")
                
                st.balloons()
                st.rerun()

    # Historial de Cocciones de SQLite
    st.write("---")
    st.subheader("📋 Historial de Cocciones y Mermas (SQLite)")
    
    df_historial = obtener_historial_horno()
    
    if df_historial.empty:
        st.info("Aún no hay registros de cocción guardados en la base de datos SQLite local.")
    else:
        # Métricas de resumen
        col_m1, col_m2, col_m3 = st.columns(3)
        total_cocciones = len(df_historial)
        rendimiento_promedio = df_historial["rendimiento"].mean()
        merma_total_kg = (df_historial["kilos_crudos"] - df_historial["kilos_cocidos"]).sum()
        
        col_m1.metric("Total Cocciones", f"{total_cocciones}")
        col_m2.metric("Rendimiento Promedio", f"{rendimiento_promedio:.2f}%")
        col_m3.metric("Merma Total Acumulada", f"{merma_total_kg:.2f} Kg", delta_color="inverse")
        
        # Gráficos interesantes si hay suficientes datos
        st.write("---")
        col_g1, col_g2 = st.columns(2)
        
        with col_g1:
            st.write("📈 **Rendimiento Promedio por Producto**")
            df_prom_prod = df_historial.groupby("producto")["rendimiento"].mean().reset_index()
            df_prom_prod = df_prom_prod.sort_values(by="rendimiento", ascending=False)
            st.bar_chart(df_prom_prod.set_index("producto")["rendimiento"], color="#FF4B4B")
            
        with col_g2:
            st.write("📉 **Evolución del Rendimiento (Últimos 10 registros)**")
            # Mostrar últimos 10 registros en orden cronológico para el gráfico de línea
            df_tiempo = df_historial.iloc[::-1].tail(10)
            st.line_chart(df_tiempo.set_index("fecha")["rendimiento"], color="#29B5E8")

        # Mostrar tabla de historial completa con formato amigable
        st.write("---")
        st.write("🔍 **Tabla de Registros Guardados**")
        
        # Formatear el DataFrame para visualización
        df_visualizacion = df_historial.copy()
        df_visualizacion["rendimiento"] = df_visualizacion["rendimiento"].map(lambda x: f"{x:.2f}%")
        df_visualizacion["merma"] = df_visualizacion["merma"].map(lambda x: f"{x:.2f}%")
        df_visualizacion["kilos_crudos"] = df_visualizacion["kilos_crudos"].map(lambda x: f"{x:.2f} Kg")
        df_visualizacion["kilos_cocidos"] = df_visualizacion["kilos_cocidos"].map(lambda x: f"{x:.2f} Kg")
        
        # Renombrar columnas para que se vean profesionales
        df_visualizacion.rename(columns={
            "id": "ID",
            "fecha": "Fecha/Hora",
            "producto": "Producto",
            "kilos_crudos": "Kilos Crudos",
            "kilos_cocidos": "Kilos Cocidos",
            "rendimiento": "Rendimiento (%)",
            "merma": "Merma (%)",
            "notas": "Notas/Observaciones"
        }, inplace=True)
        
        st.dataframe(df_visualizacion, use_container_width=True, hide_index=True)
        
        # Herramientas de administración en expander
        with st.expander("🛠️ Herramientas de Administración (Historial)"):
            st.write("Si cometiste un error al registrar, puedes eliminar un registro ingresando su ID aquí:")
            id_eliminar = st.number_input("ID del registro a eliminar:", min_value=1, step=1, value=1)
            
            if st.button("❌ Eliminar Registro Permanentemente", type="secondary"):
                # Verificar si el ID existe en el dataframe original
                if id_eliminar in df_historial["id"].values:
                    eliminar_registro_horno(id_eliminar)
                    st.success(f"¡Registro con ID {id_eliminar} eliminado correctamente de la base de datos local!")
                    st.rerun()
                else:
                    st.error(f"No se encontró ningún registro con el ID {id_eliminar} en la base de datos.")

with tab2:
    categoria_seleccionada = st.selectbox("Selecciona una pestaña del inventario:", lista_pestanas)

    try:
        # Abrir la pestaña que seleccionó el usuario
        sheet = spreadsheet.worksheet(categoria_seleccionada)
        records = sheet.get_all_records()
        df = pd.DataFrame(records)
    except Exception as e:
        st.error(f"No se pudo encontrar la pestaña '{categoria_seleccionada}' en tu Google Sheet.")
        st.stop()

    if df.empty:
        st.warning(f"La pestaña '{categoria_seleccionada}' está vacía. Pega los datos correspondientes en Google Sheets.")
    else:
        actualizaciones = {}
        st.write("---")
        
        # Generar campos interactivos en columnas para mejor vista
        for idx, row in df.iterrows():
            col1, col2 = st.columns([3, 1])
            producto = row["Producto"]
            cantidad_actual = row["Cantidad"]
            clave_widget = f"{categoria_seleccionada}_{producto}_{idx}"
            
            with col1:
                st.write(f"**{producto}**")
            
            with col2:
                # Detectar decimales
                if isinstance(cantidad_actual, float) or (isinstance(cantidad_actual, str) and "." in cantidad_actual):
                    nueva_cantidad = st.number_input("Cant:", min_value=0.0, value=float(cantidad_actual), step=0.05, format="%.2f", key=clave_widget, label_visibility="collapsed")
                else:
                    try:
                        nueva_cantidad = st.number_input("Cant:", min_value=0, value=int(cantidad_actual), step=1, key=clave_widget, label_visibility="collapsed")
                    except:
                        nueva_cantidad = st.number_input("Cant:", min_value=0.0, value=float(cantidad_actual), step=0.05, key=clave_widget, label_visibility="collapsed")
                
            actualizaciones[idx] = nueva_cantidad

        st.write("---")
        if st.button("Guardar Cambios en esta Pestaña", type="primary", use_container_width=True):
            with st.spinner(f"Actualizando {categoria_seleccionada} en la nube..."):
                for idx, nueva_cant in actualizaciones.items():
                    fila_sheets = int(idx) + 2
                    sheet.update_cell(fila_sheets, 2, nueva_cant)
            st.success("¡Sincronizado con éxito!")
            st.rerun()

with tab1:
    st.subheader("🌐 Resumen General del Restaurante")
    
    # Botón para calcular resumen global (se hace bajo demanda para no saturar la API)
    if st.button("📊 Generar Reporte de Todo el Restaurante"):
        with st.spinner("Analizando todas las pestañas..."):
            total_critico_global = 0
            detalles_alertas = []
            
            for p in lista_pestanas:
                try:
                    temp_sheet = spreadsheet.worksheet(p)
                    temp_df = pd.DataFrame(temp_sheet.get_all_records())
                    if not temp_df.empty:
                        umbral_temp = 5 
                        criticos = temp_df[temp_df["Cantidad"] <= 5] # Simplificado para el resumen
                        if not criticos.empty:
                            total_critico_global += len(criticos)
                            detalles_alertas.append(f"**{p}**: {len(criticos)} productos bajos")
                except:
                    continue
            
            col_g1, col_g2 = st.columns(2)
            col_g1.metric("Alertas Globales", total_critico_global, delta_color="inverse")
            with col_g2:
                for d in detalles_alertas:
                    st.write(d)
    
    st.write("---")
    st.subheader(f"📊 Análisis de: {categoria_seleccionada}")
    
    if not df.empty:
        # Buscador para el dashboard
        busqueda = st.text_input("🔍 Buscar producto en el gráfico:", "")
        df_plot = df.copy()
        if busqueda:
            df_plot = df_plot[df_plot["Producto"].str.contains(busqueda, case=False)]

        # Gráfico de barras mejorado
        if not df_plot.empty:
            df_sorted = df_plot.sort_values(by="Cantidad", ascending=False)
            st.bar_chart(df_sorted.set_index("Producto")["Cantidad"], color="#FF4B4B")
        else:
            st.warning("No hay productos que coincidan con la búsqueda.")
        
        st.write("---")
        # Métricas expansibles
        with st.expander("📈 Ver detalles técnicos"):
            cols = st.columns(3)
            total_items = len(df)
            stock_critico = df[df["Cantidad"] <= (5 if "Kg" not in str(df["Producto"]) else 2.0)].shape[0]
            promedio_stock = df["Cantidad"].mean()
            
            cols[0].metric("Total Productos", total_items)
            cols[1].metric("Stock Crítico", stock_critico, delta_color="inverse")
            cols[2].metric("Promedio Stock", f"{promedio_stock:.2f}")

        # Resumen de alertas en el dashboard
        if stock_critico > 0:
            st.error(f"Tienes {stock_critico} productos en nivel crítico. Revisa el panel lateral.")

# Barra lateral con alertas de color
st.sidebar.header("⚠️ Alertas de Stock Bajo, por Categoría")
if not df.empty:
    for _, row in df.iterrows():
        umbral = 5 if "Kg" not in str(row["Producto"]) else 2.0
        try:
            cant = float(row["Cantidad"])
            if cant <= umbral:
                st.sidebar.error(f"🚨 {row['Producto']}: {cant}")
            elif cant <= umbral * 1.5:
                st.sidebar.warning(f"⚠️ {row['Producto']}: {cant}")
            else:
                st.sidebar.text(f"✅ {row['Producto']}: {cant}")
        except:
            st.sidebar.text(f"⚪ {row['Producto']}: {row['Cantidad']}")