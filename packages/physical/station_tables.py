"""Shared website/workbook station and printed-coordinate evidence tables."""
from packages.physical.stations import solve_stations,station_constraints,canonical_point_id,station_comparison_basis
from packages.physical.source_review import station_source_proposals,point_label
from packages.physical.source_coordinates import proposals as coordinate_proposals


def tables(project):
    nodes={n['id']:n for n in project['nodes']}
    def label(point):
        node=nodes.get(canonical_point_id(project,point))
        return point_label(node) if node else None
    def table(name,columns,rows):
        return {'name':name,'columns':[{'key':k,'label':title,'kind':kind} for k,title,kind in columns],'rows':rows}
    solution=solve_stations(project)
    stale={point for issue in solution['issues'] if issue['code']=='STATION_SOLUTION_STALE' for point in issue.get('point_ids',[])}
    stations=[{**v,'point_label':label(v['point_id']),'constraint_ids':', '.join(v['constraint_ids']),
               'stored_proof_state':'UNKNOWN' if v['existing_station_mm'] is None else 'STALE — REVIEW REQUIRED' if v['point_id'] in stale else
                   'CURRENT ACCEPTED BASIS' if station_comparison_basis(nodes[v['point_id']]) else 'BASIS REVIEW REQUIRED'} for v in solution['points']]
    constraints=[{**v,'from_label':label(v['from_point_id']),'to_label':label(v.get('to_point_id'))} for v in station_constraints(project)]
    lengths=[{**v,'from_label':label(v['from_point_id']),'to_label':label(v['to_point_id']),
              'bbox':str(v.get('bbox')),'evidence':v.get('evidence'),'direction_state':'UNSIGNED — DIRECTION NOT ACCEPTED',
              'origin_state':'SOURCE LENGTH ONLY — NO DATUM IN THIS SOURCE RECORD'} for v in station_source_proposals(project)]
    printed=[{**v,'point_label':label(v['point_id'])} for v in coordinate_proposals(project)]
    return [
        table('Stations',[
            ('point_label','Review point','text'),('line_id','Full line ID','text'),('route','Route','text'),
            ('status','Current constraint status','text'),('existing_station_mm','Stored station (mm)','decimal'),
            ('stored_proof_state','Stored station proof state','text'),
            ('proposed_station_mm','Anchored solution (mm)','decimal'),('relative_station_mm','Relative solution (mm)','decimal'),
            ('basis','Declared station datum','text'),('basis_id','Datum ID','text'),('basis_point_id','Origin physical point ID','text'),
            ('tolerance_mm','Declared tolerance (mm)','decimal'),('constraint_ids','Source constraint IDs','text'),
            ('constraint_group_id','Source constraint evidence group','text'),
            ('point_id','Physical point ID','text'),('input_sha256','Station input SHA256','text')],stations),
        table('Station constraints',[
            ('kind','Constraint type','text'),('from_label','From / datum point','text'),('to_label','To point','text'),
            ('source_text','Original source length / station','text'),('source_format','Source convention','text'),
            ('value_mm','Accepted signed source value (mm)','decimal'),('tolerance_mm','Declared tolerance (mm)','decimal'),
            ('distance_basis','Distance basis','text'),('evidence','Engineering evidence','text'),
            ('sheet_id','Source sheet ID','text'),('source_sha256','Source PDF SHA256','text'),('id','Constraint ID','text'),
            ('source_proposal_id','Printed source proposal ID','text'),('from_point_id','From physical point ID','text'),
            ('to_point_id','To physical point ID','text')],constraints),
        table('Source lengths',[
            ('from_label','Source witness A','text'),('to_label','Source witness B','text'),
            ('source_text','Original unsigned printed length','text'),('source_format','Source convention','text'),
            ('proposed_distance_mm','Proposed unsigned conversion (mm)','decimal'),('station_mm','Accepted station (mm)','decimal'),
            ('direction_state','Printed source direction state','text'),('origin_state','Printed source station state','text'),
            ('evidence','Witness evidence','text'),('sheet_id','Source sheet ID','text'),('source_sha256','Source PDF SHA256','text'),
            ('bbox','Source box (PDF points only)','text'),('id','Source proposal ID','text')],lengths),
        table('Printed coordinates',[
            ('point_label','Source review point','text'),('axis','Engineering axis','text'),
            ('source_text','Original printed coordinate','text'),('source_format','Source convention','text'),
            ('proposed_value_mm','Proposed conversion (mm)','decimal'),('accepted_value_mm','Accepted source value (mm)','decimal'),
            ('status','Source review state','text'),('sheet_id','Source sheet ID','text'),
            ('source_sha256','Source PDF SHA256','text'),('point_id','Physical point ID','text'),('id','Source proposal ID','text')],printed),
    ]
