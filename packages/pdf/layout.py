"""Bounded native-PDF layout. Graphic coordinates never become physical data.

Boxes avoid original ink. Leaders may touch/cross ordinary pipe strokes, but
never source text, protected dimensions/material regions, NORTH, or other
generated boxes. Failure is an explicit export-blocking layout exception.
"""
from collections import defaultdict
import heapq
import math

import fitz

SCHEMA='native-source-layout-1'
CELL=40
MAX_PATHS=25000
MAX_SEGMENTS=250000
MAX_BOX_CANDIDATES=40000
MAX_ROUTE_TESTS=30000
SOURCE_1010_SHA='7b97d44bef3d544c4c98ed0667c29607ce58fa4a401dd2463f66010a9615bb59'
NORTH_1010=[102.2338,70.8129,226.9439,142.7537]


def _rect(value,padding=0):
    r=fitz.Rect(value)
    return [r.x0-padding,r.y0-padding,r.x1+padding,r.y1+padding]


def _overlap(first,second):
    return not (first[2]<second[0] or second[2]<first[0] or first[3]<second[1] or second[3]<first[1])


def _inside(point,rect):
    return rect[0]<=point[0]<=rect[2] and rect[1]<=point[1]<=rect[3]


def _line_rect(first,second,rect):
    """Closed segment versus closed rectangle, including zero-width strokes."""
    x,y=first;dx=second[0]-x;dy=second[1]-y;low=0.;high=1.
    for p,q in ((-dx,x-rect[0]),(dx,rect[2]-x),(-dy,y-rect[1]),(dy,rect[3]-y)):
        if not p:
            if q<0:return False
        else:
            ratio=q/p
            if p<0:low=max(low,ratio)
            else:high=min(high,ratio)
            if low>high:return False
    return True


def _length(first,second):
    return math.hypot(second[0]-first[0],second[1]-first[1])


def _point_segment_distance(point,first,second):
    dx=second[0]-first[0];dy=second[1]-first[1];length=dx*dx+dy*dy
    t=max(0.,min(1.,((point[0]-first[0])*dx+(point[1]-first[1])*dy)/length)) if length else 0.
    return math.hypot(point[0]-first[0]-t*dx,point[1]-first[1]-t*dy)


def _curve_segments(a,b,c,d,depth=0):
    error=max(_point_segment_distance(b,a,d),_point_segment_distance(c,a,d))
    if error<=.2 or depth>=12:
        yield a,d,error;return
    def mid(first,second):return [(first[0]+second[0])/2,(first[1]+second[1])/2]
    ab=mid(a,b);bc=mid(b,c);cd=mid(c,d);abc=mid(ab,bc);bcd=mid(bc,cd);center=mid(abc,bcd)
    yield from _curve_segments(a,ab,abc,center,depth+1)
    yield from _curve_segments(center,bcd,cd,d,depth+1)


class _Index:
    def __init__(self):self.cells=defaultdict(list);self.values=[]

    def add(self,bbox,value):
        index=len(self.values);self.values.append(value)
        for x in range(math.floor(bbox[0]/CELL),math.floor(bbox[2]/CELL)+1):
            for y in range(math.floor(bbox[1]/CELL),math.floor(bbox[3]/CELL)+1):self.cells[(x,y)].append(index)

    def query(self,bbox):
        seen=set()
        for x in range(math.floor(bbox[0]/CELL),math.floor(bbox[2]/CELL)+1):
            for y in range(math.floor(bbox[1]/CELL),math.floor(bbox[3]/CELL)+1):
                for index in self.cells.get((x,y),()):
                    if index not in seen:seen.add(index);yield self.values[index]


class LayoutPlanner:
    def __init__(self,page,sheet,source_sha256=None,protected_regions=None):
        self.sheet_id=sheet['id'];self.width=float(sheet.get('width',page.cropbox.width));self.height=float(sheet.get('height',page.cropbox.height))
        self.protected_regions=[];self.north_regions=[];self.occupied=[];self.leader_routes=[];self.issues=[]
        self.allowed_source_annotation_crossings=[];self._highlight_annotations=[];self._allowed_highlights=set()
        self.source_sha256=source_sha256
        self._ink=_Index();self._fills=_Index();self._protected=_Index();self._occupied=_Index();self._segment_count=0
        self._bounds=[3.,3.,self.width-3.,self.height-3.]
        source_words_supplied=any(r.get('kind') in ('SOURCE_OCR_TEXT','SOURCE_WORD','OCR_TEXT') for r in (protected_regions or []))
        for index,word in enumerate(page.get_text('words')):
            north=word[4].strip().upper() in ('NORTH','N')
            self._protect({'id':f'native-word-{index}','kind':'NORTH' if north else 'SOURCE_TEXT',
                'bbox':[word[0]-16,word[1]-20,word[2]+16,word[3]+72] if north else _rect(word[:4],1.5),
                'evidence':str(word[4])})
        if source_sha256==SOURCE_1010_SHA:
            self._protect({'id':'actual-1010-north','kind':'NORTH','bbox':NORTH_1010,
                'evidence':'SHA-bound actual source NORTH glyphs/arrows, native paths1149–1173 and1237–1239.'})
        for index,region in enumerate(protected_regions or []):
            self._protect({**region,'id':region.get('id',f'source-region-{index}'),
                'kind':region.get('kind','SOURCE_PROTECTED'),'bbox':region.get('bbox') or region.get('rect')})
        paths=page.get_cdrawings()
        if len(paths)>MAX_PATHS:
            self._fail('LAYOUT_SOURCE_LIMIT','Native path count exceeds the bounded collision planner. No unverified layout was emitted.','source');return
        glyphs=[]
        for index,path in enumerate(paths):
            width=max(.2,float(path.get('width',.5)))/2+.8
            rect=fitz.Rect(path['rect'])
            fill=path.get('fill')
            if fill and path.get('fill_opacity',1)>.001 and any(float(channel)<.98 for channel in fill):
                self._fills.add(_rect(rect,.8),{'bbox':_rect(rect,.8),'kind':'SOURCE_FILLED_VECTOR','path_index':index})
            # CAD outlined letters occur as small separate native paths. Keep
            # glyph regions as well as stroke geometry so leaders cannot thread
            # through the blank interior of a printed character.
            if (path.get('type')=='s' and 3.0<=rect.height<=26 and .35<=rect.width<=28 and
                    len(path.get('items',[]))>=2 and rect.width/max(rect.height,.1)<3):
                glyphs.append((index,rect))
            for item in path.get('items',[]):
                kind=item[0]
                if kind=='l':self._stroke(item[1],item[2],width)
                elif kind=='re':
                    r=fitz.Rect(item[1]);points=[r.tl,r.tr,r.br,r.bl,r.tl]
                    for a,b in zip(points,points[1:]):self._stroke(a,b,width)
                elif kind=='qu':
                    quad=fitz.Quad(item[1]);points=[quad.ul,quad.ur,quad.lr,quad.ll,quad.ul]
                    for a,b in zip(points,points[1:]):self._stroke(a,b,width)
                elif kind=='c':
                    for a,b,error in _curve_segments(*item[1:]):self._stroke(a,b,width+error)
                if self._segment_count>MAX_SEGMENTS:
                    self._fail('LAYOUT_SOURCE_LIMIT','Native stroke count exceeds the bounded collision planner. No unverified layout was emitted.','source');return
        # Size alone cannot distinguish a flange face / black dot from a CAD
        # glyph. Require a run of aligned character-sized paths, then protect
        # the entire word-like run (including spaces / character interiors).
        glyph_index=_Index();neighbors=defaultdict(set)
        for position,(index,rect) in enumerate(glyphs):glyph_index.add(_rect(rect,30),(position,index,rect))
        for position,(index,rect) in enumerate(glyphs):
            for other,_,candidate in glyph_index.query(_rect(rect,30)):
                if other<=position:continue
                horizontal=(abs(rect.y0-candidate.y0)<=1.2 and abs(rect.y1-candidate.y1)<=1.2 and
                    max(rect.x0,candidate.x0)-min(rect.x1,candidate.x1)<=max(12,rect.height*1.5))
                vertical=(abs(rect.x0-candidate.x0)<=1.2 and abs(rect.x1-candidate.x1)<=1.2 and
                    max(rect.y0,candidate.y0)-min(rect.y1,candidate.y1)<=max(12,rect.width*1.5))
                if horizontal or vertical:neighbors[position].add(other);neighbors[other].add(position)
        visited=set()
        for position in range(len(glyphs)):
            if position in visited:continue
            pending=[position];group=set()
            while pending:
                current=pending.pop()
                if current in group:continue
                group.add(current);pending.extend(neighbors[current]-group)
            visited.update(group)
            if len(group)<2 or source_words_supplied and source_sha256==SOURCE_1010_SHA:continue
            box=fitz.Rect(glyphs[min(group)][1])
            for member in group:box|=glyphs[member][1]
            self._protect({'id':f'outlined-text-run-{min(group)}','kind':'SOURCE_OUTLINED_TEXT',
                'bbox':_rect(box,1.1),'source_path_ids':[glyphs[i][0] for i in sorted(group)],
                'evidence':'Conservative aligned native outlined-character run; no engineering dimension was inferred.'})
        for annotation in page.annots() or []:
            if annotation.type[1] in ('Line','PolyLine','Polygon','Ink'):
                vertices=annotation.vertices or []
                strokes=vertices if annotation.type[1]=='Ink' else [vertices]
                padding=max(.6,float(annotation.border.get('width',1))/2)+.5
                nm=annotation.info.get('id') or f'xref-{annotation.xref}'
                multiply=page.parent.xref_get_key(annotation.xref,'BM')==('name','/Multiply')
                highlight=(annotation.type[1]=='Ink' and annotation.info.get('subject')=='Highlight' and multiply)
                if highlight:self._highlight_annotations.append({'annotation_nm':nm,'bbox':_rect(annotation.rect),
                    'source_sha256':source_sha256})
                for si,stroke in enumerate(strokes):
                    if not stroke:continue
                    for segment,(a,b) in enumerate(zip(stroke,stroke[1:])):
                        self._stroke(a,b,padding)
                        if annotation.type[1]=='Ink':
                            self._protect({'id':f'source-annotation-{annotation.xref}-stroke-{si}-{segment}',
                                'kind':'SOURCE_ANNOTATION_STROKE','bbox':[min(a[0],b[0])-padding,min(a[1],b[1])-padding,
                                    max(a[0],b[0])+padding,max(a[1],b[1])+padding],
                                'source_annotation_nm':nm,'multiply_highlight':highlight,
                                'evidence':'Precise original native Ink segment with its actual border width.'})
                continue
            self._protect({'id':'source-annotation-'+str(annotation.xref),'kind':'SOURCE_ANNOTATION',
                'bbox':_rect(annotation.rect,1.5),'evidence':'Original native annotation retained in the source layer.'})
        for index,image in enumerate(page.get_image_info()):
            bbox=_rect(image['bbox'],1)
            self._fills.add(bbox,{'bbox':bbox,'kind':'SOURCE_IMAGE','image_index':index})

    @property
    def can_export(self):return not self.issues

    def _fatal(self):
        return any(i['code'] in ('LAYOUT_SOURCE_LIMIT','LAYOUT_PROTECTION_INVALID') for i in self.issues)

    def _fail(self,code,message,key):
        self.issues.append({'code':code,'severity':'critical','color':'blue','sheet_id':self.sheet_id,
            'object_key':key,'message':message,'export_blocking':True,'engineering_approved':False})

    def _protect(self,region):
        # Ink markup is a collection of strokes, not an opaque rectangle. Its
        # native vertices are protected below; the broad extent may enclose a
        # legitimate source feature and must not become a fictitious filled box.
        if region.get('annotation_type') in ('Ink','Line','PolyLine','Polygon'):return
        try:
            padding=float(region.get('padding_pt',0))
            if not math.isfinite(padding) or not 0<=padding<=1000:raise ValueError()
            bbox=_rect(region['bbox'],padding)
        except (ValueError,TypeError):self._fail('LAYOUT_PROTECTION_INVALID','A source protection region is invalid; review its source evidence.',region.get('id','source'));return
        if len(bbox)!=4 or not all(math.isfinite(v) for v in bbox) or bbox[2]<bbox[0] or bbox[3]<bbox[1]:
            self._fail('LAYOUT_PROTECTION_INVALID','A source protection region is invalid; review its source evidence.',region.get('id','source'));return
        value={**region,'bbox':bbox};self.protected_regions.append(value);self._protected.add(bbox,value)
        if 'NORTH' in value['kind'].upper():self.north_regions.append(value)

    def _stroke(self,first,second,padding):
        a=[float(first[0]),float(first[1])];b=[float(second[0]),float(second[1])]
        bbox=[min(a[0],b[0])-padding,min(a[1],b[1])-padding,max(a[0],b[0])+padding,max(a[1],b[1])+padding]
        self._ink.add(bbox,(a,b,padding));self._segment_count+=1

    def reserve(self,rect,key,kind='generated'):
        bbox=_rect(rect)
        if not all(math.isfinite(v) for v in bbox) or bbox[0]<0 or bbox[1]<0 or bbox[2]>self.width or bbox[3]>self.height or bbox[2]<=bbox[0] or bbox[3]<=bbox[1]:
            self._fail('LAYOUT_OBJECT_OUTSIDE_PAGE','A generated object has no nonempty in-page graphic rectangle.',key);return None
        value={'key':key,'kind':kind,'bbox':bbox};self.occupied.append(value);self._occupied.add(bbox,value)
        return bbox

    def box_clear(self,rect,include_occupied=True):
        bbox=_rect(rect)
        if bbox[0]<self._bounds[0] or bbox[1]<self._bounds[1] or bbox[2]>self._bounds[2] or bbox[3]>self._bounds[3]:return False
        if any(_overlap(bbox,v['bbox']) for v in self._protected.query(bbox)):return False
        if any(_overlap(bbox,v['bbox']) for v in self._fills.query(bbox)):return False
        if include_occupied and any(_overlap(_rect(bbox,1.5),v['bbox']) for v in self._occupied.query(_rect(bbox,1.5))):return False
        for a,b,padding in self._ink.query(_rect(bbox,3)):
            if _line_rect(a,b,_rect(bbox,padding)):return False
        return True

    def place_box(self,preferred,width,height,key,near=None,max_distance=None):
        if self._fatal():return None
        try:
            width=float(width);height=float(height);x=float(preferred[0]);y=float(preferred[1])
            if not all(math.isfinite(v) for v in (x,y,width,height)) or width<=0 or height<=0:raise ValueError()
        except (ValueError,TypeError,IndexError):
            self._fail('LAYOUT_OBJECT_INVALID','A readable generated box needs finite positive dimensions and an explicit preferred graphic location.',key);return None
        step=max(6.,min(18.,min(width,height)/2));tested=0
        origin=[x+width/2,y+height/2];near=list(near) if near is not None else origin
        max_radius=math.ceil((max(self.width,self.height)+max(width,height))/step)
        for radius in range(max_radius+1):
            offsets=[(0,0)] if radius==0 else sorted(
                {(dx,dy) for dx in range(-radius,radius+1) for dy in (-radius,radius)}|
                {(dx,dy) for dy in range(-radius+1,radius) for dx in (-radius,radius)},
                key=lambda p:(p[0]*p[0]+p[1]*p[1],p[1],p[0]))
            for dx,dy in offsets:
                tested+=1
                if tested>MAX_BOX_CANDIDATES:break
                rect=[x+dx*step,y+dy*step,x+dx*step+width,y+dy*step+height]
                center=[(rect[0]+rect[2])/2,(rect[1]+rect[3])/2]
                if max_distance is not None and _length(center,near)>max_distance:continue
                if self.box_clear(rect):return self.reserve(rect,key)
            if tested>MAX_BOX_CANDIDATES:break
            if max_distance is not None and radius*step>max_distance+_length(origin,near)+max(width,height):break
        self._fail('LAYOUT_SPACE_UNAVAILABLE','No source-clear readable position was found within the bounded graphic search. Move the object or inspect a larger clear region; no object was silently omitted.',key)
        return None

    def _route_obstacles(self,rect,target):
        for region in self._protected.query(rect):
            if region.get('multiply_highlight') and region.get('source_annotation_nm') in self._allowed_highlights:continue
            if _overlap(rect,region['bbox']):yield region['bbox']
        for region in self._occupied.query(rect):
            # The leader must be allowed to enter its own bubble/label box.
            if not _inside(target,region['bbox']) and _overlap(rect,region['bbox']):yield _rect(region['bbox'],1.8)

    def segment_clear(self,first,second,target=None):
        target=target if target is not None else second
        rect=[min(first[0],second[0])-.6,min(first[1],second[1])-.6,max(first[0],second[0])+.6,max(first[1],second[1])+.6]
        return not any(_line_rect(first,second,_rect(obstacle,.65)) for obstacle in self._route_obstacles(rect,target))

    def reserve_leader(self,points,key):
        for annotation in self._highlight_annotations:
            if annotation['annotation_nm'] not in self._allowed_highlights:continue
            protected=[r for r in self.protected_regions if r.get('source_annotation_nm')==annotation['annotation_nm']]
            for first,second in zip(points,points[1:]):
                if any(_line_rect(first,second,r['bbox']) for r in protected):
                    self.allowed_source_annotation_crossings.append({'annotation_nm':annotation['annotation_nm'],
                        'source_sha256':self.source_sha256,'object_key':key,'segment':[list(first),list(second)],
                        'policy':'THIN_NO_FILL_LEADER_EXIT_FROM_ORIGINAL_MULTIPLY_HIGHLIGHT_ENCLOSING_SOURCE_ANCHOR',
                        'original_annotation_modified':False})
        for first,second in zip(points,points[1:]):self._stroke(first,second,.9)
        self.leader_routes.append({'key':key,'points':[list(point) for point in points]})
        return points

    def route_leader(self,anchor,target,key):
        if self._fatal():return None
        self._allowed_highlights=set();previous_issue_count=len(self.issues)
        try:
            result=self._route_leader(anchor,target,key)
            if result is not None:return result
            if len(self.issues)>previous_issue_count:return None
            # Retain a strict attempt first. Only a source anchor enclosed by an
            # original Multiply Highlight Ink annotation may use this narrow
            # exit exception; unrelated highlights and all text stay barriers.
            if self.source_sha256:
                self._allowed_highlights={a['annotation_nm'] for a in self._highlight_annotations if _inside(anchor,a['bbox'])}
            if self._allowed_highlights:
                result=self._route_leader(anchor,target,key)
                if result is not None:return result
            self._fail('LAYOUT_LEADER_BLOCKED','No bounded leader route avoids original text, protected dimensions/materials/NORTH and other generated boxes. The point was retained as a typed layout exception; no source text was covered.',key)
            return None
        finally:self._allowed_highlights=set()

    def _route_leader(self,anchor,target,key):
        if self._fatal():return None
        a=[float(v) for v in anchor];b=[float(v) for v in target]
        if not all(math.isfinite(v) for v in a+b) or not _inside(a,[0,0,self.width,self.height]) or not _inside(b,[0,0,self.width,self.height]):
            self._fail('LAYOUT_LEADER_INVALID','A leader needs finite source-anchor and target coordinates inside the original page.',key);return None
        def clear(points):return all(self.segment_clear(p,q,b) for p,q in zip(points,points[1:]))
        def cleaned(points):return [p for index,p in enumerate(points) if index==0 or p!=points[index-1]]
        if clear([a,b]):return self.reserve_leader([a,b],key)
        for middle in ([a[0],b[1]],[b[0],a[1]]):
            points=cleaned([a,middle,b])
            if clear(points):return self.reserve_leader(points,key)
        corridor=[max(3,min(a[0],b[0])-180),max(3,min(a[1],b[1])-180),
            min(self.width-3,max(a[0],b[0])+180),min(self.height-3,max(a[1],b[1])+180)]
        obstacles=list(self._route_obstacles(corridor,b))
        xs={a[0],b[0]};ys={a[1],b[1]}
        for rect in obstacles:
            xs.update((rect[0]-3,rect[2]+3));ys.update((rect[1]-3,rect[3]+3))
        for x in sorted(xs,key=lambda x:(abs(x-(a[0]+b[0])/2),x))[:100]:
            points=cleaned([a,[x,a[1]],[x,b[1]],b])
            if 3<=x<=self.width-3 and clear(points):return self.reserve_leader(points,key)
        for y in sorted(ys,key=lambda y:(abs(y-(a[1]+b[1])/2),y))[:100]:
            points=cleaned([a,[a[0],y],[b[0],y],b])
            if 3<=y<=self.height-3 and clear(points):return self.reserve_leader(points,key)
        # A bounded visibility graph around current protection rectangles finds
        # multi-bend paths without rasterizing source pixels or modifying ink.
        obstacles=sorted(obstacles,key=lambda r:(_length(a,[(r[0]+r[2])/2,(r[1]+r[3])/2])+_length(b,[(r[0]+r[2])/2,(r[1]+r[3])/2]),r))[:64]
        points=[a,b]
        for x0,y0,x1,y1 in obstacles:
            for point in ([x0-3,y0-3],[x1+3,y0-3],[x1+3,y1+3],[x0-3,y1+3]):
                if _inside(point,[3,3,self.width-3,self.height-3]) and self.segment_clear(point,point,b) and point not in points:points.append(point)
        queue=[(_length(a,b),0.,0)];distance={0:0.};prior={};closed=set();tests=0;edge_cache={}
        while queue and tests<MAX_ROUTE_TESTS:
            _,cost,index=heapq.heappop(queue)
            if index in closed:continue
            if index==1:
                path=[points[1]]
                while index in prior:index=prior[index];path.append(points[index])
                path.reverse();return self.reserve_leader(path,key)
            closed.add(index)
            neighbors=sorted((i for i in range(len(points)) if i not in closed and i!=index),
                key=lambda i:(_length(points[index],points[i])+_length(points[i],b),i))
            for nxt in neighbors:
                pair=(min(index,nxt),max(index,nxt))
                if pair not in edge_cache:
                    tests+=1;edge_cache[pair]=self.segment_clear(points[index],points[nxt],b)
                if not edge_cache[pair]:continue
                candidate=cost+_length(points[index],points[nxt])
                if candidate<distance.get(nxt,float('inf')):
                    distance[nxt]=candidate;prior[nxt]=index
                    heapq.heappush(queue,(candidate+_length(points[nxt],b),candidate,nxt))
        return None
