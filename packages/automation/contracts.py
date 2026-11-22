"""Untrusted parser-output contracts. No output paths, URLs or commands."""
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator

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


class PageEvidence(BaseModel):
    model_config=ConfigDict(extra="forbid")
    page_index:int=Field(ge=0,le=199)
    width:float=Field(gt=0,le=14400,allow_inf_nan=False)
    height:float=Field(gt=0,le=14400,allow_inf_nan=False)
    rotation:Literal[0,90,180,270]
    words:list[Word]=Field(max_length=30000)
    uncertain_words:list[Word]=Field(default_factory=list,max_length=5000)
    segments:list[Segment]=Field(max_length=1000)
    exclusions:list[Box]=Field(max_length=20000)
    ocr_used:bool
    issues:list[Literal["OCR_UNAVAILABLE","OBSERVATION_LIMIT_REACHED","LOW_CONFIDENCE_TEXT"]]=Field(max_length=10)
    source_sha256:str=Field(pattern=r"^[a-f0-9]{64}$")
    extractor_version:Literal["evidence-pipeline-1"]
    pdf_library_version:str=Field(max_length=40)
    content_hash:list[Annotated[str,Field(pattern=r"^[a-f0-9]{64}$")]]=Field(max_length=50000)
    isolation:Literal["container-no-network","landlock-seccomp","bounded-pilot"]
