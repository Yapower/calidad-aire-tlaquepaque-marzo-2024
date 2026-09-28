# Tlaquepaque · marzo de 2024

Análisis retrospectivo para la agencia ficticia **Pollos Asados El ING**.

## Reproducir

1. Instalar Python 3.10 o superior y las bibliotecas `pandas openpyxl numpy matplotlib reportlab`.
2. Ejecutar desde esta carpeta:

   ```bash
   python analizar_tlaquepaque.py "Hoja de cálculo sin título (1).xlsx" salida/
   ```

La ejecución genera `horas_procesadas.csv`, `dias_procesados.csv`, `resumen.json`, las dos visualizaciones y el reporte en PDF.

## Datos y alcance

La hoja corregida contiene 744 horas sin duplicados de marzo de 2024. Existen datos de O3 (665 horas), PM10 (686), PM2.5 (440), temperatura interna IT (744) y velocidad del viento WS (651). **ET, RH y WD están vacías**. La velocidad del viento no tiene unidad documentada. No se inventan ni interpolan estas variables.

La clasificación calcula O3 horario, NowCast de 12 horas para partículas y resúmenes diarios. Conserva los empates de categoría. La cobertura diaria de partículas requiere 18 horas; sólo 4 días tienen cobertura simultánea de los tres contaminantes. El reporte explica las demás limitaciones. Se usa retrospectivamente la NOM-172-SEMARNAT-2023 y sus bandas de partículas correspondientes a la etapa de 2024.

Fuentes: [SEMADET, datos históricos](https://aire.jalisco.gob.mx/Dhistoricos) y [NOM-172-SEMARNAT-2023](https://sinaica.inecc.gob.mx/archivo/noms/NOM-172-SEMARNAT-2023-Indice-AIRE-y-SALUD.pdf).

Antes de la entrega escolar, completar la bitácora real del líder y confirmar el equipo y la nomenclatura Sprint 1/Sprint 2.

Repositorio: https://github.com/Yapower/calidad-aire-tlaquepaque-marzo-2024
