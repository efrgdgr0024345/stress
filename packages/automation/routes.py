"""Engineer-selected routes over graphical candidates; stations stay unknown."""
from collections import deque
from packages.automation.recognize import identity


def propose(graph,start,end,sheet,line):
    vertices=graph["vertices"];edges=graph["edges"]
    if not 0<=start<len(vertices) or not 0<=end<len(vertices) or start==end:
        raise ValueError("Choose two different source vertices.")
    adjacent={i:set() for i in range(len(vertices))}
    for a,b in edges:adjacent[a].add(b);adjacent[b].add(a)
    parents={start:None};queue=deque([start])
    while queue:
        a=queue.popleft()
        for b in sorted(adjacent[a]):
            if b not in parents:parents[b]=a;queue.append(b)
    if end not in parents:raise ValueError("Those locations are in separate detected networks. Review the missing connection first.")
    if sum(len(adjacent[v]&parents.keys()) for v in parents)!=2*(len(parents)-1):
        raise ValueError("Detected loops need explicit engineering review; no ambiguous route was selected.")
    main=[];current=end
    while current is not None:main.append(current);current=parents[current]
    main.reverse();main_set=set(main);node_ids={v:identity(sheet,"vector-point",*vertices[v]) for v in parents}
    nodes=[];warnings=[]
    def make(v,route,order,takeoff=None):
        degree=len(adjacent[v]);kind="tee" if degree>2 else "endpoint" if degree==1 else "elbow"
        anchor=[max(12,min(graph["page_width"]-12,vertices[v][0])),max(12,min(graph["page_height"]-12,vertices[v][1]))]
        return {"id":node_ids[v],"line_id":line,"route":route,"order":order,"takeoff_id":takeoff,
                "kind":kind,"station_mm":None,"dimension_input":"","evidence":"Graphical proposal; engineer selected the main route. Physical stations and component classification require source proof.",
                "origin":"automation","verification":"proposed","graph_proposal":True,"number":None,
                "instances":[{"sheet_id":sheet,"anchor":anchor,"bubble":anchor[:]}]}
    nodes.extend(make(v,"main",i) for i,v in enumerate(main))
    visited=set(main);branch=0
    for tee in main:
        for neighbor in sorted(adjacent[tee]-visited):
            branch+=1;route=f"branch-{branch:02d}";previous=tee;current=neighbor;order=0
            if branch>99:raise ValueError("This network exceeds the bounded branch policy.")
            while current not in visited:
                visited.add(current);nodes.append(make(current,route,order,node_ids[tee]));order+=1
                following=adjacent[current]-{previous}
                if len(following)>1:
                    warnings.append({"code":"NESTED_BRANCH_REVIEW_REQUIRED","sheet_id":sheet,"point_id":node_ids[current]})
                    break
                if not following:break
                previous,current=current,next(iter(following))
    if len(visited)<len(parents):warnings.append({"code":"UNMODELLED_GRAPH_FEATURES","sheet_id":sheet,"count":len(parents)-len(visited)})
    if len(parents)<len(vertices):warnings.append({"code":"DISCONNECTED_LINEWORK_REVIEW","sheet_id":sheet,"count":len(vertices)-len(parents)})
    return nodes,warnings
