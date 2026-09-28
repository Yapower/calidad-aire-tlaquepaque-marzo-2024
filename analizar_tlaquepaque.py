"""Análisis reproducible de la estación TLA, marzo de 2024.

Uso: python analizar_tlaquepaque.py 'Hoja de cálculo sin título.xlsx' salida/
Dependencias: pandas, openpyxl, matplotlib, reportlab.
"""
from __future__ import annotations

import json
import math
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
           p('<b>Agencia ficticia:</b> Pollos Asados El ING &nbsp; | &nbsp; <b>Estación:</b> TLA &nbsp; | &nbsp; <b>Alcance:</b> análisis retrospectivo'),
           p('<b>Estado de esta versión:</b> análisis de contaminantes reproducible. Faltan temperatura ambiente, humedad relativa, dirección del viento y registro de participación para cumplir íntegramente la consigna.'),
           h('1. Fuente y preparación'),
           p('La hoja corregida proporcionada por el equipo contiene 744 horas consecutivas, del 1 al 31 de marzo, sin duplicados. El campo STATION identifica TLA. Los campos ausentes se conservaron como faltantes, sin interpolación. Se preservaron todos los valores altos no negativos para revisión; no se confirmó error instrumental con la información disponible.'),
           p('Concentraciones registradas: O₃ en ppm; PM₁₀ y PM₂.₅ en µg/m³ (unidades de las bandas de la norma, pendientes de confirmar con metadatos del archivo). IT corresponde a temperatura interna del instrumento, no a temperatura ambiente ET. WS es velocidad de viento, pero la hoja no indica su unidad. No se atribuyen unidades a columnas sin metadatos.'),
           ]
    rows=[["Campo", "Con dato / 744", "Observación"]]
    for name,col,remark in [('O₃','O3_ppm','medición horaria'),('PM₁₀','PM10_ug_m3','medición horaria'),('PM₂.₅','PM25_ug_m3','adicional'),('IT','temperatura_interna_C','no es temperatura ambiente'),('ET','temperatura_ambiente_C','sin registros'),('RH','humedad_relativa_pct','sin registros'),('WS','velocidad_viento','unidad no indicada'),('WD','direccion_viento_grados','sin registros')]:
        rows.append([name,str(d[col].count()),remark])
    table=Table(rows,colWidths=[2.5*cm,3.1*cm,10.2*cm],repeatRows=1)
    table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e8eef2')),('LINEBELOW',(0,0),(-1,0),.6,colors.grey),('BOTTOMPADDING',(0,0),(-1,-1),5),('TOPPADDING',(0,0),(-1,-1),5),('FONTSIZE',(0,0),(-1,-1),8),('FONTNAME',(0,0),(-1,-1),'DejaVu')]))
    story += [table,h('2. Cálculo y alcance normativo'),
      p('Se aplicó retrospectivamente la NOM-172-SEMARNAT-2023 a mediciones de marzo, aunque la actualización entró en vigor el 23 de julio de 2024. Para cada hora se usó O₃ de una hora y, para partículas, el promedio móvil ponderado de hasta 12 horas con factores 0.38 (PM₁₀) y 0.50 (PM₂.₅); se exige al menos dos de las tres horas recientes. Para cada día: media de PM con al menos 18 mediciones y máximo horario de O₃. El redondeo es a entero para PM y a tres decimales para O₃. Se aplicaron bandas de PM para la etapa «a partir de enero de 2024» de las tablas de la NOM.'),
      p('La categoría global corresponde a la peor banda válida entre los tres contaminantes disponibles; los empates se registran con todos sus responsables. Una categoría de día con algún contaminante sin cobertura es <b>parcial</b> y podría subestimar el estado real. NO₂, SO₂ y CO carecen de registros: no se trata de un índice integral de todos los contaminantes criterio.'),PageBreak(),
      h('3. Numeralia de marzo'),
      p(f'<b>31</b> días con alguna categoría calculable; <b>{int(daily.cobertura_3_contaminantes.sum())}</b> días con cobertura de los tres contaminantes analizados. Categoría más frecuente: <b>{counts.most_common(1)[0][0]}</b> ({counts.most_common(1)[0][1]} días).')]
    rr=[["Categoría","Días"]]+[[cat,str(counts.get(cat,0))] for cat in CATS]
    t=Table(rr,colWidths=[8*cm,3*cm]);t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e8eef2')),('FONTSIZE',(0,0),(-1,-1),9),('FONTNAME',(0,0),(-1,-1),'DejaVu'),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#f6f8fa')]),('BOTTOMPADDING',(0,0),(-1,-1),7)]))
    story += [t,p('Días en que fue responsable de la peor banda (incluye empates): '+', '.join(f'{pol}: {n}' for pol,n in days_by_pol.items())+'.'),
      Image(str(out/'matriz_diaria.png'),width=16.8*cm,height=7.85*cm),
      para('Si hay dos etiquetas, empataron en categoría. El calendario permite localizar días, conservar el contaminante y comparar la gravedad sin reducir todo marzo a un solo promedio.',styles['SmallX'])]
    worst=daily[daily.categoria_d_id==daily.categoria_d_id.max()]
    story += [p('Días con la banda diaria más desfavorable ('+CATS[int(daily.categoria_d_id.max())]+'): '+', '.join(r.fecha[-2:]+' ('+r.dominantes_d+')' for _,r in worst.iterrows())+'.'),PageBreak(),
      h('4. Simulación de recepción horaria'),
      p(f'Se reproducen las 24 horas del {event_day}. En cada paso se incorporó únicamente la hora recién recibida y las horas anteriores; no se utilizó información futura. La línea de partículas distingue concentración medida e indicador móvil. La banda de cada hora representa el mayor riesgo calculable hasta entonces.'),
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
      p('En cada hora se conocían las concentraciones presentes y anteriores, la velocidad del viento cuando existía, y una categoría calculada con esos datos. El resumen diario sólo pudo establecerse al terminar el día. Sin humedad, viento direccional y temperatura ambiente no es posible evaluar su relación con el episodio. Una comunicación apropiada habría mostrado hora, banda, contaminante y cobertura de datos, con las recomendaciones de exposición de la norma; no se puede atribuir el episodio a una fuente específica.'),PageBreak(),
      h('5. Interpretación para Pollos Asados El ING'),
      p('La agencia ficticia puede usar los cambios de banda y los horarios con peor calidad para decidir cuándo difundir avisos oportunos al público y revisar la continuidad de sus mediciones. La comparación diaria sirve para planear el seguimiento del mes; la horaria revela cambios breves que una etiqueta diaria oculta. Las asociaciones meteorológicas quedan como preguntas para un conjunto de datos completo, no como explicaciones causales.'),
      h('Limitaciones'),
      p(f'PM₂.₅ faltó en {744-int(d.PM25_ug_m3.count())} horas. Las categorías se basan en tres contaminantes, no en seis. La hoja no aporta banderas instrumentales ni registros minuto a minuto para comprobar el criterio de 45 minutos por hora; se aceptan los promedios horarios suministrados. El periodo inicia sin las horas previas de febrero para NowCast. La clasificación histórica usa una edición normativa posterior a las mediciones. Los empates entre contaminantes no permiten asignar un responsable único.'),
      h('Bitácora del líder · pendiente de datos verificables'),
      p('Integrante | Actividades realizadas | Cumplimiento | Observaciones'),
      p('El líder debe incorporar los nombres, tareas y evidencias reales del sprint y una valoración general antes de presentar la versión final. La consigna menciona simultáneamente Sprint 1 y Sprint 2; conviene confirmar cuál corresponde a la bitácora y al nombre del archivo.'),
      h('Reproducción y fuentes'),
      p('Ejecutar: <font name="DejaVu">python analizar_tlaquepaque.py "Hoja de cálculo sin título (1).xlsx" salida/</font>. Se generan dos CSV con indicadores, dos gráficas y este PDF. El repositorio incluye el libro corregido y los resultados: '+REPO+'.'),
      para('Fuente del archivo original aportado por el equipo: hoja TLA, marzo de 2024. Portal de bases históricas de SEMADET: '+SOURCE+'<br/>Norma NOM-172-SEMARNAT-2023 (tablas 2–6 y Anexo A): '+NOM,styles['SmallX'])]
    pdf=out/'Reporte_Tlaquepaque_Pollos_Asados_El_ING.pdf'
    doc=SimpleDocTemplate(str(pdf),pagesize=(21*cm,29.7*cm),leftMargin=2*cm,rightMargin=2*cm,topMargin=1.7*cm,bottomMargin=1.5*cm)
    doc.build(story,onFirstPage=footer,onLaterPages=footer)
    summary={'days':len(daily),'counts':dict(counts),'dominants_including_ties':days_by_pol,'full_coverage_days':int(daily.cobertura_3_contaminantes.sum()),'event_day':str(event_day),'worst_days':worst[['fecha','dominantes_d']].to_dict('records')}
    (out/'resumen.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False,indent=2))

def footer(canvas,doc):
    canvas.saveState();canvas.setFont('DejaVu',8);canvas.setFillColor(colors.grey)
    canvas.drawString(2*cm,1*cm,'Pollos Asados El ING · Estación TLA · Marzo 2024')
    canvas.drawRightString(19*cm,1*cm,str(doc.page));canvas.restoreState()

if __name__=='__main__':
    run(Path(sys.argv[1]),Path(sys.argv[2]))
