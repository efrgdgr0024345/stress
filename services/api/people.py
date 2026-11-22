"""Hosting-managed workspace accounts. Never send invitations automatically."""
import sqlite3
from fastapi import Depends,HTTPException
from pydantic import BaseModel,Field,ConfigDict
from services.api import account_security as security


def install(api):
    def operator(actor=Depends(api.user)):
        if actor['role']!='admin' or (not api.LOCAL_DEMO and actor['id']!='admin'):
            raise HTTPException(403,'Hosting administrator access required.')
        return actor
    class UserInput(BaseModel):
        model_config=ConfigDict(extra='forbid')
        name:str=Field(min_length=1,max_length=100)
        email:str=Field(min_length=3,max_length=254,pattern=r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
        password:str=Field(min_length=12,max_length=1024)
        role:str=Field(pattern=r'^(engineer|reviewer|viewer)$')
    class RoleInput(BaseModel):
        model_config=ConfigDict(extra='forbid')
        role:str=Field(pattern=r'^(engineer|reviewer|viewer)$')
        enabled:bool=True
        reason:str=Field(min_length=10,max_length=2000)

    @api.app.get('/api/v1/system/people')
    def people(actor=Depends(operator)):
        with api.db() as conn:
            values=[dict(r) for r in conn.execute('SELECT id,name,email,role FROM users WHERE tenant=? ORDER BY name',(actor['tenant'],))]
            for value in values:
                value['enabled']=security.active(conn,value['id'])
                value['mfa_enabled']=security.status(api,value)['enabled']
        return values

    @api.app.post('/api/v1/system/people',status_code=201)
    def create(body:UserInput,actor=Depends(operator)):
        if not body.name.strip():raise HTTPException(422,'Enter an account name.')
        email=body.email.strip().casefold()
        with api.db() as conn:
            if conn.execute('SELECT 1 FROM users WHERE lower(email)=?',(email,)).fetchone():
                raise HTTPException(409,'An account with that email already exists.')
            if conn.execute('SELECT COUNT(*) FROM users WHERE tenant=?',(actor['tenant'],)).fetchone()[0]>=100:
                raise HTTPException(409,'Workspace account limit reached.')
            identity=api.uid()
            try:conn.execute('INSERT INTO users VALUES (?,?,?,?,?,?)',(identity,body.name.strip(),email,api.password_hash(body.password),body.role,actor['tenant']))
            except sqlite3.IntegrityError:raise HTTPException(409,'Account could not be created.') from None
            api.audit(conn,'security:people',actor['name'],'Created workspace account',identity+' · '+body.role)
        api.diag.emit(api.DATA,'security.account.created',user_id=identity,role=body.role,actor_id=actor['id'])
        return {'id':identity,'name':body.name.strip(),'email':email,'role':body.role,'enabled':True}

    @api.app.patch('/api/v1/system/people/{user_id}')
    def update(user_id:str,body:RoleInput,actor=Depends(operator)):
        if user_id==actor['id'] or user_id=='admin':raise HTTPException(409,'The hosting administrator cannot be demoted or disabled here.')
        with api.db() as conn:
            conn.execute('BEGIN IMMEDIATE')
            found=conn.execute('SELECT * FROM users WHERE id=? AND tenant=?',(user_id,actor['tenant'])).fetchone()
            if not found:raise HTTPException(404,'Workspace account not found.')
            conn.execute('UPDATE users SET role=? WHERE id=?',(body.role,user_id))
            conn.execute('INSERT OR REPLACE INTO account_state VALUES (?,?)',(user_id,int(body.enabled)))
            conn.execute('DELETE FROM sessions WHERE user_id=?',(user_id,))
            conn.execute('DELETE FROM session_assurance WHERE user_id=?',(user_id,))
            api.audit(conn,'security:people',actor['name'],'Changed workspace account access',user_id+' · '+body.role+' · '+body.reason)
        api.diag.emit(api.DATA,'security.account.access_changed',user_id=user_id,role=body.role,enabled=body.enabled,actor_id=actor['id'])
        return {'id':user_id,'role':body.role,'enabled':body.enabled}
