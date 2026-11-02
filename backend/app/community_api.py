# 기능: 기숙사 커뮤니티 API(API.md 4.19) — 자유게시판 · 애로사항 제안 글 · 익명 댓글 · 공감 · 신고.
# 시스템 범위: 등록 사용자만 작성하며 화면에는 작성자를 익명(글쓴이 · 익명N)으로만 표시한다. 사용자 ID · 닉네임은 응답에 포함하지 않는다.
# 결과: 욕설 · 연락처 · 링크가 포함된 글은 거절하고, 작성 간격 · 하루 작성 수를 제한하며, 신고 3회 누적 시 자동으로 숨긴다.
# 두 게시판 모두 사진(글당 3장, 장당 600KB, JPEG · PNG · WebP 시그니처 확인)을 첨부할 수 있다.
import base64
import binascii
import re
import secrets
from datetime import datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Header, Query, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from starlette.concurrency import run_in_threadpool

from app import simulations as store
from app.matches import _now
from app.persona_api import PersonaAPIError
from app.users import get_user

Board = Literal['free', 'grievance']
Category = Literal['시설', '소음', '청결', '식당', '안전', '기타']
REPORT_HIDE = 3          # 신고 누적 시 자동 숨김 기준
FORWARD_LIKES = 5        # 애로사항 글 공감이 이 수 이상이면 '생활관 전달 대상'
LIST_LIMIT = 50
MAX_IMAGES = 3            # 애로사항 글당 사진 수
MAX_IMAGE_BYTES = 600_000  # 사진 1장 최대 크기(브라우저에서 축소 후 업로드, nginx 요청 1MB 제한 이내)
# 작성 제한: (최소 간격(초), 하루 최대 건수)
POST_LIMIT = (10, 30)
COMMENT_LIMIT = (3, 100)

# 금칙어: 낱말은 기호만 제거하고 띄어쓰기는 유지한 채 검사("감염병 신고" 같은 정상 문장 오판 방지),
# 자음 약어(ㅅㅂ 등)만 띄어쓰기까지 제거한 뒤 검사한다. 모욕 · 비하 표현 위주로 최소한만 둔다.
BANNED = ('씨발', '시발', 'ㅆㅂ', 'ㅅㅂ', '병신', 'ㅂㅅ', 'ㅄ', '개새끼', '개새', '좆', '지랄', '미친놈', '미친년',
          '썅', '니미', '느금', '애미', '애비', '창녀', '걸레년', '한남충', '김치녀', '틀딱', '장애인새끼')
# 금칙어를 포함하지만 정상적인 낱말(예: 시발점)은 검사 전에 제외한다.
ALLOWED = ('시발점', '시발역', '애비뉴', '니미츠')
PHONE = re.compile(r'01[016789][\s\-.]?\d{3,4}[\s\-.]?\d{4}')
LINK = re.compile(r'https?://|www\.|\.(com|net|kr|io|me|ly)(/|\b)', re.IGNORECASE)
SYMBOLS = re.compile(r'[^\w\s]|_', re.UNICODE)
JAMO = ('ㅆㅂ', 'ㅅㅂ', 'ㅂㅅ', 'ㅄ')
WORDS = tuple(word for word in BANNED if word not in JAMO)


def check_content(*texts: str) -> None:
    for text in texts:
        if PHONE.search(text):
            raise PersonaAPIError(422, 'CONTENT_REJECTED', '전화번호 등 연락처는 게시할 수 없어요.')
        if LINK.search(text):
            raise PersonaAPIError(422, 'CONTENT_REJECTED', '링크는 게시할 수 없어요.')
        spaced = SYMBOLS.sub('', text).lower()
        for word in ALLOWED:
            spaced = spaced.replace(word, '')
        compact = re.sub(r'\s+', '', spaced)
        if any(word in spaced for word in WORDS) or any(word in compact for word in JAMO):
            raise PersonaAPIError(422, 'CONTENT_REJECTED', '욕설 · 비하 표현이 포함되어 있어요. 표현을 바꿔 다시 작성해 주세요.')


def _clean(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError('빈 문구는 보낼 수 없어요.')
    return value


class PostCreate(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid')
    board: Board
    category: Category | None = None
    title: Annotated[str, Field(min_length=2, max_length=40)]
    body: Annotated[str, Field(min_length=2, max_length=1000)]

    @field_validator('title', 'body', mode='after')
    @classmethod
    def _strip(cls, value):
        return _clean(value)


class CommentCreate(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid')
    body: Annotated[str, Field(min_length=1, max_length=300)]

    @field_validator('body', mode='after')
    @classmethod
    def _strip(cls, value):
        return _clean(value)


class ImageCreate(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid')
    data: Annotated[str, Field(min_length=16, max_length=MAX_IMAGE_BYTES * 4 // 3 + 64)]


class PostSummary(BaseModel):
    post_id: str
    board: Board
    category: str | None
    title: str
    excerpt: str
    like_count: int
    comment_count: int
    image_count: int
    created_at: str
    is_mine: bool
    forwarded: bool


class Comment(BaseModel):
    comment_id: str
    author: str
    body: str
    created_at: str
    is_mine: bool


class PostDetail(PostSummary):
    body: str
    images: list[str]
    liked: bool
    reported: bool
    comments: list[Comment]


class PostList(BaseModel):
    posts: list[PostSummary]


class ReactionResult(BaseModel):
    like_count: int
    liked: bool
    reported: bool
    hidden: bool


def _count(db, target_type, target_id, kind):
    return db.execute('SELECT COUNT(*) FROM community_reactions WHERE target_type=? AND target_id=? AND kind=?',
                      (target_type, target_id, kind)).fetchone()[0]


def _has(db, target_type, target_id, user_id, kind):
    return db.execute('SELECT 1 FROM community_reactions WHERE target_type=? AND target_id=? AND user_id=? AND kind=?',
                      (target_type, target_id, user_id, kind)).fetchone() is not None


def _summary(db, row, user_id):
    likes = _count(db, 'post', row['post_id'], 'like')
    comments = db.execute("SELECT COUNT(*) FROM community_comments WHERE post_id=? AND status='visible'",
                          (row['post_id'],)).fetchone()[0]
    images = db.execute('SELECT COUNT(*) FROM community_images WHERE post_id=?', (row['post_id'],)).fetchone()[0]
    body = row['body'].replace('\n', ' ')
    return {'post_id': row['post_id'], 'board': row['board'], 'category': row['category'], 'title': row['title'],
            'excerpt': body[:80] + ('…' if len(body) > 80 else ''), 'like_count': likes, 'comment_count': comments,
            'image_count': images,
            'created_at': row['created_at'], 'is_mine': row['user_id'] == user_id,
            'forwarded': row['board'] == 'grievance' and likes >= FORWARD_LIKES}


def _visible_post(db, post_id):
    row = db.execute("SELECT * FROM community_posts WHERE post_id=? AND status='visible'", (post_id,)).fetchone()
    if row is None:
        raise PersonaAPIError(404, 'POST_NOT_FOUND', '삭제되었거나 신고로 숨겨진 글이에요.')
    return row


def _detail(db, row, user_id):
    comments = db.execute("SELECT * FROM community_comments WHERE post_id=? AND status='visible' "
                          'ORDER BY created_at, rowid', (row['post_id'],)).fetchall()
    images = db.execute('SELECT image_id FROM community_images WHERE post_id=? ORDER BY created_at, rowid',
                        (row['post_id'],)).fetchall()
    return {**_summary(db, row, user_id), 'body': row['body'],
            'images': [f"/api/community/images/{image['image_id']}" for image in images],
            'liked': _has(db, 'post', row['post_id'], user_id, 'like'),
            'reported': _has(db, 'post', row['post_id'], user_id, 'report'),
            'comments': [{'comment_id': c['comment_id'], 'author': '글쓴이' if c['anon_no'] == 0 else f"익명{c['anon_no']}",
                          'body': c['body'], 'created_at': c['created_at'], 'is_mine': c['user_id'] == user_id}
                         for c in comments]}


def _rate_limit(db, table, user_id, limit, label):
    gap, daily = limit
    now = datetime.fromisoformat(_now())
    latest = db.execute(f'SELECT MAX(created_at) FROM {table} WHERE user_id=?', (user_id,)).fetchone()[0]
    if latest and (now - datetime.fromisoformat(latest)).total_seconds() < gap:
        raise PersonaAPIError(429, 'TOO_MANY_POSTS', f'{label} 너무 빠르게 작성하고 있어요. 잠시 후 다시 시도해 주세요.')
    since = (now - timedelta(days=1)).isoformat(timespec='seconds')
    if db.execute(f'SELECT COUNT(*) FROM {table} WHERE user_id=? AND created_at > ?', (user_id, since)).fetchone()[0] >= daily:
        raise PersonaAPIError(429, 'TOO_MANY_POSTS', f'{label} 하루 최대 {daily}건까지 작성할 수 있어요.')


def list_posts(db_path, user_id, board):
    with store._connection(db_path) as db:
        rows = db.execute("SELECT * FROM community_posts WHERE board=? AND status='visible' "
                          'ORDER BY created_at DESC, rowid DESC LIMIT ?', (board, LIST_LIMIT)).fetchall()
        return {'posts': [_summary(db, row, user_id) for row in rows]}


def create_post(db_path, user_id, payload: PostCreate):
    check_content(payload.title, payload.body)
    category = payload.category if payload.board == 'grievance' else None
    if payload.board == 'grievance' and category is None:
        category = '기타'
    with store._connection(db_path, write=True) as db:
        _rate_limit(db, 'community_posts', user_id, POST_LIMIT, '글을')
        post_id = 'pst_' + secrets.token_hex(8)
        db.execute("INSERT INTO community_posts VALUES (?,?,?,?,?,?,'visible',?)",
                   (post_id, user_id, payload.board, category, payload.title, payload.body, _now()))
        return _detail(db, _visible_post(db, post_id), user_id)


def get_post(db_path, user_id, post_id):
    with store._connection(db_path) as db:
        return _detail(db, _visible_post(db, post_id), user_id)


def delete_post(db_path, user_id, post_id):
    with store._connection(db_path, write=True) as db:
        row = _visible_post(db, post_id)
        if row['user_id'] != user_id:
            raise PersonaAPIError(403, 'NOT_OWNER', '내가 쓴 글만 삭제할 수 있어요.')
        db.execute("UPDATE community_posts SET status='deleted' WHERE post_id=?", (post_id,))
    return {'deleted': True}


def add_comment(db_path, user_id, post_id, payload: CommentCreate):
    check_content(payload.body)
    with store._connection(db_path, write=True) as db:
        post = _visible_post(db, post_id)
        _rate_limit(db, 'community_comments', user_id, COMMENT_LIMIT, '댓글을')
        if post['user_id'] == user_id:
            anon = 0
        else:
            mine = db.execute('SELECT anon_no FROM community_comments WHERE post_id=? AND user_id=? LIMIT 1',
                              (post_id, user_id)).fetchone()
            anon = mine[0] if mine else db.execute(
                'SELECT COALESCE(MAX(anon_no), 0) + 1 FROM community_comments WHERE post_id=?', (post_id,)).fetchone()[0]
        db.execute("INSERT INTO community_comments VALUES (?,?,?,?,?,'visible',?)",
                   ('cmt_' + secrets.token_hex(8), post_id, user_id, anon, payload.body, _now()))
        return _detail(db, post, user_id)


def _decode_image(data: str) -> tuple[str, bytes]:
    """data URL 또는 base64 문자열을 바이트로 바꾸고, 선언된 형식이 아니라 파일 시그니처로 형식을 판정한다."""
    payload = data.split(',', 1)[1] if data.startswith('data:') else data
    try:
        raw = base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError):
        raise PersonaAPIError(422, 'IMAGE_REJECTED', '사진 파일을 읽을 수 없어요.')
    if len(raw) > MAX_IMAGE_BYTES:
        raise PersonaAPIError(422, 'IMAGE_REJECTED', '사진이 너무 커요. 더 작은 사진을 올려 주세요.')
    if raw[:3] == b'\xff\xd8\xff':
        return 'image/jpeg', raw
    if raw[:8] == b'\x89PNG\r\n\x1a\n':
        return 'image/png', raw
    if raw[:4] == b'RIFF' and raw[8:12] == b'WEBP':
        return 'image/webp', raw
    raise PersonaAPIError(422, 'IMAGE_REJECTED', 'JPEG · PNG · WebP 사진만 올릴 수 있어요.')


def add_image(db_path, user_id, post_id, payload: ImageCreate):
    mime, raw = _decode_image(payload.data)
    with store._connection(db_path, write=True) as db:
        post = _visible_post(db, post_id)
        if post['user_id'] != user_id:
            raise PersonaAPIError(403, 'NOT_OWNER', '내가 쓴 글에만 사진을 올릴 수 있어요.')
        if db.execute('SELECT COUNT(*) FROM community_images WHERE post_id=?', (post_id,)).fetchone()[0] >= MAX_IMAGES:
            raise PersonaAPIError(422, 'IMAGE_REJECTED', f'사진은 글마다 최대 {MAX_IMAGES}장까지 올릴 수 있어요.')
        db.execute('INSERT INTO community_images VALUES (?,?,?,?,?,?)',
                   ('img_' + secrets.token_hex(12), post_id, user_id, mime, raw, _now()))
        return _detail(db, post, user_id)


def get_image(db_path, image_id):
    with store._connection(db_path) as db:
        row = db.execute("SELECT i.mime, i.data FROM community_images i JOIN community_posts p ON p.post_id=i.post_id "
                         "WHERE i.image_id=? AND p.status='visible'", (image_id,)).fetchone()
    if row is None:
        raise PersonaAPIError(404, 'IMAGE_NOT_FOUND', '사진을 찾을 수 없어요.')
    return row['mime'], bytes(row['data'])


def _visible_comment(db, comment_id):
    row = db.execute("SELECT c.* FROM community_comments c JOIN community_posts p ON p.post_id=c.post_id "
                     "WHERE c.comment_id=? AND c.status='visible' AND p.status='visible'", (comment_id,)).fetchone()
    if row is None:
        raise PersonaAPIError(404, 'COMMENT_NOT_FOUND', '삭제되었거나 신고로 숨겨진 댓글이에요.')
    return row


def delete_comment(db_path, user_id, comment_id):
    with store._connection(db_path, write=True) as db:
        row = _visible_comment(db, comment_id)
        if row['user_id'] != user_id:
            raise PersonaAPIError(403, 'NOT_OWNER', '내가 쓴 댓글만 삭제할 수 있어요.')
        db.execute("UPDATE community_comments SET status='deleted' WHERE comment_id=?", (comment_id,))
        return _detail(db, _visible_post(db, row['post_id']), user_id)


def react(db_path, user_id, target_type, target_id, kind):
    with store._connection(db_path, write=True) as db:
        row = _visible_post(db, target_id) if target_type == 'post' else _visible_comment(db, target_id)
        if row['user_id'] == user_id:
            raise PersonaAPIError(409, 'OWN_CONTENT', '내가 쓴 글에는 공감하거나 신고할 수 없어요.')
        db.execute('INSERT OR IGNORE INTO community_reactions VALUES (?,?,?,?,?)',
                   (target_type, target_id, user_id, kind, _now()))
        hidden = False
        if kind == 'report' and _count(db, target_type, target_id, 'report') >= REPORT_HIDE:
            table, key = ('community_posts', 'post_id') if target_type == 'post' else ('community_comments', 'comment_id')
            db.execute(f"UPDATE {table} SET status='hidden' WHERE {key}=?", (target_id,))
            hidden = True
        return {'like_count': _count(db, target_type, target_id, 'like'),
                'liked': _has(db, target_type, target_id, user_id, 'like'),
                'reported': _has(db, target_type, target_id, user_id, 'report'), 'hidden': hidden}


def create_community_router(database, error_model):
    router = APIRouter(prefix='/api/community', tags=['community'])
    errors = {status: {'model': error_model} for status in (401, 404, 422, 500)}

    def require_user(x_user_id):
        if not x_user_id or get_user(database, x_user_id) is None:
            raise PersonaAPIError(401, 'USER_REQUIRED', '등록된 사용자 ID를 보내 주세요.')

    async def run(fn, x_user_id, *args):
        await run_in_threadpool(require_user, x_user_id)
        return await run_in_threadpool(fn, database, x_user_id, *args)

    @router.get('/posts', response_model=PostList, responses=errors)
    async def posts(board: Annotated[Board, Query()] = 'free', x_user_id: Annotated[str | None, Header()] = None):
        return await run(list_posts, x_user_id, board)

    @router.post('/posts', status_code=201, response_model=PostDetail, responses={**errors, 429: {'model': error_model}})
    async def write(payload: PostCreate, x_user_id: Annotated[str | None, Header()] = None):
        return await run(create_post, x_user_id, payload)

    @router.get('/posts/{post_id}', response_model=PostDetail, responses=errors)
    async def read(post_id: str, x_user_id: Annotated[str | None, Header()] = None):
        return await run(get_post, x_user_id, post_id)

    @router.delete('/posts/{post_id}', responses={**errors, 403: {'model': error_model}})
    async def remove(post_id: str, x_user_id: Annotated[str | None, Header()] = None):
        return await run(delete_post, x_user_id, post_id)

    @router.post('/posts/{post_id}/comments', status_code=201, response_model=PostDetail,
                 responses={**errors, 429: {'model': error_model}})
    async def comment(post_id: str, payload: CommentCreate, x_user_id: Annotated[str | None, Header()] = None):
        return await run(add_comment, x_user_id, post_id, payload)

    @router.post('/posts/{post_id}/images', status_code=201, response_model=PostDetail,
                 responses={**errors, 403: {'model': error_model}})
    async def upload_image(post_id: str, payload: ImageCreate, x_user_id: Annotated[str | None, Header()] = None):
        return await run(add_image, x_user_id, post_id, payload)

    @router.get('/images/{image_id}', response_class=Response, responses={404: {'model': error_model}})
    async def image(image_id: str):
        # <img>는 헤더를 보낼 수 없으므로 추측 불가능한 ID(96비트)로만 조회. 숨김 · 삭제된 글의 사진은 404
        mime, raw = await run_in_threadpool(get_image, database, image_id)
        return Response(content=raw, media_type=mime,
                        headers={'Cache-Control': 'private, max-age=3600', 'X-Content-Type-Options': 'nosniff'})

    @router.delete('/comments/{comment_id}', response_model=PostDetail, responses={**errors, 403: {'model': error_model}})
    async def remove_comment(comment_id: str, x_user_id: Annotated[str | None, Header()] = None):
        return await run(delete_comment, x_user_id, comment_id)

    @router.post('/posts/{post_id}/like', response_model=ReactionResult, responses={**errors, 409: {'model': error_model}})
    async def like(post_id: str, x_user_id: Annotated[str | None, Header()] = None):
        return await run(react, x_user_id, 'post', post_id, 'like')

    @router.post('/posts/{post_id}/report', response_model=ReactionResult, responses={**errors, 409: {'model': error_model}})
    async def report_post(post_id: str, x_user_id: Annotated[str | None, Header()] = None):
        return await run(react, x_user_id, 'post', post_id, 'report')

    @router.post('/comments/{comment_id}/report', response_model=ReactionResult,
                 responses={**errors, 409: {'model': error_model}})
    async def report_comment(comment_id: str, x_user_id: Annotated[str | None, Header()] = None):
        return await run(react, x_user_id, 'comment', comment_id, 'report')

    return router
