"""Authenticate heavy uploads before multipart parsing; bound streamed bodies."""
import hashlib
import json
import time

from fastapi import HTTPException, Request


class BodyLimit(Exception):
    pass


class IntakeGuard:
    def __init__(self, app, api):self.app,self.api=app,api
    async def __call__(self,scope,receive,send):
        if scope["type"]!="http" or scope["method"] not in ("POST","PUT","PATCH"):
            return await self.app(scope,receive,send)
        path=scope.get("path","");headers=dict(scope.get("headers",[]))
        heavy=path.endswith(("/sources","/intake","/catalogs/import"))
        worker_result='/api/v1/worker/pages/' in path and path.endswith('/result')
        maximum=32*1024**2 if heavy else 16*1024**2 if worker_result else 65536 if path.endswith("/auth/login") else 2*1024**2
        async def reject(status,message):
            data=json.dumps({"detail":message}).encode()
            await send({"type":"http.response.start","status":status,"headers":[(b"content-type",b"application/json"),(b"cache-control",b"no-store")]})
            await send({"type":"http.response.body","body":data})
        actor=None
        if heavy:
            try:
                actor=self.api.user(Request(scope))
                if actor["role"] not in ('admin','engineer'):raise HTTPException(403,"Engineering editor access required.")
            except HTTPException as error:return await reject(error.status_code,str(error.detail))
        try:
            size=int(headers.get(b"content-length",b"0"))
            if size<0:raise ValueError()
        except ValueError:return await reject(400,"Invalid request length.")
        if size>maximum:return await reject(413,"Request exceeds the allowed size.")
        if heavy or path.endswith("/auth/login"):
            key=("upload:"+actor["id"]) if actor else "login:"+hashlib.sha256(str(scope.get("client",("",))[0]).encode()).hexdigest()
            bucket=int(time.time()/60);limit=10 if heavy else 20
            with self.api.db() as conn:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute("INSERT INTO intake_limits VALUES (?,?,1) ON CONFLICT(key) DO UPDATE SET count=CASE WHEN bucket=excluded.bucket THEN count+1 ELSE 1 END,bucket=excluded.bucket",(key,bucket))
                count=conn.execute("SELECT count FROM intake_limits WHERE key=?",(key,)).fetchone()[0]
                conn.execute("DELETE FROM intake_limits WHERE bucket<?",(bucket-60,))
            if count>limit:return await reject(429,"Too many requests. Try again in a minute.")
        seen=0;overflow=False;started=False;replaced=False
        async def bounded():
            nonlocal seen,overflow
            message=await receive();seen+=len(message.get("body",b""))
            if seen>maximum:overflow=True;raise BodyLimit()
            return message
        async def output(message):
            nonlocal started,replaced
            if overflow:
                if not started:
                    await reject(413,"Request exceeds the allowed size.");started=True;replaced=True
                return
            if message["type"]=="http.response.start":started=True
            if not replaced:await send(message)
        try:await self.app(scope,bounded,output)
        except Exception:
            if not overflow:raise
            if not started:await reject(413,"Request exceeds the allowed size.")


def install(api):
    api.app.add_middleware(IntakeGuard,api=api)
