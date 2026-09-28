"""Análisis reproducible de la estación TLA, marzo de 2024.

Uso: python analizar_tlaquepaque.py 'Hoja de cálculo sin título.xlsx' salida/
Dependencias: pandas, openpyxl, matplotlib, reportlab.
"""
from __future__ import annotations

import json
import math
import shutil
import sys
from collections import Counter
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak, KeepTogether

CATS = ["Buena", "Aceptable", "Mala", "Muy mala", "Extremadamente mala"]
COLORS = ["#54aa66", "#f1c74b", "#ef9448", "#d65d57", "#9170aa"]
THRESH = {"PM10": [45, 60, 132, 213], "PM2.5": [15, 33, 79, 130], "O3": [.058, .090, .135, .175]}
SOURCE = "https://aire.jalisco.gob.mx/Dhistoricos"
NOM = "https://sinaica.inecc.gob.mx/archivo/noms/NOM-172-SEMARNAT-2023-Indice-AIRE-y-SALUD.pdf"
REPO = "https://github.com/Yapower/calidad-aire-tlaquepaque-marzo-2024"

def rnd(value, decimals=0):
    if pd.isna(value):
        return np.nan
    unit = Decimal('1').scaleb(-decimals)
    return float(Decimal(str(value)).quantize(unit, rounding=ROUND_HALF_UP))

def classify(value, pollutant):
    if pd.isna(value):
        return np.nan
    for i, limit in enumerate(THRESH[pollutant]):
        if value <= limit:
            return i
    return 4

def nowcast(values, factor):
    """Últimas 12 posiciones horarias, preservando el exponente de cada hueco."""
    if len(values) < 12:
        return np.nan  # Sin febrero, no hay una ventana completa al inicio del archivo.
    a = list(values)[::-1]
    if sum(pd.notna(x) for x in a[:3]) < 2:
        return np.nan
    valid = [x for x in a if pd.notna(x)]
    high, low = max(valid), min(valid)
    w = 1 if high == 0 else max(.5, rnd(low / high, 2))
    weights = [w ** i for i, x in enumerate(a) if pd.notna(x)]
    return rnd(factor * sum(x * w ** i for i, x in enumerate(a) if pd.notna(x)) / sum(weights))

def fmt(value, decimals=0):
    return 's/d' if pd.isna(value) else f'{value:.{decimals}f}'

def para(text, style):
    return Paragraph(text, style)

def run(source: Path, out: Path):
    out.mkdir(parents=True, exist_ok=True)
    raw = pd.read_excel(source)
    d = pd.DataFrame({"estacion": raw['STATION'], "fecha_hora": pd.to_datetime(raw['DATE']),
        "O3_ppm": raw['O3'], "PM10_ug_m3": raw['PM10'], "PM25_ug_m3": raw['PM2.5'],
        "temperatura_interna_C": raw['IT'], "velocidad_viento": raw['WS'],
        "temperatura_ambiente_C": raw['ET'], "humedad_relativa_pct": raw['RH'],
        "direccion_viento_grados": raw['WD']})
    assert len(d) == 744 and d.estacion.eq('TLA').all()
    assert d.fecha_hora.is_unique
    assert d.fecha_hora.tolist() == list(pd.date_range('2024-03-01', '2024-03-31 23:00', freq='h'))
    for c in d.columns[2:]:
        d[c] = pd.to_numeric(d[c], errors='coerce')
    for c in ['O3_ppm', 'PM10_ug_m3', 'PM25_ug_m3', 'velocidad_viento']:
        assert not d[c].dropna().lt(0).any(), c
    # La unidad de WS no consta en la hoja: conservar la magnitud sin asignarla.
    for pol, col, factor in [('PM10', 'PM10_ug_m3', .38), ('PM2.5', 'PM25_ug_m3', .5)]:
        vals = d[col].tolist()
        d[pol+'_indicador_h'] = [nowcast(vals[max(0,i-11):i+1], factor) for i in range(len(vals))]
    d['O3_indicador_h'] = d.O3_ppm.map(lambda x: rnd(x, 3))
    for pol in THRESH:
        d[pol+'_cat_h'] = d[pol+'_indicador_h'].map(lambda x: classify(x, pol))
    catcols = [p+'_cat_h' for p in THRESH]
    d['categoria_h_id'] = d[catcols].max(axis=1)
    d['categoria_h'] = d.categoria_h_id.map(lambda x: CATS[int(x)] if pd.notna(x) else 'Sin información')
    d['dominantes_h'] = d.apply(lambda r: ', '.join(p for p in THRESH if pd.notna(r[p+'_cat_h']) and r[p+'_cat_h'] == r.categoria_h_id), axis=1)
    d['fecha'] = d.fecha_hora.dt.date
    d.to_csv(out/'horas_procesadas.csv', index=False, encoding='utf-8-sig')

    records = []
    for date, g in d.groupby('fecha'):
        row = {'fecha':str(date)}
        for pol, col in [('PM10','PM10_ug_m3'), ('PM2.5','PM25_ug_m3')]:
            row[pol+'_horas_validas'] = int(g[col].count())
            row[pol+'_indicador_d'] = rnd(g[col].mean()) if g[col].count() >= 18 else np.nan
        row['O3_horas_validas'] = int(g.O3_ppm.count())
        row['O3_indicador_d'] = rnd(g.O3_ppm.max(), 3) if g.O3_ppm.count() else np.nan
        for pol in THRESH:
            row[pol+'_cat_d'] = classify(row[pol+'_indicador_d'], pol)
        valid = [row[pol+'_cat_d'] for pol in THRESH if pd.notna(row[pol+'_cat_d'])]
        row['categoria_d_id'] = max(valid) if valid else np.nan
        row['categoria_d'] = CATS[int(max(valid))] if valid else 'Sin información'
        row['dominantes_d'] = ', '.join(pol for pol in THRESH if pd.notna(row[pol+'_cat_d']) and row[pol+'_cat_d']==row['categoria_d_id'])
        row['cobertura_3_contaminantes'] = all(pd.notna(row[pol+'_cat_d']) for pol in THRESH)
        records.append(row)
    daily = pd.DataFrame(records)
    daily.to_csv(out/'dias_procesados.csv', index=False, encoding='utf-8-sig')
    counts = Counter(daily.categoria_d)
    days_by_pol = {p: int(daily.dominantes_d.str.split(', ').map(lambda items: p in items).sum()) for p in THRESH}
    # 28 de marzo: episodio observado de O3 con cambio de Buena a Mala y regreso.
    event_day = pd.Timestamp('2024-03-28').date()
    episode = d[d.fecha==event_day]

    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':9})
    fig, axs = plt.subplots(2, 1, figsize=(10.7, 5.7), sharex=True, gridspec_kw={'height_ratios':[2,1.1]})
    for pol, col, color in [('PM10','PM10_ug_m3','#d87039'), ('PM2.5','PM25_ug_m3','#8048a2')]:
        axs[0].plot(episode.fecha_hora.dt.hour, episode[col], marker='.', label=pol+' medido',color=color,alpha=.5)
        axs[0].plot(episode.fecha_hora.dt.hour, episode[pol+'_indicador_h'],label=pol+' indicador',color=color,linewidth=2)
    axs[0].set_ylabel('Partículas (µg/m³)'); axs[0].legend(ncol=2,fontsize=8,loc='upper left');axs[0].grid(alpha=.2)
    ax2=axs[0].twinx(); ax2.plot(episode.fecha_hora.dt.hour, episode.O3_ppm*1000,color='#2c7893',linewidth=1.5,label='O₃ (ppb)')
    ax2.set_ylabel('O₃ (ppb)'); ax2.legend(loc='upper right',fontsize=8)
    axs[1].step(episode.fecha_hora.dt.hour, episode.categoria_h_id,where='mid',color='#273342',linewidth=1.5)
    axs[1].scatter(episode.fecha_hora.dt.hour,episode.categoria_h_id,c=[COLORS[int(v)] if pd.notna(v) else '#aaaaaa' for v in episode.categoria_h_id],s=35)
    axs[1].set_yticks(range(5), ['Buena','Aceptable','Mala','Muy mala','Extrema']);axs[1].set_xticks(range(0,24,2));axs[1].set_xlabel('Hora local del archivo');axs[1].grid(alpha=.2)
    fig.suptitle('Evolución horaria · '+str(event_day));fig.tight_layout();fig.savefig(out/'evolucion_horaria.png',dpi=170);plt.close(fig)

    fig, ax=plt.subplots(figsize=(10.7,5.0));ax.set_xlim(0,7);ax.set_ylim(5,0)
    for i,weekday in enumerate(['Lun','Mar','Mié','Jue','Vie','Sáb','Dom']):
        ax.text(i+.5,-.12,weekday,ha='center',fontsize=10,fontweight='bold')
    for _,r in daily.iterrows():
        day=int(r.fecha[-2:]);cell=4+day-1;column,row=cell%7,cell//7
        level=int(r.categoria_d_id) if pd.notna(r.categoria_d_id) else 0
        ax.add_patch(plt.Rectangle((column+.04,row+.04),.92,.91,color=COLORS[level],alpha=.94))
        ax.text(column+.17,row+.33,str(day),ha='left',va='center',fontsize=12,fontweight='bold')
        ax.text(column+.5,row+.7,r.dominantes_d.replace('PM2.5','PM₂.₅').replace('PM10','PM₁₀').replace('O3','O₃'),ha='center',va='center',fontsize=7.2)
    ax.set_xticks([]);ax.set_yticks([]);[spine.set_visible(False) for spine in ax.spines.values()]
    ax.set_title('Marzo de 2024 · color = categoría diaria; texto = responsables',pad=21)
    fig.tight_layout();fig.savefig(out/'matriz_diaria.png',dpi=170,bbox_inches='tight');plt.close(fig)

    pdfmetrics.registerFont(TTFont('DejaVu','/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'))
    pdfmetrics.registerFont(TTFont('DejaVu-Bold','/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'))
    pdfmetrics.registerFontFamily('DejaVu',normal='DejaVu',bold='DejaVu-Bold',italic='DejaVu',boldItalic='DejaVu-Bold')
    styles=getSampleStyleSheet()
    styles.add(ParagraphStyle(name='TitleX',parent=styles['Title'],fontName='DejaVu-Bold',fontSize=16,leading=21,textColor=colors.HexColor('#263c49'),spaceAfter=16))
    styles.add(ParagraphStyle(name='H1X',parent=styles['Heading2'],fontName='DejaVu-Bold',fontSize=11,leading=15,textColor=colors.HexColor('#263c49'),spaceBefore=11,spaceAfter=6))
    styles.add(ParagraphStyle(name='BodyX',parent=styles['BodyText'],fontName='DejaVu',fontSize=8.8,leading=13,spaceAfter=7))
    styles.add(ParagraphStyle(name='SmallX',parent=styles['BodyText'],fontName='DejaVu',fontSize=7.3,leading=10,spaceAfter=4))
    styles.add(ParagraphStyle(name='TableX',parent=styles['BodyText'],fontName='DejaVu',fontSize=8,leading=10))
    p=lambda text:para(text,styles['BodyX'])
    h=lambda text:para(text,styles['H1X'])
    story=[para('Marzo de 2024 · Calidad del aire en Tlaquepaque',styles['TitleX']),
           p('<b>Presentamos:</b> Pollos Asados El ING &nbsp; | &nbsp; <b>Equipo:</b> 4 &nbsp; | &nbsp; <b>Estación:</b> TLA'),
           p('<b>Responsable de entrega:</b> Eduardo Yoab Venegas García &nbsp; | &nbsp; <b>Alcance:</b> análisis retrospectivo'),
           p('<b>Integrantes:</b> Eduardo Yoab Venegas García, Jonathan Emmanuel Alcantar López y Ana Yoseline Acosta Arreola.'),
           p('<b>Estado de nuestro reporte:</b> completamos un análisis reproducible de los contaminantes disponibles. Nos faltan temperatura ambiente, humedad relativa, dirección del viento y el registro de participación para cumplir íntegramente la consigna.'),
           h('1. Fuente y preparación'),
           p('Trabajamos con nuestra hoja corregida de 744 horas consecutivas, del 1 al 31 de marzo, sin duplicados. Identificamos nuestra estación TLA mediante el campo STATION. Conservamos los campos ausentes como faltantes, sin interpolarlos. También preservamos los valores altos no negativos para revisarlos: con la información disponible no pudimos confirmar errores instrumentales.'),
           p('Interpretamos O₃ en ppm y PM₁₀ y PM₂.₅ en µg/m³, las unidades de las bandas de la norma, aunque debemos confirmarlas con metadatos del archivo. Distinguimos IT, temperatura interna del instrumento, de ET, temperatura ambiente. La hoja no indica la unidad de WS, velocidad del viento, por lo que evitamos asignársela.'),
           ]
    rows=[["Campo", "Con dato / 744", "Observación"]]
    for name,col,remark in [('O₃','O3_ppm','medición horaria'),('PM₁₀','PM10_ug_m3','medición horaria'),('PM₂.₅','PM25_ug_m3','adicional'),('IT','temperatura_interna_C','no es temperatura ambiente'),('ET','temperatura_ambiente_C','sin registros'),('RH','humedad_relativa_pct','sin registros'),('WS','velocidad_viento','unidad no indicada'),('WD','direccion_viento_grados','sin registros')]:
        rows.append([name,str(d[col].count()),remark])
    table=Table(rows,colWidths=[2.5*cm,3.1*cm,10.2*cm],repeatRows=1)
    table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e8eef2')),('LINEBELOW',(0,0),(-1,0),.6,colors.grey),('BOTTOMPADDING',(0,0),(-1,-1),5),('TOPPADDING',(0,0),(-1,-1),5),('FONTSIZE',(0,0),(-1,-1),8),('FONTNAME',(0,0),(-1,-1),'DejaVu')]))
    story += [table,h('2. Cálculo y alcance normativo'),
      p('Aplicamos retrospectivamente la NOM-172-SEMARNAT-2023 a las mediciones de marzo, aunque la actualización entró en vigor el 23 de julio de 2024. Para cada hora utilizamos O₃ de una hora y, para partículas, el promedio móvil ponderado de hasta 12 horas con factores 0.38 (PM₁₀) y 0.50 (PM₂.₅); exigimos al menos dos de las tres horas recientes. Para cada día calculamos la media de PM con al menos 18 mediciones y el máximo horario de O₃. Redondeamos PM a enteros y O₃ a tres decimales. Aplicamos las bandas de PM de la etapa «a partir de enero de 2024» de la NOM.'),
      p('Asignamos la categoría global según la peor banda válida de los tres contaminantes disponibles y registramos a todos los responsables cuando hay empate. Consideramos <b>parcial</b> la categoría diaria si falta cobertura de algún contaminante, pues podría subestimar el estado real. No contamos con NO₂, SO₂ ni CO, así que nuestro resultado no abarca todos los contaminantes criterio.'),PageBreak(),
      h('3. Numeralia de marzo'),
      p(f'Analizamos <b>31</b> días con alguna categoría calculable; en <b>{int(daily.cobertura_3_contaminantes.sum())}</b> tuvimos cobertura de los tres contaminantes. Encontramos que la categoría más frecuente fue <b>{counts.most_common(1)[0][0]}</b> ({counts.most_common(1)[0][1]} días).')]
    rr=[["Categoría","Días"]]+[[cat,str(counts.get(cat,0))] for cat in CATS]
    t=Table(rr,colWidths=[8*cm,3*cm]);t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e8eef2')),('FONTSIZE',(0,0),(-1,-1),9),('FONTNAME',(0,0),(-1,-1),'DejaVu'),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#f6f8fa')]),('BOTTOMPADDING',(0,0),(-1,-1),7)]))
    story += [t,p('Contamos estos días en los que cada contaminante fue responsable de la peor banda (incluidos empates): '+', '.join(f'{pol}: {n}' for pol,n in days_by_pol.items())+'.'),
      Image(str(out/'matriz_diaria.png'),width=16.8*cm,height=7.85*cm),
      para('Cuando mostramos dos etiquetas, ambos contaminantes empataron en categoría. Elegimos un calendario para localizar los días, identificar el contaminante y comparar la gravedad sin reducir todo marzo a un solo promedio.',styles['SmallX'])]
    worst=daily[daily.categoria_d_id==daily.categoria_d_id.max()]
    story += [p('Identificamos estos días con la banda diaria más desfavorable ('+CATS[int(daily.categoria_d_id.max())]+'): '+', '.join(r.fecha[-2:]+' ('+r.dominantes_d+')' for _,r in worst.iterrows())+'.'),PageBreak(),
      h('4. Simulación de recepción horaria'),
      p(f'Simulamos la llegada de las 24 horas del {event_day}. En cada paso incorporamos únicamente la hora recién recibida y las anteriores, sin usar información futura. En la gráfica distinguimos la concentración medida del indicador móvil de partículas; mostramos en cada hora la categoría más desfavorable que podíamos calcular hasta ese momento.'),
      Image(str(out/'evolucion_horaria.png'),width=16.8*cm,height=8.95*cm)]
    ev=episode[['fecha_hora','O3_ppm','PM10_ug_m3','PM25_ug_m3','PM10_indicador_h','PM2.5_indicador_h','categoria_h','dominantes_h','velocidad_viento']]
    transitions=[];prev=None
    for _,r in ev.iterrows():
        if prev is not None and r.categoria_h != prev:
            transitions.append(f"{r.fecha_hora:%H:%M}: {prev} → {r.categoria_h} ({r.dominantes_h})")
        prev=r.categoria_h
    story += [p('<b>Cambios de categoría:</b> '+('; '.join(transitions) if transitions else 'no hubo cambios')+'.'),
      h('Secuencia observada · horas 10 a 20'),
      ]
    display=ev[(ev.fecha_hora.dt.hour>=10)&(ev.fecha_hora.dt.hour<=20)]
    rr=[["Hora","O₃ ppm","PM₁₀ µg/m³","Ind. PM₁₀","Banda / responsable","WS*"]]
    for _,r in display.iterrows():
        rr.append([r.fecha_hora.strftime('%H:%M'),fmt(r.O3_ppm,3),fmt(r.PM10_ug_m3),fmt(r.PM10_indicador_h),r.categoria_h+' / '+r.dominantes_h,fmt(r.velocidad_viento,2)])
    t=Table(rr,colWidths=[1.5*cm,2*cm,2.4*cm,2.1*cm,6.1*cm,1.7*cm],repeatRows=1)
    t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e8eef2')),('FONTSIZE',(0,0),(-1,-1),7.5),('FONTNAME',(0,0),(-1,-1),'DejaVu'),('BOTTOMPADDING',(0,0),(-1,-1),4),('TOPPADDING',(0,0),(-1,-1),4),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#f6f8fa')])]))
    story += [t,para('*WS: velocidad del viento, unidad no documentada. «Ind.»: indicador ponderado de PM₁₀.',styles['SmallX']),
      p('En cada hora conocimos las concentraciones presentes y anteriores, la velocidad del viento cuando estuvo disponible y la categoría calculada. Sólo al terminar el día pudimos establecer su resumen. Sin humedad, dirección del viento ni temperatura ambiente no podemos evaluar su relación con el episodio. En una situación similar comunicaríamos hora, banda, contaminante y cobertura de datos, junto con las recomendaciones oficiales de exposición; no atribuimos el episodio a una fuente específica.'),PageBreak(),
      h('5. Qué decisiones podemos tomar en nuestra pollería'),
      p('<b>Nuestra pollería, Pollos Asados El ING, está a dos cuadras de la estación TLA.</b> Por esa cercanía utilizamos las lecturas exteriores como referencia local, aunque reconocemos que la estación no mide el aire de nuestra cocina ni de nuestra entrada. El 28 de marzo O₃ alcanzó la categoría Mala entre las 14:00 y las 17:00. Si observáramos una lectura actual semejante, reduciríamos la espera de nuestros clientes afuera, agilizaríamos la recogida y reorganizaríamos las tareas exteriores. Para comunicar recomendaciones de salud al público nos apoyaríamos en los avisos de la autoridad competente.'),
      p('<b>Acciones sobre nuestra producción:</b> reconocemos que al asar pollos podemos generar partículas y humo, especialmente durante la combustión y cuando la grasa cae sobre el fuego. Mantendríamos la extracción funcionando durante la cocción, limpiaríamos la grasa acumulada y daríamos mantenimiento a campana, ductos y filtros. Evitaríamos llamas innecesarias y alimento quemado. Revisaríamos con personal técnico la ventilación y, cuando sea viable, combustibles o equipos con menores emisiones. En horas de mala calidad del aire planearíamos tandas eficientes y reduciríamos el humo evitable; una categoría Mala por O₃, por sí sola, no demuestra que debamos suspender la producción ni que nuestro asador la haya causado.'),
      p('<b>Seguimiento para decidir:</b> registraríamos horarios y cantidad de pollos asados, combustible, limpieza y episodios visibles de humo. Compararíamos esos registros con PM₁₀, PM₂.₅ y O₃ de TLA y, si contamos con equipo adecuado, mediríamos dentro y cerca de nuestro local. Usaríamos el calendario para revisar los días 13, 27 y 28 y la serie horaria para decidir cuándo ajustar la operación. Con estos datos históricos no podemos cuantificar nuestras emisiones, la exposición del personal ni nuestra contribución a las lecturas de TLA. También nos falta la dirección del viento para evaluar una posible relación espacial.'),
      h('Limitaciones'),
      p(f'Nos faltó PM₂.₅ en {744-int(d.PM25_ug_m3.count())} horas. Basamos las categorías en tres contaminantes de los seis previstos. Nuestra hoja no incluye banderas instrumentales ni datos minuto a minuto para comprobar el criterio de 45 minutos por hora; por ello utilizamos los promedios horarios recibidos. No tenemos las horas de febrero necesarias para completar el NowCast al inicio del periodo. Aplicamos retrospectivamente una edición normativa posterior a las mediciones. En los empates no podemos asignar un solo contaminante responsable.'),
      PageBreak(),h('Bitácora del líder · propuesta para validación'),
      ]
    log_rows=[['Integrante','Actividades propuestas','Cumplimiento','Observaciones propuestas'],
      ['Eduardo Yoab Venegas García','Integración del análisis, revisión de la NOM y organización del reporte y repositorio.','Completo','Coordinación y seguimiento constante de las entregas.'],
      ['Jonathan Emmanuel Alcantar López','Revisión del archivo TLA, valores faltantes y elaboración de la serie horaria.','Completo','Muy buen trabajo, participación activa y cuidado al revisar los datos.'],
      ['Ana Yoseline Acosta Arreola','Apoyo en calendario diario, interpretación para la pollería y revisión de las conclusiones.','Completo','Muy buen trabajo, aportaciones claras y colaboración continua.']]
    log_table=Table([[para(str(cell),styles['TableX']) for cell in row] for row in log_rows],colWidths=[3.8*cm,5.4*cm,2.4*cm,5.2*cm],repeatRows=1,hAlign='LEFT')
    log_table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e8eef2')),('GRID',(0,0),(-1,-1),.35,colors.HexColor('#d5dfe5')),('VALIGN',(0,0),(-1,-1),'TOP'),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#f6f8fa')]),('LEFTPADDING',(0,0),(-1,-1),6),('RIGHTPADDING',(0,0),(-1,-1),6),('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7)]))
    story += [log_table,
      p('<b>Valoración general propuesta:</b> trabajamos muy bien como equipo: repartimos tareas, colaboramos en la revisión y reunimos el análisis en un reporte reproducible. Para el siguiente sprint debemos mejorar la documentación de metadatos, conseguir las variables meteorológicas faltantes y registrar con mayor detalle las evidencias de participación.'),
      p('La consigna menciona Sprint 1 como entrega final y Sprint 2 para la bitácora. Usamos <b>sp1</b> en el nombre del archivo por la indicación de entrega final del Sprint 1; recomendamos confirmar a cuál sprint debe corresponder la bitácora.'),
      h('Reproducción y fuentes'),
      p('Para reproducir nuestro análisis ejecutamos: <font name="DejaVu">python analizar_tlaquepaque.py "Hoja de cálculo sin título (1).xlsx" salida/</font>. Obtenemos dos CSV de indicadores, dos gráficas y este PDF. Compartimos el libro corregido y los resultados en '+REPO+'.'),
      para('Nuestra fuente de datos: hoja TLA, marzo de 2024. Portal de bases históricas de SEMADET: '+SOURCE+'<br/>Norma NOM-172-SEMARNAT-2023 (tablas 2–6 y Anexo A): '+NOM+'<br/>EPA, fuentes de partículas y medidas durante la cocción: https://www.epa.gov/indoor-air-quality-iaq/sources-indoor-particulate-matter-pm',styles['SmallX'])]
    pdf=out/'Reporte_Tlaquepaque_Pollos_Asados_El_ING.pdf'
    doc=SimpleDocTemplate(str(pdf),pagesize=(21*cm,29.7*cm),leftMargin=2*cm,rightMargin=2*cm,topMargin=1.7*cm,bottomMargin=1.5*cm)
    doc.build(story,onFirstPage=footer,onLaterPages=footer)
    shutil.copyfile(pdf,out/'26B_AVI_d04_sp1_eq4_Venegas_Garcia_Eduardo_Yoab.pdf')
    summary={'days':len(daily),'counts':dict(counts),'dominants_including_ties':days_by_pol,'full_coverage_days':int(daily.cobertura_3_contaminantes.sum()),'event_day':str(event_day),'worst_days':worst[['fecha','dominantes_d']].to_dict('records')}
    (out/'resumen.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False,indent=2))

def footer(canvas,doc):
    canvas.saveState();canvas.setFont('DejaVu',8);canvas.setFillColor(colors.grey)
    canvas.drawString(2*cm,1*cm,'Pollos Asados El ING · Equipo 4 · Estación TLA · Marzo 2024')
    canvas.drawRightString(19*cm,1*cm,str(doc.page));canvas.restoreState()

if __name__=='__main__':
    run(Path(sys.argv[1]),Path(sys.argv[2]))
