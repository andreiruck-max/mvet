"""Read-only commercial adapter. OAuth is the only remote POST allowed."""
import base64
import json
import time
from datetime import timedelta
from decimal import Decimal
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, HTTPRedirectHandler, build_opener
from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db import DatabaseError
from django.utils import timezone
from apps.accounts.access import master
from apps.core.services import audit, require
from .models import BlingConnection, ImportRun, InvoiceImport

BASE = 'https://api.bling.com.br/Api/v3'
AUTHORIZE = 'https://bling.com.br/Api/v3/oauth/authorize'
PAGE_SIZE = 5


class BlingError(ValidationError):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def cipher():
    try: return Fernet(settings.BLING_TOKEN_KEY.encode())
    except (ValueError, TypeError): raise BlingError('Configure a chave de proteção dos tokens no servidor.')


def configured():
    if not all([settings.BLING_CLIENT_ID, settings.BLING_CLIENT_SECRET, settings.BLING_REDIRECT_URI]):
        raise BlingError('Configure o aplicativo Bling no ambiente do servidor.')
    issuer = settings.BLING_ISSUER_CNPJ
    if len(issuer) != 14 or not issuer.isascii() or not issuer.isdecimal():
        raise BlingError('Configure o CNPJ emitente com 14 dígitos.')
    redirect = urlsplit(settings.BLING_REDIRECT_URI)
    if redirect.scheme not in ('http', 'https') or not redirect.netloc or redirect.username or redirect.password or redirect.query or redirect.fragment or redirect.path != '/integracoes/bling/retorno/':
        raise BlingError('Configure o endereço de retorno completo do MVet, terminando em /integracoes/bling/retorno/.')
    cipher()
    return issuer


def request_json(path, *, token=None, form=None):
    # Paths are generated internally; reject arbitrary URLs and all fiscal writes.
    if form is not None:
        if path != '/oauth/token': raise BlingError('Operação remota não permitida.')
    elif path != '/nfe' and not (path.startswith('/nfe/') and path[5:].isascii() and path[5:].isdecimal()):
        # List query is passed separately below through form-free URL encoding.
        if not path.startswith('/nfe?'): raise BlingError('Consulta remota não permitida.')
    headers = {'Accept': 'application/json', 'enable-jwt': '1'}
    data = None
    if form is not None:
        credentials = f'{settings.BLING_CLIENT_ID}:{settings.BLING_CLIENT_SECRET}'
        headers['Authorization'] = 'Basic ' + base64.b64encode(credentials.encode()).decode()
        headers['Content-Type'] = 'application/x-www-form-urlencoded'
        data = urlencode(form).encode()
    elif token:
        headers['Authorization'] = 'Bearer ' + token
    try:
        with build_opener(NoRedirect()).open(Request(BASE + path, data=data, headers=headers), timeout=8) as response:
            raw = response.read(2_000_001)
        if len(raw) > 2_000_000: raise BlingError('Resposta excede o limite de segurança.')
        result = json.loads(raw, parse_float=Decimal)
        if not isinstance(result, dict): raise ValueError
        return result
    except HTTPError as exc:
        if exc.code == 429: raise BlingError('Limite do Bling atingido. Aguarde e reexecute a página; nenhum lançamento será duplicado.') from None
        if exc.code in (400, 401, 403): raise BlingError('Acesso ao Bling recusado. O master deve conferir autorização e escopos.') from None
        raise BlingError(f'Consulta Bling falhou (HTTP {exc.code}). Reexecute a página.') from None
    except (URLError, TimeoutError, OSError, ValueError):
        raise BlingError('Falha de comunicação ou resposta inválida do Bling. Reexecute a página.') from None


def store_tokens(obj, result):
    try:
        access, refresh = result['access_token'], result['refresh_token']
        seconds = int(result['expires_in'])
        if not isinstance(access, str) or not isinstance(refresh, str) or not access or not refresh or not 1 <= seconds <= 31536000:
            raise ValueError
    except (KeyError, ValueError, TypeError):
        raise BlingError('Resposta de autorização incompleta. Autorize novamente.')
    obj.tokens = cipher().encrypt(json.dumps({'access': access, 'refresh': refresh}).encode()).decode()
    obj.expires_at = timezone.now() + timedelta(seconds=seconds)
    obj.save(update_fields=['tokens', 'expires_at'])


@transaction.atomic
def authorize(*, actor, code):
    master(actor); issuer = configured()
    obj, _ = BlingConnection.objects.get_or_create(pk=1, defaults={'issuer': issuer})
    obj = BlingConnection.objects.select_for_update().get(pk=1)
    if obj.issuer != issuer: raise BlingError('Não é permitido trocar o emitente desta base.')
    store_tokens(obj, request_json('/oauth/token', form={'grant_type': 'authorization_code', 'code': code}))
    audit(actor, obj, 'bling_authorize', after={'connected': True})


@transaction.atomic
def disconnect(*, actor):
    master(actor)
    obj = BlingConnection.objects.select_for_update().filter(pk=1).first()
    if obj:
        obj.tokens = ''; obj.expires_at = None; obj.save(update_fields=['tokens', 'expires_at'])
        audit(actor, obj, 'bling_disconnect', after={'connected': False})


@transaction.atomic
def get(path):
    """Serialize requests/refresh across workers; never hold the inventory lock."""
    obj = BlingConnection.objects.select_for_update(nowait=True).get(pk=1)
    if not obj.tokens: raise BlingError('Bling desconectado. Solicite autorização ao master.')
    try: tokens = json.loads(cipher().decrypt(obj.tokens.encode()))
    except (InvalidToken, ValueError): raise BlingError('Não foi possível abrir a credencial. Reautorize a conexão.') from None
    if not obj.expires_at or obj.expires_at <= timezone.now() + timedelta(seconds=60):
        store_tokens(obj, request_json('/oauth/token', form={'grant_type': 'refresh_token', 'refresh_token': tokens['refresh']}))
        tokens = json.loads(cipher().decrypt(obj.tokens.encode()))
    if obj.last_request_at:
        time.sleep(max(0, .4 - (timezone.now() - obj.last_request_at).total_seconds()))
    # Capture errors inside the transaction so a rotated refresh token is committed.
    failure = None
    try: result = request_json(path, token=tokens['access'])
    except BlingError as exc: failure = exc; result = None
    obj.last_request_at = timezone.now(); obj.save(update_fields=['last_request_at'])
    return result, failure


def read(path):
    try: result, failure = get(path)
    except DatabaseError: raise BlingError('Outra consulta está usando a conexão. Tente novamente em instantes.') from None
    if failure: raise failure
    return result


def sync_page(*, actor, start, end, page=1, source_status=5):
    require(actor, 'core.fetch_bling'); require(actor, 'core.review_bling')
    if start > end or (end - start).days > 366 or page < 1 or page > 10000 or source_status not in (2, 5):
        raise BlingError('Período, situação ou página inválidos.')
    connection = BlingConnection.objects.filter(pk=1).first()
    if not connection or not connection.tokens: raise BlingError('Conecte o Bling antes de consultar.')
    run = ImportRun.objects.create(connection=connection, actor=actor, start=start, end=end, page=page, source_status=source_status)
    from .services import stage
    deadline = time.monotonic() + 40
    try:
        result = read('/nfe?' + urlencode({'pagina': page, 'limite': PAGE_SIZE, 'tipo': 1, 'situacao': source_status,
                    'dataEmissaoInicial': f'{start} 00:00:00', 'dataEmissaoFinal': f'{end} 23:59:59'}))
        rows = result.get('data')
        if not isinstance(rows, list) or len(rows) > PAGE_SIZE: raise BlingError('Página inválida recebida do Bling.')
        run.has_more = len(rows) == PAGE_SIZE
        for row in rows:
            if time.monotonic() >= deadline:
                raise BlingError('Consulta parcial por demora do Bling. Reexecute esta página; notas anteriores estão preservadas.')
            external_id = str(row.get('id', '')) if isinstance(row, dict) else ''
            if not external_id.isascii() or not external_id.isdecimal(): raise BlingError('Identificador inválido na listagem.')
            try:
                payload = read('/nfe/' + external_id).get('data')
                if not isinstance(payload, dict) or str(payload.get('id')) != external_id:
                    raise BlingError('Detalhe não corresponde à nota solicitada.')
                invoice = stage(actor=actor, connection=connection, payload=payload)
                run.processed += 1
                if invoice.error: run.errors += 1
            except BlingError:
                raise  # Stop on authentication/network/rate failure; safe page retry.
            except ValidationError:
                run.errors += 1
                run.error_ids.append(external_id)
                run.message = 'Uma nota não pôde ser vinculada. Confira as duplicidades e reexecute esta página.'
    except BlingError as exc:
        run.errors += 1; run.message = '; '.join(exc.messages)[:500]
    run.finished_at = timezone.now(); run.save()
    if not run.errors:
        BlingConnection.objects.filter(pk=connection.pk).update(last_sync_at=run.finished_at)
    audit(actor, run, 'bling_sync_page', after={'processed': run.processed, 'errors': run.errors, 'page': page})
    return run


def refresh_invoice(*, actor, invoice_id):
    require(actor, 'core.review_bling'); require(actor, 'core.fetch_bling')
    obj = InvoiceImport.objects.select_related('connection').get(pk=invoice_id)
    payload = read('/nfe/' + obj.external_id).get('data')
    if not isinstance(payload, dict) or str(payload.get('id')) != obj.external_id:
        raise BlingError('Detalhe inválido.')
    from .services import stage
    return stage(actor=actor, connection=obj.connection, payload=payload)
