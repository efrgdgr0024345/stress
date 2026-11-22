"""UTF-8 CSV interchange tables from the same website/workbook projection."""
import csv
import io
import json
import zipfile
from packages.workbooks import tables,FORMAT


def csv_bundle(project):
    output=io.BytesIO()
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as archive:
        for table in tables(project):
            text=io.StringIO(newline='');writer=csv.writer(text)
            writer.writerow([c['label'] for c in table['columns']])
            for row in table['rows']:
                values=[]
                for column in table['columns']:
                    value=row.get(column['key'])
                    if value is None:value=''
                    elif column['kind']=='text':
                        value=str(value)
                        if value.lstrip().startswith(('=','+','-','@')) or value.startswith(('\t','\r','\n')):value="'"+value
                    values.append(value)
                writer.writerow(values)
            archive.writestr(table['name'].lower().replace(' ','-')+'.csv',text.getvalue().encode('utf-8-sig'))
        archive.writestr('README.txt','ENGINEERING REVIEW DATA\nUnknown fields are blank. Geometry is mm; weights N; temperature Celsius; pressure MPa.\nThese CSV tables are an interchange handoff, not a claim that CAESAR directly imports arbitrary CSV.\nUse the qualified neutral-file profile for a native CAESAR import candidate.\n')
        archive.writestr('manifest.json',json.dumps({'format':FORMAT,'project_id':project['id'],'revision':project['version'],'status':'ENGINEERING_REVIEW'},indent=2))
    return output.getvalue()
