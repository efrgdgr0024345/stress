"""Formatted, editable engineering workbooks; never invent CAESAR input data."""
from decimal import Decimal,localcontext
import io
import math

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill, Border, Side
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.worksheet.table import Table, TableStyleInfo
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE

from packages.engineering import topology,validate
from packages.physical import is_support

FORMAT="caesar-engineering-workbook-1"


def literal(value):return ILLEGAL_CHARACTERS_RE.sub('',str(value))[:32767]


def readiness(project):
    nodes=project["nodes"];elements=project.get("analysis_model",{}).get("elements",[])
    from packages.physical.stations import solve_stations
    station_issues=solve_stations(project)['issues']
    from packages.engineering.graph_review import audit_graph
    graph_review=audit_graph(project)
    from packages.automation.recognize import identity
    expected={identity(project["id"],e["from"],e["to"]) for e in topology(nodes)["edges"]}
    entered={e['id']:e for e in elements}
    complete=sum(all(entered.get(key,{}).get(k) is not None for k in ("dx_mm","dy_mm","dz_mm","od_mm","wall_mm","material_code","temperature_c","pressure_mpa")) for key in expected)
    gates=[{"gate":"CAESAR import profile","passed":False,"detail":"The documented CAESAR II 15.1 straight-pipe candidate profile still needs an actual application import round trip."},
           {"gate":"Engineering approval","passed":False,"detail":"This application currently issues engineering-review drafts; lead approval of verified stress input is required."},
           {"gate":"Physical points","passed":bool(nodes),"detail":f"{len(nodes)} model points."},
           {"gate":"Explicit connected graph","passed":bool(nodes) and graph_review['summary']['connected_assigned'] and not graph_review['structural_issues'],"detail":"Every point needs an accepted route; branches must share the existing main-run tee on the same full line. Source changes require topology review."},
           {"gate":"Station evidence","passed":bool(nodes) and not station_issues and all(n.get("station_mm") is not None and n.get("evidence") and n.get("verification")!="proposed" for n in nodes),"detail":"Every required point needs source-current along-centreline evidence and an accepted station datum."},
           {"gate":"Element geometry and properties","passed":bool(expected) and complete==len(expected),"detail":f"{complete} of {len(expected)} active elements have required geometry and properties. Signed XYZ values must come from engineering evidence, never drawing pixels."}]
    return {"status":"ENGINEERING_REVIEW_ONLY","direct_import_ready":False,"format":FORMAT,"gates":gates}


def tables(project):
    issues=validate(project)
    nodes=project["nodes"];by_id={n["id"]:n for n in nodes};sheets={s["id"]:s for s in project["sheets"]}
    def table(name,columns,rows):return {"name":name,"columns":[{"key":key,"label":label,"kind":kind} for key,label,kind in columns],"rows":rows}
    result=[]
    rows=[]
    from packages.physical.constraints import solve
    solved={v['point_id']:v['axes'] for v in solve(project)['coordinates']}
    for n in nodes:
        c=dict(n.get('coordinates_mm') or {})
        for axis in ('X','Y','Z'):
            value=solved.get(n['id'],{}).get(axis,{}).get('value_mm')
            if value is not None:c[axis.lower()]=value
        rows.append({"number":n.get("number"),"line":n["line_id"],"route":n["route"],"kind":n["kind"],
            "station":n.get("station_mm"),"x":c.get("x"),"y":c.get("y"),"z":c.get("z"),
            "verification":n.get("verification","engineer-entered"),"reasons":", ".join(n.get("reasons",[])),
            "source_dimension":n.get("dimension_input",""),"evidence":n.get("evidence",""),
            "sheets":", ".join(str(sheets[v["sheet_id"]]["page_index"]+1) for v in n["instances"] if v["sheet_id"] in sheets),"id":n["id"],"proposed_station":n.get("proposed_station_mm"),"proposed_dimension":n.get("proposed_dimension_input",""),"review_label":n.get("review_label"),"topology_state":n.get("topology_state","ASSIGNED")})
    result.append(table("Nodes",[("number","Node","number"),("line","Full line ID","text"),("route","Route","text"),("kind","Type","text"),("station","Accepted station (mm)","decimal"),("x","X / East (mm)","decimal"),("y","Y / North (mm)","decimal"),("z","Z / Elevation (mm)","decimal"),("verification","Review state","text"),("reasons","Reasons","text"),("source_dimension","Accepted dimension","text"),("evidence","Evidence","text"),("sheets","Source pages","text"),("id","Physical point ID","text"),("proposed_station","Source station proposal (mm)","decimal"),("proposed_dimension","Proposed source dimension","text"),("review_label","Temporary review point","text"),("topology_state","Topology status","text")],rows))
    for row in rows:
        node=by_id[row['id']]
        row.update(route_order=node.get('order'),takeoff_id=node.get('takeoff_id'),
            topology_evidence=node.get('topology_proof',{}).get('evidence'),
            topology_review_status='UNASSIGNED' if node.get('topology_state')=='UNASSIGNED' else
                'SOURCE OR TOPOLOGY REVIEW REQUIRED' if {'TOPOLOGY_REVIEW_STALE','SOURCE_LOCATION_REVIEW_REQUIRED','POINT_SOURCE_LINE_MISMATCH'} & set(node.get('reasons',[])) else
                'REVIEWED ROUTE' if node.get('topology_proof') else 'ENTERED ORDER')
    result[-1]['columns'] += [{'key':key,'label':title,'kind':kind} for key,title,kind in (
        ('route_order','Route sequence order','number'),('takeoff_id','Shared main tee physical point ID','text'),
        ('topology_review_status','Route review state','text'),('topology_evidence','Route review evidence','text'))]
    entered={e["id"]:e for e in project.get("analysis_model",{}).get("elements",[])}
    from packages.automation.recognize import identity
    edges=topology(nodes)["edges"]
    elements=[]
    for edge in edges:
        a,b=by_id[edge["from"]],by_id[edge["to"]];key=identity(project["id"],a["id"],b["id"]);e=entered.get(key,{})
        delta={axis:e.get("d"+axis+"_mm") for axis in ('x','y','z')}
        for axis in delta:
            ac=a.get("coordinates_mm",{}).get(axis);bc=b.get("coordinates_mm",{}).get(axis)
            if delta[axis] is None and ac is not None and bc is not None:delta[axis]=str(Decimal(bc)-Decimal(ac))
        from packages.physical.stations import station_pair_comparable
        with localcontext() as context:
            context.prec=200
            distance=abs(Decimal(b["station_mm"])-Decimal(a["station_mm"])) if station_pair_comparable(a,b) else None
        elements.append({"from":a.get("number"),"to":b.get("number"),"line":edge["line_id"],"route":edge["route"],"dx":delta['x'],"dy":delta['y'],"dz":delta['z'],
            "route_distance":str(distance) if distance is not None else None,"od":e.get("od_mm"),"wall":e.get("wall_mm"),"corrosion":e.get("corrosion_mm"),
            "material":e.get("material_code"),"temperature":e.get("temperature_c"),"pressure":e.get("pressure_mpa"),"evidence":e.get("evidence",""),
            "state":"REVIEW / IMPORT UNQUALIFIED","id":key})
        for field in ('elastic_modulus_mpa','hot_modulus_mpa','poisson_ratio','pipe_density_kg_m3','fluid_density_kg_m3','insulation_thickness_mm','insulation_density_kg_m3','cold_allowable_mpa','hot_allowable_mpa'):elements[-1][field]=e.get(field)
    result.append(table("CAESAR input",[("from","From node","number"),("to","To node","number"),("line","Line","text"),("route","Route","text"),("dx","DX (mm)","decimal"),("dy","DY (mm)","decimal"),("dz","DZ (mm)","decimal"),("route_distance","Route distance only (mm)","decimal"),("od","OD (mm)","decimal"),("wall","Wall (mm)","decimal"),("corrosion","Corrosion (mm)","decimal"),("material","CAESAR material code","text"),("temperature","Temperature (C)","decimal"),("pressure","Pressure (MPa)","decimal"),("state","Readiness","text"),("evidence","Property evidence","text"),("id","Element ID","text")],elements))
    result[-1]['columns'] += [{'key':field,'label':label,'kind':'decimal'} for field,label in (
        ('elastic_modulus_mpa','Cold modulus (MPa)'),('hot_modulus_mpa','Hot modulus (MPa)'),('poisson_ratio','Poisson ratio'),('pipe_density_kg_m3','Pipe density (kg/m3)'),('fluid_density_kg_m3','Fluid density (kg/m3)'),('insulation_thickness_mm','Insulation (mm)'),('insulation_density_kg_m3','Insulation density (kg/m3)'),('cold_allowable_mpa','Cold allowable (MPa)'),('hot_allowable_mpa','Hot allowable (MPa)'))]
    result.append(table("Supports",[("number","Node","number"),("line","Line","text"),("route","Route","text"),("station","Station (mm)","decimal"),("gap","Previous support gap (mm)","decimal"),("reasons","Reasons","text"),("evidence","Evidence","text")],[{"number":n.get("number"),"line":n["line_id"],"route":n["route"],"station":n.get("station_mm"),"gap":n.get("support_gap_mm"),"reasons":", ".join(n.get("reasons",[])),"evidence":n.get("evidence","")} for n in nodes if is_support(n)]))
    components=[]
    for m in project["materials"]:
        match=m.get("catalog_match") or {};r=match.get("record") or {}
        from packages.catalogs.project_review import record_weight_values
        state=m.get('catalog_review_state',{})
        values=record_weight_values(r) if state.get('match_current') is not False else record_weight_values(None)
        components.append({"item":m["item_no"],"page":sheets.get(m["sheet_id"],{}).get("page_index",-1)+1,"family":m["family"],"description":m["description"],"size":m["size"],"quantity":m.get("quantity"),"source_value":m.get("quantity_value"),"raw_quantity":m.get("quantity_raw",""),"unit":m.get("quantity_unit","count"),"located":m.get("observed"),"weight":values.get("weight_n"),"half":values.get("half_weight_n"),"full":values.get("full_weight_n"),"length":values.get("length_mm"),"scope":r.get("weight_scope"),"quality":r.get("quality"),"match":state.get('status') or match.get("status","UNMATCHED"),"dataset":match.get("catalog_version_id"),"evidence":m.get("evidence",""),"id":m["id"],"assembly":values.get('assembly_weight_n'),'manufacturer_status':m.get('project_manufacturer_status')})
    result.append(table("Components",[("item","Item","text"),("page","Page","number"),("family","Family","text"),("description","Source description","text"),("size","Size","text"),("quantity","Listed count","number"),("source_value","Source quantity value","decimal"),("raw_quantity","Raw source quantity","text"),("unit","Quantity unit","text"),("located","Located count","number"),("weight","Bare flange / valve weight (N)","decimal"),("half","Flange + half bolting total (N)","decimal"),("full","Flange + full bolting total (N)","decimal"),("length","Length (mm)","decimal"),("scope","Weight scope","text"),("quality","Catalog source quality","text"),("match","Project match state","text"),("dataset","Dataset ID","text"),("evidence","Evidence","text"),("id","Material ID","text"),("assembly","Assembly includes bolting (N)","decimal"),("manufacturer_status","Project manufacturer state","text")],components))
    from packages.physical.spreadsheets import tables as physical_tables
    result.extend(physical_tables(project))
    from packages.physical.station_tables import tables as station_tables
    result.extend(station_tables(project))
    from packages.engineering.graph_tables import tables as graph_tables
    result.extend(graph_tables(project))
    from packages.catalogs.project_tables import tables as catalog_tables
    result.extend(catalog_tables(project))
    features=[]
    for feature in project.get('automation',{}).get('feature_proposals',[]):
        sheet=sheets.get(feature['sheet_id'])
        if not sheet:continue
        for role in ('flange_face','opposite_pipe_dot'):
            x,y=feature[role]
            features.append({'id':feature['id']+':'+role,'page':sheet['page_index']+1,
                'kind':feature['kind'],'role':role,'pdf_x':x,'pdf_y':y,'station':None,
                'verification':'proposed','profile':feature['profile'],'sha':feature['source_sha256'],
                'evidence':'Graphical source proposal only. Inspect Detected features in the drawing. Material, route and physical distance require review.'})
    result.append(table('Source features',[("page","Page","number"),("kind","Symbol","text"),
        ("role","Proposed interface","text"),("pdf_x","PDF X (pt, graphic only)","decimal"),
        ("pdf_y","PDF Y (pt, graphic only)","decimal"),("station","Physical station (mm)","decimal"),
        ("verification","Review state","text"),("profile","Recognition convention","text"),
        ("evidence","Evidence","text"),("sha","Original SHA-256","text"),("id","Source feature ID","text")],features))
    result.append(table("Exceptions",[("severity","Severity","text"),("code","Code","text"),("node","Node","number"),("message","Review action","text"),("material_id","Material ID","text"),("sheet_id","Sheet ID","text"),("id","Exception ID","text"),("requirement_id","Physical requirement ID","text"),("port","Interface","text"),("point_id","Physical point ID","text"),("source_sha256","Source PDF SHA256","text"),("evidence","Source evidence","text"),("color","Review colour","text"),("status","Status","text")],[{k:i.get(k) for k in ('severity','code','node','message','material_id','sheet_id','id','requirement_id','port','point_id','source_sha256','evidence','color','status')} for i in issues]))
    result.append(table("Sources",[("filename","Source file","text"),("page","PDF page","number"),("printed","Printed sheet ID","text"),("line","Full line ID","text"),("sha","SHA-256","text"),("format","Content type","text"),("id","Sheet ID","text")],[{"filename":s["filename"],"page":s["page_index"]+1,"printed":s["printed_id"],"line":s["line_id"],"sha":s["sha256"],"format":s["format"],"id":s["id"]} for s in project["sheets"]]))
    return result


def workbook(project):
    """No macros, external links or formulas derived from drawing/user text."""
    data=tables(project)
    if sum(len(t["rows"]) for t in data)>20000:raise ValueError("Workbook row limit exceeded; split the project issue.")
    book=Workbook();overview=book.active;overview.title="Read me";overview.sheet_properties.tabColor="007AFF"
    overview.append(["CAESAR ISO | ENGINEERING WORKBOOK"]);overview.merge_cells('A1:H2')
    overview['A1'].font=Font(name="Aptos Display",size=20,bold=True,color="FFFFFF");overview['A1'].fill=PatternFill('solid',fgColor='1677E8');overview['A1'].alignment=Alignment(vertical='center')
    entries=[("Project",project["title"]),("Full line ID",project["line_id"]),("Project revision",project["version"]),("Status","ENGINEERING REVIEW — NOT VERIFIED FOR MODELLING"),("Workbook schema",FORMAT),("Units","Geometry/stations: mm; weights: N; pressure: MPa; temperature: Celsius."),("Unknown values","Blank numeric cells are unknown, never zero. Original decimal text is retained in Exact values."),("CAESAR use","Direct import needs a confirmed CAESAR II version/template and a successful round trip. This workbook is not labelled import-ready."),("Geometry","Route distances are not signed XYZ element deltas. Drawing pixels are not physical measurements."),("Editing","Data cells are editable. This file contains no macros or executable connector. Edits in Excel do not silently change the website model."),("Evidence","Review the Exceptions and source/provenance fields before using engineering values.")]
    for i,(key,value) in enumerate(entries,4):
        overview.cell(i,1,key).font=Font(bold=True,color='53677F');c=overview.cell(i,2,literal(value));c.data_type='s';c.alignment=Alignment(wrap_text=True,vertical='top');overview.merge_cells(start_row=i,start_column=2,end_row=i,end_column=8);overview.row_dimensions[i].height=32 if len(str(value))>100 else 25
    overview.column_dimensions['A'].width=24
    for key in 'BCDEFGH':overview.column_dimensions[key].width=16
    overview.freeze_panes='B4';overview.sheet_view.showGridLines=False
    exact=[]
    for index,table in enumerate(data):
        sheet=book.create_sheet(table['name']);sheet.sheet_properties.tabColor='229E73' if table['name']=='CAESAR input' else '2682EC'
        sheet.sheet_view.showGridLines=False
        sheet.append([literal(f"{project['title']} | {table['name']} | revision {project['version']}")]);sheet['A1'].data_type='s';sheet.merge_cells(start_row=1,start_column=1,end_row=2,end_column=max(2,len(table['columns'])))
        sheet['A1'].font=Font(name='Aptos Display',size=16,bold=True,color='FFFFFF');sheet['A1'].fill=PatternFill('solid',fgColor='247FD2');sheet['A1'].alignment=Alignment(vertical='center')
        sheet.cell(3,1,'ENGINEERING REVIEW · Unknown numeric values remain blank · Verify source evidence before CAESAR use').font=Font(size=10,color='A66B27')
        headers=[c['label'] for c in table['columns']];sheet.append([]);sheet.append(headers)
        for row_index,row in enumerate(table['rows'],6):
            for col_index,column in enumerate(table['columns'],1):
                value=row.get(column['key']);cell=sheet.cell(row_index,col_index)
                if value is None:cell.fill=PatternFill('solid',fgColor='FFF6E4');continue
                if column['kind']=='decimal':
                    exact.append([table['name'],row.get('id',row_index-5),column['label'],str(value)])
                    number=Decimal(str(value))
                    if not number.is_finite():raise ValueError('Non-finite engineering value cannot be exported.')
                    converted=float(number)
                    if not math.isfinite(converted) or number!=0 and converted==0:raise ValueError('Engineering value is outside the numeric range supported by Excel.')
                    cell.value=converted;cell.number_format='0.#########'
                elif column['kind']=='number':cell.value=int(value);cell.number_format='0'
                else:cell.value=literal(value);cell.data_type='s'
                cell.font=Font(name='Aptos',size=10,color='225EAC' if row.get('verification')=='proposed' else '34465E')
                cell.alignment=Alignment(vertical='top',wrap_text=column['key'] in ('description','message','evidence','reasons'))
        last=max(6,5+len(table['rows']))
        if not table['rows']:sheet.append([None]*len(headers))
        from openpyxl.utils import get_column_letter
        tab=Table(displayName=f'EngineeringTable{index+1}',ref=f'A5:{get_column_letter(len(headers))}{last}')
        tab.tableStyleInfo=TableStyleInfo(name='TableStyleMedium2',showRowStripes=True,showFirstColumn=False,showLastColumn=False)
        sheet.add_table(tab);sheet.freeze_panes='C6';sheet.auto_filter.ref=tab.ref
        for i,column in enumerate(table['columns'],1):
            if column['kind'] in ('decimal','number'):
                rule=DataValidation(type='decimal' if column['kind']=='decimal' else 'whole',operator='between',formula1='-1000000000000' if column['kind']=='decimal' else '0',formula2='1000000000000',allow_blank=True)
                rule.errorTitle='Numeric engineering value required';rule.error='Enter a numeric value in the column unit, or leave unknown values blank.';rule.showErrorMessage=True
                sheet.add_data_validation(rule);rule.add(f'{get_column_letter(i)}6:{get_column_letter(i)}{last+1000}')
        sheet.print_title_rows='1:5';sheet.sheet_properties.pageSetUpPr.fitToPage=True;sheet.page_setup.orientation='landscape';sheet.page_setup.paperSize=sheet.PAPERSIZE_A3;sheet.page_setup.fitToWidth=1;sheet.page_setup.fitToHeight=0
        sheet.sheet_view.zoomScale=85
        for i,column in enumerate(table['columns'],1):sheet.column_dimensions[get_column_letter(i)].width=60 if column['key'] in ('description','message','evidence') else 32 if column['key'] in ('id','sha','reasons') else max(14,min(28,len(column['label'])+3))
    exact_sheet=book.create_sheet('Exact values');exact_sheet.append(['Sheet','Entity','Field','Exact canonical decimal text'])
    for row in exact:
        exact_sheet.append(row)
        for cell in exact_sheet[exact_sheet.max_row]:cell.value=literal(cell.value);cell.data_type='s'
    exact_sheet.freeze_panes='D2';exact_sheet.auto_filter.ref=exact_sheet.dimensions
    exact_sheet.column_dimensions['A'].width=24;exact_sheet.column_dimensions['B'].width=40;exact_sheet.column_dimensions['C'].width=30;exact_sheet.column_dimensions['D'].width=45
    ready=book.create_sheet('CAESAR readiness');ready.sheet_properties.tabColor='E6A03B';ready.append(['Readiness gate','Result','Explanation'])
    for gate in readiness(project)['gates']:ready.append([gate['gate'],'PASS' if gate['passed'] else 'REVIEW REQUIRED',gate['detail']])
    ready.freeze_panes='B2';ready.column_dimensions['A'].width=34;ready.column_dimensions['B'].width=24;ready.column_dimensions['C'].width=110
    output=io.BytesIO();book.save(output);book.close()
    # Reopen using a separate reader path before publishing an engineering file.
    with io.BytesIO(output.getvalue()) as check:
        reopened=load_workbook(check,read_only=True,data_only=False,keep_links=False)
        if any(name not in reopened.sheetnames for name in ('Nodes','CAESAR input','Exact values','CAESAR readiness')):raise ValueError('Workbook verification failed.')
        reopened.close()
    return output.getvalue()
