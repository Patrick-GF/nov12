"""Perfil Conductor Operativo: check-in / reporte de estado del vehículo."""
import pandas as pd
import streamlit as st

from core.auth import exigir_rol
from core.db import tabla
from core.flota import registrar_reporte
from core.storage import subir_evidencia

NEUMATICOS = ["Normal", "Presión baja (leve)", "Presión severamente baja"]
FRENOS = ["Normal", "Falla / sin respuesta"]


def checkin() -> None:
    usuario = exigir_rol("conductor")
    rut = usuario["rut_conductor"]
    st.title("📝 Check-in operativo")

    autorizadas = (
        tabla("autorizaciones").select("patente").eq("rut_conductor", rut).eq("vigente", True).execute().data
    )
    patentes = [a["patente"] for a in autorizadas]
    if not patentes:
        st.warning("No tienes vehículos con autorización vigente. Contacta al Puesto de Mando.")
        return
    vehiculos = {
        v["patente"]: v
        for v in tabla("vehiculos")
        .select("patente,marca_modelo,tipo_vehiculo,kilometraje_actual,estado_operativo")
        .in_("patente", patentes)
        .execute()
        .data
    }

    # El selector va FUERA del formulario: al cambiar de vehículo la página se recalcula
    # y el kilometraje mínimo/por defecto corresponde al vehículo elegido.
    patente = st.selectbox(
        "Vehículo", patentes,
        format_func=lambda p: f"{p} · {vehiculos[p]['marca_modelo']} ({vehiculos[p]['estado_operativo']})",
    )
    km_min = int(vehiculos[patente]["kilometraje_actual"])

    with st.form("checkin", clear_on_submit=True):
        km = st.number_input(
            f"Kilometraje (último registrado: {km_min:,} km)",
            min_value=0, value=km_min, step=1, key=f"km_{patente}",
        )
        combustible = st.slider("Nivel de combustible (%)", 0, 100, 50, step=5)
        c1, c2 = st.columns(2)
        neumaticos = c1.selectbox("Estado de neumáticos", NEUMATICOS)
        frenos = c2.selectbox("Sistema de frenos", FRENOS)
        luces = st.checkbox("Luces operativas", value=True)
        observaciones = st.text_area("Novedades mecánicas / observaciones")
        foto = st.file_uploader("Foto del odómetro (obligatoria)", type=["jpg", "jpeg", "png", "webp"])
        enviar = st.form_submit_button("Enviar reporte", type="primary", width="stretch")

    if enviar:
        if km < km_min:
            st.error(f"El kilometraje no puede ser menor al último registrado ({km_min:,} km).")
        elif foto is None:
            st.error("Adjunta la fotografía del odómetro.")
        else:
            try:
                ruta = subir_evidencia("odometros", patente, foto.getvalue())
                resultado = registrar_reporte(
                    patente=patente, rut=rut, km=int(km), combustible=combustible,
                    neumaticos_ok=neumaticos == NEUMATICOS[0], neumaticos_severo=neumaticos == NEUMATICOS[2],
                    luces_ok=luces, frenos_falla=frenos != FRENOS[0],
                    observaciones=observaciones, foto_ruta=ruta,
                )
            except Exception as e:
                st.error(f"No se pudo enviar el reporte: {e}")
            else:
                if resultado["motivos"]:
                    st.error(
                        f"Parámetro crítico detectado ({'; '.join(resultado['motivos'])}). "
                        + (f"El vehículo {patente} pasó automáticamente a **Requiere Mantención**."
                           if resultado["estado_cambiado"] else f"El vehículo {patente} ya figuraba fuera de servicio.")
                    )
                else:
                    st.success("Reporte registrado correctamente.")

    st.divider()
    st.subheader("Mis últimos reportes")
    ultimos = (
        tabla("reportes_estado")
        .select("fecha_reporte,patente,kilometraje_salida,nivel_combustible,observaciones")
        .eq("rut_conductor", rut)
        .order("fecha_reporte", desc=True)
        .limit(5)
        .execute()
        .data
    )
    if ultimos:
        st.dataframe(pd.DataFrame(ultimos), width="stretch", hide_index=True)
    else:
        st.caption("Aún no has enviado reportes.")
