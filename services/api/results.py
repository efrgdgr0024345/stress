"""Engineering spreadsheet results and exact, evidence-backed element inputs."""
from decimal import Decimal,InvalidOperation
import io
import json
import zipfile

from fastapi import Depends,HTTPException
from pydantic import BaseModel,Field,ConfigDict
from packages.automation.recognize import identity
from packages.engineering import topology
from packages.workbooks import FORMAT,readiness,tables,workbook
from packages.workbooks.csv_export import csv_bundle
from packages.workbooks.caesar_neutral import assess,neutral_file


class ElementInput(BaseModel):
    model_config=ConfigDict(extra="forbid")
    version:int=Field(ge=1)
    dx_mm:str|None=Field(default=None,max_length=100)
    dy_mm:str|None=Field(default=None,max_length=100)
    dz_mm:str|None=Field(default=None,max_length=100)
    od_mm:str|None=Field(default=None,max_length=100)
    wall_mm:str|None=Field(default=None,max_length=100)
    corrosion_mm:str|None=Field(default=None,max_length=100)
    material_code:str|None=Field(default=None,max_length=100)
    temperature_c:str|None=Field(default=None,max_length=100)
    pressure_mpa:str|None=Field(default=None,max_length=100)
    elastic_modulus_mpa:str|None=Field(default=None,max_length=100)
    hot_modulus_mpa:str|None=Field(default=None,max_length=100)
    poisson_ratio:str|None=Field(default=None,max_length=100)
    pipe_density_kg_m3:str|None=Field(default=None,max_length=100)
    fluid_density_kg_m3:str|None=Field(default=None,max_length=100)
    insulation_thickness_mm:str|None=Field(default=None,max_length=100)
    insulation_density_kg_m3:str|None=Field(default=None,max_length=100)
    cold_allowable_mpa:str|None=Field(default=None,max_length=100)
    hot_allowable_mpa:str|None=Field(default=None,max_length=100)
    evidence:str=Field(min_length=10,max_length=3000)


def install(api):
    class NativeSettings(BaseModel):
        version:int=Field(ge=1)
        piping_code_id:int=Field(ge=1,le=999)
        ambient_temperature_c:str=Field(max_length=100)
        vertical_axis:str=Field(pattern=r'^[YZ]$')
        local_origin_confirmed:bool
        origin_point_id:str
    def project(project_id,actor):
        with api.db() as conn:return api.project_read(project_id,actor,conn)
    @api.app.get("/api/v1/projects/{project_id}/results")
    def results(project_id:str,actor=Depends(api.user)):
        p=project(project_id,actor)
        return {"format":FORMAT,"revision":p["version"],"tables":tables(p),"caesar":readiness(p),"native":assess(p)}

    @api.app.get("/api/v1/projects/{project_id}/results/csv")
    def download_csv(project_id:str,actor=Depends(api.user)):
        p=project(project_id,actor)
        return api.Response(csv_bundle(p),media_type='application/zip',headers={'Content-Disposition':f'attachment; filename="caesar-csv-r{p["version"]}.zip"'})

    @api.app.get("/api/v1/projects/{project_id}/results/caesar-neutral")
    def download_native(project_id:str,actor=Depends(api.user)):
        p=project(project_id,actor)
        try:contents=neutral_file(p)
        except ValueError as error:raise HTTPException(422,str(error))
        return api.Response(contents,media_type='text/plain; charset=windows-1252',headers={'Content-Disposition':f'attachment; filename="caesar-import-candidate-r{p["version"]}.cii"','X-CAESAR-Profile':'caesar-15.1-straight-pipe-v1'})

    @api.app.patch("/api/v1/projects/{project_id}/results/settings")
    def settings(project_id:str,body:NativeSettings,actor=Depends(api.editor)):
        def update(p):
            node=next((n for n in p['nodes'] if n['id']==body.origin_point_id and n['route']=='main'),None)
            if not node:raise HTTPException(422,'Select an active main-route point for the local origin.')
            try:value=Decimal(body.ambient_temperature_c)
            except InvalidOperation:raise HTTPException(422,'Ambient temperature must be numeric Celsius.')
            if not value.is_finite() or not Decimal('-273.15')<=value<=Decimal('2000'):raise HTTPException(422,'Ambient temperature is outside the supported range.')
            p.setdefault('analysis_model',{}).update(body.model_dump(exclude={'version'}))
            p['analysis_model']['ambient_temperature_c']=str(value)
        return api.change(project_id,body.version,actor,'Updated explicit native-model code, units and origin settings',update)

    @api.app.get("/api/v1/projects/{project_id}/results/workbook")
    def download(project_id:str,actor=Depends(api.user)):
        p=project(project_id,actor)
        try:contents=workbook(p)
        except ValueError as error:raise HTTPException(422,str(error))
        return api.Response(contents,media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",headers={"Content-Disposition":f'attachment; filename="caesar-engineering-r{p["version"]}.xlsx"'})

    @api.app.get("/api/v1/projects/{project_id}/artifacts/{artifact_id}/workbook")
    def artifact_workbook(project_id:str,artifact_id:str,actor=Depends(api.user)):
        p=project(project_id,actor)
        with api.db() as conn:row=conn.execute("SELECT * FROM artifacts WHERE id=? AND project_id=?",(artifact_id,project_id)).fetchone()
        if not row:raise HTTPException(404,"Artifact not found.")
        try:
            with zipfile.ZipFile(api.DATA/"exports"/f"{artifact_id}.zip") as archive:contents=archive.read("engineering-workbook.xlsx")
        except (KeyError,OSError,zipfile.BadZipFile):raise HTTPException(409,"This earlier artifact has no workbook. Generate a new review issue.")
        return api.Response(contents,media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",headers={"Content-Disposition":f'attachment; filename="caesar-engineering-r{row["revision"]}.xlsx"'})

    @api.app.patch("/api/v1/projects/{project_id}/results/elements/{element_id}")
    def save_element(project_id:str,element_id:str,body:ElementInput,actor=Depends(api.editor)):
        def update(p):
            edge=next((e for e in topology(p["nodes"])["edges"] if identity(p["id"],e["from"],e["to"])==element_id),None)
            if not edge:raise HTTPException(404,"Active model element not found.")
            data={"id":element_id,"from_point_id":edge["from"],"to_point_id":edge["to"],"evidence":body.evidence,"entered_by":actor["id"],"verification":"engineer-entered"}
            for key,value in body.model_dump(exclude={"version","evidence"}).items():
                if key=="material_code":data[key]=value.strip() if value and value.strip() else None;continue
                if value is None or not value.strip():data[key]=None;continue
                try:number=Decimal(value)
                except InvalidOperation:raise HTTPException(422,f"{key}: enter a canonical numeric value in the displayed unit.")
                if not number.is_finite() or number.copy_abs()>Decimal('1000000000000'):raise HTTPException(422,"Engineering values must be finite and within the supported range.")
                if key in ("od_mm","wall_mm","elastic_modulus_mpa","hot_modulus_mpa","pipe_density_kg_m3","cold_allowable_mpa","hot_allowable_mpa") and number<=0:raise HTTPException(422,"Pipe dimensions, moduli, density and allowables must be positive when supplied.")
                if key in ("corrosion_mm","pressure_mpa","fluid_density_kg_m3","insulation_thickness_mm","insulation_density_kg_m3") and number<0:raise HTTPException(422,"Pressure, thickness and densities cannot be negative.")
                if key=='poisson_ratio' and not 0<number<Decimal('.5'):raise HTTPException(422,'Poisson ratio must be between zero and 0.5.')
                if key=='temperature_c' and number<Decimal('-273.15'):raise HTTPException(422,'Temperature cannot be below absolute zero.')
                data[key]=str(number)
            if data.get("od_mm") and data.get("wall_mm") and Decimal(data['wall_mm'])*2>=Decimal(data['od_mm']):raise HTTPException(422,"Wall thickness must be less than half the outside diameter.")
            if data.get('corrosion_mm') and data.get('wall_mm') and Decimal(data['corrosion_mm'])>=Decimal(data['wall_mm']):raise HTTPException(422,'Corrosion allowance must be less than the wall thickness.')
            stored=p.setdefault("analysis_model",{}).setdefault("elements",[])
            stored[:]=[e for e in stored if e['id']!=element_id]+[data]
        return api.change(project_id,body.version,actor,"Updated evidence-backed analysis element properties",update)
