import sys
from pathlib import Path

# backend/ 를 import 경로에 추가 (app 패키지)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# API.md 4.4 요청 예시 (하늘)
HANEUL_ANSWERS = {
    "q01": {"bedtime": "23:00", "wake": "06:30"},
    "q02": "sensitive",
    "q03": "earlier",
    "q04": "every_2_3_days",
    "q05": "right_away",
    "q06": "moderate",
    "q07": "when_needed",
    "q08": "all_separate",
    "q09": "say_now",
    "q10": "ask_now",
    "q11": "say_now",
    "q12": "after_friend_leaves",
}
