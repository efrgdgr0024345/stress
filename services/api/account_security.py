"""Self-service authenticator enrollment and recent-factor assurance.

No external QR service, email sender or password recovery service is used.
Authenticator seeds and recovery hashes are owner-only files outside web/code.
"""
import base64
import hashlib
import hmac
from pathlib import Path
import re
import secrets
import struct
import time
from urllib.parse import quote, urlencode
from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from services.api import diagnostics as diag
from services.api.updates import read, write


def schema(conn):
    conn.executescript('''
    CREATE TABLE IF NOT EXISTS session_assurance (session_hash TEXT PRIMARY KEY,user_id TEXT,mfa_at REAL);
    CREATE TABLE IF NOT EXISTS mfa_limits (user_id TEXT,bucket INTEGER,count INTEGER,PRIMARY KEY(user_id,bucket));
    CREATE TABLE IF NOT EXISTS account_state (user_id TEXT PRIMARY KEY,enabled INTEGER DEFAULT 1);
    CREATE TABLE IF NOT EXISTS mfa_accounts (user_id TEXT PRIMARY KEY,enabled INTEGER,fingerprint TEXT);
    ''')


def path(api, user_id):
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',user_id):raise HTTPException(400,'Invalid account identity.')
    result=api.DATA/'security/mfa'/f'{user_id}.json'
    if result.is_symlink() or (result.exists() and result.stat().st_mode&0o077):
        raise HTTPException(503,'Private authenticator storage requires operator attention.')
    return result


def totp(secret,counter,digits=6):
    key=base64.b32decode(secret+'='*((8-len(secret)%8)%8),casefold=True)
    value=hmac.new(key,struct.pack('>Q',counter),hashlib.sha1).digest()
    offset=value[-1]&15
    number=struct.unpack('>I',value[offset:offset+4])[0]&0x7fffffff
    return str(number%(10**digits)).zfill(digits)


def cookie_hash(request):
    return hashlib.sha256(request.cookies.get('caesar_session','').encode()).hexdigest()


def active(conn,user_id):
    value=conn.execute('SELECT enabled FROM account_state WHERE user_id=?',(user_id,)).fetchone()
    return not value or bool(value['enabled'])


def bind(conn,session_hash,user_id,verified=False):
    conn.execute('INSERT OR REPLACE INTO session_assurance VALUES (?,?,?)',(session_hash,user_id,time.time() if verified else 0))


def read_value(api,user_id,conn=None):
    """An enabled database anchor must never degrade to password-only login."""
    try:value=read(path(api,user_id))
    except (ValueError,TypeError,OSError):raise HTTPException(503,'Private authenticator storage requires restoration by the hosting operator.') from None
    if not isinstance(value,dict):raise HTTPException(503,'Private authenticator storage requires operator attention.')
    if conn is None:
        with api.db() as connection:ref=connection.execute('SELECT enabled,fingerprint FROM mfa_accounts WHERE user_id=?',(user_id,)).fetchone()
    else:ref=conn.execute('SELECT enabled,fingerprint FROM mfa_accounts WHERE user_id=?',(user_id,)).fetchone()
    if ref and ref['enabled'] and (not value.get('enabled') or not value.get('secret') or
        hashlib.sha256(value['secret'].encode()).hexdigest()!=ref['fingerprint']):
        raise HTTPException(503,'Private authenticator storage requires restoration by the hosting operator.')
    return value


def status(api,actor):
    value=read_value(api,actor['id'])
    return {'enabled':bool(value.get('enabled')),'enrollment_pending':bool(value.get('pending',{}).get('expires',0)>time.time()),
            'recovery_codes_remaining':len(value.get('recovery_hashes',[]))}


def attempt(conn,user_id):
    bucket=int(time.time()/60)
    found=conn.execute('SELECT count FROM mfa_limits WHERE user_id=? AND bucket=?',(user_id,bucket)).fetchone()
    if found and found['count']>=5:raise HTTPException(429,'Too many authenticator attempts. Wait a minute.')
    conn.execute('INSERT INTO mfa_limits VALUES (?,?,1) ON CONFLICT(user_id,bucket) DO UPDATE SET count=count+1',(user_id,bucket))
    conn.execute('DELETE FROM mfa_limits WHERE bucket<?',(bucket-10,))


def verify(api,actor,code,request=None,enroll=False):
    """Consume one counter/recovery code. Errors never include supplied codes."""
    code=(code or '').replace(' ','').strip()
    filename=path(api,actor['id'])
    error=None;recovery_codes=None
    with api.db() as conn:
        conn.execute('BEGIN IMMEDIATE');attempt(conn,actor['id'])
        value=read_value(api,actor['id'],conn)
        pending=value.get('pending',{}) if enroll else None
        if enroll and (not pending or pending.get('expires',0)<time.time() or pending.get('session')!=cookie_hash(request)):
            error='Authenticator enrollment expired. Start again.'
        elif not enroll and not value.get('enabled'):
            error='Set up your authenticator before signing a final approval.'
        else:
            seed=pending['secret'] if enroll else value['secret']
            counter=int(time.time()/30)
            match=next((c for c in (counter-1,counter,counter+1) if c>=0 and secrets.compare_digest(totp(seed,c),code)),None) if re.fullmatch(r'\d{6}',code) else None
            recovered=hashlib.sha256(code.replace('-','').upper().encode()).hexdigest()
            if not enroll and recovered in value.get('recovery_hashes',[]):
                value['recovery_hashes'].remove(recovered)
            elif match is None or (not enroll and match<=value.get('last_counter',-1)):
                error='Authenticator or recovery code is invalid or has already been used.'
            elif enroll:
                raw_codes=[secrets.token_hex(10).upper() for _ in range(10)]
                recovery_codes=['-'.join(text[i:i+4] for i in range(0,20,4)) for text in raw_codes]
                value={'enabled':True,'secret':seed,'last_counter':match,
                       'recovery_hashes':[hashlib.sha256(c.replace('-','').encode()).hexdigest() for c in recovery_codes]}
            else:value['last_counter']=match
            if error is None:
                write(filename,value)
                conn.execute('INSERT OR REPLACE INTO mfa_accounts VALUES (?,?,?)',(actor['id'],1,hashlib.sha256(value['secret'].encode()).hexdigest()))
    if error:
        diag.emit(api.DATA,'security.mfa.failed','WARNING',user_id=actor['id'])
        raise HTTPException(401,error)
    diag.emit(api.DATA,'security.mfa.verified',user_id=actor['id'],enrollment=enroll)
    return recovery_codes


def require_recent(api,actor,request,code=None):
    if not status(api,actor)['enabled']:
        raise HTTPException(409,'Set up your authenticator in Account security before final approval.')
    with api.db() as conn:
        found=conn.execute('SELECT mfa_at FROM session_assurance WHERE session_hash=? AND user_id=?',(cookie_hash(request),actor['id'])).fetchone()
    if found and found['mfa_at']>time.time()-300:return
    verify(api,actor,code)
    with api.db() as conn:bind(conn,cookie_hash(request),actor['id'],True)


def install(api):
    class PasswordInput(BaseModel):
        model_config=ConfigDict(extra='forbid')
        password:str=Field(max_length=1024)
        code:str|None=Field(default=None,max_length=80)
    class CodeInput(BaseModel):
        model_config=ConfigDict(extra='forbid')
        code:str=Field(min_length=6,max_length=80)

    @api.app.get('/api/v1/account/security')
    def get(actor=Depends(api.user)):
        return status(api,actor)

    @api.app.post('/api/v1/account/security/enroll')
    def enroll(body:PasswordInput,request:Request,actor=Depends(api.user)):
        valid=actor['password'] and secrets.compare_digest(api.password_hash(body.password,actor['password'].split(':')[0]),actor['password'])
        if not valid and not (api.LOCAL_DEMO and actor['id']=='local-engineer'):
            raise HTTPException(401,'Your current account password is required.')
        if status(api,actor)['enabled']:require_recent(api,actor,request,body.code)
        filename=path(api,actor['id'])
        secret=base64.b32encode(secrets.token_bytes(20)).decode().rstrip('=')
        with api.db() as conn:
            conn.execute('BEGIN IMMEDIATE');value=read_value(api,actor['id'],conn)
            value['pending']={'secret':secret,'expires':time.time()+600,'session':cookie_hash(request)}
            write(filename,value)
        uri='otpauth://totp/'+quote('CAESAR:'+actor['email'],safe='')+'?'+urlencode({'secret':secret,'issuer':'CAESAR','algorithm':'SHA1','digits':6,'period':30})
        diag.emit(api.DATA,'security.mfa.enrollment_started',user_id=actor['id'])
        return {'secret':secret,'uri':uri,'expires_in_seconds':600}

    @api.app.post('/api/v1/account/security/confirm')
    def confirm(body:CodeInput,request:Request,actor=Depends(api.user)):
        recovery=verify(api,actor,body.code,request,enroll=True)
        with api.db() as conn:bind(conn,cookie_hash(request),actor['id'],True)
        return {'enabled':True,'recovery_codes':recovery}

    @api.app.post('/api/v1/account/security/disable')
    def disable(body:PasswordInput,request:Request,actor=Depends(api.user)):
        if not actor['password'] or not secrets.compare_digest(api.password_hash(body.password,actor['password'].split(':')[0]),actor['password']):
            raise HTTPException(401,'Your current account password is required.')
        require_recent(api,actor,request,body.code)
        with api.db() as conn:
            conn.execute('BEGIN IMMEDIATE')
            write(path(api,actor['id']),{'enabled':False})
            conn.execute('INSERT OR REPLACE INTO mfa_accounts VALUES (?,?,?)',(actor['id'],0,None))
            conn.execute('DELETE FROM session_assurance WHERE user_id=?',(actor['id'],))
        diag.emit(api.DATA,'security.mfa.disabled',user_id=actor['id'])
        return {'enabled':False}
