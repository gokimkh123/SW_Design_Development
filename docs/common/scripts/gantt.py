"""룸메궁합 일정 간트 차트 PNG 생성.

일정 변경 시 아래 GROUPS · MILESTONES 수정 후 재실행 (matplotlib, 맑은 고딕 필요).
usage: python docs/common/scripts/gantt.py docs/common/images/gantt.png
"""
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Rectangle

plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False

SURFACE, INK, INK2, MUTED = "#fcfcfb", "#0b0b0b", "#52514e", "#898781"
GRID, BASE, BAND = "#e1e0d9", "#c3c2b7", "#f2f1ec"

DAYS = ["10/19", "10/20", "10/21", "10/22", "10/23", "10/24", "10/25", "10/26",
        "10/27", "10/28", "10/29", "10/30", "10/31", "11/1", "11/2", "11/3"]
WEEK = ["월", "화", "수", "목", "금", "토", "일"]

# (그룹, 색, [(작업, 시작 인덱스, 끝 인덱스(포함), 선택 여부)])
GROUPS = [
    ("건한 · PM", "#2a78d6", [
        ("킥오프 · 문서 · 팀원 초대", 0, 1, False),
        ("설문 12문항 · 장면 20개 확정", 2, 7, False),
        ("포스터 제작 · 제출", 3, 7, False),
        ("통합 점검 · 기능 동결", 11, 13, False),
        ("리허설 · 부스 준비", 14, 14, False),
    ]),
    ("건한 · AI 엔진", "#eb6834", [
        ("LLM 클라이언트 · 페르소나 생성", 8, 8, False),
        ("장면 1개 대화 + 판정 PoC", 9, 9, False),
        ("20장면 루프 · 점수 · 규칙 초안", 10, 11, False),
        ("리플레이 데이터 · 프롬프트 튜닝", 12, 12, False),
        ("골든 페어 회귀 확인", 13, 13, False),
    ]),
    ("동현 · 프론트엔드", "#1baf7a", [
        ("세팅 · 공통 레이아웃 · A1", 8, 8, False),
        ("흐름 A 화면", 9, 9, False),
        ("흐름 B 화면 · SSE", 10, 11, False),
        ("흐름 C 화면", 12, 12, False),
        ("실연동 마무리", 13, 13, False),
    ]),
    ("일준 · 백엔드", "#eda100", [
        ("서버 세팅 · health · users", 8, 8, False),
        ("설문 · 페르소나 API", 9, 9, False),
        ("시뮬레이션 API · SSE", 10, 10, False),
        ("후보 추림 API", 11, 11, False),
        ("부스 실행 환경", 12, 12, False),
        ("통합 버그 수정", 13, 13, False),
    ]),
    ("범찬 · 백엔드", "#e87ba4", [
        ("DB 스키마 · 시드 로더", 8, 8, False),
        ("엔진 어댑터 · 시드 인물 11명", 9, 9, False),
        ("시뮬레이션 실행기 · 리포트 API", 10, 10, False),
        ("매칭 · 규칙 API, 실제 엔진 연결", 11, 11, False),
        ("흐름 C 화면 지원 · 리플레이 검토", 12, 12, False),
        ("통합 버그 수정", 13, 13, False),
    ]),
    ("전원", "#008300", [
        ("API 명세 · 기술 스택 리뷰", 0, 7, False),
        ("P1 기능 (여유 시)", 12, 13, True),
        ("리허설 3회 · 코드 프리즈", 14, 14, False),
        ("발표회 부스 시연", 15, 15, False),
    ]),
]
# (x 위치, 이름, 위/아래, 강조)
MILESTONES = [
    (8.0, "포스터 제출", "up", True),
    (10.0, "M1 한 줄 연결", "down", False),
    (12.0, "M2 핵심 기능", "up", False),
    (14.0, "M3 기능 동결", "down", True),
    (15.0, "M4 리허설", "up", False),
    (15.5, "발표회", "down", True),
]
PHASES = [(0, 8, "준비 · 중간고사 기간 (10/20 ~ 10/26)"), (8, 14, "개발 6일"), (14, 16, "리허설·발표회")]

# ---- 레이아웃 (인치) ----
FIG_W, LEFT_IN, RIGHT_IN = 9.6, 2.75, 0.25
DAY_IN = (FIG_W - LEFT_IN - RIGHT_IN) / 16
ROW_IN, HEAD_ROWS, TOP_ROWS = 0.235, 1.25, 6.4
n_tasks = sum(len(g[2]) for g in GROUPS)
total_rows = n_tasks + HEAD_ROWS * len(GROUPS)
TITLE_IN = 0.95
FIG_H = TITLE_IN + (TOP_ROWS + total_rows) * ROW_IN + 0.2

fig = plt.figure(figsize=(FIG_W, FIG_H), dpi=200, facecolor=SURFACE)
ax = fig.add_axes([LEFT_IN / FIG_W, 0.2 / FIG_H, 16 * DAY_IN / FIG_W, (TOP_ROWS + total_rows) * ROW_IN / FIG_H])
ax.set_xlim(0, 16)
ax.set_ylim(total_rows, -TOP_ROWS)
ax.axis("off")
ax.set_facecolor(SURFACE)

L = (LEFT_IN - 0.2) / DAY_IN  # 왼쪽 라벨 영역 폭 (일 단위)
ASPECT = DAY_IN / ROW_IN  # 같은 반지름의 둥근 모서리를 위한 y/x 비율

# 제목
fig.text(0.2 / FIG_W, 1 - 0.32 / FIG_H, "룸메궁합 개발 일정", fontsize=15, fontweight="bold", color=INK, va="center")
fig.text(0.2 / FIG_W, 1 - 0.66 / FIG_H, "2026.10.19 ~ 11.3  ·  개발 6일(10/27 ~ 11/1)  ·  11/1 기능 동결  ·  11/3 발표회",
         fontsize=9.5, color=INK2, va="center")

# 단계 띠
for x0, x1, name in PHASES:
    ax.add_patch(FancyBboxPatch((x0 + 0.05, -6.15), x1 - x0 - 0.1, 0.95, boxstyle="round,pad=0,rounding_size=0.08",
                                mutation_aspect=ASPECT, facecolor=BAND, edgecolor="none", clip_on=False))
    ax.text((x0 + x1) / 2, -5.67, name, ha="center", va="center", fontsize=8.8 if x1 - x0 > 2 else 7.8, color=INK2, fontweight="bold")

# 날짜 축
for i, d in enumerate(DAYS):
    wd = WEEK[i % 7]
    weekend = wd in ("토", "일")
    ax.text(i + 0.5, -4.55, d, ha="center", va="center", fontsize=7.6, color=INK2)
    ax.text(i + 0.5, -3.85, wd, ha="center", va="center", fontsize=7.6, color=INK if weekend else MUTED,
            fontweight="bold" if weekend else "normal")
ax.plot([0, 16], [-3.35, -3.35], color=BASE, lw=0.8, solid_capstyle="butt")

# 중간고사 기간 배경
ax.add_patch(Rectangle((1, -3.35), 7, total_rows + 3.35, facecolor=BAND, edgecolor="none", zorder=0))
# 하루 단위 세로 격자
for i in range(17):
    ax.plot([i, i], [-3.35, total_rows], color=GRID, lw=0.5, zorder=0.5)
# 마감선 (포스터 제출, 기능 동결)
for x in (8, 14):
    ax.plot([x, x], [-1.75, total_rows], color=MUTED, lw=1.0, zorder=1)

# 마일스톤
for x, name, pos, strong in MILESTONES:
    ax.scatter([x], [-1.75], marker="D", s=34 if strong else 22, color=INK if strong else INK2,
               edgecolors=SURFACE, linewidths=1.2, zorder=5, clip_on=False)
    ax.text(x, -2.6 if pos == "up" else -0.95, name, ha="center", va="center", fontsize=7.8,
            color=INK if strong else INK2, fontweight="bold" if strong else "normal", zorder=6,
            bbox=dict(boxstyle="round,pad=0.18", facecolor=SURFACE, edgecolor="none"))

# 그룹 · 작업
y = 0.0
GAP, BAR_H = 0.07, 0.58
for gname, color, tasks in GROUPS:
    ax.plot([-L, 16], [y + 0.12, y + 0.12], color=GRID, lw=0.8, clip_on=False)
    ax.scatter([-L + 0.18], [y + HEAD_ROWS / 2 + 0.08], marker="s", s=30, color=color, clip_on=False, zorder=5)
    ax.text(-L + 0.5, y + HEAD_ROWS / 2 + 0.08, gname, ha="left", va="center", fontsize=10, fontweight="bold",
            color=INK, clip_on=False)
    y += HEAD_ROWS
    for name, s, e, optional in tasks:
        ax.text(-L + 0.5, y + 0.5, name, ha="left", va="center", fontsize=8.6, color=INK2, clip_on=False)
        ax.add_patch(FancyBboxPatch((s + GAP, y + (1 - BAR_H) / 2), e - s + 1 - 2 * GAP, BAR_H,
                                    boxstyle="round,pad=0,rounding_size=0.09", mutation_aspect=ASPECT,
                                    facecolor=color, edgecolor="none", alpha=0.45 if optional else 1.0, zorder=3))
        y += 1.0

fig.savefig(sys.argv[1], dpi=200, facecolor=SURFACE)
print("saved", sys.argv[1], fig.get_size_inches() * 200)
