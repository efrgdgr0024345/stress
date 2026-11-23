"""Untrusted parser-output contracts. No output paths, URLs or commands."""
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Coordinate=Annotated[float,Field(ge=-28800,le=28800,allow_inf_nan=False)]
Box=tuple[Coordinate,Coordinate,Coordinate,Coordinate]
Point=tuple[Coordinate,Coordinate]


class Word(BaseModel):
    model_config=ConfigDict(extra="forbid")
    text:str=Field(max_length=300)
    bbox:Box
    confidence:float=Field(ge=0,le=1,allow_inf_nan=False)
    method:Literal["native","ocr"]
    evidence_id:str=Field(pattern=r"^[a-f0-9-]{36}$")


class Segment(BaseModel):
    model_config=ConfigDict(extra="forbid")
    a:Point
    b:Point
    width:float=Field(ge=0,le=1000,allow_inf_nan=False)


class Symbol(BaseModel):
    model_config=ConfigDict(extra="forbid")
    id:str=Field(pattern=r"^[a-f0-9-]{36}$")
    kind:Literal['flange']
    profile:Literal['iso-weld-neck-plate-v1']
    bbox:Box
    flange_face:Point
    opposite_pipe_dot:Point
    source_paths:list[Annotated[int,Field(ge=0,lt=50000)]]=Field(min_length=2,max_length=2)

    @model_validator(mode='after')
    def plausible_geometry(self):
        x0,y0,x1,y1=self.bbox
        if not (x0<x1 and y0<y1 and self.flange_face!=self.opposite_pipe_dot
                and all(x0<=p[0]<=x1 and y0<=p[1]<=y1 for p in (self.flange_face,self.opposite_pipe_dot))):
            raise ValueError('Source symbol needs distinct anchors enclosed by its source box.')
        return self


class PageEvidence(BaseModel):
    model_config=ConfigDict(extra="forbid")
    page_index:int=Field(ge=0,le=199)
    width:float=Field(gt=0,le=14400,allow_inf_nan=False)
    height:float=Field(gt=0,le=14400,allow_inf_nan=False)
    rotation:Literal[0,90,180,270]
    words:list[Word]=Field(max_length=30000)
    uncertain_words:list[Word]=Field(default_factory=list,max_length=5000)
    segments:list[Segment]=Field(max_length=1000)
    symbols:list[Symbol]=Field(default_factory=list,max_length=500)
    exclusions:list[Box]=Field(max_length=20000)
    ocr_used:bool
    issues:list[Literal["OCR_UNAVAILABLE","OBSERVATION_LIMIT_REACHED","LOW_CONFIDENCE_TEXT"]]=Field(max_length=10)
    source_sha256:str=Field(pattern=r"^[a-f0-9]{64}$")
    extractor_version:Literal["evidence-pipeline-1"]
    pdf_library_version:str=Field(max_length=40)
    content_hash:list[Annotated[str,Field(pattern=r"^[a-f0-9]{64}$")]]=Field(max_length=50000)
    isolation:Literal["container-no-network","landlock-seccomp","bounded-pilot","provider-function"]

    @model_validator(mode='after')
    def symbols_on_source_page(self):
        if any(not (0<=s.bbox[0]<s.bbox[2]<=self.width and 0<=s.bbox[1]<s.bbox[3]<=self.height) for s in self.symbols):
            raise ValueError('Source symbol lies outside its unrotated page.')
        return self
