# 기능: 기숙사 커뮤니티 API(API.md 4.19)의 글 · 익명 댓글 · 공감 · 신고 숨김 · 금칙어 · 작성 제한을 검증한다.
# 시스템 범위: 임시 SQLite만 사용하며 외부 서비스는 호출하지 않는다. 작성 간격 제한은 시험에서 0초로 낮춘다.
# 결과: 작성자 정보가 응답에 노출되지 않고, 신고 3회 누적 시 글이 숨겨지며, 본인 글 외 삭제 · 본인 글 공감이 거절됨을 확인한다.
import asyncio

import httpx
import pytest

from app import community_api
from app.database import connect_database
from app.main import create_app
from app.users import create_user


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(community_api, 'POST_LIMIT', (0, 10))
    monkeypatch.setattr(community_api, 'COMMENT_LIMIT', (0, 60))
    db = tmp_path / 'community.sqlite3'
    users = [create_user(db, name)['user_id'] for name in ('하늘', '다은', '지호', '수빈', '민서')]
    application = create_app(db_path=db)

    def call(method, path, user, body=None, params=None):
        async def run():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application, raise_app_exceptions=False),
                                         base_url='http://test') as client:
                return await client.request(method, path, json=body, params=params,
                                            headers={'X-User-Id': user} if user else {})
        return asyncio.run(run())
    return db, users, call


def write(call, user, **fields):
    body = {'board': 'free', 'title': '세탁실 건조기 질문', 'body': '3층 건조기 몇 분 돌려야 다 마르나요?', **fields}
    return call('POST', '/api/community/posts', user, body)


def test_post_comment_anonymity_and_list(env):
    db, (me, a, b, *_), call = env
    created = write(call, me)
    assert created.status_code == 201
    post = created.json()
    assert post['is_mine'] and post['comments'] == [] and post['board'] == 'free' and post['category'] is None
    # 사용자 ID · 닉네임은 응답에 없음
    assert me not in created.text and '하늘' not in created.text

    pid = post['post_id']
    call('POST', f'/api/community/posts/{pid}/comments', a, {'body': '60분이면 충분해요'})
    call('POST', f'/api/community/posts/{pid}/comments', me, {'body': '감사합니다!'})
    call('POST', f'/api/community/posts/{pid}/comments', b, {'body': '저는 80분 돌려요'})
    detail = call('POST', f'/api/community/posts/{pid}/comments', a, {'body': '그것도 좋아요'}).json()
    assert [c['author'] for c in detail['comments']] == ['익명1', '글쓴이', '익명2', '익명1']
    assert a not in str(detail) and '다은' not in str(detail)

    listed = call('GET', '/api/community/posts', b, params={'board': 'free'}).json()['posts']
    assert len(listed) == 1 and listed[0]['comment_count'] == 4 and not listed[0]['is_mine']
    assert call('GET', '/api/community/posts', b, params={'board': 'grievance'}).json()['posts'] == []


def test_grievance_category_like_forward_and_own_rules(env):
    _, (me, *others), call = env
    post = write(call, me, board='grievance', category='소음', title='밤 12시 이후 복도 소음', body='복도 통화 자제 안내를 부탁드립니다.').json()
    assert post['category'] == '소음' and not post['forwarded']
    pid = post['post_id']
    own = call('POST', f'/api/community/posts/{pid}/like', me)
    assert own.status_code == 409 and own.json()['error']['code'] == 'OWN_CONTENT'
    for user in others:
        result = call('POST', f'/api/community/posts/{pid}/like', user).json()
        assert result['liked']
    assert call('POST', f'/api/community/posts/{pid}/like', others[0]).json()['like_count'] == 4  # 중복 공감 무시
    # 기본 분류: 애로사항 글은 분류 생략 시 '기타'
    assert write(call, others[0], board='grievance').json()['category'] == '기타'


def test_reports_hide_post_and_comment(env):
    _, (me, a, b, c, d), call = env
    pid = write(call, me).json()['post_id']
    cid = call('POST', f'/api/community/posts/{pid}/comments', a, {'body': '좋은 정보네요'}).json()['comments'][0]['comment_id']
    for user in (b, c):
        assert not call('POST', f'/api/community/comments/{cid}/report', user).json()['hidden']
    assert call('POST', f'/api/community/comments/{cid}/report', d).json()['hidden']
    assert call('GET', f'/api/community/posts/{pid}', me).json()['comments'] == []

    for user in (a, b):
        assert call('POST', f'/api/community/posts/{pid}/report', user).json()['reported']
    call('POST', f'/api/community/posts/{pid}/report', a)  # 같은 사용자 반복 신고는 1회로 계산
    assert call('GET', f'/api/community/posts/{pid}', c).status_code == 200
    assert call('POST', f'/api/community/posts/{pid}/report', c).json()['hidden']
    hidden = call('GET', f'/api/community/posts/{pid}', me)
    assert hidden.status_code == 404 and hidden.json()['error']['code'] == 'POST_NOT_FOUND'
    assert call('GET', '/api/community/posts', me).json()['posts'] == []


def test_delete_only_own(env):
    _, (me, a, *_), call = env
    pid = write(call, me).json()['post_id']
    cid = call('POST', f'/api/community/posts/{pid}/comments', a, {'body': '댓글'}).json()['comments'][0]['comment_id']
    assert call('DELETE', f'/api/community/comments/{cid}', me).json()['error']['code'] == 'NOT_OWNER'
    assert call('DELETE', f'/api/community/comments/{cid}', a).json()['comments'] == []
    assert call('DELETE', f'/api/community/posts/{pid}', a).status_code == 403
    assert call('DELETE', f'/api/community/posts/{pid}', me).json() == {'deleted': True}
    assert call('GET', f'/api/community/posts/{pid}', me).status_code == 404


@pytest.mark.parametrize('text,needle', [
    ('진짜 씨.발 너무하네', '욕설'), ('병신 같은 소리', '욕설'), ('연락 주세요 010-1234-5678', '연락처'), ('여기 보세요 https://example.com', '링크'),
    ('ㅅ ㅂ 시끄럽다', '욕설')])
def test_content_filter(env, text, needle):
    db, (me, *_), call = env
    response = write(call, me, body=text)
    assert response.status_code == 422 and response.json()['error']['code'] == 'CONTENT_REJECTED'
    assert needle in response.json()['error']['message']
    with connect_database(db) as conn:
        assert conn.execute('SELECT COUNT(*) FROM community_posts').fetchone()[0] == 0


@pytest.mark.parametrize('text', ['새 학기 시발점은 기숙사 대청소부터', '책 두 개 새로 샀어요', '감염병 신고는 어디에 하나요',
                                  '아니 미안, 내가 늦었어', '장애 비율 통계'])
def test_ordinary_sentences_pass(env, text):
    _, (me, *_), call = env
    assert write(call, me, body=text).status_code == 201


def test_validation_auth_and_rate_limit(env, monkeypatch):
    _, (me, *_), call = env
    assert write(call, None).status_code == 401
    assert call('GET', '/api/community/posts', 'usr_unknown').status_code == 401
    for fields in ({'board': 'market'}, {'title': 'a'}, {'body': ' '}, {'title': '가' * 41}, {'nickname': '하늘'},
                   {'board': 'grievance', 'category': '연애'}):
        response = write(call, me, **fields)
        assert response.status_code == 422 and response.json()['error']['code'] in ('VALIDATION_ERROR',)
    monkeypatch.setattr(community_api, 'POST_LIMIT', (10, 30))
    assert write(call, me).status_code == 201
    limited = write(call, me)
    assert limited.status_code == 429 and limited.json()['error']['code'] == 'TOO_MANY_POSTS'
    assert call('GET', '/api/community/posts/pst_none', me).status_code == 404


PNG = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=='


def test_grievance_photo_upload_and_serve(env):
    _, (me, a, b, c, _), call = env
    pid = write(call, me, board='grievance', category='시설').json()['post_id']
    uploaded = call('POST', f'/api/community/posts/{pid}/images', me, {'data': PNG})
    assert uploaded.status_code == 201
    detail = uploaded.json()
    assert detail['image_count'] == 1 and len(detail['images']) == 1
    url = detail['images'][0]
    served = call('GET', url, None)  # <img>는 헤더 없이 요청
    assert served.status_code == 200 and served.headers['content-type'] == 'image/png'
    assert served.content.startswith(b'\x89PNG')
    assert call('GET', '/api/community/posts', a, params={'board': 'grievance'}).json()['posts'][0]['image_count'] == 1
    # 타인 업로드 · 4장째 · 형식 위장 · 자유게시판 거절
    assert call('POST', f'/api/community/posts/{pid}/images', a, {'data': PNG}).status_code == 403
    for _ in range(2):
        assert call('POST', f'/api/community/posts/{pid}/images', me, {'data': PNG}).status_code == 201
    fourth = call('POST', f'/api/community/posts/{pid}/images', me, {'data': PNG})
    assert fourth.status_code == 422 and fourth.json()['error']['code'] == 'IMAGE_REJECTED'
    fake = 'data:image/png;base64,' + __import__('base64').b64encode(b'<svg onload=alert(1)></svg>' * 2).decode()
    assert call('POST', f'/api/community/posts/{pid}/images', me, {'data': fake}).json()['error']['code'] in ('IMAGE_REJECTED',)
    free = write(call, b).json()['post_id']
    assert call('POST', f'/api/community/posts/{free}/images', b, {'data': PNG}).json()['error']['code'] == 'IMAGE_REJECTED'
    # 신고로 숨겨진 글의 사진은 더 이상 제공하지 않음
    for user in (a, b, c):
        call('POST', f'/api/community/posts/{pid}/report', user)
    assert call('GET', url, None).status_code == 404


def test_photo_size_and_encoding_limits(env, monkeypatch):
    _, (me, *_), call = env
    pid = write(call, me, board='grievance').json()['post_id']
    assert call('POST', f'/api/community/posts/{pid}/images', me, {'data': 'data:image/png;base64,@@@@not-base64@@@@'}).status_code == 422
    monkeypatch.setattr(community_api, 'MAX_IMAGE_BYTES', 10)
    too_big = call('POST', f'/api/community/posts/{pid}/images', me, {'data': PNG})
    assert too_big.status_code == 422 and '너무 커요' in too_big.json()['error']['message']
