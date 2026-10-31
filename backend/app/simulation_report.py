# 기능: 저장된 완료 결과와 장면 판정으로 공개 리포트를 구성한다.
# 시스템 범위: 소유 실행을 읽기 트랜잭션으로 조회하며 엔진 호출·저장·점수 재계산은 하지 않는다.
# 결과: 명세의 Report를 반환하고 미완료·누락·손상된 결과는 오류로 처리한다.
import json
import sqlite3
from typing import Literal

from pydantic import Field

from app.database import connect_database
from app import simulations as store


class Candidate(store.EventData):
    candidate_id: str
    alias: Literal['후보 A', '후보 B', '후보 C']
    type_name: str


class Counts(store.EventData):
    harmonious: int = Field(ge=0)
    negotiated: int = Field(ge=0)
    conflict: int = Field(ge=0)
    pending: int = Field(ge=0)


class Highlight(store.EventData):
    scene_index: int = Field(ge=1, le=20)
    day: int = Field(ge=1, le=7)
    title: str
    verdict: Literal['conflict', 'negotiated']
    agreement: str | None


class Report(store.EventData):
    simulation_id: str
    candidate: Candidate
    score: int = Field(ge=0, le=100)
    headline: str
    verdict_counts: Counts
    scene_verdicts: list[Literal['harmonious', 'negotiated', 'conflict', 'pending']] = Field(min_length=20, max_length=20)
    highlights: list[Highlight]
    expected_conflicts_per_month: None


def get_report(database, simulation_id, *, user_id):
    # 상태·결과·장면을 같은 스냅샷으로 읽고 공개 필드만 명시적으로 구성한다.
    with connect_database(database) as db:
        db.row_factory = sqlite3.Row
        db.execute('BEGIN')
        row = db.execute('SELECT * FROM simulations WHERE simulation_id=? AND user_id=?',
                         (simulation_id, user_id)).fetchone()
        if row is None:
            return None
        if row['status'] != 'completed':
            raise store.StorageConflictError('완료되지 않은 실행입니다.')
        result = json.loads(row['result'])
        inputs = json.loads(row['inputs'])
        candidate = inputs['candidate']
        scenes = db.execute('SELECT * FROM simulation_scenes WHERE simulation_id=? ORDER BY scene_index',
                            (simulation_id,)).fetchall()
        if row['total'] != 20 or row['done'] != 20 or len(scenes) != 20 or len(inputs['scenes']) != 20:
            raise ValueError('완료 장면이 누락되었습니다.')
        counts = dict.fromkeys(store.VERDICTS, 0)
        verdicts, highlights = [], []
        for index, saved in enumerate(scenes, 1):
            scene = store.Scene.model_validate(json.loads(saved['scene']))
            judgement = store.Judged.model_validate(dict(json.loads(saved['judgement']),
                progress={'done': index, 'total': 20}))
            if (saved['scene_index'] != index or judgement.scene_index != index
                    or judgement.scene_id != scene.scene_id
                    or scene.scene_id != inputs['scenes'][index - 1]['scene_id']):
                raise ValueError('장면 순서 또는 ID가 일치하지 않습니다.')
            counts[judgement.verdict] += 1
            verdicts.append(judgement.verdict)
            if judgement.verdict in ('conflict', 'negotiated'):
                highlights.append(dict(scene_index=index, day=scene.day, title=scene.title,
                    verdict=judgement.verdict, agreement=judgement.agreement))
        if Counts.model_validate(result['verdict_counts']).model_dump() != counts:
            raise ValueError('완료 집계와 장면 판정이 다릅니다.')
        highlights.sort(key=lambda h: (h['verdict'] != 'conflict', h['scene_index']))
        # 선택적 result.report는 검증되지 않은 내부 자료이므로 공개 응답에 펼치지 않는다.
        public = dict(simulation_id=simulation_id,
            candidate=dict(candidate_id=row['candidate_id'], alias=row['alias'], type_name=candidate['type_name']),
            score=result['score'], headline=result['headline'], verdict_counts=counts,
            scene_verdicts=verdicts, highlights=highlights, expected_conflicts_per_month=None)
        # 식별자는 보존하고 스냅샷의 알려진 실명은 공개 자유 문구에서 다시 제거한다.
        public['candidate']['type_name'] = store._anonymize(public['candidate']['type_name'], candidate, row['alias'])
        for key in ('headline', 'highlights'):
            public[key] = store._anonymize(public[key], candidate, row['alias'])
        return Report.model_validate(public)
