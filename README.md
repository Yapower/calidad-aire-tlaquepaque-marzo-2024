# Tlaquepaque · marzo de 2024

Presentamos nuestro análisis retrospectivo como **Pollos Asados El ING**.

**Equipo 4 · Responsable de entrega: Eduardo Yoab Venegas García · Estación TLA.**

Integrantes: Eduardo Yoab Venegas García, Jonathan Emmanuel Alcantar López y Ana Yoseline Acosta Arreola.

## Reproducir

1. Instalar Python 3.10 o superior y las bibliotecas `pandas openpyxl numpy matplotlib reportlab`.
2. Ejecutar desde esta carpeta:

   ```bash
   python analizar_tlaquepaque.py "Hoja de cálculo sin título (1).xlsx" salida/
   ```

La ejecución genera `horas_procesadas.csv`, `dias_procesados.csv`, `resumen.json`, las dos visualizaciones y el reporte en PDF. También crea una copia con el nombre solicitado para la entrega de Sprint 1: `26B_AVI_d04_sp1_eq4_Venegas_Garcia_Eduardo_Yoab.pdf`.

## Datos y alcance

Nuestra hoja corregida contiene 744 horas sin duplicados de marzo de 2024. Disponemos de datos de O3 (665 horas), PM10 (686), PM2.5 (440), temperatura interna IT (744) y velocidad del viento WS (651). **ET, RH y WD están vacías**. No tenemos documentada la unidad del viento y evitamos inventar o interpolar estas variables.

Calculamos O3 horario, NowCast de 12 horas para partículas y resúmenes diarios. Conservamos los empates de categoría y exigimos 18 horas para la cobertura diaria de partículas; sólo 4 días tienen cobertura simultánea de los tres contaminantes. Explicamos las demás limitaciones en el reporte. Aplicamos retrospectivamente la NOM-172-SEMARNAT-2023 y sus bandas de partículas correspondientes a la etapa de 2024.

## Uso para Pollos Asados El ING

Nuestra pollería está a **dos cuadras de la estación TLA**. Distinguimos las lecturas exteriores de la calidad del aire de nuestro local. Proponemos agilizar la atención exterior durante episodios y mejorar la operación del asador: extracción, limpieza de grasa, mantenimiento y control del humo evitable. Para evaluar nuestra contribución necesitamos registros de producción y mediciones adicionales; las lecturas de TLA por sí solas no permiten atribuirnos las concentraciones ni cuantificar nuestras emisiones.

Fuentes: [SEMADET, datos históricos](https://aire.jalisco.gob.mx/Dhistoricos), [NOM-172-SEMARNAT-2023](https://sinaica.inecc.gob.mx/archivo/noms/NOM-172-SEMARNAT-2023-Indice-AIRE-y-SALUD.pdf) y [EPA, partículas generadas al cocinar y medidas de control](https://www.epa.gov/indoor-air-quality-iaq/sources-indoor-particulate-matter-pm).

Incluimos una bitácora **propuesta** para que cada integrante valide las actividades y el cumplimiento antes de entregarla. Usamos `sp1` en el nombre del PDF porque la consigna llama a esta entrega la versión final del Sprint 1; el apartado de bitácora menciona Sprint 2 y queda pendiente de confirmación.

Repositorio: https://github.com/Yapower/calidad-aire-tlaquepaque-marzo-2024
