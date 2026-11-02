# 기능: 정식 서비스 기능(이용권 구매 · 기숙사 커뮤니티)의 추가 스키마를 정의한다.
# 시스템 범위: 공통 DB 초기화에서 사용하는 내부 DDL이다. 신규 테이블은 기존 DB에 자동 생성되며, 기존 테이블 DDL은 변경하지 않는다.
# 결과: 상품 · 게시판 · 상태 값은 API 계층(Pydantic)에서 검증하여, 구성이 바뀌어도 테이블 구조 충돌이 발생하지 않게 한다.
SCHEMAS = {
    # 가상 동거 이용권 구매 내역 (API.md 4.18). 결제 수단 · 카드 · 연락처는 저장하지 않는다.
    'pass_purchases': '''CREATE TABLE pass_purchases (
        purchase_id TEXT NOT NULL PRIMARY KEY,
        user_id TEXT NOT NULL REFERENCES users(user_id),
        product TEXT NOT NULL,
        credits INTEGER NOT NULL CHECK (credits > 0),
        price INTEGER NOT NULL CHECK (price >= 0),
        created_at TEXT NOT NULL
    )''',
    # 기숙사 커뮤니티 (API.md 4.19). 작성자는 user_id로만 연결하고 화면에는 익명(글쓴이 · 익명N)으로 표시한다.
    # status: visible(공개) · hidden(신고 누적 숨김) · deleted(작성자 삭제)
    'community_posts': '''CREATE TABLE community_posts (
        post_id TEXT NOT NULL PRIMARY KEY,
        user_id TEXT NOT NULL REFERENCES users(user_id),
        board TEXT NOT NULL,
        category TEXT,
        title TEXT NOT NULL,
        body TEXT NOT NULL,
        status TEXT NOT NULL,
        created_at TEXT NOT NULL
    )''',
    # anon_no: 0 = 글쓴이, 1 이상 = 글마다 처음 댓글을 단 순서대로 부여한 익명 번호
    'community_comments': '''CREATE TABLE community_comments (
        comment_id TEXT NOT NULL PRIMARY KEY,
        post_id TEXT NOT NULL REFERENCES community_posts(post_id),
        user_id TEXT NOT NULL REFERENCES users(user_id),
        anon_no INTEGER NOT NULL CHECK (anon_no >= 0),
        body TEXT NOT NULL,
        status TEXT NOT NULL,
        created_at TEXT NOT NULL
    )''',
    # 공감 · 신고: 사용자당 대상별 1회 (target_type: post · comment, kind: like · report)
    'community_reactions': '''CREATE TABLE community_reactions (
        target_type TEXT NOT NULL,
        target_id TEXT NOT NULL,
        user_id TEXT NOT NULL REFERENCES users(user_id),
        kind TEXT NOT NULL,
        created_at TEXT NOT NULL,
        PRIMARY KEY (target_type, target_id, user_id, kind)
    )''',
    # 애로사항 첨부 사진(글당 최대 3장). 서버에서 파일 시그니처로 형식(JPEG · PNG · WebP)을 확인한 원본 바이트만 저장
    'community_images': '''CREATE TABLE community_images (
        image_id TEXT NOT NULL PRIMARY KEY,
        post_id TEXT NOT NULL REFERENCES community_posts(post_id),
        user_id TEXT NOT NULL REFERENCES users(user_id),
        mime TEXT NOT NULL,
        data BLOB NOT NULL,
        created_at TEXT NOT NULL
    )''',
}
