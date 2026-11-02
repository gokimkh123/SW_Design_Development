# 기능: 정식 서비스 기능(이용권 구매)의 추가 스키마를 정의한다.
# 시스템 범위: 공통 DB 초기화에서 사용하는 내부 DDL이다. 신규 테이블은 기존 DB에 자동 생성되며, 기존 테이블 DDL은 변경하지 않는다.
# 결과: 상품 종류는 API 계층(Pydantic)에서 검증하여, 상품 구성이 바뀌어도 테이블 구조 충돌이 발생하지 않게 한다.
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
}
